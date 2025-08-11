#!/usr/bin/env python3
"""
Monitor launcher utility for automatic exit-monitor management.

Handles spawning and tracking of monitor_alpaca.py processes for each symbol.
"""

import sys
import subprocess
import psutil
import logging
from pathlib import Path
from typing import Optional
import atexit

# Import enhanced Slack for S1 breadcrumbs
try:
    from .enhanced_slack import EnhancedSlackIntegration
except ImportError:
    # Handle standalone execution
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from utils.enhanced_slack import EnhancedSlackIntegration

logger = logging.getLogger(__name__)


class MonitorLauncher:
    """Manages automatic launching and tracking of monitor processes."""

    def __init__(self, project_root: Optional[Path] = None):
        """Initialize monitor launcher.

        Args:
            project_root: Path to project root directory. If None, auto-detect.
        """
        if project_root is None:
            # Auto-detect project root (directory containing main.py)
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent

        self.project_root = Path(project_root)
        self.pid_dir = self.project_root
        
        # Initialize Slack integration for S1 breadcrumbs
        try:
            self.slack = EnhancedSlackIntegration()
        except Exception as e:
            logger.warning(f"Slack integration not available: {e}")
            self.slack = None

        # Register cleanup on exit
        atexit.register(self.cleanup_all_monitors)

    def _get_pid_file(self, symbol: str) -> Path:
        """Get PID file path for a symbol."""
        return self.pid_dir / f".monitor_{symbol.upper()}.pid"

    def _is_process_running(self, pid: int) -> bool:
        """Check if a process with given PID is running."""
        try:
            process = psutil.Process(pid)
            return process.is_running()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return False

    def _read_pid_file(self, symbol: str) -> Optional[int]:
        """Read PID from file for a symbol."""
        pid_file = self._get_pid_file(symbol)
        if not pid_file.exists():
            return None

        try:
            with open(pid_file, "r") as f:
                pid = int(f.read().strip())
            return pid
        except (ValueError, IOError) as e:
            logger.warning(f"Invalid PID file for {symbol}: {e}")
            # Remove corrupted PID file
            try:
                pid_file.unlink()
            except OSError:
                pass
            return None

    def _write_pid_file(self, symbol: str, pid: int) -> None:
        """Write PID to file for a symbol."""
        pid_file = self._get_pid_file(symbol)
        try:
            with open(pid_file, "w") as f:
                f.write(str(pid))
            logger.info(f"Created PID file for {symbol}: {pid_file}")
        except IOError as e:
            logger.error(f"Failed to write PID file for {symbol}: {e}")

    def _spawn_monitor(self, symbol: str) -> Optional[int]:
        """Spawn monitor_alpaca.py process for a symbol."""
        monitor_script = self.project_root / "monitor_alpaca.py"

        if not monitor_script.exists():
            logger.error(f"Monitor script not found: {monitor_script}")
            return None

        try:
            # Build command line
            cmd = [
                sys.executable,
                str(monitor_script),
                "--symbol",
                symbol.upper(),
                "--interval",
                "15",  # Default 15-second monitoring
            ]

            # Spawn process with detached behavior
            process = subprocess.Popen(
                cmd,
                cwd=str(self.project_root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,  # Detach from parent
            )

            logger.info(f"Spawned monitor for {symbol}: PID {process.pid}")
            return process.pid

        except Exception as e:
            logger.error(f"Failed to spawn monitor for {symbol}: {e}")
            return None

    def ensure_monitor_running(self, symbol: str) -> bool:
        """Ensure monitor is running for a symbol.

        Args:
            symbol: Trading symbol (e.g., "SPY", "QQQ", "IWM")

        Returns:
            True if monitor is running (existing or newly started), False otherwise
        """
        symbol = symbol.upper()
        logger.info(f"Ensuring monitor is running for {symbol}")

        # Check if PID file exists and process is running
        existing_pid = self._read_pid_file(symbol)
        if existing_pid and self._is_process_running(existing_pid):
            logger.info(f"Monitor already running for {symbol}: PID {existing_pid}")
            return True

        # Clean up stale PID file if exists
        if existing_pid:
            logger.info(f"Cleaning up stale PID file for {symbol}: PID {existing_pid}")
            try:
                self._get_pid_file(symbol).unlink()
            except OSError:
                pass

        # Spawn new monitor process
        new_pid = self._spawn_monitor(symbol)
        if new_pid:
            self._write_pid_file(symbol, new_pid)
            logger.info(f"Successfully started monitor for {symbol}: PID {new_pid}")
            
            # S1: Send monitor started breadcrumb
            if self.slack:
                try:
                    # Load config to get monitor interval
                    from .llm import load_config
                    config = load_config()
                    interval = config.get('MONITOR_INTERVAL', 15)
                    self.slack.send_info(f"🟢 Exit-monitor started for {symbol} ({interval}s interval)")
                except Exception as e:
                    logger.debug(f"Could not send monitor started breadcrumb: {e}")
            
            return True
        else:
            logger.error(f"Failed to start monitor for {symbol}")
            return False

    def stop_monitor(self, symbol: str) -> bool:
        """Stop monitor for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            True if monitor was stopped, False otherwise
        """
        symbol = symbol.upper()
        pid = self._read_pid_file(symbol)

        if not pid:
            logger.info(f"No monitor running for {symbol}")
            return True

        if not self._is_process_running(pid):
            logger.info(f"Monitor for {symbol} already stopped")
            try:
                self._get_pid_file(symbol).unlink()
            except OSError:
                pass
            return True

        try:
            process = psutil.Process(pid)
            process.terminate()

            # Wait for graceful shutdown
            try:
                process.wait(timeout=5)
            except psutil.TimeoutExpired:
                logger.warning(f"Force killing monitor for {symbol}: PID {pid}")
                process.kill()

            # Remove PID file
            try:
                self._get_pid_file(symbol).unlink()
            except OSError:
                pass

            logger.info(f"Stopped monitor for {symbol}: PID {pid}")
            
            # S1: Send monitor stopped breadcrumb
            if self.slack:
                try:
                    self.slack.send_info(f"🔴 Exit-monitor for {symbol} shut down")
                except Exception as e:
                    logger.debug(f"Could not send monitor stopped breadcrumb: {e}")
            
            return True

        except Exception as e:
            logger.error(f"Failed to stop monitor for {symbol}: {e}")
            return False

    def kill_all_monitors(self) -> int:
        """Kill all running monitor processes (S1: for graceful shutdown).

        Returns:
            Number of processes killed
        """
        stopped_count = 0
        logger.info("Killing all monitors...")

        # Find all PID files
        pid_files = list(self.pid_dir.glob(".monitor_*.pid"))
        for pid_file in pid_files:
            try:
                # Extract symbol from filename
                symbol = pid_file.stem.replace(".monitor_", "")
                if self.stop_monitor(symbol):
                    stopped_count += 1
            except Exception as e:
                logger.error(f"Error killing monitor {pid_file}: {e}")

        return stopped_count

    def cleanup_all_monitors(self) -> int:
        """Stop all running monitors and clean up PID files.
        
        Returns:
            Number of monitors stopped
        """
        stopped_count = 0
        logger.info("Cleaning up all monitors...")

        # Find all PID files
        pid_files = list(self.pid_dir.glob(".monitor_*.pid"))
        for pid_file in pid_files:
            try:
                # Extract symbol from filename
                symbol = pid_file.stem.replace(".monitor_", "")
                if self.stop_monitor(symbol):
                    stopped_count += 1
            except Exception as e:
                logger.error(f"Error cleaning up {pid_file}: {e}")
                # Force remove PID file
                try:
                    pid_file.unlink()
                except OSError:
                    pass

        logger.info(f"Cleaned up {stopped_count} monitors")
        
        # S1: Send bulk shutdown breadcrumb if any monitors were stopped
        if stopped_count > 0 and self.slack:
            try:
                self.slack.send_info(f"🔴 All exit-monitors shut down ({stopped_count} stopped)")
            except Exception as e:
                logger.debug(f"Could not send bulk shutdown breadcrumb: {e}")

        logger.info("Monitor cleanup complete")
        return stopped_count

    def list_running_monitors(self) -> dict:
        """List all running monitors.

        Returns:
            Dict mapping symbol to PID for running monitors
        """
        running = {}
        pid_files = list(self.pid_dir.glob(".monitor_*.pid"))

        for pid_file in pid_files:
            try:
                symbol = pid_file.stem.replace(".monitor_", "")
                pid = self._read_pid_file(symbol)

                if pid and self._is_process_running(pid):
                    running[symbol] = pid
                else:
                    # Clean up stale PID file
                    try:
                        pid_file.unlink()
                    except OSError:
                        pass
            except Exception as e:
                logger.error(f"Error checking {pid_file}: {e}")

        return running


# Global instance for easy access
_launcher = None


def get_monitor_launcher() -> MonitorLauncher:
    """Get global monitor launcher instance."""
    global _launcher
    if _launcher is None:
        _launcher = MonitorLauncher()
    return _launcher


def ensure_monitor_running(symbol: str) -> bool:
    """Convenience function to ensure monitor is running for a symbol."""
    return get_monitor_launcher().ensure_monitor_running(symbol)


def stop_monitor(symbol: str) -> bool:
    """Convenience function to stop monitor for a symbol."""
    return get_monitor_launcher().stop_monitor(symbol)


def cleanup_all_monitors() -> None:
    """Convenience function to clean up all monitors."""
    get_monitor_launcher().cleanup_all_monitors()


if __name__ == "__main__":
    # CLI interface for testing
    import argparse

    parser = argparse.ArgumentParser(description="Monitor launcher utility")
    parser.add_argument("action", choices=["start", "stop", "list", "cleanup"])
    parser.add_argument("--symbol", help="Symbol for start/stop actions")

    args = parser.parse_args()

    # Centralized logging
    from utils.logging_utils import setup_logging
    setup_logging(log_level="INFO", log_file="logs/monitor_launcher.log")
    launcher = get_monitor_launcher()

    if args.action == "start":
        if not args.symbol:
            print("--symbol required for start action")
            sys.exit(1)
        success = launcher.ensure_monitor_running(args.symbol)
        sys.exit(0 if success else 1)

    elif args.action == "stop":
        if not args.symbol:
            print("--symbol required for stop action")
            sys.exit(1)
        success = launcher.stop_monitor(args.symbol)
        sys.exit(0 if success else 1)

    elif args.action == "list":
        running = launcher.list_running_monitors()
        if running:
            print("Running monitors:")
            for symbol, pid in running.items():
                print(f"  {symbol}: PID {pid}")
        else:
            print("No monitors running")

    elif args.action == "cleanup":
        launcher.cleanup_all_monitors()
        print("Cleanup complete")
