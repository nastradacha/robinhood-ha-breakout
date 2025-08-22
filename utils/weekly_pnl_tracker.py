"""
Weekly P&L Tracker for US-FA-005 Weekly Drawdown Protection

This module implements rolling 7-day P&L tracking to monitor weekly performance
and trigger system-wide disable when weekly losses exceed configurable thresholds.
"""

from utils.logging_utils import setup_logging
from utils.llm import load_config
from utils.scoped_files import get_scoped_paths
import pandas as pd
import json
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from pathlib import Path
import pytz

from .daily_pnl_tracker import get_daily_pnl_tracker

logger = logging.getLogger(__name__)

# Eastern Time zone for market hours
ET_TZ = pytz.timezone('US/Eastern')
UTC_TZ = pytz.UTC


class WeeklyPnLTracker:
    """
    Weekly P&L tracker that monitors rolling 7-day performance.
    
    Features:
    - Rolling 7-day P&L calculation across all broker environments
    - Historical daily P&L storage for weekly analysis
    - Configurable weekly loss threshold (default: 15%)
    - Performance summary generation for strategy analysis
    """
    _initialized = False
    
    def __init__(self, config: Dict = None):
        """Initialize weekly P&L tracker"""
        self.config = config or {}
        self.enabled = self.config.get("WEEKLY_DRAWDOWN_ENABLED", True)
        self.threshold_pct = self.config.get("WEEKLY_DRAWDOWN_THRESHOLD_PCT", 15.0)
        self.lookback_days = self.config.get("WEEKLY_DRAWDOWN_LOOKBACK_DAYS", 7)
        
        # Initialize daily P&L tracker for current data
        self.daily_pnl_tracker = get_daily_pnl_tracker(config)
        
        # Load or create state
        self.state_file = Path("weekly_pnl_state.json")
        self._state = self._load_state()
        
        # Only log initialization once per process
        if not WeeklyPnLTracker._initialized:
            logger.info(f"[WEEKLY-PNL] Initialized (enabled: {self.enabled}, threshold: {self.threshold_pct}%, lookback: {self.lookback_days} days)")
            WeeklyPnLTracker._initialized = True
    
    def _load_state(self) -> Dict:
        """Load weekly P&L state from file"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    logger.debug(f"[WEEKLY-PNL] Loaded state with {len(state.get('daily_history', []))} daily records")
                    return state
            else:
                logger.info(f"[WEEKLY-PNL] No existing state file, creating new state")
                return self._create_new_state()
        except Exception as e:
            logger.error(f"[WEEKLY-PNL] Error loading state: {e}, creating new state")
            return self._create_new_state()
    
    def _create_new_state(self) -> Dict:
        """Create new weekly P&L state"""
        now_et = datetime.now(ET_TZ)
        state = {
            "daily_history": [],  # List of daily P&L records
            "last_updated": now_et.isoformat(),
            "weekly_summary": {
                "current_week_pnl": 0.0,
                "current_week_percent": 0.0,
                "worst_week_pnl": 0.0,
                "worst_week_percent": 0.0,
                "best_week_pnl": 0.0,
                "best_week_percent": 0.0
            }
        }
        self._save_state(state)
        return state
    
    def _save_state(self, state: Dict):
        """Save state to file"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
            logger.debug(f"[WEEKLY-PNL] State saved successfully")
        except Exception as e:
            logger.error(f"[WEEKLY-PNL] Error saving state: {e}")
    
    def update_daily_pnl(self) -> Tuple[float, float, Dict]:
        """
        Update daily P&L record and return current daily performance.
        
        Returns:
            Tuple of (daily_pnl_amount, daily_pnl_percent, breakdown)
        """
        try:
            # Get current daily P&L from daily tracker
            daily_pnl, daily_pnl_percent, breakdown = self.daily_pnl_tracker.calculate_current_daily_pnl()
            
            now_et = datetime.now(ET_TZ)
            today_date = now_et.strftime("%Y-%m-%d")
            
            # Update or add today's record
            daily_history = self._state.get("daily_history", [])
            
            # Check if today's record already exists
            today_record = None
            for record in daily_history:
                if record.get("date") == today_date:
                    today_record = record
                    break
            
            if today_record:
                # Update existing record
                today_record.update({
                    "pnl_amount": daily_pnl,
                    "pnl_percent": daily_pnl_percent,
                    "breakdown": breakdown,
                    "last_updated": now_et.isoformat()
                })
            else:
                # Add new record
                new_record = {
                    "date": today_date,
                    "pnl_amount": daily_pnl,
                    "pnl_percent": daily_pnl_percent,
                    "breakdown": breakdown,
                    "timestamp": now_et.isoformat(),
                    "last_updated": now_et.isoformat()
                }
                daily_history.append(new_record)
            
            # Keep only the last 30 days of history (for performance)
            cutoff_date = (now_et - timedelta(days=30)).strftime("%Y-%m-%d")
            daily_history = [r for r in daily_history if r.get("date", "") >= cutoff_date]
            
            # Sort by date
            daily_history.sort(key=lambda x: x.get("date", ""))
            
            self._state["daily_history"] = daily_history
            self._state["last_updated"] = now_et.isoformat()
            
            self._save_state(self._state)
            
            logger.debug(f"[WEEKLY-PNL] Updated daily P&L: ${daily_pnl:.2f} ({daily_pnl_percent:.2f}%)")
            
            return daily_pnl, daily_pnl_percent, breakdown
            
        except Exception as e:
            logger.error(f"[WEEKLY-PNL] Error updating daily P&L: {e}")
            return 0.0, 0.0, {}
    
    def calculate_weekly_pnl(self) -> Tuple[float, float, List[Dict]]:
        """
        Calculate rolling 7-day P&L performance.
        
        Returns:
            Tuple of (weekly_pnl_amount, weekly_pnl_percent, weekly_records)
        """
        try:
            # First update today's P&L
            self.update_daily_pnl()
            
            now_et = datetime.now(ET_TZ)
            cutoff_date = (now_et - timedelta(days=self.lookback_days)).strftime("%Y-%m-%d")
            
            # Get records within the lookback period
            daily_history = self._state.get("daily_history", [])
            weekly_records = [r for r in daily_history if r.get("date", "") >= cutoff_date]
            
            if not weekly_records:
                logger.warning(f"[WEEKLY-PNL] No records found for weekly calculation")
                return 0.0, 0.0, []
            
            # Calculate total weekly P&L
            total_pnl = sum(record.get("pnl_amount", 0.0) for record in weekly_records)
            
            # Calculate weekly percentage (approximate based on average daily percentages)
            # This is a simplified calculation - in production, you might want to use
            # actual starting balance from 7 days ago for more accuracy
            daily_percentages = [record.get("pnl_percent", 0.0) for record in weekly_records]
            weekly_percent = sum(daily_percentages)  # Simplified additive approach
            
            logger.debug(f"[WEEKLY-PNL] Weekly calculation: ${total_pnl:.2f} ({weekly_percent:.2f}%) over {len(weekly_records)} days")
            
            # Update weekly summary
            self._update_weekly_summary(total_pnl, weekly_percent)
            
            return total_pnl, weekly_percent, weekly_records
            
        except Exception as e:
            logger.error(f"[WEEKLY-PNL] Error calculating weekly P&L: {e}")
            return 0.0, 0.0, []
    
    def _update_weekly_summary(self, weekly_pnl: float, weekly_percent: float):
        """Update weekly summary statistics"""
        summary = self._state.get("weekly_summary", {})
        
        # Update current week
        summary["current_week_pnl"] = weekly_pnl
        summary["current_week_percent"] = weekly_percent
        
        # Update worst week if this is worse
        if weekly_pnl < summary.get("worst_week_pnl", 0.0):
            summary["worst_week_pnl"] = weekly_pnl
            summary["worst_week_percent"] = weekly_percent
        
        # Update best week if this is better
        if weekly_pnl > summary.get("best_week_pnl", 0.0):
            summary["best_week_pnl"] = weekly_pnl
            summary["best_week_percent"] = weekly_percent
        
        self._state["weekly_summary"] = summary
    
    def is_weekly_threshold_exceeded(self) -> Tuple[bool, str, Dict]:
        """
        Check if weekly drawdown threshold is exceeded.
        
        Returns:
            Tuple of (threshold_exceeded, reason, performance_summary)
        """
        if not self.enabled:
            return False, "Weekly drawdown protection disabled", {}
        
        try:
            weekly_pnl, weekly_percent, weekly_records = self.calculate_weekly_pnl()
            
            # Check if weekly loss exceeds threshold (negative percentage)
            if weekly_percent <= -self.threshold_pct:
                reason = f"Weekly loss {weekly_percent:.2f}% exceeds {self.threshold_pct}% threshold (${weekly_pnl:.2f})"
                
                # Generate performance summary
                performance_summary = self._generate_performance_summary(weekly_records, weekly_pnl, weekly_percent)
                
                logger.critical(f"[WEEKLY-PNL] THRESHOLD EXCEEDED: {reason}")
                return True, reason, performance_summary
            
            # Within limits
            reason = f"Weekly P&L within limits: {weekly_percent:.2f}% (threshold: -{self.threshold_pct}%)"
            logger.debug(f"[WEEKLY-PNL] {reason}")
            
            return False, reason, {}
            
        except Exception as e:
            logger.error(f"[WEEKLY-PNL] Error checking weekly threshold: {e}")
            # Fail-safe: don't trigger threshold if we can't calculate
            return False, f"Weekly threshold check failed: {str(e)}", {}
    
    def _generate_performance_summary(self, weekly_records: List[Dict], weekly_pnl: float, weekly_percent: float) -> Dict:
        """Generate detailed performance summary for analysis"""
        try:
            summary = {
                "period": f"Last {len(weekly_records)} days",
                "total_pnl": weekly_pnl,
                "total_percent": weekly_percent,
                "threshold_percent": self.threshold_pct,
                "daily_breakdown": [],
                "statistics": {
                    "winning_days": 0,
                    "losing_days": 0,
                    "best_day_pnl": 0.0,
                    "worst_day_pnl": 0.0,
                    "average_daily_pnl": 0.0
                }
            }
            
            # Process daily records
            total_days = len(weekly_records)
            if total_days > 0:
                daily_pnls = []
                
                for record in weekly_records:
                    day_pnl = record.get("pnl_amount", 0.0)
                    day_percent = record.get("pnl_percent", 0.0)
                    
                    daily_pnls.append(day_pnl)
                    
                    summary["daily_breakdown"].append({
                        "date": record.get("date"),
                        "pnl": day_pnl,
                        "percent": day_percent
                    })
                    
                    if day_pnl > 0:
                        summary["statistics"]["winning_days"] += 1
                    elif day_pnl < 0:
                        summary["statistics"]["losing_days"] += 1
                
                # Calculate statistics
                if daily_pnls:
                    summary["statistics"]["best_day_pnl"] = max(daily_pnls)
                    summary["statistics"]["worst_day_pnl"] = min(daily_pnls)
                    summary["statistics"]["average_daily_pnl"] = sum(daily_pnls) / len(daily_pnls)
            
            return summary
            
        except Exception as e:
            logger.error(f"[WEEKLY-PNL] Error generating performance summary: {e}")
            return {"error": str(e)}
    
    def get_weekly_status(self) -> Dict:
        """Get current weekly P&L status and summary"""
        try:
            weekly_pnl, weekly_percent, weekly_records = self.calculate_weekly_pnl()
            threshold_exceeded, reason, performance_summary = self.is_weekly_threshold_exceeded()
            
            status = {
                "enabled": self.enabled,
                "threshold_percent": self.threshold_pct,
                "lookback_days": self.lookback_days,
                "current_weekly_pnl": weekly_pnl,
                "current_weekly_percent": weekly_percent,
                "threshold_exceeded": threshold_exceeded,
                "reason": reason,
                "days_in_period": len(weekly_records),
                "performance_summary": performance_summary,
                "weekly_summary": self._state.get("weekly_summary", {}),
                "last_updated": self._state.get("last_updated")
            }
            
            return status
            
        except Exception as e:
            logger.error(f"[WEEKLY-PNL] Error getting weekly status: {e}")
            return {"error": str(e), "enabled": self.enabled}


# Global instance management
_weekly_pnl_tracker = None

def get_weekly_pnl_tracker(config: Dict) -> WeeklyPnLTracker:
    """Get or create global weekly P&L tracker instance"""
    global _weekly_pnl_tracker
    if _weekly_pnl_tracker is None:
        _weekly_pnl_tracker = WeeklyPnLTracker(config)
    return _weekly_pnl_tracker
