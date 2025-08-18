#!/usr/bin/env python3
"""
Emergency Stop Mechanism (Kill Switch)

Provides immediate halt capability for trading operations via multiple triggers:
- File-based: EMERGENCY_STOP.txt in project root
- Programmatic: activate()/deactivate() methods
- Persistent state across restarts

Key Features:
- Atomic file operations for persistence
- Thread-safe state management
- Comprehensive logging and status reporting
- Graceful degradation on file system errors

Author: Robinhood HA Breakout System
Version: 1.0.0
License: MIT
"""

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class KillSwitch:
    """Emergency stop mechanism for trading operations."""
    
    def __init__(self, project_root: Optional[str] = None):
        """Initialize kill switch.
        
        Args:
            project_root: Path to project root directory (defaults to current working directory)
        """
        self.project_root = Path(project_root or os.getcwd())
        self.stop_file = self.project_root / "EMERGENCY_STOP.txt"
        self._lock = threading.Lock()
        
        # State variables
        self._active = False
        self._reason = ""
        self._activated_at = None
        self._source = ""
        self._monitor_only = False
        
        # Load state from disk on initialization
        self._load_from_disk()
        
        logger.info(f"[KILL-SWITCH] Initialized (active: {self._active})")
        if self._active:
            logger.warning(f"[KILL-SWITCH] Emergency stop is ACTIVE: {self._reason}")
    
    def activate(self, reason: str, source: str = "programmatic", monitor_only: bool = False) -> bool:
        """Activate emergency stop.
        
        Args:
            reason: Human-readable reason for activation
            source: Source of activation ('file', 'slack', 'api', 'programmatic')
            monitor_only: If True, only halt new trades but continue monitoring
            
        Returns:
            True if successfully activated, False if already active
        """
        with self._lock:
            if self._active:
                logger.warning(f"[KILL-SWITCH] Already active, ignoring activation request")
                return False
            
            self._active = True
            self._reason = reason
            self._activated_at = datetime.now()
            self._source = source
            self._monitor_only = monitor_only
            
            # Persist to disk
            success = self._persist_to_disk()
            
            if success:
                logger.critical(f"[KILL-SWITCH] EMERGENCY STOP ACTIVATED - Reason: {reason} (source: {source})")
                if monitor_only:
                    logger.info("[KILL-SWITCH] Monitor-only mode: existing positions will continue to be tracked")
            else:
                logger.error("[KILL-SWITCH] Failed to persist emergency stop to disk")
            
            return True
    
    def deactivate(self, source: str = "programmatic") -> bool:
        """Deactivate emergency stop.
        
        Args:
            source: Source of deactivation
            
        Returns:
            True if successfully deactivated, False if not active
        """
        with self._lock:
            if not self._active:
                logger.warning(f"[KILL-SWITCH] Not active, ignoring deactivation request")
                return False
            
            previous_reason = self._reason
            
            self._active = False
            self._reason = ""
            self._activated_at = None
            self._source = ""
            self._monitor_only = False
            
            # Remove persistence file
            success = self._remove_stop_file()
            
            if success:
                logger.info(f"[KILL-SWITCH] Emergency stop DEACTIVATED (was: {previous_reason}, source: {source})")
            else:
                logger.error("[KILL-SWITCH] Failed to remove emergency stop file")
            
            return True
    
    def is_active(self) -> bool:
        """Check if emergency stop is currently active.
        
        Returns:
            True if emergency stop is active
        """
        with self._lock:
            return self._active
    
    def is_monitor_only(self) -> bool:
        """Check if in monitor-only mode.
        
        Returns:
            True if only monitoring (not halting position management)
        """
        with self._lock:
            return self._monitor_only
    
    def get_status(self) -> Dict[str, Any]:
        """Get current kill switch status.
        
        Returns:
            Dictionary with status information
        """
        with self._lock:
            return {
                "active": self._active,
                "reason": self._reason,
                "activated_at": self._activated_at.isoformat() if self._activated_at else None,
                "source": self._source,
                "monitor_only": self._monitor_only,
                "stop_file_exists": self.stop_file.exists()
            }
    
    def check_file_trigger(self) -> bool:
        """Check if emergency stop file was created externally.
        
        Returns:
            True if file trigger activated emergency stop
        """
        if self.stop_file.exists() and not self._active:
            logger.info("[KILL-SWITCH] Emergency stop file detected, activating...")
            
            # Try to read reason from file
            reason = "Emergency stop file created"
            try:
                content = self.stop_file.read_text().strip()
                if content:
                    # Try to parse as JSON first
                    try:
                        data = json.loads(content)
                        reason = data.get("reason", reason)
                    except json.JSONDecodeError:
                        # Treat as plain text reason
                        reason = content
            except Exception as e:
                logger.warning(f"[KILL-SWITCH] Could not read stop file content: {e}")
            
            self.activate(reason, source="file")
            return True
        
        return False
    
    def _load_from_disk(self) -> None:
        """Load kill switch state from disk on startup."""
        if not self.stop_file.exists():
            return
        
        try:
            content = self.stop_file.read_text().strip()
            if not content:
                logger.warning("[KILL-SWITCH] Empty emergency stop file found, removing")
                self.stop_file.unlink()
                return
            
            # Try to parse as JSON
            try:
                data = json.loads(content)
                reason = data.get("reason", "Emergency stop file found")
                activated_at_str = data.get("activated_at")
                source = data.get("source", "file")
                monitor_only = data.get("monitor_only", False)
                
                # Parse timestamp
                activated_at = None
                if activated_at_str:
                    try:
                        activated_at = datetime.fromisoformat(activated_at_str)
                    except ValueError:
                        logger.warning(f"[KILL-SWITCH] Invalid timestamp in stop file: {activated_at_str}")
                
            except json.JSONDecodeError:
                # Treat as plain text reason
                reason = content
                activated_at = None
                source = "file"
                monitor_only = False
            
            # Activate without persistence (already on disk)
            self._active = True
            self._reason = reason
            self._activated_at = activated_at or datetime.now()
            self._source = source
            self._monitor_only = monitor_only
            
            logger.warning(f"[KILL-SWITCH] Loaded emergency stop from disk: {reason}")
            
        except Exception as e:
            logger.error(f"[KILL-SWITCH] Error loading emergency stop from disk: {e}")
    
    def _persist_to_disk(self) -> bool:
        """Persist current state to emergency stop file.
        
        Returns:
            True if successfully persisted
        """
        try:
            data = {
                "reason": self._reason,
                "activated_at": self._activated_at.isoformat() if self._activated_at else None,
                "source": self._source,
                "monitor_only": self._monitor_only
            }
            
            # Atomic write using temporary file
            temp_file = self.stop_file.with_suffix('.tmp')
            temp_file.write_text(json.dumps(data, indent=2))
            temp_file.replace(self.stop_file)
            
            return True
            
        except Exception as e:
            logger.error(f"[KILL-SWITCH] Error persisting to disk: {e}")
            return False
    
    def _remove_stop_file(self) -> bool:
        """Remove emergency stop file.
        
        Returns:
            True if successfully removed or file doesn't exist
        """
        try:
            if self.stop_file.exists():
                self.stop_file.unlink()
            return True
            
        except Exception as e:
            logger.error(f"[KILL-SWITCH] Error removing stop file: {e}")
            return False


# Global instance for easy access
_global_kill_switch = None


def get_kill_switch(project_root: Optional[str] = None) -> KillSwitch:
    """Get global kill switch instance.
    
    Args:
        project_root: Path to project root (only used on first call)
        
    Returns:
        Global KillSwitch instance
    """
    global _global_kill_switch
    if _global_kill_switch is None:
        _global_kill_switch = KillSwitch(project_root)
    return _global_kill_switch


def is_trading_halted() -> bool:
    """Quick check if trading is currently halted.
    
    Returns:
        True if emergency stop is active
    """
    return get_kill_switch().is_active()


def halt_trading(reason: str, source: str = "programmatic") -> bool:
    """Quick function to halt trading.
    
    Args:
        reason: Reason for halting
        source: Source of halt request
        
    Returns:
        True if successfully halted
    """
    return get_kill_switch().activate(reason, source)


def resume_trading(source: str = "programmatic") -> bool:
    """Quick function to resume trading.
    
    Args:
        source: Source of resume request
        
    Returns:
        True if successfully resumed
    """
    return get_kill_switch().deactivate(source)


if __name__ == "__main__":
    # Demo usage
    import time
    
    print("Kill Switch Demo")
    print("================")
    
    ks = KillSwitch()
    
    print(f"Initial status: {ks.get_status()}")
    
    # Test activation
    print("\nActivating emergency stop...")
    ks.activate("Demo test", "manual")
    print(f"Status: {ks.get_status()}")
    print(f"Is active: {ks.is_active()}")
    
    # Test file persistence
    print(f"Stop file exists: {ks.stop_file.exists()}")
    
    # Test deactivation
    print("\nDeactivating emergency stop...")
    ks.deactivate("manual")
    print(f"Status: {ks.get_status()}")
    print(f"Stop file exists: {ks.stop_file.exists()}")
    
    # Test file trigger
    print("\nTesting file trigger...")
    ks.stop_file.write_text("Manual file creation test")
    ks.check_file_trigger()
    print(f"Status after file trigger: {ks.get_status()}")
    
    # Cleanup
    ks.deactivate("cleanup")
    print("\nDemo complete.")
