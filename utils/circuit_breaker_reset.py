"""
Manual Reset Mechanisms for Daily Drawdown Circuit Breaker

This module provides multiple ways to manually reset the circuit breaker:
1. File-based reset (circuit_breaker_reset.trigger)
2. Slack command integration
3. API endpoint for programmatic reset
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple, Optional
import pytz

from .drawdown_circuit_breaker import get_drawdown_circuit_breaker

logger = logging.getLogger(__name__)

# Eastern Time zone
ET_TZ = pytz.timezone('US/Eastern')

class CircuitBreakerResetManager:
    """
    Manages manual reset mechanisms for the circuit breaker.
    
    Features:
    - File-based reset trigger
    - Slack command integration
    - API endpoint support
    - Reset validation and logging
    - Multiple reset reason tracking
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.reset_trigger_file = Path("circuit_breaker_reset.trigger")
        self.reset_log_file = Path("circuit_breaker_reset.log")
        
    def check_file_based_reset(self) -> Tuple[bool, str]:
        """
        Check if file-based reset has been triggered.
        
        Returns:
            Tuple of (reset_triggered, reset_reason)
        """
        try:
            if self.reset_trigger_file.exists():
                # Read reset reason from file if provided
                try:
                    with open(self.reset_trigger_file, 'r') as f:
                        content = f.read().strip()
                        reset_reason = content if content else "File-based manual reset"
                except:
                    reset_reason = "File-based manual reset"
                
                # Remove trigger file
                self.reset_trigger_file.unlink()
                
                logger.info(f"[RESET-MANAGER] File-based reset triggered: {reset_reason}")
                return True, reset_reason
            
            return False, "No file-based reset trigger found"
            
        except Exception as e:
            logger.error(f"[RESET-MANAGER] Error checking file-based reset: {e}")
            return False, f"File-based reset check failed: {str(e)}"
    
    def execute_manual_reset(self, reset_reason: str = "Manual reset", reset_source: str = "Unknown") -> Tuple[bool, str]:
        """
        Execute manual reset of the circuit breaker.
        
        Args:
            reset_reason: Reason for the reset
            reset_source: Source of the reset (file, slack, api, etc.)
            
        Returns:
            Tuple of (success, message)
        """
        try:
            circuit_breaker = get_drawdown_circuit_breaker(self.config)
            
            # Check if circuit breaker is active
            if not circuit_breaker.is_circuit_breaker_active():
                message = "Circuit breaker is not active, no reset needed"
                logger.info(f"[RESET-MANAGER] {message}")
                return True, message
            
            # Get current status for logging
            status_before = circuit_breaker.get_circuit_breaker_status()
            
            # Execute the reset
            full_reset_reason = f"{reset_reason} (via {reset_source})"
            success = circuit_breaker.manual_reset_circuit_breaker(full_reset_reason)
            
            if success:
                # Log the reset
                self._log_reset(reset_reason, reset_source, status_before)
                
                message = f"Circuit breaker successfully reset: {reset_reason}"
                logger.info(f"[RESET-MANAGER] {message}")
                return True, message
            else:
                message = "Circuit breaker reset failed"
                logger.error(f"[RESET-MANAGER] {message}")
                return False, message
                
        except Exception as e:
            message = f"Reset execution failed: {str(e)}"
            logger.error(f"[RESET-MANAGER] {message}")
            return False, message
    
    def _log_reset(self, reset_reason: str, reset_source: str, status_before: Dict):
        """Log reset action for audit trail"""
        try:
            now_et = datetime.now(ET_TZ)
            
            reset_entry = {
                "timestamp": now_et.isoformat(),
                "reset_reason": reset_reason,
                "reset_source": reset_source,
                "status_before_reset": {
                    "was_active": status_before.get("is_active", False),
                    "activation_date": status_before.get("activation_date"),
                    "activation_time": status_before.get("activation_time"),
                    "activation_pnl_percent": status_before.get("activation_pnl_percent"),
                    "activation_reason": status_before.get("activation_reason")
                }
            }
            
            # Append to reset log file
            reset_log = []
            if self.reset_log_file.exists():
                try:
                    with open(self.reset_log_file, 'r') as f:
                        reset_log = json.load(f)
                except:
                    reset_log = []
            
            reset_log.append(reset_entry)
            
            # Keep only last 100 reset entries
            if len(reset_log) > 100:
                reset_log = reset_log[-100:]
            
            with open(self.reset_log_file, 'w') as f:
                json.dump(reset_log, f, indent=2)
            
            logger.debug(f"[RESET-MANAGER] Reset logged to {self.reset_log_file}")
            
        except Exception as e:
            logger.error(f"[RESET-MANAGER] Failed to log reset: {e}")
    
    def process_slack_reset_command(self, slack_message: str, user_id: str = "unknown") -> Tuple[bool, str]:
        """
        Process Slack reset command.
        
        Args:
            slack_message: The Slack message content
            user_id: Slack user ID who sent the command
            
        Returns:
            Tuple of (success, response_message)
        """
        try:
            # Parse reset command and reason
            message_lower = slack_message.lower().strip()
            
            # Check for reset command variations
            reset_commands = ["reset circuit breaker", "reset cb", "cb reset", "circuit breaker reset"]
            
            is_reset_command = any(cmd in message_lower for cmd in reset_commands)
            
            if not is_reset_command:
                return False, "Not a circuit breaker reset command"
            
            # Extract reset reason if provided
            reset_reason = "Slack command reset"
            if "reason:" in message_lower:
                try:
                    reason_part = slack_message.split("reason:", 1)[1].strip()
                    if reason_part:
                        reset_reason = f"Slack reset: {reason_part}"
                except:
                    pass
            
            # Add user information
            reset_reason += f" (by user: {user_id})"
            
            # Execute the reset
            success, message = self.execute_manual_reset(reset_reason, "slack")
            
            if success:
                response = f"✅ {message}\n🟢 Trading has been resumed and new opportunities will be evaluated."
            else:
                response = f"❌ {message}\n🔍 Please check system logs for details."
            
            return success, response
            
        except Exception as e:
            error_msg = f"Slack reset command processing failed: {str(e)}"
            logger.error(f"[RESET-MANAGER] {error_msg}")
            return False, f"❌ {error_msg}"
    
    def create_reset_trigger_file(self, reset_reason: str = "File-based manual reset"):
        """
        Create a reset trigger file for file-based reset.
        
        Args:
            reset_reason: Reason for the reset to be written to the file
        """
        try:
            with open(self.reset_trigger_file, 'w') as f:
                f.write(reset_reason)
            
            logger.info(f"[RESET-MANAGER] Reset trigger file created: {reset_reason}")
            
        except Exception as e:
            logger.error(f"[RESET-MANAGER] Failed to create reset trigger file: {e}")
    
    def get_reset_history(self, limit: int = 10) -> list:
        """
        Get recent reset history for monitoring.
        
        Args:
            limit: Maximum number of recent resets to return
            
        Returns:
            List of recent reset entries
        """
        try:
            if not self.reset_log_file.exists():
                return []
            
            with open(self.reset_log_file, 'r') as f:
                reset_log = json.load(f)
            
            # Return most recent entries
            return reset_log[-limit:] if len(reset_log) > limit else reset_log
            
        except Exception as e:
            logger.error(f"[RESET-MANAGER] Failed to get reset history: {e}")
            return []


_reset_manager_instance = None

def get_reset_manager(config: Dict) -> CircuitBreakerResetManager:
    """Factory function to get CircuitBreakerResetManager singleton instance"""
    global _reset_manager_instance
    
    if _reset_manager_instance is None:
        _reset_manager_instance = CircuitBreakerResetManager(config)
    
    return _reset_manager_instance


def check_and_process_file_reset(config: Dict) -> Tuple[bool, str]:
    """
    Check for and process file-based reset trigger.
    This should be called periodically by the main trading loop.
    
    Returns:
        Tuple of (reset_executed, message)
    """
    try:
        reset_manager = get_reset_manager(config)
        
        # Check for file-based reset
        reset_triggered, reset_reason = reset_manager.check_file_based_reset()
        
        if reset_triggered:
            # Execute the reset
            success, message = reset_manager.execute_manual_reset(reset_reason, "file")
            return success, message
        
        return False, "No file-based reset trigger"
        
    except Exception as e:
        error_msg = f"File reset check failed: {str(e)}"
        logger.error(f"[RESET-MANAGER] {error_msg}")
        return False, error_msg


def process_slack_reset_command(config: Dict, slack_message: str, user_id: str = "unknown") -> Tuple[bool, str]:
    """
    Public API function to process Slack reset commands.
    
    Returns:
        Tuple of (success, response_message)
    """
    try:
        reset_manager = get_reset_manager(config)
        return reset_manager.process_slack_reset_command(slack_message, user_id)
    except Exception as e:
        error_msg = f"Slack reset processing failed: {str(e)}"
        logger.error(f"[RESET-MANAGER] {error_msg}")
        return False, f"❌ {error_msg}"


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
    
    reset_manager = get_reset_manager(config)
    
    print("=== Circuit Breaker Reset Manager ===")
    
    # Check current circuit breaker status
    circuit_breaker = get_drawdown_circuit_breaker(config)
    status = circuit_breaker.get_circuit_breaker_status()
    print(f"Circuit breaker active: {status.get('is_active', False)}")
    
    # Check for file-based reset
    reset_triggered, reason = reset_manager.check_file_based_reset()
    print(f"File reset triggered: {reset_triggered}")
    if reset_triggered:
        print(f"Reset reason: {reason}")
    
    # Show recent reset history
    history = reset_manager.get_reset_history(5)
    print(f"\nRecent resets: {len(history)}")
    for entry in history:
        print(f"  {entry['timestamp']}: {entry['reset_reason']} (via {entry['reset_source']})")
