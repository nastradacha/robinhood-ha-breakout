"""
Cross-Source Data Validation Module (US-FA-007)

Validates market data quality across multiple sources to ensure trading decisions
are based on accurate, timely information. Prioritizes real-time Alpaca data
while using Yahoo Finance for validation and fallback scenarios.

Key Features:
- Cross-source price validation with configurable tolerance
- Data staleness detection and alerting
- Automatic fallback when primary source fails
- Comprehensive logging for data quality monitoring
- Slack alerts for critical data discrepancies

Data Source Priority:
1. Primary: Alpaca API (real-time, professional-grade)
2. Validation: Yahoo Finance (delayed, for cross-reference)
3. Fallback: Yahoo Finance (when Alpaca unavailable)

Author: Robinhood HA Breakout System
Version: 1.0.0 (US-FA-007)
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import pandas as pd
import yfinance as yf
from utils.alpaca_client import AlpacaClient
from utils.enhanced_slack import EnhancedSlackIntegration

logger = logging.getLogger(__name__)


class DataQuality(Enum):
    """Data quality assessment levels"""
    EXCELLENT = "excellent"  # Real-time, validated
    GOOD = "good"           # Real-time, not validated
    ACCEPTABLE = "acceptable" # Delayed but recent
    POOR = "poor"           # Stale or conflicting data
    CRITICAL = "critical"   # No reliable data available


@dataclass
class DataPoint:
    """Represents a single data point with metadata"""
    value: float
    timestamp: datetime
    source: str
    symbol: str
    data_type: str  # 'price', 'volume', etc.
    
    @property
    def age_seconds(self) -> float:
        """Age of data point in seconds"""
        now = datetime.now()
        timestamp = self.timestamp
        
        # Normalize both to naive datetime for comparison
        if timestamp.tzinfo is not None:
            timestamp = timestamp.replace(tzinfo=None)
        if now.tzinfo is not None:
            now = now.replace(tzinfo=None)
            
        return (now - timestamp).total_seconds()
    
    def is_stale(self, max_age_seconds: int = 120) -> bool:
        """Check if data is stale (default: 2 minutes)"""
        return self.age_seconds > max_age_seconds


@dataclass
class ValidationResult:
    """Result of cross-source data validation"""
    symbol: str
    primary_data: Optional[DataPoint]
    validation_data: Optional[DataPoint]
    quality: DataQuality
    discrepancy_pct: Optional[float]
    issues: List[str]
    recommendation: str
    timestamp: datetime


class DataValidator:
    """
    Cross-source data validation system for market data quality assurance
    """
    _instance = None
    _initialized = False
    
    def __new__(cls, config: Dict = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config: Dict = None):
        """Initialize data validator with configuration (singleton)"""
        if self._initialized:
            return
            
        self.config = config or {}
        
        # Configuration
        self.validation_enabled = self.config.get("DATA_VALIDATION_ENABLED", True)
        self.max_discrepancy_pct = self.config.get("DATA_MAX_DISCREPANCY_PCT", 1.0)
        self.max_staleness_seconds = self.config.get("DATA_MAX_STALENESS_SECONDS", 120)
        self.prioritize_alpaca = self.config.get("DATA_PRIORITIZE_ALPACA", True)
        self.alert_on_discrepancy = self.config.get("DATA_ALERT_ON_DISCREPANCY", True)
        self.require_validation = self.config.get("DATA_REQUIRE_VALIDATION", False)
        
        # Symbol-specific overrides for vendor mismatch tolerance
        self.split_whitelist = self.config.get("DATA_SPLIT_WHITELIST", {"GLD", "SLV", "TLT"})
        self.symbol_attention_thresholds = self.config.get("DATA_SYMBOL_ATTENTION_THRESHOLDS", {
            "GLD": 15.0,  # Higher threshold for GLD due to vendor differences
            "SLV": 12.0,
            "TLT": 10.0
        })
        
        # Strict validation mode and pause functionality
        self.strict_validation = self.config.get("DATA_STRICT_VALIDATION", False)
        self.pause_on_validate_fail = self.config.get("DATA_PAUSE_ON_VALIDATE_FAIL", None)
        self.paused_symbols = {}  # Track paused symbols with expiry times
        
        # Initialize clients
        self.alpaca_client = None
        self.slack = None
        
        try:
            self.alpaca_client = AlpacaClient()
            logger.debug("[DATA-VALIDATION] Alpaca client initialized")
        except Exception as e:
            logger.warning(f"[DATA-VALIDATION] Alpaca client unavailable: {e}")
        
        try:
            self.slack = EnhancedSlackIntegration()
            logger.debug("[DATA-VALIDATION] Slack integration initialized")
        except Exception as e:
            logger.warning(f"[DATA-VALIDATION] Slack unavailable: {e}")
            
        self._initialized = True
        logger.info(f"[DATA-VALIDATION] Initialized (enabled: {self.validation_enabled})")
    
    def get_alpaca_price(self, symbol: str) -> Optional[DataPoint]:
        """Get current price from Alpaca API"""
        if not self.alpaca_client:
            return None
        
        try:
            price = self.alpaca_client.get_current_price(symbol)
            if price and price > 0:
                return DataPoint(
                    value=price,
                    timestamp=datetime.now(),
                    source="alpaca",
                    symbol=symbol,
                    data_type="price"
                )
        except Exception as e:
            logger.warning(f"[DATA-VALIDATION] Alpaca price fetch failed for {symbol}: {e}")
        
        return None
    
    def get_yahoo_price(self, symbol: str) -> Optional[DataPoint]:
        """Get current price from Yahoo Finance"""
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period="1d", interval="1m")
            
            if not data.empty:
                latest_price = float(data["Close"].iloc[-1])
                latest_time = data.index[-1].to_pydatetime()
                
                return DataPoint(
                    value=latest_price,
                    timestamp=latest_time,
                    source="yahoo",
                    symbol=symbol,
                    data_type="price"
                )
        except Exception as e:
            logger.warning(f"[DATA-VALIDATION] Yahoo price fetch failed for {symbol}: {e}")
        
        return None
    
    def calculate_discrepancy(self, primary: DataPoint, validation: DataPoint) -> float:
        """Calculate percentage discrepancy between two data points using max denominator"""
        if primary.value == 0 or validation.value == 0:
            return float('inf')
        
        # Use max(p1, p2) as denominator for more accurate discrepancy calculation
        return abs(primary.value - validation.value) / max(primary.value, validation.value) * 100.0
    
    def detect_split_mismatch(self, primary: DataPoint, validation: DataPoint) -> Tuple[bool, str]:
        """Detect potential stock split mismatches between data sources"""
        if not primary or not validation or primary.value == 0 or validation.value == 0:
            return False, ""
        
        # Calculate ratio between prices
        ratio = max(primary.value, validation.value) / min(primary.value, validation.value)
        
        # Common split ratios: 2:1, 3:1, 4:1, 5:1, 10:1, etc.
        common_splits = [2.0, 3.0, 4.0, 5.0, 10.0, 20.0]
        
        for split_ratio in common_splits:
            # Allow 5% tolerance for split detection
            if abs(ratio - split_ratio) / split_ratio < 0.05:
                return True, f"SUSPECT_SPLIT_MISMATCH ({split_ratio}:1 ratio)"
        
        # Check for reverse splits (fractional ratios)
        for split_ratio in common_splits:
            reverse_ratio = 1.0 / split_ratio
            if abs(ratio - reverse_ratio) / reverse_ratio < 0.05:
                return True, f"SUSPECT_REVERSE_SPLIT ({split_ratio}:1 ratio)"
        
        return False, ""
    
    def validate_symbol_data(self, symbol: str) -> ValidationResult:
        """
        Validate data quality for a single symbol across sources
        
        Returns ValidationResult with quality assessment and recommendations
        """
        issues = []
        
        # Get data from both sources
        alpaca_data = self.get_alpaca_price(symbol)
        yahoo_data = self.get_yahoo_price(symbol)
        
        # Determine primary and validation data
        primary_data = alpaca_data if alpaca_data else yahoo_data
        validation_data = yahoo_data if alpaca_data else None
        
        # Check data availability
        if not primary_data:
            return ValidationResult(
                symbol=symbol,
                primary_data=None,
                validation_data=None,
                quality=DataQuality.CRITICAL,
                discrepancy_pct=None,
                issues=["No data available from any source"],
                recommendation="BLOCK_TRADING",
                timestamp=datetime.now()
            )
        
        # Check data staleness
        if primary_data.is_stale(self.max_staleness_seconds):
            issues.append(f"Primary data is stale ({primary_data.age_seconds:.0f}s old)")
        
        # Cross-source validation if both sources available
        discrepancy_pct = None
        split_detected = False
        split_reason = ""
        
        if validation_data and not validation_data.is_stale(300):  # Allow 5min for Yahoo
            discrepancy_pct = self.calculate_discrepancy(primary_data, validation_data)
            split_detected, split_reason = self.detect_split_mismatch(primary_data, validation_data)
            
            if split_detected and symbol not in self.split_whitelist:
                issues.append(f"Potential split mismatch detected: {split_reason}")
            elif split_detected and symbol in self.split_whitelist:
                # Log but don't flag as issue for whitelisted symbols
                logger.info(f"[DATA-VALIDATION] {symbol}: Split mismatch ignored (whitelisted): {split_reason}")
            elif discrepancy_pct > 10.0:  # Major discrepancy threshold
                issues.append(f"Major price discrepancy {discrepancy_pct:.1f}% - possible data error")
            else:
                # Use symbol-specific attention threshold
                attention_threshold = self.symbol_attention_thresholds.get(symbol, 2.0)
                if discrepancy_pct > attention_threshold:
                    issues.append(f"Price discrepancy {discrepancy_pct:.1f}% requires attention")
        
        # Determine quality and recommendation
        quality, recommendation = self._assess_quality(primary_data, validation_data, discrepancy_pct, issues)
        
        result = ValidationResult(
            symbol=symbol,
            primary_data=primary_data,
            validation_data=validation_data,
            quality=quality,
            discrepancy_pct=discrepancy_pct,
            issues=issues,
            recommendation=recommendation,
            timestamp=datetime.now()
        )
        
        # Log validation result
        self._log_validation_result(result)
        
        # Send alerts for critical issues
        if quality in [DataQuality.POOR, DataQuality.CRITICAL]:
            self._send_data_quality_alert(result)
        
        return result
    
    def _assess_quality(self, primary: DataPoint, validation: Optional[DataPoint], 
                       discrepancy_pct: Optional[float], issues: List[str]) -> Tuple[DataQuality, str]:
        """Assess overall data quality and provide recommendation"""
        
        # Critical: No primary data
        if not primary:
            return DataQuality.CRITICAL, "BLOCK_TRADING"
        
        # Check for split mismatch - always pause trading
        split_issues = [issue for issue in issues if "split mismatch" in issue.lower()]
        if split_issues:
            return DataQuality.POOR, "PAUSE_SYMBOL"
        
        # Check for major discrepancies (>10%)
        major_discrepancy = [issue for issue in issues if "Major price discrepancy" in issue]
        if major_discrepancy:
            return DataQuality.POOR, "PAUSE_SYMBOL"
        
        # Poor: Stale primary data
        if primary.is_stale(self.max_staleness_seconds):
            if self.require_validation:
                return DataQuality.POOR, "BLOCK_TRADING"
            else:
                return DataQuality.POOR, "PROCEED_WITH_CAUTION"
        
        # Attention: Moderate discrepancy (2-10%)
        attention_issues = [issue for issue in issues if "requires attention" in issue]
        if attention_issues:
            return DataQuality.ACCEPTABLE, "ATTENTION"
        
        # Poor: High discrepancy between sources (legacy check)
        if discrepancy_pct and discrepancy_pct > self.max_discrepancy_pct:
            if self.require_validation:
                return DataQuality.POOR, "REQUIRE_MANUAL_APPROVAL"
            else:
                return DataQuality.ACCEPTABLE, "PROCEED_WITH_CAUTION"
        
        # Excellent: Real-time primary + validated
        if primary.source == "alpaca" and validation and discrepancy_pct is not None and discrepancy_pct <= 2.0:
            return DataQuality.EXCELLENT, "PROCEED_NORMAL"
        
        # Good: Real-time primary, no validation
        if primary.source == "alpaca":
            return DataQuality.GOOD, "PROCEED_NORMAL"
        
        # Acceptable: Delayed but recent data
        return DataQuality.ACCEPTABLE, "PROCEED_WITH_CAUTION"
    
    def _log_validation_result(self, result: ValidationResult):
        """Log validation result with clear, actionable information"""
        if not result.primary_data:
            logger.error(f"[DATA-VALIDATION] {result.symbol}: No data available → BLOCK_TRADING")
            return
        
        # Build price comparison string
        if result.validation_data:
            price_comparison = f"{result.primary_data.value:.2f} vs {result.validation_data.value:.2f}"
            if result.discrepancy_pct:
                price_comparison += f" (diff {result.discrepancy_pct:.1f}%)"
        else:
            price_comparison = f"{result.primary_data.value:.2f} (no validation data)"
        
        # Create single actionable log message (using ASCII arrow for Windows compatibility)
        log_msg = f"[DATA-VALIDATION] {result.symbol}: {price_comparison} -> {result.recommendation}"
        
        # Add specific issue context
        if result.issues:
            issue_context = result.issues[0]  # Show most important issue
            if "split mismatch" in issue_context.lower():
                log_msg += f" ({issue_context})"
            elif "Major price discrepancy" in issue_context:
                log_msg += f" (major discrepancy)"
            elif "requires attention" in issue_context:
                log_msg += f" (attention needed)"
        
        # Log at appropriate level
        if result.recommendation in ["BLOCK_TRADING", "PAUSE_SYMBOL"]:
            logger.error(log_msg)
        elif result.recommendation in ["ATTENTION", "PROCEED_WITH_CAUTION"]:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)
    
    def _send_data_quality_alert(self, result: ValidationResult):
        """Send Slack alert for data quality issues"""
        if not self.slack:
            return
        
        try:
            urgency = "🚨 CRITICAL" if result.quality == DataQuality.CRITICAL else "⚠️ WARNING"
            
            primary_info = f"{result.primary_data.source}: ${result.primary_data.value:.2f}" if result.primary_data else "None"
            validation_info = f"{result.validation_data.source}: ${result.validation_data.value:.2f}" if result.validation_data else "None"
            
            message = (
                f"{urgency} **DATA QUALITY ISSUE**\n\n"
                f"**Symbol:** {result.symbol}\n"
                f"**Quality:** {result.quality.value.upper()}\n"
                f"**Primary Source:** {primary_info}\n"
                f"**Validation Source:** {validation_info}\n"
                f"**Discrepancy:** {result.discrepancy_pct:.2f}%" if result.discrepancy_pct else "N/A"
                f"\n**Recommendation:** {result.recommendation}\n\n"
            )
            
            if result.issues:
                message += f"**Issues:**\n" + "\n".join(f"• {issue}" for issue in result.issues)
            
            self.slack.send_alert(message)
            logger.info(f"[DATA-VALIDATION] Sent data quality alert for {result.symbol}")
            
        except Exception as e:
            logger.error(f"[DATA-VALIDATION] Failed to send alert: {e}")
    
    def validate_multiple_symbols(self, symbols: List[str]) -> Dict[str, ValidationResult]:
        """Validate data quality for multiple symbols"""
        results = {}
        
        for symbol in symbols:
            try:
                results[symbol] = self.validate_symbol_data(symbol)
            except Exception as e:
                logger.error(f"[DATA-VALIDATION] Failed to validate {symbol}: {e}")
                results[symbol] = ValidationResult(
                    symbol=symbol,
                    primary_data=None,
                    validation_data=None,
                    quality=DataQuality.CRITICAL,
                    discrepancy_pct=None,
                    issues=[f"Validation error: {e}"],
                    recommendation="BLOCK_TRADING",
                    timestamp=datetime.now()
                )
        
        return results
    
    def _parse_duration(self, duration_str: str) -> int:
        """Parse duration string like '30m', '1h' into seconds."""
        if not duration_str:
            return 0
        
        duration_str = duration_str.lower().strip()
        if duration_str.endswith('m'):
            return int(duration_str[:-1]) * 60
        elif duration_str.endswith('h'):
            return int(duration_str[:-1]) * 3600
        elif duration_str.endswith('s'):
            return int(duration_str[:-1])
        else:
            # Assume minutes if no unit
            return int(duration_str) * 60
    
    def _is_symbol_paused(self, symbol: str) -> Tuple[bool, str]:
        """Check if symbol is currently paused due to validation failures."""
        if symbol not in self.paused_symbols:
            return False, ""
        
        pause_expiry = self.paused_symbols[symbol]
        if datetime.now() > pause_expiry:
            # Pause expired, remove from list
            del self.paused_symbols[symbol]
            logger.info(f"[DATA-VALIDATION] {symbol}: Pause expired, resuming validation")
            return False, ""
        
        remaining = (pause_expiry - datetime.now()).total_seconds()
        return True, f"Symbol paused for {remaining/60:.0f}m due to validation failures"
    
    def _pause_symbol(self, symbol: str, reason: str):
        """Pause symbol for configured duration due to validation failure."""
        if not self.pause_on_validate_fail:
            return
        
        duration_seconds = self._parse_duration(self.pause_on_validate_fail)
        if duration_seconds <= 0:
            return
        
        pause_expiry = datetime.now() + timedelta(seconds=duration_seconds)
        self.paused_symbols[symbol] = pause_expiry
        
        logger.warning(f"[DATA-VALIDATION] {symbol}: Paused for {self.pause_on_validate_fail} - {reason}")
        
        # Send Slack alert for symbol pause
        if self.slack:
            try:
                self.slack.send_alert(
                    f"⏸️ **SYMBOL PAUSED**\n\n"
                    f"**Symbol:** {symbol}\n"
                    f"**Duration:** {self.pause_on_validate_fail}\n"
                    f"**Reason:** {reason}\n"
                    f"**Auto-resume:** {pause_expiry.strftime('%H:%M:%S')}"
                )
            except Exception as e:
                logger.error(f"[DATA-VALIDATION] Failed to send pause alert: {e}")

    def should_allow_trading(self, symbol: str) -> Tuple[bool, str]:
        """
        Determine if trading should be allowed based on data quality
        
        Returns:
            Tuple of (allow_trading, reason)
        """
        if not self.validation_enabled:
            return True, "Data validation disabled"
        
        # Check if symbol is currently paused
        is_paused, pause_reason = self._is_symbol_paused(symbol)
        if is_paused:
            return False, pause_reason
        
        result = self.validate_symbol_data(symbol)
        
        # In strict validation mode, any validation issue blocks trading
        if self.strict_validation:
            if result.recommendation not in ["PROCEED_NORMAL"]:
                reason = f"Strict validation: {', '.join(result.issues) if result.issues else result.recommendation}"
                self._pause_symbol(symbol, reason)
                return False, reason
        
        # Standard validation logic
        if result.recommendation in ["BLOCK_TRADING", "PAUSE_SYMBOL"]:
            reason = f"Trading blocked: {', '.join(result.issues)}"
            self._pause_symbol(symbol, reason)
            return False, reason
        elif result.recommendation == "REQUIRE_MANUAL_APPROVAL":
            reason = f"Manual approval required: {result.discrepancy_pct:.1f}% discrepancy"
            if self.strict_validation:
                self._pause_symbol(symbol, reason)
            return False, reason
        elif result.recommendation == "ATTENTION":
            reason = f"Data requires attention: {result.discrepancy_pct:.1f}% discrepancy"
            if self.strict_validation:
                self._pause_symbol(symbol, reason)
            return False, reason
        else:
            return True, f"Data quality acceptable ({result.quality.value})"


# Convenience functions for easy integration
def validate_symbol_data_quality(symbol: str, config: Dict = None) -> ValidationResult:
    """Convenience function to validate single symbol data quality"""
    validator = DataValidator(config)
    return validator.validate_symbol_data(symbol)


def check_trading_allowed(symbol: str, config: Dict = None) -> Tuple[bool, str]:
    """Convenience function to check if trading is allowed for symbol"""
    validator = DataValidator(config)
    return validator.should_allow_trading(symbol)


def get_data_validator(config: Dict = None) -> DataValidator:
    """Get singleton data validator instance"""
    if not hasattr(get_data_validator, '_instance'):
        get_data_validator._instance = DataValidator(config)
    return get_data_validator._instance
