#!/usr/bin/env python3
"""
Unit tests for monitor launcher functionality.

Tests PID file management, process spawning, and restart logic.
"""

import pytest
import tempfile
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import psutil

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.monitor_launcher import MonitorLauncher, ensure_monitor_running


class TestMonitorLauncher:
    """Test monitor launcher functionality."""
    
    def test_pid_file_operations(self):
        """Test PID file read/write operations."""
        with tempfile.TemporaryDirectory() as temp_dir:
            launcher = MonitorLauncher(project_root=temp_dir)
            
            # Test writing PID file
            launcher._write_pid_file("SPY", 12345)
            pid_file = Path(temp_dir) / ".monitor_SPY.pid"
            assert pid_file.exists()
            
            # Test reading PID file
            pid = launcher._read_pid_file("SPY")
            assert pid == 12345
            
            # Test non-existent PID file
            pid = launcher._read_pid_file("QQQ")
            assert pid is None
    
    def test_corrupted_pid_file_cleanup(self):
        """Test cleanup of corrupted PID files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            launcher = MonitorLauncher(project_root=temp_dir)
            
            # Create corrupted PID file
            pid_file = Path(temp_dir) / ".monitor_SPY.pid"
            with open(pid_file, 'w') as f:
                f.write("invalid_pid_data")
            
            # Should return None and clean up file
            pid = launcher._read_pid_file("SPY")
            assert pid is None
            assert not pid_file.exists()
    
    @patch('psutil.Process')
    def test_process_running_check(self, mock_process_class):
        """Test process running detection."""
        with tempfile.TemporaryDirectory() as temp_dir:
            launcher = MonitorLauncher(project_root=temp_dir)
            
            # Test running process
            mock_process = Mock()
            mock_process.is_running.return_value = True
            mock_process_class.return_value = mock_process
            
            assert launcher._is_process_running(12345) is True
            mock_process_class.assert_called_with(12345)
            
            # Test non-existent process
            mock_process_class.side_effect = psutil.NoSuchProcess(12345)
            assert launcher._is_process_running(12345) is False
    
    @patch('subprocess.Popen')
    def test_spawn_monitor_success(self, mock_popen):
        """Test successful monitor spawning."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create fake monitor script
            monitor_script = Path(temp_dir) / "monitor_alpaca.py"
            monitor_script.write_text("# fake monitor script")
            
            launcher = MonitorLauncher(project_root=temp_dir)
            
            # Mock successful process spawn
            mock_process = Mock()
            mock_process.pid = 54321
            mock_popen.return_value = mock_process
            
            pid = launcher._spawn_monitor("SPY")
            assert pid == 54321
            
            # Verify command line
            mock_popen.assert_called_once()
            call_args = mock_popen.call_args
            cmd = call_args[0][0]
            assert str(monitor_script) in cmd
            assert "--symbol" in cmd
            assert "SPY" in cmd
    
    @patch('subprocess.Popen')
    def test_spawn_monitor_missing_script(self, mock_popen):
        """Test monitor spawning with missing script."""
        with tempfile.TemporaryDirectory() as temp_dir:
            launcher = MonitorLauncher(project_root=temp_dir)
            
            # No monitor script exists
            pid = launcher._spawn_monitor("SPY")
            assert pid is None
            mock_popen.assert_not_called()
    
    @patch('subprocess.Popen')
    def test_spawn_monitor_exception(self, mock_popen):
        """Test monitor spawning with subprocess exception."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create fake monitor script
            monitor_script = Path(temp_dir) / "monitor_alpaca.py"
            monitor_script.write_text("# fake monitor script")
            
            launcher = MonitorLauncher(project_root=temp_dir)
            
            # Mock subprocess exception
            mock_popen.side_effect = OSError("Permission denied")
            
            pid = launcher._spawn_monitor("SPY")
            assert pid is None
    
    @patch('utils.monitor_launcher.MonitorLauncher._is_process_running')
    @patch('utils.monitor_launcher.MonitorLauncher._spawn_monitor')
    def test_ensure_monitor_running_new(self, mock_spawn, mock_is_running):
        """Test ensuring monitor runs when none exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            launcher = MonitorLauncher(project_root=temp_dir)
            
            # No existing PID file
            mock_spawn.return_value = 98765
            
            result = launcher.ensure_monitor_running("SPY")
            assert result is True
            
            mock_spawn.assert_called_once_with("SPY")
            
            # Verify PID file was created
            pid_file = Path(temp_dir) / ".monitor_SPY.pid"
            assert pid_file.exists()
            with open(pid_file, 'r') as f:
                assert f.read().strip() == "98765"
    
    @patch('utils.monitor_launcher.MonitorLauncher._is_process_running')
    def test_ensure_monitor_running_existing(self, mock_is_running):
        """Test ensuring monitor runs when already running."""
        with tempfile.TemporaryDirectory() as temp_dir:
            launcher = MonitorLauncher(project_root=temp_dir)
            
            # Create existing PID file
            launcher._write_pid_file("SPY", 11111)
            mock_is_running.return_value = True
            
            result = launcher.ensure_monitor_running("SPY")
            assert result is True
            
            mock_is_running.assert_called_once_with(11111)
    
    @patch('utils.monitor_launcher.MonitorLauncher._is_process_running')
    @patch('utils.monitor_launcher.MonitorLauncher._spawn_monitor')
    def test_ensure_monitor_running_stale_pid(self, mock_spawn, mock_is_running):
        """Test ensuring monitor runs when PID is stale."""
        with tempfile.TemporaryDirectory() as temp_dir:
            launcher = MonitorLauncher(project_root=temp_dir)
            
            # Create stale PID file
            launcher._write_pid_file("SPY", 22222)
            mock_is_running.return_value = False  # Process not running
            mock_spawn.return_value = 33333
            
            result = launcher.ensure_monitor_running("SPY")
            assert result is True
            
            mock_is_running.assert_called_once_with(22222)
            mock_spawn.assert_called_once_with("SPY")
            
            # Verify new PID file
            with open(Path(temp_dir) / ".monitor_SPY.pid", 'r') as f:
                assert f.read().strip() == "33333"
    
    @patch('psutil.Process')
    def test_stop_monitor_success(self, mock_process_class):
        """Test successful monitor stopping."""
        with tempfile.TemporaryDirectory() as temp_dir:
            launcher = MonitorLauncher(project_root=temp_dir)
            
            # Create PID file
            launcher._write_pid_file("SPY", 44444)
            
            # Mock process termination
            mock_process = Mock()
            mock_process.is_running.return_value = True
            mock_process.wait.return_value = None
            mock_process_class.return_value = mock_process
            
            result = launcher.stop_monitor("SPY")
            assert result is True
            
            mock_process.terminate.assert_called_once()
            mock_process.wait.assert_called_once_with(timeout=5)
            
            # Verify PID file was removed
            pid_file = Path(temp_dir) / ".monitor_SPY.pid"
            assert not pid_file.exists()
    
    @patch('psutil.Process')
    def test_stop_monitor_force_kill(self, mock_process_class):
        """Test force killing unresponsive monitor."""
        with tempfile.TemporaryDirectory() as temp_dir:
            launcher = MonitorLauncher(project_root=temp_dir)
            
            # Create PID file
            launcher._write_pid_file("SPY", 55555)
            
            # Mock process that doesn't terminate gracefully
            mock_process = Mock()
            mock_process.is_running.return_value = True
            mock_process.wait.side_effect = psutil.TimeoutExpired(55555, 5)
            mock_process_class.return_value = mock_process
            
            result = launcher.stop_monitor("SPY")
            assert result is True
            
            mock_process.terminate.assert_called_once()
            mock_process.kill.assert_called_once()
    
    def test_cleanup_all_monitors(self):
        """Test cleanup of all monitor processes."""
        with tempfile.TemporaryDirectory() as temp_dir:
            launcher = MonitorLauncher(project_root=temp_dir)
            
            # Create multiple PID files
            launcher._write_pid_file("SPY", 11111)
            launcher._write_pid_file("QQQ", 22222)
            launcher._write_pid_file("IWM", 33333)
            
            with patch.object(launcher, 'stop_monitor') as mock_stop:
                mock_stop.return_value = True
                launcher.cleanup_all_monitors()
                
                # Should call stop_monitor for each symbol
                assert mock_stop.call_count == 3
                mock_stop.assert_any_call("SPY")
                mock_stop.assert_any_call("QQQ")
                mock_stop.assert_any_call("IWM")
    
    def test_list_running_monitors(self):
        """Test listing running monitors."""
        with tempfile.TemporaryDirectory() as temp_dir:
            launcher = MonitorLauncher(project_root=temp_dir)
            
            # Create PID files
            launcher._write_pid_file("SPY", 11111)
            launcher._write_pid_file("QQQ", 22222)
            
            with patch.object(launcher, '_is_process_running') as mock_is_running:
                # SPY running, QQQ not running
                mock_is_running.side_effect = lambda pid: pid == 11111
                
                running = launcher.list_running_monitors()
                assert running == {"SPY": 11111}
                
                # QQQ PID file should be cleaned up
                assert not (Path(temp_dir) / ".monitor_QQQ.pid").exists()


class TestConvenienceFunctions:
    """Test convenience functions."""
    
    @patch('utils.monitor_launcher.get_monitor_launcher')
    def test_ensure_monitor_running_convenience(self, mock_get_launcher):
        """Test convenience function for ensure_monitor_running."""
        mock_launcher = Mock()
        mock_launcher.ensure_monitor_running.return_value = True
        mock_get_launcher.return_value = mock_launcher
        
        result = ensure_monitor_running("SPY")
        assert result is True
        mock_launcher.ensure_monitor_running.assert_called_once_with("SPY")


if __name__ == '__main__':
    pytest.main([__file__])
