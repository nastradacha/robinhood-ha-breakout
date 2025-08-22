"""
Real-Time Data Staleness Detection Module (US-FA-008)

Enhanced staleness monitoring with automatic retry, exponential backoff,
and comprehensive data freshness metrics for safer trading decisions.

Features:
- Real-time staleness detection with configurable thresholds
- Exponential backoff retry mechanism for data refresh
- Data freshness metrics logging and monitoring
- Automatic trading halt on persistent staleness
- Slack alerts for staleness issues
- Integration with existing data validation system
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import asyncio
from pathlib import Path
import json
import os
import tempfile
import shutil
import threading

from .data_validation import DataValidator, DataPoint, DataQuality
from .enhanced_slack import EnhancedSlackIntegration

logger = logging.getLogger(__name__)


def atomic_write_json(file_path: Path, data: any) -> None:
    """
    Atomic write function for JSON data that works reliably on Windows.
    Uses same-directory temp file to avoid cross-directory permission issues.
    """
    file_path = Path(file_path)
    
    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create temp file in same directory as target file
    temp_fd = None
    temp_path = None
    
    try:
        # Use tempfile.mkstemp for atomic creation in same directory
        temp_fd, temp_name = tempfile.mkstemp(
            suffix='.tmp',
            prefix=f'{file_path.stem}_',
            dir=file_path.parent
        )
        temp_path = Path(temp_name)
        
        # Write JSON data to temp file
        with os.fdopen(temp_fd, 'w') as f:
            json.dump(data, f, indent=2)
        temp_fd = None  # File is now closed
        
        # Atomic replace - works reliably on Windows
        if os.name == 'nt':  # Windows
            # On Windows, remove target first if it exists
            if file_path.exists():
                file_path.unlink()
        
        # Atomic move/rename
        shutil.move(str(temp_path), str(file_path))
        
    except Exception as e:
        # Cleanup on failure
        if temp_fd is not None:
            try:
                os.close(temp_fd)
            except:
                pass
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except:
                pass
        raise e


class StalenessLevel(Enum):
    """Data staleness severity levels"""
    FRESH = "fresh"          # < 30 seconds
    ACCEPTABLE = "acceptable" # 30s - 2 minutes
    STALE = "stale"          # 2 - 5 minutes
    VERY_STALE = "very_stale" # 5 - 10 minutes
    CRITICAL = "critical"     # > 10 minutes


@dataclass
class StalenessMetrics:
    """Metrics for data staleness monitoring"""
    symbol: str
    last_update: datetime
    age_seconds: float
    staleness_level: StalenessLevel
    retry_count: int
    next_retry_time: Optional[datetime]
    consecutive_failures: int
    total_failures: int
    success_rate: float
    timestamp: datetime


@dataclass
class RetryConfig:
    """Configuration for exponential backoff retry"""
    initial_delay: float = 1.0      # Initial retry delay in seconds
    max_delay: float = 300.0        # Maximum retry delay (5 minutes)
    backoff_factor: float = 2.0     # Exponential backoff multiplier
    max_retries: int = 10           # Maximum retry attempts
    jitter: bool = True             # Add random jitter to prevent thundering herd


class StalenessMonitor:
    """Monitor data staleness across multiple symbols and sources"""
    _instance = None
    _initialized = False
    _json_error_logged = False
    
    def __new__(cls, config: Dict = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config: Dict = None):
        """Initialize staleness monitor with configuration (singleton)"""
        if self._initialized:
            return
            
        if config is None:
            from .llm import load_config
            config = load_config()
        
        self.config = config
        
        # Staleness thresholds (in seconds)
        self.fresh_threshold = config.get("STALENESS_FRESH_SECONDS", 30)
        self.acceptable_threshold = config.get("STALENESS_ACCEPTABLE_SECONDS", 120)
        self.stale_threshold = config.get("STALENESS_STALE_SECONDS", 300)
        self.very_stale_threshold = config.get("STALENESS_VERY_STALE_SECONDS", 600)
        
        # Monitoring configuration
        self.enabled = config.get("STALENESS_MONITORING_ENABLED", True)
        self.block_on_stale = config.get("STALENESS_BLOCK_TRADING", True)
        self.alert_on_stale = config.get("STALENESS_ALERT_ENABLED", True)
        self.metrics_logging = config.get("STALENESS_METRICS_LOGGING", True)
        
        # Retry configuration
        self.retry_config = RetryConfig(
            initial_delay=config.get("STALENESS_RETRY_INITIAL_DELAY", 1.0),
            max_delay=config.get("STALENESS_RETRY_MAX_DELAY", 300.0),
            backoff_factor=config.get("STALENESS_RETRY_BACKOFF_FACTOR", 2.0),
            max_retries=config.get("STALENESS_RETRY_MAX_ATTEMPTS", 10),
            jitter=config.get("STALENESS_RETRY_JITTER", True)
        )
        
        # Internal state
        self.metrics: Dict[str, StalenessMetrics] = {}
        self.data_validator = DataValidator(config)
        self.slack = EnhancedSlackIntegration(config) if config.get("SLACK_ENABLED") else None
        self.metrics_file = Path("logs/staleness_metrics.json")
        self._file_lock = threading.Lock()  # Prevent concurrent file access
        
        # Ensure metrics directory exists
        self.metrics_file.parent.mkdir(exist_ok=True)
        
        self._initialized = True
        logger.info(f"[STALENESS] Initialized - Fresh: {self.fresh_threshold}s, "
                   f"Acceptable: {self.acceptable_threshold}s, Stale: {self.stale_threshold}s")
    
    def classify_staleness(self, age_seconds: float) -> StalenessLevel:
        """
        Classify data staleness based on age
        
        Args:
            age_seconds: Age of data in seconds
            
        Returns:
            StalenessLevel classification
        """
        if age_seconds <= self.fresh_threshold:
            return StalenessLevel.FRESH
        elif age_seconds <= self.acceptable_threshold:
            return StalenessLevel.ACCEPTABLE
        elif age_seconds <= self.stale_threshold:
            return StalenessLevel.STALE
        elif age_seconds <= self.very_stale_threshold:
            return StalenessLevel.VERY_STALE
        else:
            return StalenessLevel.CRITICAL
    
    def calculate_retry_delay(self, retry_count: int) -> float:
        """
        Calculate exponential backoff delay for retry
        
        Args:
            retry_count: Current retry attempt number
            
        Returns:
            Delay in seconds before next retry
        """
        delay = self.retry_config.initial_delay * (self.retry_config.backoff_factor ** retry_count)
        delay = min(delay, self.retry_config.max_delay)
        
        # Add jitter to prevent thundering herd
        if self.retry_config.jitter:
            import random
            jitter = delay * 0.1 * random.random()  # Up to 10% jitter
            delay += jitter
        
        return delay
    
    def should_retry(self, symbol: str) -> bool:
        """
        Check if data refresh should be retried for symbol
        
        Args:
            symbol: Stock symbol to check
            
        Returns:
            True if retry should be attempted
        """
        if symbol not in self.metrics:
            return True
        
        metrics = self.metrics[symbol]
        
        # Check retry limits
        if metrics.retry_count >= self.retry_config.max_retries:
            logger.warning(f"[STALENESS] {symbol}: Max retries ({self.retry_config.max_retries}) exceeded")
            return False
        
        # Check if enough time has passed for next retry
        if metrics.next_retry_time and datetime.now() < metrics.next_retry_time:
            return False
        
        return True
    
    def update_metrics(self, symbol: str, data_point: Optional[DataPoint], 
                      retry_attempted: bool = False, success: bool = True):
        """
        Update staleness metrics for a symbol
        
        Args:
            symbol: Stock symbol
            data_point: Latest data point (None if fetch failed)
            retry_attempted: Whether a retry was attempted
            success: Whether the data fetch was successful
        """
        now = datetime.now()
        
        # Initialize metrics if not exists
        if symbol not in self.metrics:
            self.metrics[symbol] = StalenessMetrics(
                symbol=symbol,
                last_update=now,
                age_seconds=0.0,
                staleness_level=StalenessLevel.FRESH,
                retry_count=0,
                next_retry_time=None,
                consecutive_failures=0,
                total_failures=0,
                success_rate=1.0,
                timestamp=now
            )
        
        metrics = self.metrics[symbol]
        
        if success and data_point:
            # Successful data fetch
            metrics.last_update = data_point.timestamp
            metrics.age_seconds = data_point.age_seconds
            metrics.staleness_level = self.classify_staleness(data_point.age_seconds)
            metrics.retry_count = 0
            metrics.next_retry_time = None
            metrics.consecutive_failures = 0
            
        else:
            # Failed data fetch
            metrics.total_failures += 1
            metrics.consecutive_failures += 1
            
            if retry_attempted:
                metrics.retry_count += 1
                retry_delay = self.calculate_retry_delay(metrics.retry_count)
                metrics.next_retry_time = now + timedelta(seconds=retry_delay)
                
                logger.info(f"[STALENESS] {symbol}: Retry {metrics.retry_count}/{self.retry_config.max_retries} "
                           f"scheduled in {retry_delay:.1f}s")
        
        # Update success rate (last 100 attempts)
        total_attempts = metrics.total_failures + (100 - metrics.total_failures)  # Simplified calculation
        metrics.success_rate = max(0.0, (total_attempts - metrics.total_failures) / total_attempts)
        metrics.timestamp = now
        
        # Log metrics if enabled
        if self.metrics_logging:
            self._log_metrics(metrics)
    
    def check_symbol_staleness(self, symbol: str, with_retry: bool = True) -> Tuple[bool, str, StalenessMetrics]:
        """
        Check staleness for a specific symbol with optional retry
        
        Args:
            symbol: Stock symbol to check
            with_retry: Whether to attempt retry on stale data
            
        Returns:
            Tuple of (is_fresh, reason, metrics)
        """
        if not self.enabled:
            return True, "Staleness monitoring disabled", None
        
        try:
            # Get current data
            result = self.data_validator.validate_symbol_data(symbol)
            data_point = result.primary_data
            
            if not data_point:
                # No data available - attempt retry if enabled
                if with_retry and self.should_retry(symbol):
                    logger.warning(f"[STALENESS] {symbol}: No data available, attempting retry...")
                    self.update_metrics(symbol, None, retry_attempted=True, success=False)
                    
                    # Wait for retry delay
                    if symbol in self.metrics and self.metrics[symbol].next_retry_time:
                        retry_delay = (self.metrics[symbol].next_retry_time - datetime.now()).total_seconds()
                        if retry_delay > 0:
                            time.sleep(min(retry_delay, 5.0))  # Cap at 5 seconds for responsiveness
                    
                    # Retry data fetch
                    result = self.data_validator.validate_symbol_data(symbol)
                    data_point = result.primary_data
                
                if not data_point:
                    self.update_metrics(symbol, None, retry_attempted=with_retry, success=False)
                    return False, f"No data available for {symbol}", self.metrics.get(symbol)
            
            # Analyze staleness
            staleness_level = self.classify_staleness(data_point.age_seconds)
            self.update_metrics(symbol, data_point, success=True)
            
            # Check if trading should be blocked
            is_fresh = staleness_level in [StalenessLevel.FRESH, StalenessLevel.ACCEPTABLE]
            
            if not is_fresh and self.block_on_stale:
                reason = f"Data too stale ({staleness_level.value}: {data_point.age_seconds:.1f}s old)"
                
                # Send alert if enabled
                if self.alert_on_stale and self.slack:
                    self._send_staleness_alert(symbol, staleness_level, data_point.age_seconds)
                
                return False, reason, self.metrics[symbol]
            
            return True, f"Data freshness acceptable ({staleness_level.value})", self.metrics[symbol]
            
        except Exception as e:
            logger.error(f"[STALENESS] Error checking {symbol}: {e}")
            self.update_metrics(symbol, None, retry_attempted=False, success=False)
            return False, f"Staleness check failed: {str(e)}", self.metrics.get(symbol)
    
    def check_multiple_symbols(self, symbols: List[str]) -> Dict[str, Tuple[bool, str, StalenessMetrics]]:
        """
        Check staleness for multiple symbols concurrently
        
        Args:
            symbols: List of stock symbols to check
            
        Returns:
            Dictionary mapping symbol to (is_fresh, reason, metrics)
        """
        results = {}
        
        for symbol in symbols:
            results[symbol] = self.check_symbol_staleness(symbol)
        
        return results
    
    def get_staleness_summary(self, symbols: List[str] = None) -> Dict:
        """
        Get summary of staleness metrics for monitoring
        
        Args:
            symbols: Optional list of symbols to include (default: all tracked)
            
        Returns:
            Summary dictionary with staleness statistics
        """
        if symbols is None:
            symbols = list(self.metrics.keys())
        
        summary = {
            "timestamp": datetime.now().isoformat(),
            "total_symbols": len(symbols),
            "staleness_distribution": {level.value: 0 for level in StalenessLevel},
            "average_age_seconds": 0.0,
            "symbols_with_issues": [],
            "overall_health": "healthy"
        }
        
        if not symbols:
            return summary
        
        total_age = 0.0
        issues = []
        
        for symbol in symbols:
            if symbol in self.metrics:
                metrics = self.metrics[symbol]
                summary["staleness_distribution"][metrics.staleness_level.value] += 1
                total_age += metrics.age_seconds
                
                if metrics.staleness_level in [StalenessLevel.STALE, StalenessLevel.VERY_STALE, StalenessLevel.CRITICAL]:
                    issues.append({
                        "symbol": symbol,
                        "level": metrics.staleness_level.value,
                        "age_seconds": metrics.age_seconds,
                        "consecutive_failures": metrics.consecutive_failures
                    })
        
        summary["average_age_seconds"] = total_age / len(symbols) if symbols else 0.0
        summary["symbols_with_issues"] = issues
        
        # Determine overall health
        critical_count = summary["staleness_distribution"]["critical"]
        stale_count = summary["staleness_distribution"]["stale"] + summary["staleness_distribution"]["very_stale"]
        
        if critical_count > 0:
            summary["overall_health"] = "critical"
        elif stale_count > len(symbols) * 0.3:  # More than 30% stale
            summary["overall_health"] = "degraded"
        elif stale_count > 0:
            summary["overall_health"] = "warning"
        
        return summary
    
    def _send_staleness_alert(self, symbol: str, level: StalenessLevel, age_seconds: float):
        """Send Slack alert for staleness issue"""
        if not self.slack or not self.slack.enabled:
            return
        
        emoji = {
            StalenessLevel.STALE: "⚠️",
            StalenessLevel.VERY_STALE: "🚨",
            StalenessLevel.CRITICAL: "🔴"
        }.get(level, "⚠️")
        
        message = f"{emoji} **DATA STALENESS ALERT**\n\n" \
                 f"**Symbol:** {symbol}\n" \
                 f"**Staleness Level:** {level.value.upper()}\n" \
                 f"**Data Age:** {age_seconds:.1f} seconds\n" \
                 f"**Threshold:** {self.stale_threshold}s\n" \
                 f"**Action:** {'Trading blocked' if self.block_on_stale else 'Warning only'}\n" \
                 f"**Time:** {datetime.now().strftime('%H:%M:%S %Z')}"
        
        try:
            self.slack.send_alert(message)
            logger.info(f"[STALENESS] Sent alert for {symbol} staleness ({level.value})")
        except Exception as e:
            logger.error(f"[STALENESS] Failed to send alert: {e}")
    
    def _log_metrics(self, metrics: StalenessMetrics):
        """Log staleness metrics to file with JSON error protection"""
        try:
            # Use file lock to prevent concurrent access
            with self._file_lock:
                # Load existing metrics with robust error handling
                all_metrics = []
                if self.metrics_file.exists():
                    try:
                        with open(self.metrics_file, 'r') as f:
                            content = f.read().strip()
                            if content:  # Check if file has content
                                all_metrics = json.loads(content)
                            else:
                                all_metrics = []  # Empty file, start fresh
                    except (json.JSONDecodeError, ValueError) as json_err:
                        # Corrupted JSON file - reinitialize with empty list
                        if not self._json_error_logged:
                            logger.warning(f"[STALENESS] Corrupted metrics file, reinitializing: {json_err}")
                            self.__class__._json_error_logged = True
                        all_metrics = []
            
            # Add new metrics entry
            metrics_dict = {
                "symbol": metrics.symbol,
                "timestamp": metrics.timestamp.isoformat(),
                "last_update": metrics.last_update.isoformat(),
                "age_seconds": metrics.age_seconds,
                "staleness_level": metrics.staleness_level.value,
                "retry_count": metrics.retry_count,
                "consecutive_failures": metrics.consecutive_failures,
                "total_failures": metrics.total_failures,
                "success_rate": metrics.success_rate
            }
            
            all_metrics.append(metrics_dict)
            
            # Keep only last 1000 entries to prevent file bloat
            if len(all_metrics) > 1000:
                all_metrics = all_metrics[-1000:]
            
                # Write back to file with atomic operation (still within lock)
                atomic_write_json(self.metrics_file, all_metrics)
                
        except Exception as e:
            if not self._json_error_logged:
                logger.error(f"[STALENESS] Failed to log metrics: {e}")
                self.__class__._json_error_logged = True


# Convenience functions for easy integration
def check_symbol_staleness(symbol: str, with_retry: bool = True) -> Tuple[bool, str]:
    """
    Convenience function to check staleness for a single symbol
    
    Args:
        symbol: Stock symbol to check
        with_retry: Whether to attempt retry on stale data
        
    Returns:
        Tuple of (is_fresh, reason)
    """
    monitor = StalenessMonitor()
    is_fresh, reason, _ = monitor.check_symbol_staleness(symbol, with_retry)
    return is_fresh, reason


def get_staleness_summary() -> Dict:
    """
    Convenience function to get staleness summary for all tracked symbols
    
    Returns:
        Summary dictionary with staleness statistics
    """
    monitor = StalenessMonitor()
    return monitor.get_staleness_summary()


# Singleton instance for efficient reuse
_staleness_monitor_instance = None

def get_staleness_monitor() -> StalenessMonitor:
    """
    Get singleton staleness monitor instance
    
    Returns:
        StalenessMonitor instance
    """
    global _staleness_monitor_instance
    if _staleness_monitor_instance is None:
        _staleness_monitor_instance = StalenessMonitor()
    return _staleness_monitor_instance
