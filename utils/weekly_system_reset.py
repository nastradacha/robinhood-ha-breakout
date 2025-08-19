"""
Weekly System Reset Manager for US-FA-005

This module provides manual re-enable workflows and reset mechanisms for the
weekly drawdown protection system.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
import pytz

logger = logging.getLogger(__name__)

# Eastern Time zone for market hours
ET_TZ = pytz.timezone('US/Eastern')


class WeeklySystemResetManager:
    """
    Manager for weekly system reset and re-enable operations.
    
    Features:
    - Manual system re-enable with intervention tracking
    - File-based reset triggers for operational convenience
    - Slack command integration for remote system management
    - Comprehensive audit trail of all reset operations
    - Safety checks to prevent accidental re-enables
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.reset_trigger_file = Path("weekly_system_reset.trigger")
        self.reset_history_file = Path("weekly_reset_history.json")
        
        logger.info(f"[WEEKLY-RESET] Initialized weekly system reset manager")
    
    def check_for_reset_trigger(self) -> Tuple[bool, str]:
        """
        Check for file-based reset trigger.
        
        Returns:
            Tuple of (reset_requested, reset_reason)
        """
        try:
            if self.reset_trigger_file.exists():
                # Read reset reason from file
                try:
                    reset_reason = self.reset_trigger_file.read_text().strip()
                    if not reset_reason:
                        reset_reason = "File-based reset (no reason specified)"
                except Exception:
                    reset_reason = "File-based reset"
                
                logger.info(f"[WEEKLY-RESET] Reset trigger file detected: {reset_reason}")
                return True, reset_reason
            
            return False, "No reset trigger detected"
            
        except Exception as e:
            logger.error(f"[WEEKLY-RESET] Error checking reset trigger: {e}")
            return False, f"Reset trigger check failed: {str(e)}"
    
    def process_reset_trigger(self) -> Tuple[bool, str]:
        """
        Process detected reset trigger and perform system re-enable.
        
        Returns:
            Tuple of (reset_successful, result_message)
        """
        try:
            reset_requested, reset_reason = self.check_for_reset_trigger()
            
            if not reset_requested:
                return False, "No reset trigger found"
            
            # Perform the reset
            success, message = self.manual_reenable_system(reset_reason)
            
            if success:
                # Remove the trigger file
                try:
                    self.reset_trigger_file.unlink()
                    logger.info(f"[WEEKLY-RESET] Reset trigger file removed")
                except Exception as e:
                    logger.warning(f"[WEEKLY-RESET] Failed to remove trigger file: {e}")
                
                # Log the reset operation
                self._log_reset_operation(reset_reason, "file_trigger", success, message)
                
                return True, f"System re-enabled via file trigger: {message}"
            else:
                self._log_reset_operation(reset_reason, "file_trigger", success, message)
                return False, f"Reset failed: {message}"
                
        except Exception as e:
            error_msg = f"Reset processing failed: {str(e)}"
            logger.error(f"[WEEKLY-RESET] {error_msg}")
            return False, error_msg
    
    def manual_reenable_system(self, reason: str = "Manual intervention") -> Tuple[bool, str]:
        """
        Manually re-enable the trading system.
        
        Args:
            reason: Reason for the manual re-enable
            
        Returns:
            Tuple of (success, message)
        """
        try:
            from .weekly_drawdown_circuit_breaker import get_weekly_circuit_breaker
            
            # Get the weekly circuit breaker instance
            weekly_cb = get_weekly_circuit_breaker(self.config)
            
            # Check if system is actually disabled
            if not weekly_cb.is_system_disabled():
                message = "System is not currently disabled"
                logger.warning(f"[WEEKLY-RESET] {message}")
                return False, message
            
            # Perform the re-enable
            success = weekly_cb.manual_reenable_system(reason)
            
            if success:
                message = f"System successfully re-enabled: {reason}"
                logger.info(f"[WEEKLY-RESET] {message}")
                
                # Send Slack notification
                self._send_reenable_notification(reason)
                
                return True, message
            else:
                message = "Failed to re-enable system"
                logger.error(f"[WEEKLY-RESET] {message}")
                return False, message
                
        except Exception as e:
            error_msg = f"Manual re-enable failed: {str(e)}"
            logger.error(f"[WEEKLY-RESET] {error_msg}")
            return False, error_msg
    
    def create_reset_trigger(self, reason: str = "Manual reset request") -> bool:
        """
        Create a reset trigger file for file-based reset.
        
        Args:
            reason: Reason for the reset request
            
        Returns:
            True if trigger file created successfully
        """
        try:
            self.reset_trigger_file.write_text(reason)
            logger.info(f"[WEEKLY-RESET] Reset trigger file created: {reason}")
            return True
        except Exception as e:
            logger.error(f"[WEEKLY-RESET] Failed to create reset trigger file: {e}")
            return False
    
    def get_reset_status(self) -> Dict:
        """Get current reset status and system state"""
        try:
            from .weekly_drawdown_circuit_breaker import get_weekly_circuit_breaker
            
            weekly_cb = get_weekly_circuit_breaker(self.config)
            cb_status = weekly_cb.get_weekly_circuit_breaker_status()
            
            reset_requested, reset_reason = self.check_for_reset_trigger()
            
            status = {
                "system_disabled": cb_status.get("is_system_disabled", False),
                "disable_reason": cb_status.get("disable_reason"),
                "disable_date": cb_status.get("disable_date"),
                "manual_reenable_required": cb_status.get("manual_reenable_required", False),
                "reset_trigger_pending": reset_requested,
                "reset_trigger_reason": reset_reason if reset_requested else None,
                "reset_history_count": self._get_reset_history_count(),
                "weekly_circuit_breaker_status": cb_status
            }
            
            return status
            
        except Exception as e:
            logger.error(f"[WEEKLY-RESET] Error getting reset status: {e}")
            return {"error": str(e)}
    
    def _send_reenable_notification(self, reason: str):
        """Send Slack notification for system re-enable"""
        try:
            from .enhanced_slack import EnhancedSlackIntegration
            slack = EnhancedSlackIntegration()
            
            notification_data = {
                "reenable_reason": reason,
                "reenable_time": datetime.now(ET_TZ).isoformat(),
                "reset_method": "manual_intervention"
            }
            
            # Send notification (method to be implemented in enhanced_slack.py)
            slack.send_weekly_system_reenable_notification(notification_data)
            
        except Exception as e:
            logger.error(f"[WEEKLY-RESET] Failed to send re-enable notification: {e}")
    
    def _log_reset_operation(self, reason: str, method: str, success: bool, message: str):
        """Log reset operation to history file"""
        try:
            # Load existing history
            history = []
            if self.reset_history_file.exists():
                with open(self.reset_history_file, 'r') as f:
                    history = json.load(f)
            
            # Add new entry
            entry = {
                "timestamp": datetime.now(ET_TZ).isoformat(),
                "reason": reason,
                "method": method,
                "success": success,
                "message": message
            }
            
            history.append(entry)
            
            # Keep only last 100 entries
            if len(history) > 100:
                history = history[-100:]
            
            # Save updated history
            with open(self.reset_history_file, 'w') as f:
                json.dump(history, f, indent=2)
                
            logger.debug(f"[WEEKLY-RESET] Reset operation logged to history")
            
        except Exception as e:
            logger.error(f"[WEEKLY-RESET] Failed to log reset operation: {e}")
    
    def _get_reset_history_count(self) -> int:
        """Get count of reset operations in history"""
        try:
            if self.reset_history_file.exists():
                with open(self.reset_history_file, 'r') as f:
                    history = json.load(f)
                    return len(history)
            return 0
        except Exception:
            return 0
    
    def get_reset_history(self, limit: int = 10) -> List[Dict]:
        """
        Get recent reset history.
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            List of recent reset operations
        """
        try:
            if not self.reset_history_file.exists():
                return []
            
            with open(self.reset_history_file, 'r') as f:
                history = json.load(f)
                
            # Return most recent entries
            return history[-limit:] if len(history) > limit else history
            
        except Exception as e:
            logger.error(f"[WEEKLY-RESET] Error getting reset history: {e}")
            return []


# Global instance management
_weekly_reset_manager = None

def get_weekly_reset_manager(config: Dict) -> WeeklySystemResetManager:
    """Get or create global weekly reset manager instance"""
    global _weekly_reset_manager
    if _weekly_reset_manager is None:
        _weekly_reset_manager = WeeklySystemResetManager(config)
    return _weekly_reset_manager


def check_and_process_weekly_reset(config: Dict) -> Tuple[bool, str]:
    """
    Convenience function to check and process weekly system reset.
    
    Args:
        config: Trading configuration
        
    Returns:
        Tuple of (reset_processed, message)
    """
    try:
        reset_manager = get_weekly_reset_manager(config)
        return reset_manager.process_reset_trigger()
    except Exception as e:
        error_msg = f"Weekly reset check failed: {str(e)}"
        logger.error(f"[WEEKLY-RESET] {error_msg}")
        return False, error_msg
