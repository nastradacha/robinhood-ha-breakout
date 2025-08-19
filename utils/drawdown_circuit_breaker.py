"""
Daily Drawdown Circuit Breaker for US-FA-004

This module implements the circuit breaker logic that halts trading when daily losses
exceed configurable thresholds to prevent catastrophic daily losses.
"""

from utils.logging_utils import setup_logging
from utils.llm import load_config
from utils.enhanced_slack import EnhancedSlackIntegration
from utils.weekly_pnl_tracker import WeeklyPnLTracker
import json
import os
import logging
from datetime import datetime, time
from typing import Dict, List, Optional, Tuple
import pytz
from pathlib import Path

from .daily_pnl_tracker import get_daily_pnl_tracker

logger = logging.getLogger(__name__)

# Eastern Time zone for market hours
ET_TZ = pytz.timezone('US/Eastern')
UTC_TZ = pytz.UTC

class DrawdownCircuitBreaker:
    """
    Circuit breaker that halts trading when daily drawdown exceeds thresholds.
    
    Features:
    - Configurable daily loss threshold (default: 5%)
    - Automatic activation when threshold exceeded
    - Persistent state across system restarts
    - Manual reset requirement for next-day trading
    - Integration with daily P&L tracking
    - Detailed logging and audit trail
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        """Initialize the circuit breaker with configuration"""
        self.config = load_config(config_path)
        self.state_file = "circuit_breaker_state.json"
        self.slack = EnhancedSlackIntegration()
        
        # Load daily configuration
        self.enabled = self.config.get("DAILY_DRAWDOWN_ENABLED", True)
        self.threshold_percent = self.config.get("DAILY_DRAWDOWN_THRESHOLD_PERCENT", 5.0)
        self.post_threshold_percent = self.config.get("DAILY_DRAWDOWN_POST_THRESHOLD_PERCENT", 0.0)
        self.require_manual_reset = self.config.get("DAILY_DRAWDOWN_REQUIRE_MANUAL_RESET", True)
        self.reset_time_str = self.config.get("DAILY_DRAWDOWN_RESET_TIME", "09:30")
        self.alert_levels = self.config.get("DAILY_DRAWDOWN_ALERT_LEVELS", [2.5, 4.0, 5.0])
        
        # Load weekly configuration
        self.weekly_enabled = self.config.get("WEEKLY_DRAWDOWN_ENABLED", True)
        self.weekly_threshold_percent = self.config.get("WEEKLY_DRAWDOWN_THRESHOLD_PERCENT", 15.0)
        self.weekly_require_manual_reset = self.config.get("WEEKLY_DRAWDOWN_REQUIRE_MANUAL_RESET", True)
        self.weekly_alert_levels = self.config.get("WEEKLY_DRAWDOWN_ALERT_LEVELS", [10.0, 12.5, 15.0])
        self.weekly_performance_window = self.config.get("WEEKLY_DRAWDOWN_PERFORMANCE_WINDOW", 7)
        self.weekly_min_trading_days = self.config.get("WEEKLY_DRAWDOWN_MIN_TRADING_DAYS", 3)
        
        # Parse reset time
        reset_hour, reset_minute = map(int, self.reset_time_str.split(":"))
        self.reset_time = time(reset_hour, reset_minute)
        
        # Initialize weekly tracker
        self.weekly_tracker = WeeklyPnLTracker() if self.weekly_enabled else None
        
        # Initialize state
        self.state = self._load_state()
        
        logger.info(f"[CIRCUIT-BREAKER] Initialized - Daily: {self.enabled} ({self.threshold_percent}%), Weekly: {self.weekly_enabled} ({self.weekly_threshold_percent}%)")
        
    def _load_state(self) -> Dict:
        """Load circuit breaker state from file"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    logger.debug(f"[CIRCUIT-BREAKER] Loaded state: {state}")
                    return state
            else:
                logger.info(f"[CIRCUIT-BREAKER] No existing state file, creating new state")
                return self._create_new_state()
        except Exception as e:
            logger.error(f"[CIRCUIT-BREAKER] Error loading state: {e}, creating new state")
            return self._create_new_state()
    
    def _create_new_state(self) -> Dict:
        """Create new circuit breaker state"""
        now_et = datetime.now(ET_TZ)
        state = {
            "is_active": False,
            "activation_date": None,
            "activation_time": None,
            "activation_pnl_percent": None,
            "activation_reason": None,
            "last_updated": now_et.isoformat(),
            "manual_reset_required": False,
            "reset_count": 0
        }
        self._save_state(state)
        return state
    
    def _save_state(self, state: Dict):
        """Save state to file"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
            logger.debug(f"[CIRCUIT-BREAKER] Saved state to {self.state_file}")
        except Exception as e:
            logger.error(f"[CIRCUIT-BREAKER] Error saving state: {e}")
    
    def _is_new_trading_day(self) -> bool:
        """Check if we should reset circuit breaker for new trading day"""
        if not self._state.get("activation_date"):
            return False
            
        now_et = datetime.now(ET_TZ)
        current_date = now_et.strftime("%Y-%m-%d")
        activation_date = self._state.get("activation_date")
        
        return current_date != activation_date
    
    def check_trading_allowed(self, current_pnl_percent: float = None) -> Tuple[bool, str]:
        """
        Check if trading is allowed based on current drawdown levels (daily and weekly)
        
        Args:
            current_pnl_percent: Current daily P&L percentage (optional, will fetch if not provided)
            
        Returns:
            Tuple of (is_allowed, reason)
        """
        if not self.enabled and not self.weekly_enabled:
            return True, "Circuit breakers disabled"
        
        # Check if manually disabled
        if self.state.get("manually_disabled", False):
            return False, "Trading manually disabled via circuit breaker"
        
        # Get current daily P&L if not provided
        if current_pnl_percent is None:
            daily_tracker = get_daily_pnl_tracker()
            current_pnl_percent = daily_tracker.get_current_pnl_percent()
        
        # Check if we should auto-reset (new trading day)
        if self._should_auto_reset():
            self._reset_circuit_breaker(auto_reset=True)
            # Note: Weekly protection doesn't auto-reset, only manual
        
        # Check weekly protection first (higher priority)
        if self.weekly_enabled and self.weekly_tracker:
            weekly_check = self._check_weekly_protection()
            if not weekly_check[0]:
                return weekly_check
        
        # Check daily protection
        if self.enabled:
            # Check if circuit breaker is already triggered
            if self.state.get("triggered", False):
                trigger_reason = self.state.get("trigger_reason", "Unknown")
                return False, f"Daily circuit breaker active: {trigger_reason}"
            
            # Check if current loss exceeds threshold
            loss_percent = abs(current_pnl_percent) if current_pnl_percent < 0 else 0
            
            if loss_percent >= self.threshold_percent:
                # Trigger circuit breaker
                self._trigger_circuit_breaker(loss_percent, current_pnl_percent)
                return False, f"Daily circuit breaker triggered: {loss_percent:.2f}% loss exceeds {self.threshold_percent}% threshold"
            
            # Check for alert levels
            self._check_alert_levels(loss_percent)
            
            return True, f"Trading allowed: {loss_percent:.2f}% daily loss within {self.threshold_percent}% threshold"
        
        return True, "Trading allowed: No active protection thresholds exceeded"
    
    def _should_auto_reset(self) -> bool:
        """Check if we should reset circuit breaker for new trading day"""
        if not self.state.get("activation_date"):
            return False
            
        now_et = datetime.now(ET_TZ)
        current_date = now_et.strftime("%Y-%m-%d")
        activation_date = self.state.get("activation_date")
        
        return current_date != activation_date
    
    def _reset_circuit_breaker(self, auto_reset: bool = False):
        """Reset circuit breaker"""
        logger.info(f"[CIRCUIT-BREAKER] Resetting circuit breaker (auto-reset: {auto_reset})")
        
        # Reset state
        self.state = self._create_new_state()
        self._save_state()
        
        # Send Slack alert for circuit breaker reset
        try:
            from .enhanced_slack import EnhancedSlackIntegration
            slack = EnhancedSlackIntegration()
            slack.send_circuit_breaker_reset_alert({"auto_reset": auto_reset})
        except Exception as e:
            logger.error(f"[CIRCUIT-BREAKER] Failed to send reset alert: {e}")
    
    def _trigger_circuit_breaker(self, loss_percent: float, current_pnl_percent: float):
        """Trigger circuit breaker"""
        logger.critical(f"[CIRCUIT-BREAKER] Triggered: {loss_percent:.2f}% loss exceeds {self.threshold_percent}% threshold")
        
        # Update state
        self.state.update({
            "triggered": True,
            "trigger_reason": f"{loss_percent:.2f}% loss exceeds {self.threshold_percent}% threshold",
            "last_updated": datetime.now(ET_TZ).isoformat()
        })
        self._save_state()
        
        # Send Slack alert for circuit breaker trigger
        try:
            from .enhanced_slack import EnhancedSlackIntegration
            slack = EnhancedSlackIntegration()
            slack.send_circuit_breaker_trigger_alert({"loss_percent": loss_percent, "threshold_percent": self.threshold_percent})
        except Exception as e:
            logger.error(f"[CIRCUIT-BREAKER] Failed to send trigger alert: {e}")
    
    def _check_alert_levels(self, loss_percent: float):
        """Check for alert levels"""
        for alert_level in self.alert_levels:
            if loss_percent >= alert_level:
                logger.warning(f"[CIRCUIT-BREAKER] Alert level reached: {loss_percent:.2f}% loss exceeds {alert_level}% threshold")
                
                # Send Slack alert for alert level
                try:
                    from .enhanced_slack import EnhancedSlackIntegration
                    slack = EnhancedSlackIntegration()
                    slack.send_circuit_breaker_alert_level_alert({"loss_percent": loss_percent, "alert_level": alert_level})
                except Exception as e:
                    logger.error(f"[CIRCUIT-BREAKER] Failed to send alert level alert: {e}")
    
    def _check_weekly_protection(self) -> Tuple[bool, str]:
        """Check weekly drawdown protection"""
        try:
            # Check if weekly system is disabled
            if self.state.get("weekly_disabled", False):
                disable_reason = self.state.get("weekly_disable_reason", "Weekly threshold exceeded")
                return False, f"Weekly protection active: {disable_reason}"
            
            # Get weekly performance
            weekly_performance = self.weekly_tracker.get_weekly_performance()
            weekly_pnl_percent = weekly_performance.get("weekly_pnl_percent", 0.0)
            trading_days = weekly_performance.get("trading_days", 0)
            
            # Check minimum trading days requirement
            if trading_days < self.weekly_min_trading_days:
                return True, f"Weekly protection inactive: Only {trading_days} trading days (minimum {self.weekly_min_trading_days})"
            
            # Check weekly loss threshold
            weekly_loss_percent = abs(weekly_pnl_percent) if weekly_pnl_percent < 0 else 0
            
            if weekly_loss_percent >= self.weekly_threshold_percent:
                # Trigger weekly protection
                self._trigger_weekly_protection(weekly_loss_percent, weekly_performance)
                return False, f"Weekly protection triggered: {weekly_loss_percent:.2f}% loss exceeds {self.weekly_threshold_percent}% threshold"
            
            # Check for weekly alert levels
            self._check_weekly_alert_levels(weekly_loss_percent)
            
            return True, f"Weekly protection OK: {weekly_loss_percent:.2f}% loss within {self.weekly_threshold_percent}% threshold"
            
        except Exception as e:
            logger.error(f"[CIRCUIT-BREAKER] Error checking weekly protection: {e}")
            return True, "Weekly protection check failed, allowing trading"
    
    def _trigger_weekly_protection(self, weekly_loss_percent: float, weekly_performance: Dict):
        """Trigger weekly drawdown protection"""
        logger.critical(f"[CIRCUIT-BREAKER] Weekly protection triggered: {weekly_loss_percent:.2f}% loss exceeds {self.weekly_threshold_percent}% threshold")
        
        # Update state
        self.state.update({
            "weekly_disabled": True,
            "weekly_disable_reason": f"{weekly_loss_percent:.2f}% weekly loss exceeds {self.weekly_threshold_percent}% threshold",
            "weekly_disable_date": datetime.now(ET_TZ).isoformat(),
            "weekly_disable_performance": weekly_performance,
            "weekly_disable_count": self.state.get("weekly_disable_count", 0) + 1,
            "last_updated": datetime.now(ET_TZ).isoformat()
        })
        self._save_state()
        
        # Send critical Slack alert
        try:
            alert_data = {
                "disable_reason": self.state["weekly_disable_reason"],
                "threshold_percent": self.weekly_threshold_percent,
                "disable_weekly_pnl_percent": weekly_loss_percent,
                "performance_summary": weekly_performance,
                "disable_count": self.state["weekly_disable_count"]
            }
            self.slack.send_weekly_system_disable_alert(alert_data)
        except Exception as e:
            logger.error(f"[CIRCUIT-BREAKER] Failed to send weekly disable alert: {e}")
    
    def _check_weekly_alert_levels(self, weekly_loss_percent: float):
        """Check for weekly alert levels"""
        for alert_level in self.weekly_alert_levels:
            if weekly_loss_percent >= alert_level and not self.state.get(f"weekly_alert_{alert_level}_sent", False):
                logger.warning(f"[CIRCUIT-BREAKER] Weekly alert level reached: {weekly_loss_percent:.2f}% loss exceeds {alert_level}% threshold")
                
                # Mark alert as sent to avoid spam
                self.state[f"weekly_alert_{alert_level}_sent"] = True
                self._save_state()
                
                # Send Slack alert for weekly alert level
                try:
                    alert_data = {
                        "weekly_loss_percent": weekly_loss_percent,
                        "alert_level": alert_level,
                        "threshold_percent": self.weekly_threshold_percent
                    }
                    # Use basic heartbeat for weekly alerts to avoid creating new method
                    message = f"⚠️ **WEEKLY DRAWDOWN ALERT** ⚠️\n\nWeekly Loss: {weekly_loss_percent:.2f}%\nAlert Level: {alert_level}%\nThreshold: {self.weekly_threshold_percent}%"
                    self.slack.send_heartbeat(message)
                except Exception as e:
                    logger.error(f"[CIRCUIT-BREAKER] Failed to send weekly alert level alert: {e}")
    
    def reset_weekly_protection(self, reason: str = "Manual intervention"):
        """Manually reset weekly drawdown protection"""
        if not self.state.get("weekly_disabled", False):
            logger.info("[CIRCUIT-BREAKER] Weekly protection not active, no reset needed")
            return False, "Weekly protection not active"
        
        logger.info(f"[CIRCUIT-BREAKER] Resetting weekly protection: {reason}")
        
        # Store previous disable info for alert
        previous_disable = {
            "disable_date": self.state.get("weekly_disable_date"),
            "disable_reason": self.state.get("weekly_disable_reason"),
            "disable_weekly_pnl_percent": self.state.get("weekly_disable_performance", {}).get("weekly_pnl_percent", 0.0)
        }
        
        # Reset weekly protection state
        weekly_keys_to_remove = [k for k in self.state.keys() if k.startswith("weekly_")]
        for key in weekly_keys_to_remove:
            if key != "weekly_disable_count":  # Keep disable count for tracking
                del self.state[key]
        
        self.state["last_updated"] = datetime.now(ET_TZ).isoformat()
        self._save_state()
        
        # Send re-enable alert
        try:
            reenable_info = {
                "reenable_reason": reason,
                "reenable_time": datetime.now(ET_TZ).strftime("%Y-%m-%d %H:%M:%S ET"),
                "previous_disable": previous_disable
            }
            self.slack.send_weekly_system_reenable_alert(reenable_info)
        except Exception as e:
            logger.error(f"[CIRCUIT-BREAKER] Failed to send weekly re-enable alert: {e}")
        
        return True, f"Weekly protection reset: {reason}"
    
    def check_daily_drawdown_limit(self) -> Tuple[bool, str]:
        """
        Check if daily drawdown exceeds threshold and activate circuit breaker if needed.
        
        Returns:
            Tuple of (should_block_trading, reason)
        """
        if not self.enabled:
            return False, "Daily drawdown circuit breaker disabled"
        
        # Auto-reset for new trading day if not requiring manual reset
        if self._should_auto_reset() and not self.require_manual_reset:
            self._reset_circuit_breaker(auto_reset=True)
        
        # If circuit breaker is already active, check if manual reset is required
        if self._state.get("is_active"):
            if self.require_manual_reset:
                return True, f"Circuit breaker active (manual reset required): {self._state.get('activation_reason', 'Unknown')}"
            elif self._should_auto_reset():
                self._reset_circuit_breaker(auto_reset=True)
                return False, "Circuit breaker auto-reset for new trading day"
            else:
                return True, f"Circuit breaker active: {self._state.get('activation_reason', 'Unknown')}"
        
        # Check current daily P&L
        try:
            daily_pnl, daily_pnl_percent, breakdown = self.pnl_tracker.calculate_current_daily_pnl()
            
            # Check if we've exceeded the drawdown threshold (negative percentage)
            if daily_pnl_percent <= -self.threshold_percent:
                self._activate_circuit_breaker(daily_pnl_percent, daily_pnl, breakdown)
                return True, f"Daily drawdown limit exceeded: {daily_pnl_percent:.2f}% (threshold: -{self.threshold_percent}%)"
            
            # Log current status for monitoring
            logger.debug(f"[CIRCUIT-BREAKER] Daily P&L check: {daily_pnl_percent:.2f}% (threshold: -{self.threshold_percent}%)")
            return False, f"Daily P&L within limits: {daily_pnl_percent:.2f}%"
            
        except Exception as e:
            logger.error(f"[CIRCUIT-BREAKER] Error checking daily P&L: {e}")
            # Fail-safe: allow trading if we can't calculate P&L
            return False, f"Circuit breaker check failed (allowing trading): {str(e)}"
    
    def _activate_circuit_breaker(self, pnl_percent: float, pnl_amount: float, breakdown: Dict):
        """Activate the circuit breaker due to drawdown threshold breach"""
        now_et = datetime.now(ET_TZ)
        
        activation_reason = f"Daily loss {pnl_percent:.2f}% exceeds {self.threshold_percent}% threshold (${pnl_amount:.2f})"
        
        self._state.update({
            "is_active": True,
            "activation_date": now_et.strftime("%Y-%m-%d"),
            "activation_time": now_et.strftime("%H:%M:%S"),
            "activation_pnl_percent": pnl_percent,
            "activation_reason": activation_reason,
            "last_updated": now_et.isoformat(),
            "manual_reset_required": self.require_manual_reset,
            "breakdown_at_activation": breakdown
        })
        
        self._save_state(self._state)
        
        logger.critical(f"[CIRCUIT-BREAKER] ACTIVATED: {activation_reason}")
        
        # Log detailed breakdown for analysis
        logger.info(f"[CIRCUIT-BREAKER] Position breakdown at activation:")
        for ledger_id, details in breakdown.items():
            logger.info(f"[CIRCUIT-BREAKER]   {ledger_id}: ${details['pnl']:.2f} ({details['pnl_percent']:.2f}%)")
        
        # Send Slack alert for circuit breaker activation
        try:
            from .enhanced_slack import EnhancedSlackIntegration
            slack = EnhancedSlackIntegration()
            circuit_breaker_info = {
                "activation_pnl_percent": pnl_percent,
                "threshold_percent": self.threshold_percent,
                "activation_reason": activation_reason,
                "breakdown_at_activation": breakdown
            }
            slack.send_circuit_breaker_activation_alert(circuit_breaker_info)
        except Exception as e:
            logger.error(f"[CIRCUIT-BREAKER] Failed to send Slack activation alert: {e}")
    
    def _auto_reset_for_new_day(self):
        """Automatically reset circuit breaker for new trading day"""
        logger.info(f"[CIRCUIT-BREAKER] Auto-resetting for new trading day")
        self._state = self._create_new_state()
    
    def is_circuit_breaker_active(self) -> bool:
        """Check if circuit breaker is currently active"""
        return self._state.get("is_active", False)
    
    def manual_reset_circuit_breaker(self, reset_reason: str = "Manual reset") -> bool:
        """
        Manually reset the circuit breaker.
        
        Args:
            reset_reason: Reason for the manual reset
            
        Returns:
            True if reset was successful, False otherwise
        """
        if not self._state.get("is_active"):
            logger.warning(f"[CIRCUIT-BREAKER] Attempted to reset inactive circuit breaker")
            return False
        
        now_et = datetime.now(ET_TZ)
        
        logger.info(f"[CIRCUIT-BREAKER] Manual reset: {reset_reason}")
        
        # Store reset information for audit trail
        reset_info = {
            "reset_time": now_et.isoformat(),
            "reset_reason": reset_reason,
            "previous_activation": {
                "date": self._state.get("activation_date"),
                "time": self._state.get("activation_time"),
                "pnl_percent": self._state.get("activation_pnl_percent"),
                "reason": self._state.get("activation_reason")
            }
        }
        
        # Reset state but keep audit trail
        self._state.update({
            "is_active": False,
            "activation_date": None,
            "activation_time": None,
            "activation_pnl_percent": None,
            "activation_reason": None,
            "last_updated": now_et.isoformat(),
            "manual_reset_required": False,
            "reset_count": self._state.get("reset_count", 0) + 1,
            "last_reset": reset_info
        })
        
        self._save_state(self._state)
        
        logger.info(f"[CIRCUIT-BREAKER] Successfully reset circuit breaker")
        
        # Send Slack alert for circuit breaker reset
        try:
            from .enhanced_slack import EnhancedSlackIntegration
            slack = EnhancedSlackIntegration()
            slack.send_circuit_breaker_reset_alert(reset_info)
        except Exception as e:
            logger.error(f"[CIRCUIT-BREAKER] Failed to send reset alert: {e}")
    
    def get_circuit_breaker_status(self) -> Dict:
        """Get current circuit breaker status and daily P&L information"""
        now_et = datetime.now(ET_TZ)
        
        status = {
            "enabled": self.enabled,
            "threshold_percent": self.threshold_percent,
            "is_active": self._state.get("is_active", False),
            "require_manual_reset": self.require_manual_reset,
            "current_time_et": now_et.strftime("%Y-%m-%d %H:%M:%S %Z")
        }
        
        if self._state.get("is_active"):
            status.update({
                "activation_date": self._state.get("activation_date"),
                "activation_time": self._state.get("activation_time"),
                "activation_pnl_percent": self._state.get("activation_pnl_percent"),
                "activation_reason": self._state.get("activation_reason")
            })
        
        # Add current P&L status if available
        try:
            daily_pnl, daily_pnl_percent, _ = self.pnl_tracker.calculate_current_daily_pnl()
            status.update({
                "current_daily_pnl": daily_pnl,
                "current_daily_pnl_percent": daily_pnl_percent,
                "distance_to_threshold": daily_pnl_percent + self.threshold_percent
            })
        except Exception as e:
            status["pnl_error"] = str(e)
        
        return status
    
    def force_activate_circuit_breaker(self, reason: str = "Manual activation"):
        """Force activate circuit breaker (for testing or emergency use)"""
        now_et = datetime.now(ET_TZ)
        
        self._state.update({
            "is_active": True,
            "activation_date": now_et.strftime("%Y-%m-%d"),
            "activation_time": now_et.strftime("%H:%M:%S"),
            "activation_pnl_percent": 0.0,
            "activation_reason": f"Manual activation: {reason}",
            "last_updated": now_et.isoformat(),
            "manual_reset_required": True
        })
        
        self._save_state(self._state)
        logger.warning(f"[CIRCUIT-BREAKER] Manually activated: {reason}")


def validate_circuit_breaker_config(config: Dict) -> Tuple[bool, List[str]]:
    """
    Validate circuit breaker configuration settings.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    try:
        # Check if circuit breaker is enabled
        enabled = config.get("DAILY_DRAWDOWN_ENABLED", False)
        if not isinstance(enabled, bool):
            errors.append("DAILY_DRAWDOWN_ENABLED must be a boolean (true/false)")
        
        # Validate threshold percentage
        threshold = config.get("DAILY_DRAWDOWN_THRESHOLD_PERCENT", 5.0)
        if not isinstance(threshold, (int, float)):
            errors.append("DAILY_DRAWDOWN_THRESHOLD_PERCENT must be a number")
        elif threshold <= 0 or threshold > 50:
            errors.append("DAILY_DRAWDOWN_THRESHOLD_PERCENT must be between 0 and 50")
        
        # Validate manual reset requirement
        manual_reset = config.get("DAILY_DRAWDOWN_REQUIRE_MANUAL_RESET", True)
        if not isinstance(manual_reset, bool):
            errors.append("DAILY_DRAWDOWN_REQUIRE_MANUAL_RESET must be a boolean (true/false)")
        
        # Validate reset time format
        reset_time = config.get("DAILY_DRAWDOWN_RESET_TIME", "09:30")
        if not isinstance(reset_time, str):
            errors.append("DAILY_DRAWDOWN_RESET_TIME must be a string")
        else:
            try:
                # Validate time format HH:MM
                time_parts = reset_time.split(":")
                if len(time_parts) != 2:
                    raise ValueError("Invalid format")
                hour, minute = int(time_parts[0]), int(time_parts[1])
                if not (0 <= hour <= 23) or not (0 <= minute <= 59):
                    raise ValueError("Invalid time range")
            except (ValueError, IndexError):
                errors.append("DAILY_DRAWDOWN_RESET_TIME must be in HH:MM format (e.g., '09:30')")
        
        # Validate alert levels
        alert_levels = config.get("DAILY_DRAWDOWN_ALERT_LEVELS", [2.5, 4.0])
        if not isinstance(alert_levels, list):
            errors.append("DAILY_DRAWDOWN_ALERT_LEVELS must be a list of numbers")
        else:
            for i, level in enumerate(alert_levels):
                if not isinstance(level, (int, float)):
                    errors.append(f"DAILY_DRAWDOWN_ALERT_LEVELS[{i}] must be a number")
                elif level <= 0 or level >= threshold:
                    errors.append(f"DAILY_DRAWDOWN_ALERT_LEVELS[{i}] must be between 0 and {threshold}")
        
        # Validate that alert levels are sorted and unique
        if isinstance(alert_levels, list) and all(isinstance(x, (int, float)) for x in alert_levels):
            if alert_levels != sorted(set(alert_levels)):
                errors.append("DAILY_DRAWDOWN_ALERT_LEVELS should be sorted and contain unique values")
        
        # Check for required environment variables if Slack is enabled
        slack_enabled = config.get("SLACK_WEBHOOK_URL") or config.get("SLACK_BOT_TOKEN")
        if enabled and not slack_enabled:
            errors.append("Circuit breaker requires Slack integration (SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN)")
        
        return len(errors) == 0, errors
        
    except Exception as e:
        errors.append(f"Configuration validation error: {e}")
        return False, errors


def get_drawdown_circuit_breaker(config: Dict) -> DrawdownCircuitBreaker:
    """Factory function to get DrawdownCircuitBreaker instance"""
    return DrawdownCircuitBreaker(config)


def check_circuit_breaker(config: Dict) -> Tuple[bool, str]:
    """
    Public API function to check if circuit breaker should block trading.
    Used for integration with pre-LLM gates.
    
    Returns:
        Tuple of (should_block_trading, reason)
    """
    try:
        circuit_breaker = get_drawdown_circuit_breaker(config)
        return circuit_breaker.check_daily_drawdown_limit()
    except Exception as e:
        logger.error(f"[CIRCUIT-BREAKER] Check failed: {e}")
        # Fail-safe: allow trading if circuit breaker check fails
        return False, f"Circuit breaker check failed (allowing trading): {str(e)}"


def validate_circuit_breaker_integration(symbol: str, config: Dict) -> Tuple[bool, str]:
    """
    Public API function to validate circuit breaker integration.
    Used for testing and monitoring.
    
    Returns:
        Tuple of (is_working, status_message)
    """
    try:
        circuit_breaker = get_drawdown_circuit_breaker(config)
        status = circuit_breaker.get_circuit_breaker_status()
        
        if not status["enabled"]:
            return True, "Circuit breaker disabled in configuration"
        
        if status["is_active"]:
            return True, f"Circuit breaker ACTIVE: {status.get('activation_reason', 'Unknown')}"
        
        current_pnl = status.get("current_daily_pnl_percent", 0.0)
        threshold = status["threshold_percent"]
        distance = status.get("distance_to_threshold", threshold)
        
        return True, f"Circuit breaker armed: {current_pnl:.2f}% daily P&L ({distance:.2f}% to -{threshold}% threshold)"
        
    except Exception as e:
        logger.error(f"[CIRCUIT-BREAKER] Validation failed for {symbol}: {e}")
        return False, f"Circuit breaker validation error: {str(e)}"


if __name__ == "__main__":
    # Test/debug functionality
    import yaml
    
    # Load config for testing
    try:
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
    except:
        config = {
            "DAILY_DRAWDOWN_ENABLED": True,
            "DAILY_DRAWDOWN_THRESHOLD_PERCENT": 5.0,
            "DAILY_DRAWDOWN_REQUIRE_MANUAL_RESET": True
        }
    
    circuit_breaker = get_drawdown_circuit_breaker(config)
    
    print("=== Circuit Breaker Status ===")
    status = circuit_breaker.get_circuit_breaker_status()
    for key, value in status.items():
        print(f"{key}: {value}")
    
    print("\n=== Circuit Breaker Check ===")
    should_block, reason = circuit_breaker.check_daily_drawdown_limit()
    print(f"Should block trading: {should_block}")
    print(f"Reason: {reason}")
