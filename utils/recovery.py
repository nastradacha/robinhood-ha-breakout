#!/usr/bin/env python3
"""
Automated Recovery System

Provides automatic recovery from transient failures including:
- API timeouts with exponential backoff
- Network connectivity issues
- Failed monitoring processes
- Comprehensive recovery logging
- Escalation to manual intervention

Author: Robinhood HA Breakout System
Version: 1.0.0
License: MIT
"""

import logging
import time
import threading
import subprocess
import psutil
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class RecoveryStatus(Enum):
    """Recovery attempt status."""
    SUCCESS = "success"
    FAILED = "failed"
    ESCALATED = "escalated"
    IN_PROGRESS = "in_progress"


@dataclass
class RecoveryAttempt:
    """Record of a recovery attempt."""
    timestamp: datetime
    failure_type: str
    component: str
    attempt_number: int
    status: RecoveryStatus
    details: str
    duration_seconds: float = 0.0


class ExponentialBackoff:
    """Exponential backoff retry logic."""
    
    def __init__(self, 
                 initial_delay: float = 1.0,
                 max_delay: float = 300.0,
                 backoff_factor: float = 2.0,
                 max_attempts: int = 3):
        """Initialize exponential backoff.
        
        Args:
            initial_delay: Initial delay in seconds
            max_delay: Maximum delay in seconds
            backoff_factor: Multiplier for each retry
            max_attempts: Maximum number of attempts before escalation
        """
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.max_attempts = max_attempts
        self.current_attempt = 0
        
    def get_delay(self) -> float:
        """Get delay for current attempt."""
        if self.current_attempt == 0:
            return 0.0
        
        delay = self.initial_delay * (self.backoff_factor ** (self.current_attempt - 1))
        return min(delay, self.max_delay)
    
    def should_retry(self) -> bool:
        """Check if should retry based on attempt count."""
        return self.current_attempt < self.max_attempts
    
    def next_attempt(self) -> None:
        """Increment attempt counter."""
        self.current_attempt += 1
    
    def reset(self) -> None:
        """Reset attempt counter."""
        self.current_attempt = 0


class RecoveryManager:
    """Manages automated recovery procedures."""
    
    def __init__(self, project_root: Optional[str] = None):
        """Initialize recovery manager.
        
        Args:
            project_root: Path to project root directory
        """
        self.project_root = Path(project_root or ".")
        self.recovery_log_file = self.project_root / "logs" / "recovery.log"
        self.recovery_history: List[RecoveryAttempt] = []
        self.active_recoveries: Dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        
        # Ensure logs directory exists
        self.recovery_log_file.parent.mkdir(exist_ok=True)
        
        logger.info("[RECOVERY] Recovery manager initialized")
    
    def log_recovery_attempt(self, attempt: RecoveryAttempt) -> None:
        """Log recovery attempt to file and memory.
        
        Args:
            attempt: Recovery attempt record
        """
        with self._lock:
            self.recovery_history.append(attempt)
            
            # Write to recovery log file
            try:
                with open(self.recovery_log_file, 'a') as f:
                    log_entry = {
                        "timestamp": attempt.timestamp.isoformat(),
                        "failure_type": attempt.failure_type,
                        "component": attempt.component,
                        "attempt_number": attempt.attempt_number,
                        "status": attempt.status.value,
                        "details": attempt.details,
                        "duration_seconds": attempt.duration_seconds
                    }
                    f.write(json.dumps(log_entry) + "\n")
            except Exception as e:
                logger.error(f"[RECOVERY] Failed to write recovery log: {e}")
        
        # Log to main logger
        level = logging.INFO if attempt.status == RecoveryStatus.SUCCESS else logging.WARNING
        logger.log(level, 
                  f"[RECOVERY] {attempt.component} {attempt.failure_type} - "
                  f"Attempt {attempt.attempt_number}: {attempt.status.value} - {attempt.details}")
    
    def retry_with_backoff(self, 
                          operation: Callable,
                          operation_name: str,
                          component: str,
                          failure_type: str = "api_timeout",
                          **kwargs) -> Any:
        """Retry operation with exponential backoff.
        
        Args:
            operation: Function to retry
            operation_name: Human-readable operation name
            component: Component name (e.g., 'alpaca_api', 'slack_api')
            failure_type: Type of failure being recovered from
            **kwargs: Arguments to pass to operation
            
        Returns:
            Result of successful operation
            
        Raises:
            Exception: If all retry attempts fail
        """
        backoff = ExponentialBackoff()
        last_exception = None
        
        while backoff.should_retry():
            start_time = datetime.now()
            
            try:
                # Wait for backoff delay
                delay = backoff.get_delay()
                if delay > 0:
                    logger.info(f"[RECOVERY] Waiting {delay:.1f}s before retry {backoff.current_attempt + 1}")
                    time.sleep(delay)
                
                backoff.next_attempt()
                
                # Attempt operation
                logger.info(f"[RECOVERY] Attempting {operation_name} (attempt {backoff.current_attempt})")
                result = operation(**kwargs)
                
                # Success
                duration = (datetime.now() - start_time).total_seconds()
                attempt = RecoveryAttempt(
                    timestamp=start_time,
                    failure_type=failure_type,
                    component=component,
                    attempt_number=backoff.current_attempt,
                    status=RecoveryStatus.SUCCESS,
                    details=f"{operation_name} succeeded after {backoff.current_attempt} attempts",
                    duration_seconds=duration
                )
                self.log_recovery_attempt(attempt)
                
                return result
                
            except Exception as e:
                last_exception = e
                duration = (datetime.now() - start_time).total_seconds()
                
                attempt = RecoveryAttempt(
                    timestamp=start_time,
                    failure_type=failure_type,
                    component=component,
                    attempt_number=backoff.current_attempt,
                    status=RecoveryStatus.FAILED,
                    details=f"{operation_name} failed: {str(e)}",
                    duration_seconds=duration
                )
                self.log_recovery_attempt(attempt)
                
                logger.warning(f"[RECOVERY] {operation_name} attempt {backoff.current_attempt} failed: {e}")
        
        # All attempts failed - escalate
        escalation_attempt = RecoveryAttempt(
            timestamp=datetime.now(),
            failure_type=failure_type,
            component=component,
            attempt_number=backoff.max_attempts + 1,
            status=RecoveryStatus.ESCALATED,
            details=f"{operation_name} escalated after {backoff.max_attempts} failed attempts",
            duration_seconds=0.0
        )
        self.log_recovery_attempt(escalation_attempt)
        
        # Send escalation alert
        self._send_escalation_alert(component, operation_name, last_exception)
        
        # Re-raise the last exception
        raise last_exception
    
    def check_network_connectivity(self) -> bool:
        """Check network connectivity to key services.
        
        Returns:
            True if network is accessible
        """
        test_urls = [
            "https://api.alpaca.markets",
            "https://hooks.slack.com",
            "https://finance.yahoo.com",
            "https://8.8.8.8"  # Google DNS
        ]
        
        for url in test_urls:
            try:
                response = requests.get(url, timeout=5)
                if response.status_code < 500:  # Any non-server error is considered connectivity
                    logger.info(f"[RECOVERY] Network connectivity confirmed via {url}")
                    return True
            except Exception as e:
                logger.debug(f"[RECOVERY] Network test failed for {url}: {e}")
                continue
        
        logger.warning("[RECOVERY] Network connectivity check failed for all test URLs")
        return False
    
    def recover_network_connectivity(self) -> bool:
        """Attempt to recover network connectivity.
        
        Returns:
            True if recovery successful
        """
        def check_and_wait():
            """Check connectivity with progressive delays."""
            delays = [5, 15, 30, 60]  # Progressive delays in seconds
            
            for delay in delays:
                if self.check_network_connectivity():
                    return True
                logger.info(f"[RECOVERY] Network still down, waiting {delay}s...")
                time.sleep(delay)
            
            return False
        
        try:
            return self.retry_with_backoff(
                operation=check_and_wait,
                operation_name="network connectivity check",
                component="network",
                failure_type="connectivity_loss"
            )
        except Exception:
            return False
    
    def restart_monitoring_process(self, process_name: str, command: List[str]) -> bool:
        """Restart a failed monitoring process.
        
        Args:
            process_name: Name of the process for logging
            command: Command to start the process
            
        Returns:
            True if restart successful
        """
        def start_process():
            """Start the monitoring process."""
            logger.info(f"[RECOVERY] Starting {process_name} process: {' '.join(command)}")
            
            # Start process in background
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.project_root)
            )
            
            # Give process time to start
            time.sleep(2)
            
            # Check if process is still running
            if process.poll() is None:
                logger.info(f"[RECOVERY] {process_name} process started successfully (PID: {process.pid})")
                return process.pid
            else:
                stdout, stderr = process.communicate()
                error_msg = f"Process exited with code {process.returncode}. stderr: {stderr.decode()}"
                raise RuntimeError(error_msg)
        
        try:
            pid = self.retry_with_backoff(
                operation=start_process,
                operation_name=f"{process_name} restart",
                component="monitoring",
                failure_type="process_failure"
            )
            return True
        except Exception as e:
            logger.error(f"[RECOVERY] Failed to restart {process_name}: {e}")
            return False
    
    def monitor_process_health(self, process_name: str, pid: int) -> bool:
        """Monitor health of a specific process.
        
        Args:
            process_name: Name of the process
            pid: Process ID to monitor
            
        Returns:
            True if process is healthy
        """
        try:
            process = psutil.Process(pid)
            
            # Check if process is running
            if not process.is_running():
                logger.warning(f"[RECOVERY] {process_name} process (PID: {pid}) is not running")
                return False
            
            # Check CPU and memory usage
            cpu_percent = process.cpu_percent(interval=1)
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            
            # Log health metrics
            logger.debug(f"[RECOVERY] {process_name} health - CPU: {cpu_percent:.1f}%, Memory: {memory_mb:.1f}MB")
            
            # Check for excessive resource usage (basic health check)
            if cpu_percent > 90:
                logger.warning(f"[RECOVERY] {process_name} high CPU usage: {cpu_percent:.1f}%")
            
            if memory_mb > 1000:  # 1GB threshold
                logger.warning(f"[RECOVERY] {process_name} high memory usage: {memory_mb:.1f}MB")
            
            return True
            
        except psutil.NoSuchProcess:
            logger.warning(f"[RECOVERY] {process_name} process (PID: {pid}) no longer exists")
            return False
        except Exception as e:
            logger.error(f"[RECOVERY] Error monitoring {process_name} health: {e}")
            return False
    
    def _send_escalation_alert(self, component: str, operation: str, exception: Exception) -> None:
        """Send escalation alert for manual intervention.
        
        Args:
            component: Component that failed
            operation: Operation that failed
            exception: Last exception encountered
        """
        try:
            # Try to send Slack alert
            from .enhanced_slack import EnhancedSlackIntegration
            
            slack = EnhancedSlackIntegration({})
            if slack.enabled:
                alert_msg = (
                    f"🚨 *ESCALATION REQUIRED*\n"
                    f"Component: {component}\n"
                    f"Operation: {operation}\n"
                    f"Error: {str(exception)}\n"
                    f"All automatic recovery attempts failed.\n"
                    f"Manual intervention required."
                )
                slack.send_error_alert("Recovery Escalation", alert_msg)
                logger.info("[RECOVERY] Escalation alert sent to Slack")
            else:
                logger.warning("[RECOVERY] Cannot send escalation alert - Slack not configured")
                
        except Exception as e:
            logger.error(f"[RECOVERY] Failed to send escalation alert: {e}")
    
    def get_recovery_stats(self) -> Dict[str, Any]:
        """Get recovery statistics.
        
        Returns:
            Dictionary with recovery statistics
        """
        with self._lock:
            if not self.recovery_history:
                return {"total_attempts": 0}
            
            total_attempts = len(self.recovery_history)
            successful = sum(1 for a in self.recovery_history if a.status == RecoveryStatus.SUCCESS)
            failed = sum(1 for a in self.recovery_history if a.status == RecoveryStatus.FAILED)
            escalated = sum(1 for a in self.recovery_history if a.status == RecoveryStatus.ESCALATED)
            
            # Component breakdown
            components = {}
            for attempt in self.recovery_history:
                comp = attempt.component
                if comp not in components:
                    components[comp] = {"total": 0, "success": 0, "failed": 0, "escalated": 0}
                components[comp]["total"] += 1
                components[comp][attempt.status.value] += 1
            
            # Recent activity (last 24 hours)
            recent_cutoff = datetime.now() - timedelta(hours=24)
            recent_attempts = [a for a in self.recovery_history if a.timestamp > recent_cutoff]
            
            return {
                "total_attempts": total_attempts,
                "successful": successful,
                "failed": failed,
                "escalated": escalated,
                "success_rate": successful / total_attempts if total_attempts > 0 else 0,
                "components": components,
                "recent_24h": len(recent_attempts),
                "last_attempt": self.recovery_history[-1].timestamp.isoformat() if self.recovery_history else None
            }


# Global recovery manager instance
_global_recovery_manager = None


def get_recovery_manager(project_root: Optional[str] = None) -> RecoveryManager:
    """Get global recovery manager instance.
    
    Args:
        project_root: Path to project root (only used on first call)
        
    Returns:
        Global RecoveryManager instance
    """
    global _global_recovery_manager
    if _global_recovery_manager is None:
        _global_recovery_manager = RecoveryManager(project_root)
    return _global_recovery_manager


def retry_with_recovery(operation: Callable, 
                       operation_name: str,
                       component: str,
                       **kwargs) -> Any:
    """Convenience function for retrying operations with recovery.
    
    Args:
        operation: Function to retry
        operation_name: Human-readable operation name
        component: Component name
        **kwargs: Arguments to pass to operation
        
    Returns:
        Result of successful operation
    """
    recovery_manager = get_recovery_manager()
    return recovery_manager.retry_with_backoff(
        operation=operation,
        operation_name=operation_name,
        component=component,
        **kwargs
    )


if __name__ == "__main__":
    # Demo usage
    import sys
    
    print("Recovery System Demo")
    print("===================")
    
    recovery = RecoveryManager()
    
    # Test network connectivity
    print(f"Network connectivity: {recovery.check_network_connectivity()}")
    
    # Test recovery stats
    stats = recovery.get_recovery_stats()
    print(f"Recovery stats: {stats}")
    
    # Test exponential backoff
    def failing_operation():
        raise Exception("Simulated failure")
    
    try:
        recovery.retry_with_backoff(
            operation=failing_operation,
            operation_name="test operation",
            component="demo"
        )
    except Exception as e:
        print(f"Expected failure after retries: {e}")
    
    # Show final stats
    final_stats = recovery.get_recovery_stats()
    print(f"Final stats: {final_stats}")
    
    print("\nDemo complete.")
