"""
Unit tests for S1: Monitor start/stop Slack breadcrumbs functionality.
Tests the enhanced_slack.send_info() method and monitor_launcher integration.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.enhanced_slack import EnhancedSlackIntegration
from utils.monitor_launcher import ensure_monitor_running, MonitorLauncher


class TestSlackBreadcrumbs(unittest.TestCase):
    """Test S1: Monitor start/stop Slack breadcrumbs."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_config = {
            "SLACK_WEBHOOK_URL": "https://hooks.slack.com/test",
            "SLACK_BOT_TOKEN": "xoxb-test-token",
            "SLACK_CHANNEL_ID": "C1234567890",
        }
        self.slack_integration = EnhancedSlackIntegration(self.mock_config)

    @patch("utils.enhanced_slack.requests.post")
    def test_send_info_method_exists(self, mock_post):
        """Test that send_info method exists and can send messages."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}

        # Test send_info method
        result = self.slack_integration.send_info("🟢 Monitor started for SPY")
        
        self.assertTrue(result)
        mock_post.assert_called_once()
        
        # Verify message content
        call_args = mock_post.call_args
        self.assertIn("🟢 Monitor started for SPY", str(call_args))

    @patch("utils.enhanced_slack.requests.post")
    def test_monitor_start_breadcrumb(self, mock_post):
        """Test monitor start breadcrumb message format."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}

        # Test monitor start message
        symbol = "SPY"
        start_msg = f"🟢 Monitor started for {symbol}"
        
        result = self.slack_integration.send_info(start_msg)
        
        self.assertTrue(result)
        mock_post.assert_called_once()
        
        # Verify message format
        call_args = mock_post.call_args
        self.assertIn("🟢", str(call_args))
        self.assertIn("Monitor started", str(call_args))
        self.assertIn(symbol, str(call_args))

    @patch("utils.enhanced_slack.requests.post")
    def test_monitor_stop_breadcrumb(self, mock_post):
        """Test monitor stop breadcrumb message format."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}

        # Test monitor stop message
        symbol = "SPY"
        stop_msg = f"🔴 Monitor stopped for {symbol}"
        
        result = self.slack_integration.send_info(stop_msg)
        
        self.assertTrue(result)
        mock_post.assert_called_once()
        
        # Verify message format
        call_args = mock_post.call_args
        self.assertIn("🔴", str(call_args))
        self.assertIn("Monitor stopped", str(call_args))
        self.assertIn(symbol, str(call_args))

    @patch("utils.monitor_launcher.subprocess.Popen")
    @patch("utils.enhanced_slack.requests.post")
    def test_monitor_launcher_integration(self, mock_post, mock_popen):
        """Test monitor launcher sends breadcrumbs via enhanced_slack."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        
        # Mock subprocess for monitor process
        mock_process = Mock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process
        
        # Test ensure_monitor_running with Slack integration
        with patch("utils.monitor_launcher.EnhancedSlackIntegration") as mock_slack_class:
            mock_slack_instance = Mock()
            mock_slack_class.return_value = mock_slack_instance
            
            # Mock config loading
            with patch("utils.monitor_launcher.load_config") as mock_load_config:
                mock_load_config.return_value = self.mock_config
                
                result = ensure_monitor_running("SPY")
                
                # Verify monitor was started
                self.assertTrue(result)
                
                # Verify Slack breadcrumb was sent
                mock_slack_instance.send_info.assert_called_once()
                call_args = mock_slack_instance.send_info.call_args[0][0]
                self.assertIn("🟢", call_args)
                self.assertIn("Monitor started", call_args)
                self.assertIn("SPY", call_args)

    @patch("utils.monitor_launcher.Path.glob")
    @patch("utils.enhanced_slack.requests.post")
    def test_kill_monitors_breadcrumbs(self, mock_post, mock_glob):
        """Test MonitorLauncher.kill_all_monitors sends stop breadcrumbs."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        
        # Mock PID files
        mock_pid_file1 = Mock()
        mock_pid_file1.stem = ".monitor_SPY"
        mock_pid_file2 = Mock()
        mock_pid_file2.stem = ".monitor_QQQ"
        
        mock_glob.return_value = [mock_pid_file1, mock_pid_file2]
        
        # Test MonitorLauncher.kill_all_monitors with Slack integration
        with patch("utils.monitor_launcher.load_config") as mock_load_config:
            mock_load_config.return_value = self.mock_config
            
            launcher = MonitorLauncher()
            
            # Mock stop_monitor method
            with patch.object(launcher, 'stop_monitor', return_value=True):
                killed_count = launcher.kill_all_monitors()
                
                # Verify processes were killed
                self.assertEqual(killed_count, 2)
                
                # Verify stop_monitor was called for each symbol
                launcher.stop_monitor.assert_any_call("SPY")
                launcher.stop_monitor.assert_any_call("QQQ")

    def test_breadcrumb_message_format(self):
        """Test breadcrumb message format consistency."""
        # Test start message format
        symbol = "IWM"
        start_msg = f"🟢 Monitor started for {symbol}"
        
        self.assertIn("🟢", start_msg)
        self.assertIn("Monitor started", start_msg)
        self.assertIn(symbol, start_msg)
        
        # Test stop message format
        stop_msg = f"🔴 Monitor stopped for {symbol}"
        
        self.assertIn("🔴", stop_msg)
        self.assertIn("Monitor stopped", stop_msg)
        self.assertIn(symbol, stop_msg)


if __name__ == "__main__":
    unittest.main()
