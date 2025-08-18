#!/usr/bin/env python3
"""
Tests for Automated Recovery System

Comprehensive test suite for the recovery system including:
- ExponentialBackoff retry logic
- RecoveryManager functionality
- Network connectivity monitoring
- Process health monitoring
- Integration with trading components

Author: Robinhood HA Breakout System
Version: 1.0.0
License: MIT
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import shutil
import json
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path

# Import recovery system components
from utils.recovery import (
    ExponentialBackoff,
    RecoveryManager,
    RecoveryStatus,
    RecoveryAttempt,
    get_recovery_manager,
    retry_with_recovery
)


class TestExponentialBackoff(unittest.TestCase):
    """Test exponential backoff logic."""
    
    def test_initial_delay_zero(self):
        """Test that first attempt has zero delay."""
        backoff = ExponentialBackoff(initial_delay=2.0)
        self.assertEqual(backoff.get_delay(), 0.0)
        self.assertTrue(backoff.should_retry())
    
    def test_exponential_progression(self):
        """Test exponential delay progression."""
        backoff = ExponentialBackoff(initial_delay=1.0, backoff_factor=2.0)
        
        # First attempt - no delay
        self.assertEqual(backoff.get_delay(), 0.0)
        backoff.next_attempt()
        
        # Second attempt - initial delay
        self.assertEqual(backoff.get_delay(), 1.0)
        backoff.next_attempt()
        
        # Third attempt - doubled delay
        self.assertEqual(backoff.get_delay(), 2.0)
        backoff.next_attempt()
        
        # Fourth attempt - doubled again
        self.assertEqual(backoff.get_delay(), 4.0)
    
    def test_max_delay_cap(self):
        """Test that delay is capped at max_delay."""
        backoff = ExponentialBackoff(initial_delay=10.0, max_delay=15.0, backoff_factor=2.0)
        
        backoff.next_attempt()  # Attempt 1
        backoff.next_attempt()  # Attempt 2
        
        # Should be capped at max_delay
        self.assertEqual(backoff.get_delay(), 15.0)
    
    def test_max_attempts(self):
        """Test max attempts limit."""
        backoff = ExponentialBackoff(max_attempts=2)
        
        self.assertTrue(backoff.should_retry())  # Attempt 0
        backoff.next_attempt()
        
        self.assertTrue(backoff.should_retry())  # Attempt 1
        backoff.next_attempt()
        
        self.assertFalse(backoff.should_retry())  # Attempt 2 - exceeded
    
    def test_reset(self):
        """Test backoff reset functionality."""
        backoff = ExponentialBackoff()
        
        backoff.next_attempt()
        backoff.next_attempt()
        self.assertEqual(backoff.current_attempt, 2)
        
        backoff.reset()
        self.assertEqual(backoff.current_attempt, 0)
        self.assertTrue(backoff.should_retry())


class TestRecoveryManager(unittest.TestCase):
    """Test recovery manager functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.recovery_manager = RecoveryManager(self.temp_dir)
    
    def tearDown(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_recovery_manager_initialization(self):
        """Test recovery manager initialization."""
        self.assertIsInstance(self.recovery_manager, RecoveryManager)
        self.assertEqual(self.recovery_manager.project_root, Path(self.temp_dir))
        self.assertTrue(self.recovery_manager.recovery_log_file.parent.exists())
    
    def test_log_recovery_attempt(self):
        """Test recovery attempt logging."""
        attempt = RecoveryAttempt(
            timestamp=datetime.now(),
            failure_type="api_timeout",
            component="alpaca_api",
            attempt_number=1,
            status=RecoveryStatus.SUCCESS,
            details="Test recovery attempt",
            duration_seconds=1.5
        )
        
        self.recovery_manager.log_recovery_attempt(attempt)
        
        # Check in-memory storage
        self.assertEqual(len(self.recovery_manager.recovery_history), 1)
        self.assertEqual(self.recovery_manager.recovery_history[0], attempt)
        
        # Check file logging
        self.assertTrue(self.recovery_manager.recovery_log_file.exists())
        with open(self.recovery_manager.recovery_log_file) as f:
            log_line = f.read().strip()
            log_data = json.loads(log_line)
            self.assertEqual(log_data["failure_type"], "api_timeout")
            self.assertEqual(log_data["component"], "alpaca_api")
            self.assertEqual(log_data["status"], "success")
    
    def test_successful_retry_with_backoff(self):
        """Test successful operation with retry."""
        call_count = 0
        
        def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Temporary failure")
            return "success"
        
        result = self.recovery_manager.retry_with_backoff(
            operation=flaky_operation,
            operation_name="test operation",
            component="test_component"
        )
        
        self.assertEqual(result, "success")
        self.assertEqual(call_count, 2)
        self.assertEqual(len(self.recovery_manager.recovery_history), 2)  # 1 failed + 1 success
    
    def test_escalation_after_max_attempts(self):
        """Test escalation after maximum attempts."""
        def always_failing_operation():
            raise Exception("Persistent failure")
        
        with patch.object(self.recovery_manager, '_send_escalation_alert') as mock_alert:
            with self.assertRaises(Exception):
                self.recovery_manager.retry_with_backoff(
                    operation=always_failing_operation,
                    operation_name="failing operation",
                    component="test_component"
                )
            
            # Should have called escalation alert
            mock_alert.assert_called_once()
            
            # Should have logged escalation
            escalated_attempts = [a for a in self.recovery_manager.recovery_history 
                                if a.status == RecoveryStatus.ESCALATED]
            self.assertEqual(len(escalated_attempts), 1)
    
    @patch('requests.get')
    def test_network_connectivity_success(self, mock_get):
        """Test successful network connectivity check."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        result = self.recovery_manager.check_network_connectivity()
        self.assertTrue(result)
    
    @patch('requests.get')
    def test_network_connectivity_failure(self, mock_get):
        """Test network connectivity failure."""
        mock_get.side_effect = Exception("Network error")
        
        result = self.recovery_manager.check_network_connectivity()
        self.assertFalse(result)
    
    @patch('subprocess.Popen')
    def test_restart_monitoring_process_success(self, mock_popen):
        """Test successful process restart."""
        mock_process = Mock()
        mock_process.poll.return_value = None  # Process still running
        mock_process.pid = 12345
        mock_popen.return_value = mock_process
        
        result = self.recovery_manager.restart_monitoring_process(
            "test_monitor", ["python", "monitor.py"]
        )
        self.assertTrue(result)
    
    @patch('subprocess.Popen')
    def test_restart_monitoring_process_failure(self, mock_popen):
        """Test failed process restart."""
        mock_process = Mock()
        mock_process.poll.return_value = 1  # Process exited with error
        mock_process.returncode = 1
        mock_process.communicate.return_value = (b"", b"Process failed")
        mock_popen.return_value = mock_process
        
        with patch.object(self.recovery_manager, '_send_escalation_alert'):
            result = self.recovery_manager.restart_monitoring_process(
                "test_monitor", ["python", "monitor.py"]
            )
            self.assertFalse(result)
    
    @patch('psutil.Process')
    def test_monitor_process_health_success(self, mock_process_class):
        """Test successful process health monitoring."""
        mock_process = Mock()
        mock_process.is_running.return_value = True
        mock_process.cpu_percent.return_value = 25.0
        mock_process.memory_info.return_value = Mock(rss=100 * 1024 * 1024)  # 100MB
        mock_process_class.return_value = mock_process
        
        result = self.recovery_manager.monitor_process_health("test_process", 12345)
        self.assertTrue(result)
    
    @patch('psutil.Process')
    def test_monitor_process_health_not_running(self, mock_process_class):
        """Test process health when process not running."""
        mock_process = Mock()
        mock_process.is_running.return_value = False
        mock_process_class.return_value = mock_process
        
        result = self.recovery_manager.monitor_process_health("test_process", 12345)
        self.assertFalse(result)
    
    def test_get_recovery_stats_empty(self):
        """Test recovery stats with no history."""
        stats = self.recovery_manager.get_recovery_stats()
        self.assertEqual(stats["total_attempts"], 0)
    
    def test_get_recovery_stats_with_history(self):
        """Test recovery stats with history."""
        # Add some test attempts
        attempts = [
            RecoveryAttempt(
                timestamp=datetime.now(),
                failure_type="api_timeout",
                component="alpaca_api",
                attempt_number=1,
                status=RecoveryStatus.SUCCESS,
                details="Success"
            ),
            RecoveryAttempt(
                timestamp=datetime.now(),
                failure_type="network_error",
                component="slack_api",
                attempt_number=1,
                status=RecoveryStatus.FAILED,
                details="Failed"
            ),
            RecoveryAttempt(
                timestamp=datetime.now(),
                failure_type="api_timeout",
                component="alpaca_api",
                attempt_number=2,
                status=RecoveryStatus.ESCALATED,
                details="Escalated"
            )
        ]
        
        for attempt in attempts:
            self.recovery_manager.log_recovery_attempt(attempt)
        
        stats = self.recovery_manager.get_recovery_stats()
        
        self.assertEqual(stats["total_attempts"], 3)
        self.assertEqual(stats["successful"], 1)
        self.assertEqual(stats["failed"], 1)
        self.assertEqual(stats["escalated"], 1)
        self.assertAlmostEqual(stats["success_rate"], 1/3, places=2)
        self.assertIn("alpaca_api", stats["components"])
        self.assertIn("slack_api", stats["components"])


class TestRecoveryIntegration(unittest.TestCase):
    """Test recovery system integration with trading components."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_global_recovery_manager(self):
        """Test global recovery manager singleton."""
        manager1 = get_recovery_manager(self.temp_dir)
        manager2 = get_recovery_manager()
        
        # Should return same instance
        self.assertIs(manager1, manager2)
    
    def test_retry_with_recovery_convenience_function(self):
        """Test convenience function for retry with recovery."""
        call_count = 0
        
        def test_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Temporary failure")
            return "success"
        
        result = retry_with_recovery(
            operation=test_operation,
            operation_name="test operation",
            component="test_component"
        )
        
        self.assertEqual(result, "success")
        self.assertEqual(call_count, 2)
    
    @patch('utils.recovery.RecoveryManager._send_escalation_alert')
    def test_escalation_alert_integration(self, mock_alert):
        """Test escalation alert integration."""
        def always_failing():
            raise Exception("Persistent failure")
        
        with self.assertRaises(Exception):
            retry_with_recovery(
                operation=always_failing,
                operation_name="failing operation",
                component="test_component"
            )
        
        # Should have called escalation alert
        mock_alert.assert_called_once()
        args = mock_alert.call_args[0]
        self.assertEqual(args[0], "test_component")  # component
        self.assertEqual(args[1], "failing operation")  # operation
        self.assertIsInstance(args[2], Exception)  # exception
    
    def test_thread_safety(self):
        """Test thread safety of recovery manager."""
        manager = RecoveryManager(self.temp_dir)
        results = []
        
        def concurrent_operation(thread_id):
            try:
                result = manager.retry_with_backoff(
                    operation=lambda: f"success_{thread_id}",
                    operation_name=f"thread_{thread_id}_operation",
                    component="test_component"
                )
                results.append(result)
            except Exception as e:
                results.append(f"error_{thread_id}")
        
        # Run multiple threads concurrently
        threads = []
        for i in range(5):
            thread = threading.Thread(target=concurrent_operation, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # All operations should succeed
        self.assertEqual(len(results), 5)
        for i, result in enumerate(results):
            self.assertEqual(result, f"success_{i}")
        
        # Should have 5 successful recovery attempts logged
        successful_attempts = [a for a in manager.recovery_history 
                             if a.status == RecoveryStatus.SUCCESS]
        self.assertEqual(len(successful_attempts), 5)


class TestRecoveryWithMockedComponents(unittest.TestCase):
    """Test recovery integration with mocked trading components."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('utils.alpaca_options.AlpacaOptionsTrader')
    def test_alpaca_api_recovery(self, mock_trader_class):
        """Test Alpaca API call recovery."""
        # Mock trader instance
        mock_trader = Mock()
        mock_trader_class.return_value = mock_trader
        
        # Mock client that fails first time, succeeds second time
        call_count = 0
        def mock_get_clock():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("API timeout")
            return Mock(is_open=True, timestamp=datetime.now())
        
        mock_trader.client.get_clock = mock_get_clock
        
        # Import and test the actual method
        from utils.alpaca_options import AlpacaOptionsTrader
        trader = AlpacaOptionsTrader("test_key", "test_secret")
        trader.client = mock_trader.client
        
        # Should succeed after retry
        result = trader.is_market_open_and_valid_time()
        self.assertTrue(result[0])  # Should be valid
        self.assertEqual(call_count, 2)  # Should have retried once
    
    @patch('utils.enhanced_slack.EnhancedSlackIntegration')
    def test_slack_api_recovery(self, mock_slack_class):
        """Test Slack API call recovery."""
        # Mock Slack integration
        mock_slack = Mock()
        mock_slack_class.return_value = mock_slack
        mock_slack.enabled = True
        mock_slack.charts_enabled = True
        
        # Mock chart sender that fails first time, succeeds second time
        call_count = 0
        def mock_send_chart(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Slack API error")
            return True
        
        mock_slack.enhanced_chart_sender.send_breakout_chart_to_slack = mock_send_chart
        
        # Test should succeed after retry
        from utils.enhanced_slack import EnhancedSlackIntegration
        slack = EnhancedSlackIntegration()
        slack.enhanced_chart_sender = mock_slack.enhanced_chart_sender
        slack.enabled = True
        slack.charts_enabled = True
        
        # Mock the internal methods to avoid complex setup
        slack._send_enhanced_text_alert = Mock()
        slack._send_basic_fallback_alert = Mock()
        
        # Should not raise exception
        slack.send_breakout_alert_with_chart(
            symbol="SPY",
            decision="CALL", 
            analysis={},
            market_data=Mock(),
            confidence=0.8
        )
        
        self.assertEqual(call_count, 2)  # Should have retried once
    
    @patch('yfinance.Ticker')
    def test_yahoo_finance_recovery(self, mock_ticker_class):
        """Test Yahoo Finance data fetching recovery."""
        # Mock ticker that fails first time, succeeds second time
        call_count = 0
        def mock_history(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Yahoo Finance timeout")
            
            # Return mock DataFrame
            import pandas as pd
            return pd.DataFrame({
                'Open': [100.0, 101.0],
                'High': [102.0, 103.0], 
                'Low': [99.0, 100.0],
                'Close': [101.0, 102.0],
                'Volume': [1000, 1100]
            })
        
        mock_ticker = Mock()
        mock_ticker.history = mock_history
        mock_ticker_class.return_value = mock_ticker
        
        # Mock Alpaca to force Yahoo Finance fallback
        with patch('utils.data.get_alpaca_client') as mock_alpaca:
            mock_alpaca.return_value.enabled = False
            
            from utils.data import fetch_market_data
            result = fetch_market_data("SPY")
            
            self.assertIsNotNone(result)
            self.assertEqual(len(result), 2)
            self.assertEqual(call_count, 2)  # Should have retried once


class TestRecoveryConfiguration(unittest.TestCase):
    """Test recovery system configuration and edge cases."""
    
    def test_custom_backoff_parameters(self):
        """Test custom backoff parameters."""
        backoff = ExponentialBackoff(
            initial_delay=0.5,
            max_delay=10.0,
            backoff_factor=3.0,
            max_attempts=5
        )
        
        self.assertEqual(backoff.initial_delay, 0.5)
        self.assertEqual(backoff.max_delay, 10.0)
        self.assertEqual(backoff.backoff_factor, 3.0)
        self.assertEqual(backoff.max_attempts, 5)
    
    def test_recovery_stats_component_breakdown(self):
        """Test recovery stats component breakdown."""
        manager = RecoveryManager()
        
        # Add mixed attempts for different components
        attempts = [
            RecoveryAttempt(datetime.now(), "timeout", "alpaca_api", 1, RecoveryStatus.SUCCESS, "OK"),
            RecoveryAttempt(datetime.now(), "timeout", "alpaca_api", 2, RecoveryStatus.FAILED, "Failed"),
            RecoveryAttempt(datetime.now(), "network", "slack_api", 1, RecoveryStatus.SUCCESS, "OK"),
            RecoveryAttempt(datetime.now(), "timeout", "yahoo_finance", 1, RecoveryStatus.ESCALATED, "Escalated")
        ]
        
        for attempt in attempts:
            manager.log_recovery_attempt(attempt)
        
        stats = manager.get_recovery_stats()
        
        # Check component breakdown
        self.assertIn("alpaca_api", stats["components"])
        self.assertIn("slack_api", stats["components"])
        self.assertIn("yahoo_finance", stats["components"])
        
        alpaca_stats = stats["components"]["alpaca_api"]
        self.assertEqual(alpaca_stats["total"], 2)
        self.assertEqual(alpaca_stats["success"], 1)
        self.assertEqual(alpaca_stats["failed"], 1)
    
    def test_recovery_with_no_retries(self):
        """Test recovery with max_attempts=1 (no retries)."""
        manager = RecoveryManager()
        
        def failing_operation():
            raise Exception("Immediate failure")
        
        with patch.object(manager, '_send_escalation_alert'):
            with self.assertRaises(Exception):
                manager.retry_with_backoff(
                    operation=failing_operation,
                    operation_name="no retry test",
                    component="test",
                    max_attempts=1
                )
        
        # Should have 1 failed attempt and 1 escalation
        self.assertEqual(len(manager.recovery_history), 2)
        self.assertEqual(manager.recovery_history[0].status, RecoveryStatus.FAILED)
        self.assertEqual(manager.recovery_history[1].status, RecoveryStatus.ESCALATED)


if __name__ == "__main__":
    # Run tests
    unittest.main(verbosity=2)
