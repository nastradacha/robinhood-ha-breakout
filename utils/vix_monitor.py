"""
VIX Spike Detection Module (US-FA-001)

Provides real-time VIX monitoring to block new positions during high volatility periods.
Integrates with the trading decision gate to prevent trades when VIX > threshold.
"""

import logging
import time
import yfinance as yf
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dataclasses import dataclass
import yaml

logger = logging.getLogger(__name__)

@dataclass
class VIXData:
    """VIX data container with timestamp and value."""
    value: float
    timestamp: datetime
    source: str = "yahoo_finance"
    
    @property
    def age_minutes(self) -> float:
        """Get age of VIX data in minutes."""
        return (datetime.now() - self.timestamp).total_seconds() / 60

class VIXMonitor:
    """
    VIX Spike Detection Monitor
    
    Fetches and caches VIX data to detect high volatility periods.
    Blocks new trading positions when VIX exceeds configured threshold.
    """
    _instance = None
    _initialized = False
    
    def __new__(cls, config_path: str = "config.yaml"):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config_path: str = "config.yaml"):
        """Initialize VIX monitor with configuration (singleton)"""
        if self._initialized:
            return
            
        self.logger = logging.getLogger(__name__)
        self.config = self._load_config(config_path)
        self.vix_threshold = self.config.get('VIX_SPIKE_THRESHOLD', 30.0)
        self.cache_minutes = self.config.get('VIX_CACHE_MINUTES', 5)
        self.enabled = self.config.get('VIX_ENABLED', True)
        
        self._cached_vix: Optional[VIXData] = None
        self._last_spike_state = False  # Track spike state changes for alerts
        self._initialized = True
        
        self.logger.info(f"[VIX-MONITOR] Initialized (enabled: {self.enabled}, threshold: {self.vix_threshold})")
    
    def _load_config(self, config_or_path=None) -> Dict[str, Any]:
        """Load configuration from dict or YAML file."""
        if config_or_path is None:
            return {}
        if isinstance(config_or_path, dict):
            return config_or_path
        # assume path-like
        try:
            with open(config_or_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            self.logger.warning(f"[VIX-MONITOR] Config load failed: {e}, using defaults")
            return {}
    
    def get_current_vix(self, force_refresh: bool = False) -> Optional[VIXData]:
        """
        Get current VIX value with caching.
        
        Args:
            force_refresh: Force fetch new data ignoring cache
            
        Returns:
            VIXData object or None if fetch fails
        """
        if not self.enabled:
            logger.debug("[VIX-MONITOR] VIX monitoring disabled")
            return None
        
        # Check cache validity
        if (not force_refresh and 
            self._cached_vix and 
            self._cached_vix.age_minutes < self.cache_minutes):
            logger.debug(f"[VIX-MONITOR] Using cached VIX: {self._cached_vix.value:.2f} "
                        f"(age: {self._cached_vix.age_minutes:.1f}min)")
            return self._cached_vix
        
        # Fetch fresh VIX data
        try:
            logger.debug("[VIX-MONITOR] Fetching fresh VIX data...")
            vix_ticker = yf.Ticker("^VIX")
            vix_info = vix_ticker.history(period="1d", interval="1m")
            
            if vix_info.empty:
                logger.error("[VIX-MONITOR] No VIX data returned from Yahoo Finance")
                return self._cached_vix  # Return stale cache if available
            
            current_vix = float(vix_info['Close'].iloc[-1])
            
            self._cached_vix = VIXData(
                value=current_vix,
                timestamp=datetime.now(),
                source="yahoo_finance"
            )
            
            logger.info(f"[VIX-MONITOR] Fresh VIX data: {current_vix:.2f}")
            return self._cached_vix
            
        except Exception as e:
            logger.error(f"[VIX-MONITOR] Failed to fetch VIX data: {e}")
            return self._cached_vix  # Return stale cache if available
    
    def is_vix_spike_active(self, send_alerts: bool = True) -> tuple[bool, Optional[float], str]:
        """
        Check if VIX spike is currently blocking trades.
        
        Args:
            send_alerts: Whether to send Slack alerts on state changes
        
        Returns:
            Tuple of (is_spike_active, vix_value, reason)
        """
        if not self.enabled:
            return False, None, "VIX monitoring disabled"
        
        vix_data = self.get_current_vix()
        
        if not vix_data:
            logger.warning("[VIX-MONITOR] No VIX data available, allowing trades (fail-safe)")
            return False, None, "VIX data unavailable (fail-safe mode)"
        
        is_spike = vix_data.value > self.vix_threshold
        
        # Send alerts on state changes
        if send_alerts and is_spike != self._last_spike_state:
            self._send_vix_alert(is_spike, vix_data.value)
            self._last_spike_state = is_spike
        
        if is_spike:
            reason = f"VIX spike detected: {vix_data.value:.2f} > {self.vix_threshold:.1f} threshold"
            logger.warning(f"[VIX-MONITOR] {reason}")
        else:
            reason = f"VIX normal: {vix_data.value:.2f} <= {self.vix_threshold:.1f} threshold"
            logger.debug(f"[VIX-MONITOR] {reason}")
        
        return is_spike, vix_data.value, reason
    
    def _send_vix_alert(self, is_spike: bool, vix_value: float):
        """Send VIX state change alert via Slack."""
        try:
            from .enhanced_slack import EnhancedSlackIntegration
            slack = EnhancedSlackIntegration()
            
            if is_spike:
                slack.send_vix_spike_alert(vix_value, self.vix_threshold)
            else:
                slack.send_vix_normalized_alert(vix_value, self.vix_threshold)
                
        except Exception as e:
            logger.error(f"[VIX-MONITOR] Failed to send VIX alert: {e}")
    
    def get_vix_status_summary(self) -> Dict[str, Any]:
        """
        Get VIX monitoring status for system dashboard.
        
        Returns:
            Dictionary with VIX status information
        """
        if not self.enabled:
            return {
                "enabled": False,
                "status": "disabled",
                "message": "VIX monitoring disabled in config"
            }
        
        vix_data = self.get_current_vix()
        
        if not vix_data:
            return {
                "enabled": True,
                "status": "error",
                "message": "VIX data fetch failed",
                "threshold": self.vix_threshold
            }
        
        is_spike, vix_value, reason = self.is_vix_spike_active()
        
        return {
            "enabled": True,
            "status": "spike" if is_spike else "normal",
            "vix_value": vix_value,
            "threshold": self.vix_threshold,
            "last_update": vix_data.timestamp.isoformat(),
            "age_minutes": vix_data.age_minutes,
            "message": reason,
            "blocking_trades": is_spike
        }

# Singleton instance for global access
_vix_monitor_instance: Optional[VIXMonitor] = None

def get_vix_monitor(config_path: str = "config.yaml") -> VIXMonitor:
    """Get singleton VIX monitor instance."""
    global _vix_monitor_instance
    if _vix_monitor_instance is None:
        _vix_monitor_instance = VIXMonitor(config_path)
    return _vix_monitor_instance

def check_vix_spike() -> tuple[bool, Optional[float], str]:
    """
    Convenience function to check VIX spike status.
    
    Returns:
        Tuple of (is_spike_active, vix_value, reason)
    """
    monitor = get_vix_monitor()
    return monitor.is_vix_spike_active()

if __name__ == "__main__":
    # Test VIX monitoring
    monitor = VIXMonitor()
    is_spike, vix_value, reason = monitor.is_vix_spike_active()
    
    print(f"VIX Spike Detection Test:")
    print(f"VIX Value: {vix_value:.2f}" if vix_value else "VIX Value: N/A")
    print(f"Spike Active: {is_spike}")
    print(f"Reason: {reason}")
    
    status = monitor.get_vix_status_summary()
    print(f"\nStatus Summary: {status}")
