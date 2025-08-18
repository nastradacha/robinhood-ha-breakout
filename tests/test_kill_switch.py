#!/usr/bin/env python3
"""
Unit and Integration Tests for Emergency Stop Mechanism (Kill Switch)

Tests cover:
- File-based kill switch activation/deactivation
- Programmatic API usage
- Thread safety and persistence
- Integration with main trading loop
- Slack command handling
- API endpoint security

Author: Robinhood HA Breakout System
Version: 1.0.0
"""

import unittest
import tempfile
import os
import json
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.kill_switch import KillSwitch, get_kill_switch, is_trading_halted, halt_trading, resume_trading


class TestKillSwitchCore(unittest.TestCase):
    """Test core kill switch functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.kill_switch = KillSwitch(project_root=self.temp_dir)
        
    def tearDown(self):
        """Clean up test fixtures."""
        # Ensure kill switch is deactivated
        if self.kill_switch.is_active():
            self.kill_switch.deactivate()
        
        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_initial_state(self):
        """Test kill switch initial state."""
        self.assertFalse(self.kill_switch.is_active())
        self.assertFalse(self.kill_switch.is_monitor_only())
        
        status = self.kill_switch.get_status()
        self.assertFalse(status['active'])
        self.assertEqual(status['reason'], '')
        self.assertIsNone(status['activated_at'])
        self.assertEqual(status['source'], '')
        self.assertFalse(status['monitor_only'])
        self.assertFalse(status['stop_file_exists'])
    
    def test_activation_deactivation(self):
        """Test basic activation and deactivation."""
        # Test activation
        success = self.kill_switch.activate("Test reason", "unit_test")
        self.assertTrue(success)
        self.assertTrue(self.kill_switch.is_active())
        
        status = self.kill_switch.get_status()
        self.assertTrue(status['active'])
        self.assertEqual(status['reason'], "Test reason")
        self.assertEqual(status['source'], "unit_test")
        self.assertIsNotNone(status['activated_at'])
        self.assertTrue(status['stop_file_exists'])
        
        # Test deactivation
        success = self.kill_switch.deactivate("unit_test")
        self.assertTrue(success)
        self.assertFalse(self.kill_switch.is_active())
        
        status = self.kill_switch.get_status()
        self.assertFalse(status['active'])
        self.assertEqual(status['reason'], '')
        self.assertFalse(status['stop_file_exists'])
    
    def test_double_activation(self):
        """Test that double activation is handled gracefully."""
        # First activation
        success1 = self.kill_switch.activate("First reason", "test")
        self.assertTrue(success1)
        
        # Second activation should return False
        success2 = self.kill_switch.activate("Second reason", "test")
        self.assertFalse(success2)
        
        # Should still be active with original reason
        status = self.kill_switch.get_status()
        self.assertTrue(status['active'])
        self.assertEqual(status['reason'], "First reason")
    
    def test_deactivation_when_not_active(self):
        """Test deactivation when not active."""
        success = self.kill_switch.deactivate("test")
        self.assertFalse(success)
    
    def test_monitor_only_mode(self):
        """Test monitor-only mode functionality."""
        success = self.kill_switch.activate("Monitor test", "test", monitor_only=True)
        self.assertTrue(success)
        self.assertTrue(self.kill_switch.is_active())
        self.assertTrue(self.kill_switch.is_monitor_only())
        
        status = self.kill_switch.get_status()
        self.assertTrue(status['monitor_only'])
    
    def test_file_persistence(self):
        """Test file-based persistence."""
        # Activate and check file creation
        self.kill_switch.activate("Persistence test", "test")
        self.assertTrue(self.kill_switch.stop_file.exists())
        
        # Read file content
        content = json.loads(self.kill_switch.stop_file.read_text())
        self.assertEqual(content['reason'], "Persistence test")
        self.assertEqual(content['source'], "test")
        self.assertIsNotNone(content['activated_at'])
        
        # Deactivate and check file removal
        self.kill_switch.deactivate("test")
        self.assertFalse(self.kill_switch.stop_file.exists())
    
    def test_load_from_disk(self):
        """Test loading state from disk on initialization."""
        # Create stop file manually
        stop_data = {
            "reason": "Loaded from disk",
            "activated_at": "2025-08-18T12:00:00",
            "source": "file",
            "monitor_only": False
        }
        stop_file = Path(self.temp_dir) / "EMERGENCY_STOP.txt"
        stop_file.write_text(json.dumps(stop_data))
        
        # Create new kill switch instance
        new_kill_switch = KillSwitch(project_root=self.temp_dir)
        
        # Should be active with loaded data
        self.assertTrue(new_kill_switch.is_active())
        status = new_kill_switch.get_status()
        self.assertEqual(status['reason'], "Loaded from disk")
        self.assertEqual(status['source'], "file")
    
    def test_file_trigger_detection(self):
        """Test external file trigger detection."""
        # Create stop file externally
        stop_file = Path(self.temp_dir) / "EMERGENCY_STOP.txt"
        stop_file.write_text("External trigger test")
        
        # Check file trigger
        triggered = self.kill_switch.check_file_trigger()
        self.assertTrue(triggered)
        self.assertTrue(self.kill_switch.is_active())
        
        status = self.kill_switch.get_status()
        self.assertEqual(status['reason'], "External trigger test")
        self.assertEqual(status['source'], "file")
    
    def test_thread_safety(self):
        """Test thread safety of kill switch operations."""
        results = []
        
        def activate_worker():
            success = self.kill_switch.activate(f"Thread {threading.current_thread().ident}", "thread_test")
            results.append(success)
        
        # Start multiple threads trying to activate
        threads = []
        for i in range(5):
            thread = threading.Thread(target=activate_worker)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # Only one should succeed
        successful_activations = sum(results)
        self.assertEqual(successful_activations, 1)
        self.assertTrue(self.kill_switch.is_active())


class TestKillSwitchIntegration(unittest.TestCase):
    """Test kill switch integration with trading system."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        """Clean up test fixtures."""
        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('utils.alpaca_options.logger')
    def test_alpaca_order_blocking(self, mock_logger):
        """Test that Alpaca orders are blocked when kill switch is active."""
        from utils.alpaca_options import AlpacaOptionsTrader
        
        # Mock the Alpaca client
        mock_client = Mock()
        trader = AlpacaOptionsTrader("test_key", "test_secret", paper=True)
        trader.client = mock_client
        
        # Activate kill switch
        kill_switch = KillSwitch(project_root=self.temp_dir)
        kill_switch.activate("Test blocking", "test")
        
        # Mock the global kill switch
        with patch('utils.kill_switch._global_kill_switch', kill_switch):
            # Try to place order - should raise RuntimeError
            with self.assertRaises(RuntimeError) as context:
                trader.place_market_order("TEST_CONTRACT", 1, "BUY")
            
            self.assertIn("Emergency stop active", str(context.exception))
            mock_logger.error.assert_called_with("[KILL-SWITCH] Emergency stop active - blocking order execution")
    
    def test_global_functions(self):
        """Test global convenience functions."""
        # Test is_trading_halted
        self.assertFalse(is_trading_halted())
        
        # Test halt_trading
        success = halt_trading("Global test", "test")
        self.assertTrue(success)
        self.assertTrue(is_trading_halted())
        
        # Test resume_trading
        success = resume_trading("test")
        self.assertTrue(success)
        self.assertFalse(is_trading_halted())


class TestSlackWebhookIntegration(unittest.TestCase):
    """Test Slack webhook integration with kill switch."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch.dict(os.environ, {'SLACK_SIGNING_SECRET': 'test_secret'})
    def test_slack_command_handlers(self):
        """Test Slack slash command handlers."""
        from utils.slack_webhook import SlackWebhookServer
        
        server = SlackWebhookServer(port=3001)
        
        # Mock kill switch
        kill_switch = KillSwitch(project_root=self.temp_dir)
        
        with patch('utils.kill_switch.get_kill_switch', return_value=kill_switch):
            # Test stop command
            response = server._handle_stop_trading("Test emergency", "test_user")
            response_data = response.get_json()
            
            self.assertEqual(response_data['response_type'], 'in_channel')
            self.assertIn('EMERGENCY STOP ACTIVATED', response_data['text'])
            self.assertTrue(kill_switch.is_active())
            
            # Test resume command
            response = server._handle_resume_trading("test_user")
            response_data = response.get_json()
            
            self.assertEqual(response_data['response_type'], 'in_channel')
            self.assertIn('TRADING RESUMED', response_data['text'])
            self.assertFalse(kill_switch.is_active())
    
    @patch.dict(os.environ, {'CONTROL_API_TOKEN': 'test_token_123'})
    def test_api_endpoints(self):
        """Test API endpoint functionality."""
        from utils.slack_webhook import SlackWebhookServer
        from flask import Flask
        
        server = SlackWebhookServer(port=3002)
        kill_switch = KillSwitch(project_root=self.temp_dir)
        
        with patch('utils.kill_switch.get_kill_switch', return_value=kill_switch):
            with server.app.test_client() as client:
                # Test unauthorized access
                response = client.post('/api/stop')
                self.assertEqual(response.status_code, 401)
                
                # Test authorized stop
                headers = {'Authorization': 'Bearer test_token_123'}
                response = client.post('/api/stop', 
                                     json={'reason': 'API test'}, 
                                     headers=headers)
                self.assertEqual(response.status_code, 200)
                data = response.get_json()
                self.assertTrue(data['success'])
                self.assertTrue(kill_switch.is_active())
                
                # Test status endpoint
                response = client.get('/api/status', headers=headers)
                self.assertEqual(response.status_code, 200)
                data = response.get_json()
                self.assertTrue(data['success'])
                self.assertTrue(data['kill_switch']['active'])
                
                # Test resume
                response = client.post('/api/resume', headers=headers)
                self.assertEqual(response.status_code, 200)
                data = response.get_json()
                self.assertTrue(data['success'])
                self.assertFalse(kill_switch.is_active())


class TestTradeConfirmationIntegration(unittest.TestCase):
    """Test trade confirmation emergency stop integration."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_emergency_message_parsing(self):
        """Test emergency stop message parsing in trade confirmation."""
        from utils.trade_confirmation import TradeConfirmationManager
        
        # Mock dependencies
        mock_portfolio = Mock()
        mock_bankroll = Mock()
        mock_slack = Mock()
        
        manager = TradeConfirmationManager(mock_portfolio, mock_bankroll, mock_slack)
        kill_switch = KillSwitch(project_root=self.temp_dir)
        
        with patch('utils.kill_switch.get_kill_switch', return_value=kill_switch):
            # Test emergency stop message
            result = manager.process_slack_message("emergency stop now")
            self.assertTrue(result)
            self.assertTrue(kill_switch.is_active())
            
            # Test resume message
            result = manager.process_slack_message("resume trading")
            self.assertTrue(result)
            self.assertFalse(kill_switch.is_active())


if __name__ == '__main__':
    # Configure logging for tests
    import logging
    logging.basicConfig(level=logging.WARNING)
    
    # Run tests
    unittest.main(verbosity=2)
