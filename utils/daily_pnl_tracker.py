"""
Daily P&L Tracking System for US-FA-004 Daily Drawdown Circuit Breaker

This module provides real-time daily P&L tracking across all broker environments
to support the daily drawdown circuit breaker functionality.
"""

import json
import logging
from datetime import datetime, time
from pathlib import Path
from typing import Dict, Tuple, Optional
import pytz

from .bankroll import BankrollManager
from .scoped_files import get_scoped_paths

logger = logging.getLogger(__name__)

# Eastern Time zone for market hours
ET_TZ = pytz.timezone('US/Eastern')
UTC_TZ = pytz.UTC

class DailyPnLTracker:
    """
    Tracks daily P&L across all broker environments for drawdown protection.
    
    Features:
    - Multi-broker environment support (Alpaca paper/live, Robinhood)
    - Daily reset at market open (9:30 AM ET)
    - Real-time P&L calculation from positions and cash
    - Persistent state storage
    - Timezone-aware tracking
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.state_file = Path("daily_pnl_tracker.json")
        self.market_open_time = time(9, 30)  # 9:30 AM ET
        
        # Get current broker and environment from config
        self.current_broker = config.get("BROKER", "robinhood")
        self.current_env = config.get("ALPACA_ENV", "paper") if self.current_broker == "alpaca" else "live"
        
        self._state = self._load_state()
        
    def _load_state(self) -> Dict:
        """Load daily P&L tracking state from file"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    logger.debug(f"[DAILY-PNL] Loaded state: {state}")
                    return state
            else:
                logger.info(f"[DAILY-PNL] No existing state file, creating new tracking state")
                return self._create_new_state()
        except Exception as e:
            logger.error(f"[DAILY-PNL] Error loading state: {e}, creating new state")
            return self._create_new_state()
    
    def _create_new_state(self) -> Dict:
        """Create new daily tracking state"""
        now_et = datetime.now(ET_TZ)
        state = {
            "tracking_date": now_et.strftime("%Y-%m-%d"),
            "market_open_time": "09:30",
            "daily_start_balances": {},
            "last_updated": now_et.isoformat(),
            "reset_required": False
        }
        self._save_state(state)
        return state
    
    def _save_state(self, state: Dict):
        """Save state to file"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
            logger.debug(f"[DAILY-PNL] Saved state to {self.state_file}")
        except Exception as e:
            logger.error(f"[DAILY-PNL] Error saving state: {e}")
    
    def _is_new_trading_day(self) -> bool:
        """Check if we need to reset for a new trading day"""
        now_et = datetime.now(ET_TZ)
        current_date = now_et.strftime("%Y-%m-%d")
        tracking_date = self._state.get("tracking_date")
        
        # Reset if date changed or if it's past market open and we haven't reset today
        if current_date != tracking_date:
            return True
            
        # Check if we're past market open and haven't captured starting balances today
        market_open_today = now_et.replace(
            hour=self.market_open_time.hour,
            minute=self.market_open_time.minute,
            second=0,
            microsecond=0
        )
        
        if now_et >= market_open_today and not self._state.get("daily_start_balances"):
            return True
            
        return False
    
    def _get_all_broker_environments(self) -> list:
        """Get list of current active broker/environment combination only"""
        # Only return the currently active environment to avoid logging inactive environments
        return [(self.current_broker, self.current_env)]
    
    def _get_current_balance(self, broker: str, env: str) -> float:
        """Get current balance for a specific broker/environment"""
        try:
            bankroll_manager = BankrollManager(broker=broker, env=env)
            current_balance = bankroll_manager.get_current_bankroll()
            
            # Ensure balance is a float for formatting
            if isinstance(current_balance, str):
                try:
                    current_balance = float(current_balance)
                except ValueError:
                    logger.warning(f"[DAILY-PNL] Invalid balance format for {broker}:{env}: {current_balance}")
                    return 0.0
            
            logger.debug(f"[DAILY-PNL] {broker}:{env} current balance: ${current_balance:.2f}")
            return float(current_balance)
        except Exception as e:
            logger.warning(f"[DAILY-PNL] Error getting balance for {broker}:{env}: {e}")
            return 0.0
    
    def track_daily_start_balance(self) -> Dict[str, float]:
        """
        Capture starting balances for all broker environments at market open.
        Should be called at or after 9:30 AM ET.
        """
        if self._is_new_trading_day():
            logger.info(f"[DAILY-PNL] Starting new trading day tracking")
            self._state = self._create_new_state()
        
        now_et = datetime.now(ET_TZ)
        start_balances = {}
        
        for broker, env in self._get_all_broker_environments():
            ledger_id = f"{broker}:{env}"
            current_balance = self._get_current_balance(broker, env)
            start_balances[ledger_id] = current_balance
            
        self._state["daily_start_balances"] = start_balances
        self._state["last_updated"] = now_et.isoformat()
        self._state["tracking_date"] = now_et.strftime("%Y-%m-%d")
        self._save_state(self._state)
    
    def _check_progressive_warnings(self, daily_pnl_percentage: float, breakdown: Dict):
        """Check and send progressive warning alerts at configured loss levels."""
        if daily_pnl_percentage >= 0:
            return  # No warnings needed for positive P&L
        
        # Get alert levels from config (default: 2.5%, 4.0%)
        alert_levels = self.config.get("DAILY_DRAWDOWN_ALERT_LEVELS", [2.5, 4.0])
        
        # Check which warning level we've crossed
        current_loss_pct = abs(daily_pnl_percentage)
        warning_level = None
        
        for level in sorted(alert_levels, reverse=True):
            if current_loss_pct >= level:
                warning_level = level
                break
        
        if warning_level is None:
            return  # No warning threshold crossed
        
        # Check if we've already sent this warning today
        today = datetime.now(ET_TZ).strftime("%Y-%m-%d")
        warning_key = f"warning_{warning_level}_{today}"
        
        if warning_key in self._state.get("warnings_sent", {}):
            return  # Already sent this warning today
        
        # Send progressive warning alert
        logger.warning(f"[DAILY-PNL] Progressive warning: Daily loss {current_loss_pct:.2f}% exceeds {warning_level}% threshold")
        
        try:
            from .enhanced_slack import EnhancedSlackIntegration
            slack = EnhancedSlackIntegration(self.config)
            
            warning_info = {
                "current_loss_percent": current_loss_pct,
                "warning_level": warning_level,
                "daily_pnl_percentage": daily_pnl_percentage,
                "breakdown": breakdown,
                "circuit_breaker_threshold": self.config.get("DAILY_DRAWDOWN_THRESHOLD_PERCENT", 5.0)
            }
            
            slack.send_daily_pnl_warning_alert(warning_info)
            
            # Mark warning as sent
            if "warnings_sent" not in self._state:
                self._state["warnings_sent"] = {}
            self._state["warnings_sent"][warning_key] = {
                "timestamp": datetime.now(ET_TZ).isoformat(),
                "loss_percent": current_loss_pct,
                "warning_level": warning_level
            }
            self._save_state(self._state)
            
        except Exception as e:
            logger.error(f"[DAILY-PNL] Failed to send progressive warning alert: {e}")
    
    def calculate_current_daily_pnl(self) -> Tuple[float, float, Dict]:
        """
        Calculate current daily P&L across all broker environments.
        
        Returns:
            Tuple of (total_daily_pnl, daily_pnl_percentage, detailed_breakdown)
        """
        if not self._state.get("daily_start_balances"):
            logger.warning(f"[DAILY-PNL] No daily start balances captured, initializing...")
            self.track_daily_start_balance()
        
        start_balances = self._state.get("daily_start_balances", {})
        current_balances = {}
        detailed_breakdown = {}
        
        total_start_balance = 0.0
        total_current_balance = 0.0
        
        for broker, env in self._get_all_broker_environments():
            ledger_id = f"{broker}:{env}"
            
            start_balance = start_balances.get(ledger_id, 0.0)
            current_balance = self._get_current_balance(broker, env)
            
            pnl = current_balance - start_balance
            pnl_percent = (pnl / start_balance * 100) if start_balance > 0 else 0.0
            
            detailed_breakdown[ledger_id] = {
                "start_balance": start_balance,
                "current_balance": current_balance,
                "pnl": pnl,
                "pnl_percent": pnl_percent
            }
            
            total_start_balance += start_balance
            total_current_balance += current_balance
        
        total_daily_pnl = total_current_balance - total_start_balance
        daily_pnl_percentage = (total_daily_pnl / total_start_balance * 100) if total_start_balance > 0 else 0.0
        
        logger.debug(f"[DAILY-PNL] Total daily P&L: ${total_daily_pnl:.2f} ({daily_pnl_percentage:.2f}%)")
        
        # Check for progressive warning alerts
        self._check_progressive_warnings(daily_pnl_percentage, detailed_breakdown)
        
        return total_daily_pnl, daily_pnl_percentage, detailed_breakdown
    
    def get_daily_pnl_percentage(self) -> float:
        """Get current daily P&L percentage (simplified interface)"""
        _, daily_pnl_percentage, _ = self.calculate_current_daily_pnl()
        return daily_pnl_percentage
    
    def reset_daily_tracking(self):
        """Manually reset daily tracking (for testing or manual intervention)"""
        logger.info(f"[DAILY-PNL] Manually resetting daily tracking")
        self._state = self._create_new_state()
        self.track_daily_start_balance()
    
    def get_tracking_status(self) -> Dict:
        """Get current tracking status for monitoring/debugging"""
        now_et = datetime.now(ET_TZ)
        is_market_hours = self._is_market_hours(now_et)
        
        status = {
            "tracking_date": self._state.get("tracking_date"),
            "has_start_balances": bool(self._state.get("daily_start_balances")),
            "last_updated": self._state.get("last_updated"),
            "is_market_hours": is_market_hours,
            "current_time_et": now_et.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "needs_reset": self._is_new_trading_day()
        }
        
        if self._state.get("daily_start_balances"):
            _, daily_pnl_percent, _ = self.calculate_current_daily_pnl()
            status["current_daily_pnl_percent"] = daily_pnl_percent
        
        return status
    
    def _is_market_hours(self, dt: datetime) -> bool:
        """Check if given datetime is during market hours (9:30 AM - 4:00 PM ET)"""
        if dt.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False
            
        market_open = dt.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = dt.replace(hour=16, minute=0, second=0, microsecond=0)
        
        return market_open <= dt <= market_close


def get_daily_pnl_tracker(config: Dict) -> DailyPnLTracker:
    """Factory function to get DailyPnLTracker instance"""
    return DailyPnLTracker(config)


def validate_daily_pnl_tracking(symbol: str, config: Dict) -> Tuple[bool, str]:
    """
    Public API function to validate if daily P&L tracking is working properly.
    Used for integration testing and monitoring.
    
    Returns:
        Tuple of (is_working, status_message)
    """
    try:
        tracker = get_daily_pnl_tracker(config)
        status = tracker.get_tracking_status()
        
        if not status["has_start_balances"]:
            return True, "Daily P&L tracking initialized, capturing start balances"
        
        daily_pnl_percent = status.get("current_daily_pnl_percent", 0.0)
        return True, f"Daily P&L tracking active: {daily_pnl_percent:.2f}% daily performance"
        
    except Exception as e:
        logger.error(f"[DAILY-PNL] Validation failed for {symbol}: {e}")
        return False, f"Daily P&L tracking error: {str(e)}"


if __name__ == "__main__":
    # Test/debug functionality
    import yaml
    
    # Load config for testing
    try:
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
    except:
        config = {}
    
    tracker = get_daily_pnl_tracker(config)
    
    print("=== Daily P&L Tracker Status ===")
    status = tracker.get_tracking_status()
    for key, value in status.items():
        print(f"{key}: {value}")
    
    print("\n=== Current Daily P&L ===")
    total_pnl, pnl_percent, breakdown = tracker.calculate_current_daily_pnl()
    print(f"Total Daily P&L: ${total_pnl:.2f} ({pnl_percent:.2f}%)")
    
    print("\n=== Breakdown by Environment ===")
    for ledger_id, details in breakdown.items():
        print(f"{ledger_id}: ${details['pnl']:.2f} ({details['pnl_percent']:.2f}%)")
