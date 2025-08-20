"""
Weekly Drawdown Circuit Breaker for US-FA-005

This module implements the weekly drawdown protection system that completely
disables the trading system when weekly losses exceed configurable thresholds.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple
import pytz

from .weekly_pnl_tracker import get_weekly_pnl_tracker

logger = logging.getLogger(__name__)

# Eastern Time zone for market hours
ET_TZ = pytz.timezone('US/Eastern')
UTC_TZ = pytz.UTC


class WeeklyDrawdownCircuitBreaker:
    """
    Weekly drawdown circuit breaker that disables the entire trading system
    when weekly losses exceed configurable thresholds.
    
    Features:
    - Complete system disable when weekly loss > 15% (configurable)
    - Persistent state management across system restarts
    - Manual intervention required to re-enable system
    - Critical Slack alerts with performance summary
    - Integration with weekly P&L tracking
    - Comprehensive audit trail and logging
    - Fail-safe design for system reliability
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.state_file = Path("weekly_circuit_breaker_state.json")
        self.threshold_percent = config.get("WEEKLY_DRAWDOWN_THRESHOLD_PERCENT", 15.0)
        self.enabled = config.get("WEEKLY_DRAWDOWN_ENABLED", True)
        self.require_manual_reenable = config.get("WEEKLY_DRAWDOWN_REQUIRE_MANUAL_REENABLE", True)
        
        # Initialize weekly P&L tracker
        self.weekly_pnl_tracker = get_weekly_pnl_tracker(config)
        
        # Load or create state
        self._state = self._load_state()
        
        # Only log initialization once per instance
        if not hasattr(self, '_initialized'):
            self._initialized = True
            logger.info(f"[WEEKLY-CIRCUIT-BREAKER] Initialized (enabled: {self.enabled}, threshold: {self.threshold_percent}%)")
    
    def _load_state(self) -> Dict:
        """Load weekly circuit breaker state from file"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    logger.debug(f"[WEEKLY-CIRCUIT-BREAKER] Loaded state: {state.get('is_system_disabled', False)}")
                    return state
            else:
                logger.info(f"[WEEKLY-CIRCUIT-BREAKER] No existing state file, creating new state")
                return self._create_new_state()
        except Exception as e:
            logger.error(f"[WEEKLY-CIRCUIT-BREAKER] Error loading state: {e}, creating new state")
            return self._create_new_state()
    
    def _create_new_state(self) -> Dict:
        """Create new weekly circuit breaker state"""
        now_et = datetime.now(ET_TZ)
        state = {
            "is_system_disabled": False,
            "disable_date": None,
            "disable_time": None,
            "disable_weekly_pnl_percent": None,
            "disable_reason": None,
            "last_updated": now_et.isoformat(),
            "manual_reenable_required": False,
            "disable_count": 0,
            "performance_summary_at_disable": None,
            "reenable_history": []
        }
        self._save_state(state)
        return state
    
    def _save_state(self, state: Dict):
        """Save state to file"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
            logger.debug(f"[WEEKLY-CIRCUIT-BREAKER] State saved successfully")
        except Exception as e:
            logger.error(f"[WEEKLY-CIRCUIT-BREAKER] Error saving state: {e}")
    
    def check_weekly_drawdown_limit(self) -> Tuple[bool, str]:
        """
        Check if weekly drawdown exceeds threshold and disable system if needed.
        
        Returns:
            Tuple of (should_disable_system, reason)
        """
        if not self.enabled:
            return False, "Weekly drawdown circuit breaker disabled"
        
        # If system is already disabled, check if manual re-enable is required
        if self._state.get("is_system_disabled"):
            if self.require_manual_reenable:
                return True, f"System disabled (manual re-enable required): {self._state.get('disable_reason', 'Unknown')}"
            else:
                # Auto re-enable could be implemented here if needed
                return True, f"System disabled: {self._state.get('disable_reason', 'Unknown')}"
        
        # Check current weekly P&L
        try:
            threshold_exceeded, reason, performance_summary = self.weekly_pnl_tracker.is_weekly_threshold_exceeded()
            
            if threshold_exceeded:
                self._disable_system(reason, performance_summary)
                return True, f"Weekly drawdown limit exceeded - SYSTEM DISABLED: {reason}"
            
            # Log current status for monitoring
            weekly_status = self.weekly_pnl_tracker.get_weekly_status()
            weekly_percent = weekly_status.get("current_weekly_percent", 0.0)
            logger.debug(f"[WEEKLY-CIRCUIT-BREAKER] Weekly P&L check: {weekly_percent:.2f}% (threshold: -{self.threshold_percent}%)")
            
            return False, f"Weekly P&L within limits: {weekly_percent:.2f}%"
            
        except Exception as e:
            logger.error(f"[WEEKLY-CIRCUIT-BREAKER] Error checking weekly P&L: {e}")
            # Fail-safe: don't disable system if we can't calculate P&L
            return False, f"Weekly circuit breaker check failed (system remains enabled): {str(e)}"
    
    def _disable_system(self, reason: str, performance_summary: Dict):
        """Disable the entire trading system due to weekly drawdown threshold breach"""
        now_et = datetime.now(ET_TZ)
        
        # Get current weekly P&L for logging
        weekly_status = self.weekly_pnl_tracker.get_weekly_status()
        weekly_percent = weekly_status.get("current_weekly_percent", 0.0)
        
        disable_reason = f"Weekly loss {weekly_percent:.2f}% exceeds {self.threshold_percent}% threshold"
        
        self._state.update({
            "is_system_disabled": True,
            "disable_date": now_et.strftime("%Y-%m-%d"),
            "disable_time": now_et.strftime("%H:%M:%S"),
            "disable_weekly_pnl_percent": weekly_percent,
            "disable_reason": disable_reason,
            "last_updated": now_et.isoformat(),
            "manual_reenable_required": self.require_manual_reenable,
            "performance_summary_at_disable": performance_summary,
            "disable_count": self._state.get("disable_count", 0) + 1
        })
        
        self._save_state(self._state)
        
        logger.critical(f"[WEEKLY-CIRCUIT-BREAKER] SYSTEM DISABLED: {disable_reason}")
        
        # Log performance summary for analysis
        if performance_summary:
            logger.critical(f"[WEEKLY-CIRCUIT-BREAKER] Performance summary at disable:")
            logger.critical(f"[WEEKLY-CIRCUIT-BREAKER]   Period: {performance_summary.get('period', 'Unknown')}")
            logger.critical(f"[WEEKLY-CIRCUIT-BREAKER]   Total P&L: ${performance_summary.get('total_pnl', 0):.2f} ({performance_summary.get('total_percent', 0):.2f}%)")
            
            stats = performance_summary.get('statistics', {})
            logger.critical(f"[WEEKLY-CIRCUIT-BREAKER]   Winning days: {stats.get('winning_days', 0)}")
            logger.critical(f"[WEEKLY-CIRCUIT-BREAKER]   Losing days: {stats.get('losing_days', 0)}")
            logger.critical(f"[WEEKLY-CIRCUIT-BREAKER]   Worst day: ${stats.get('worst_day_pnl', 0):.2f}")
        
        # Send critical Slack alert
        self._send_system_disable_alert(disable_reason, performance_summary)
    
    def _send_system_disable_alert(self, disable_reason: str, performance_summary: Dict):
        """Send critical Slack alert for system disable"""
        try:
            from .enhanced_slack import EnhancedSlackIntegration
            slack = EnhancedSlackIntegration()
            
            # Prepare alert data
            alert_data = {
                "disable_reason": disable_reason,
                "threshold_percent": self.threshold_percent,
                "disable_weekly_pnl_percent": self._state.get("disable_weekly_pnl_percent", 0.0),
                "performance_summary": performance_summary,
                "disable_count": self._state.get("disable_count", 1),
                "manual_reenable_required": self.require_manual_reenable
            }
            
            # Send alert (method to be implemented in enhanced_slack.py)
            slack.send_weekly_system_disable_alert(alert_data)
            
        except Exception as e:
            logger.error(f"[WEEKLY-CIRCUIT-BREAKER] Failed to send Slack disable alert: {e}")
    
    def is_system_disabled(self) -> bool:
        """Check if the trading system is currently disabled"""
        return self._state.get("is_system_disabled", False)
    
    def manual_reenable_system(self, reenable_reason: str = "Manual re-enable") -> bool:
        """
        Manually re-enable the trading system.
        
        Args:
            reenable_reason: Reason for the manual re-enable
            
        Returns:
            True if re-enable was successful, False otherwise
        """
        if not self._state.get("is_system_disabled"):
            logger.warning(f"[WEEKLY-CIRCUIT-BREAKER] Attempted to re-enable system that is not disabled")
            return False
        
        now_et = datetime.now(ET_TZ)
        
        logger.info(f"[WEEKLY-CIRCUIT-BREAKER] Manual re-enable: {reenable_reason}")
        
        # Store re-enable information for audit trail
        reenable_info = {
            "reenable_time": now_et.isoformat(),
            "reenable_reason": reenable_reason,
            "previous_disable": {
                "disable_date": self._state.get("disable_date"),
                "disable_time": self._state.get("disable_time"),
                "disable_reason": self._state.get("disable_reason"),
                "disable_weekly_pnl_percent": self._state.get("disable_weekly_pnl_percent")
            }
        }
        
        # Add to re-enable history
        reenable_history = self._state.get("reenable_history", [])
        reenable_history.append(reenable_info)
        
        # Reset state to enabled
        self._state.update({
            "is_system_disabled": False,
            "disable_date": None,
            "disable_time": None,
            "disable_weekly_pnl_percent": None,
            "disable_reason": None,
            "last_updated": now_et.isoformat(),
            "manual_reenable_required": False,
            "performance_summary_at_disable": None,
            "reenable_history": reenable_history,
            "last_reenable": reenable_info
        })
        
        self._save_state(self._state)
        
        logger.info(f"[WEEKLY-CIRCUIT-BREAKER] Successfully re-enabled trading system")
        
        # Send Slack alert for system re-enable
        self._send_system_reenable_alert(reenable_info)
        
        return True
    
    def _send_system_reenable_alert(self, reenable_info: Dict):
        """Send Slack alert for system re-enable"""
        try:
            from .enhanced_slack import EnhancedSlackIntegration
            slack = EnhancedSlackIntegration()
            
            # Send alert (method to be implemented in enhanced_slack.py)
            slack.send_weekly_system_reenable_alert(reenable_info)
            
        except Exception as e:
            logger.error(f"[WEEKLY-CIRCUIT-BREAKER] Failed to send Slack re-enable alert: {e}")
    
    def force_disable_system(self, reason: str = "Manual disable"):
        """Force disable the system for testing or manual intervention"""
        now_et = datetime.now(ET_TZ)
        
        self._state.update({
            "is_system_disabled": True,
            "disable_date": now_et.strftime("%Y-%m-%d"),
            "disable_time": now_et.strftime("%H:%M:%S"),
            "disable_weekly_pnl_percent": 0.0,
            "disable_reason": f"Manual disable: {reason}",
            "last_updated": now_et.isoformat(),
            "manual_reenable_required": True
        })
        
        self._save_state(self._state)
        logger.warning(f"[WEEKLY-CIRCUIT-BREAKER] Manually disabled: {reason}")
    
    def get_weekly_circuit_breaker_status(self) -> Dict:
        """Get current weekly circuit breaker status and performance information"""
        try:
            weekly_status = self.weekly_pnl_tracker.get_weekly_status()
            should_disable, reason = self.check_weekly_drawdown_limit()
            
            status = {
                "enabled": self.enabled,
                "threshold_percent": self.threshold_percent,
                "is_system_disabled": self._state.get("is_system_disabled", False),
                "disable_reason": self._state.get("disable_reason"),
                "disable_date": self._state.get("disable_date"),
                "disable_time": self._state.get("disable_time"),
                "disable_weekly_pnl_percent": self._state.get("disable_weekly_pnl_percent"),
                "manual_reenable_required": self._state.get("manual_reenable_required", False),
                "disable_count": self._state.get("disable_count", 0),
                "current_weekly_status": weekly_status,
                "should_disable": should_disable,
                "check_reason": reason,
                "last_updated": self._state.get("last_updated"),
                "reenable_history_count": len(self._state.get("reenable_history", []))
            }
            
            return status
            
        except Exception as e:
            logger.error(f"[WEEKLY-CIRCUIT-BREAKER] Error getting status: {e}")
            return {"error": str(e), "enabled": self.enabled}


# Global instance management
_weekly_circuit_breaker = None

def get_weekly_circuit_breaker(config: Dict) -> WeeklyDrawdownCircuitBreaker:
    """Get or create global weekly circuit breaker instance"""
    global _weekly_circuit_breaker
    if _weekly_circuit_breaker is None:
        _weekly_circuit_breaker = WeeklyDrawdownCircuitBreaker(config)
    return _weekly_circuit_breaker
