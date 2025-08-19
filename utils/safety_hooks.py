"""
Safety hooks for dry run validation and production deployment.
Provides time gates, validation pauses, emergency stops, and session detection.
"""

import os
import sys
import time
from datetime import datetime, time as dt_time, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Eastern Time zone for all trading operations
ET = ZoneInfo("America/New_York")


def parse_hhmm(s):
    """Parse HH:MM time string to time object."""
    return datetime.strptime(s, "%H:%M").time()


def parse_duration(s):
    """Parse duration string like '30m', '2h', '45s' to timedelta."""
    if not s:
        return timedelta(0)
    
    unit = s[-1].lower()
    val = int(s[:-1])
    
    if unit == "m":
        return timedelta(minutes=val)
    elif unit == "h":
        return timedelta(hours=val)
    elif unit == "s":
        return timedelta(seconds=val)
    else:
        raise ValueError(f"Unknown duration unit: {unit}")


def check_time_gate_exit(args):
    """Check if current time exceeds end_at time gate and exit if so."""
    if not args.end_at:
        return
    
    now_et = datetime.now(ET)
    end_at = parse_hhmm(args.end_at)
    end_dt = datetime.combine(now_et.date(), end_at, ET)
    
    if now_et >= end_dt:
        logger.info("[EXIT] %s ≥ end_at %s ET, exiting.", 
                   now_et.strftime("%H:%M"), end_dt.strftime("%H:%M"))
        sys.exit(0)


def session_phase(now_et=None):
    """Determine current market session phase."""
    if now_et is None:
        now_et = datetime.now(ET)
    
    if now_et.weekday() >= 5:  # Saturday=5, Sunday=6
        return "Weekend"
    
    t = now_et.time()
    if t < dt_time(9, 30):
        return "Pre-market"
    elif t >= dt_time(16, 0):
        return "After-hours"
    else:
        return "Regular session"


def check_emergency_stop(config, slack_notifier=None):
    """Check for emergency stop file and handle accordingly."""
    emergency_file = config.get("risk", {}).get("emergency_stop_file", "EMERGENCY_STOP.txt")
    
    if os.path.exists(emergency_file):
        logger.error("[EMERGENCY-STOP] File present; halting all trading.")
        
        if slack_notifier:
            try:
                slack_notifier.send_message(
                    ":stop_sign: Emergency stop file present — trading halted.",
                    channel=config.get("notifiers", {}).get("slack", {}).get("channel")
                )
            except Exception as e:
                logger.warning(f"[EMERGENCY-STOP] Failed to send Slack alert: {e}")
        
        time.sleep(30)  # back off to avoid log spam
        return True
    
    return False


class ValidationPauseManager:
    """Manages validation failure auto-pause functionality."""
    
    def __init__(self, config):
        self.config = config
        self.paused_until = None
        self.pause_duration = config.get("validation", {}).get("pause_on_validate_fail")
    
    def trigger_pause(self, reason, slack_notifier=None):
        """Trigger validation pause for specified duration."""
        if not self.pause_duration:
            return
        
        duration = parse_duration(self.pause_duration)
        self.paused_until = datetime.now(ET) + duration
        
        logger.warning("[VALIDATION-PAUSE] Paused until %s ET due to: %s", 
                      self.paused_until.strftime("%H:%M"), reason)
        
        if slack_notifier:
            try:
                slack_notifier.send_message(
                    f":pause_button: Validation pause until {self.paused_until.strftime('%H:%M %Z')} - {reason}",
                    channel=self.config.get("notifiers", {}).get("slack", {}).get("channel")
                )
            except Exception as e:
                logger.warning(f"[VALIDATION-PAUSE] Failed to send Slack alert: {e}")
    
    def is_paused(self):
        """Check if currently in validation pause period."""
        if not self.paused_until:
            return False
        
        if datetime.now(ET) < self.paused_until:
            return True
        else:
            # Pause period ended
            logger.info("[VALIDATION-PAUSE] Pause period ended, resuming operations")
            self.paused_until = None
            return False
    
    def get_pause_remaining(self):
        """Get remaining pause time in seconds, or 0 if not paused."""
        if not self.is_paused():
            return 0
        
        remaining = self.paused_until - datetime.now(ET)
        return max(0, int(remaining.total_seconds()))


class HealthSnapshotManager:
    """Manages hourly health snapshots during dry run."""
    
    def __init__(self, metrics_logger, config):
        self.metrics_logger = metrics_logger
        self.config = config
        self.last_snapshot_min = None
        self.enabled = config.get("logging", {}).get("hourly_health_snapshot", True)
    
    def maybe_take_snapshot(self, extra_data=None):
        """Take health snapshot at top of each hour."""
        if not self.enabled:
            return
        
        now = datetime.now(ET)
        
        # Take snapshot at top of the hour (minute == 0)
        if now.minute == 0 and (self.last_snapshot_min is None or now.minute != self.last_snapshot_min):
            extra = extra_data or {}
            self.metrics_logger.snapshot_system(extra=extra)
            logger.info("[HEALTH-SNAPSHOT] Hourly system health snapshot taken")
        
        self.last_snapshot_min = now.minute


def log_session_status(symbols_status, rejected_count=0):
    """Log current session status with rejection summary."""
    phase = session_phase()
    
    if rejected_count > 0:
        logger.info("[MULTI-SYMBOL] %s: %d symbols blocked/rejected", phase, rejected_count)
    
    # Log session transitions
    now_et = datetime.now(ET)
    if phase == "Regular session" and now_et.time() == dt_time(9, 30):
        logger.info("[SESSION] Market open - Regular trading session started")
    elif phase == "After-hours" and now_et.time() == dt_time(16, 0):
        logger.info("[SESSION] Market close - After-hours session started")


def validate_dry_run_config(config):
    """Validate dry run configuration for safety."""
    errors = []
    
    # Check broker settings
    broker = config.get("broker", {})
    if broker.get("env") != "paper":
        errors.append("Dry run must use paper trading (broker.env: paper)")
    
    # Check position sizing
    if broker.get("position_sizing_pct", 1.0) > 0.6:
        errors.append("Dry run should use reduced position sizing (≤60%)")
    
    # Check validation settings
    validation = config.get("validation", {})
    if not validation.get("strict"):
        errors.append("Dry run should use strict validation mode")
    
    # Check logging
    logging_cfg = config.get("logging", {})
    if not logging_cfg.get("json_metrics_file"):
        errors.append("Dry run requires JSON metrics logging")
    
    if errors:
        logger.error("[CONFIG-VALIDATION] Dry run configuration errors:")
        for error in errors:
            logger.error("  - %s", error)
        return False
    
    logger.info("[CONFIG-VALIDATION] Dry run configuration validated successfully")
    return True
