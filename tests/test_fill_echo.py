"""
Unit tests for S3: Fill-price echo after Slack confirmation functionality.
Tests the enhanced fill-price echo in TradeConfirmationManager.record_trade_outcome.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.trade_confirmation import TradeConfirmationManager


class TestFillEcho(unittest.TestCase):
    """Test S3: Fill-price echo after Slack confirmation."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_portfolio_manager = Mock()
        self.mock_bankroll_manager = Mock()
        self.mock_slack_notifier = Mock()
        
        self.trade_confirmation_manager = TradeConfirmationManager(
            portfolio_manager=self.mock_portfolio_manager,
            bankroll_manager=self.mock_bankroll_manager,
            slack_notifier=self.mock_slack_notifier,
        )

    def test_fill_echo_message_format_call(self):
        """Test fill-price echo message format for CALL options."""
        trade_details = {
            "symbol": "SPY",
            "direction": "CALL",
            "strike": 580,
            "quantity": 1,
            "premium": 1.25,
            "expiry": "2025-01-10",
        }
        
        actual_premium = 1.28
        
        # Mock dependencies
        self.mock_bankroll_manager.get_current_bankroll.return_value = 500.0
        
        # Call record_trade_outcome
        self.trade_confirmation_manager.record_trade_outcome(
            trade_details=trade_details,
            decision="SUBMITTED",
            actual_premium=actual_premium,
            auto_start_monitor=False,
        )
        
        # Verify Slack fill-price echo was sent
        self.mock_slack_notifier.send_heartbeat.assert_called()
        
        # Check the fill-price echo message format
        call_args = self.mock_slack_notifier.send_heartbeat.call_args[0][0]
        expected_msg = "✅ Trade recorded: CALL 580 @ $1.28 · Qty 1"
        
        self.assertEqual(call_args, expected_msg)

    def test_fill_echo_message_format_put(self):
        """Test fill-price echo message format for PUT options."""
        trade_details = {
            "symbol": "QQQ",
            "direction": "PUT",
            "strike": 485,
            "quantity": 2,
            "premium": 2.50,
            "expiry": "2025-01-10",
        }
        
        actual_premium = 2.45
        
        # Mock dependencies
        self.mock_bankroll_manager.get_current_bankroll.return_value = 500.0
        
        # Call record_trade_outcome
        self.trade_confirmation_manager.record_trade_outcome(
            trade_details=trade_details,
            decision="SUBMITTED",
            actual_premium=actual_premium,
            auto_start_monitor=False,
        )
        
        # Verify Slack fill-price echo was sent
        self.mock_slack_notifier.send_heartbeat.assert_called()
        
        # Check the fill-price echo message format
        call_args = self.mock_slack_notifier.send_heartbeat.call_args[0][0]
        expected_msg = "✅ Trade recorded: PUT 485 @ $2.45 · Qty 2"
        
        self.assertEqual(call_args, expected_msg)

    def test_fill_echo_with_estimated_premium(self):
        """Test fill-price echo when using estimated premium (no actual fill)."""
        trade_details = {
            "symbol": "IWM",
            "direction": "CALL",
            "strike": 220,
            "quantity": 1,
            "premium": 1.50,
            "expiry": "2025-01-10",
        }
        
        # No actual_premium provided, should use estimated premium
        actual_premium = None
        
        # Mock dependencies
        self.mock_bankroll_manager.get_current_bankroll.return_value = 500.0
        
        # Call record_trade_outcome
        self.trade_confirmation_manager.record_trade_outcome(
            trade_details=trade_details,
            decision="SUBMITTED",
            actual_premium=actual_premium,
            auto_start_monitor=False,
        )
        
        # Verify Slack fill-price echo was sent
        self.mock_slack_notifier.send_heartbeat.assert_called()
        
        # Check the fill-price echo message format (should use estimated premium)
        call_args = self.mock_slack_notifier.send_heartbeat.call_args[0][0]
        expected_msg = "✅ Trade recorded: CALL 220 @ $1.50 · Qty 1"
        
        self.assertEqual(call_args, expected_msg)

    def test_fill_echo_cancelled_trade(self):
        """Test fill-price echo for cancelled trades."""
        trade_details = {
            "symbol": "SPY",
            "direction": "CALL",
            "strike": 580,
            "quantity": 1,
            "premium": 1.25,
            "expiry": "2025-01-10",
        }
        
        # Call record_trade_outcome for cancelled trade
        self.trade_confirmation_manager.record_trade_outcome(
            trade_details=trade_details,
            decision="CANCELLED",
            actual_premium=None,
            auto_start_monitor=False,
        )
        
        # Verify Slack cancellation message was sent
        self.mock_slack_notifier.send_heartbeat.assert_called()
        
        # Check the cancellation message format
        call_args = self.mock_slack_notifier.send_heartbeat.call_args[0][0]
        expected_msg = "❌ Trade cancelled: CALL 580"
        
        self.assertEqual(call_args, expected_msg)

    def test_fill_echo_no_slack_notifier(self):
        """Test fill-price echo when no Slack notifier is configured."""
        # Create manager without Slack notifier
        manager_no_slack = TradeConfirmationManager(
            portfolio_manager=self.mock_portfolio_manager,
            bankroll_manager=self.mock_bankroll_manager,
            slack_notifier=None,
        )
        
        trade_details = {
            "symbol": "SPY",
            "direction": "CALL",
            "strike": 580,
            "quantity": 1,
            "premium": 1.25,
            "expiry": "2025-01-10",
        }
        
        # Mock dependencies
        self.mock_bankroll_manager.get_current_bankroll.return_value = 500.0
        
        # Should not raise exception when no Slack notifier
        try:
            manager_no_slack.record_trade_outcome(
                trade_details=trade_details,
                decision="SUBMITTED",
                actual_premium=1.28,
                auto_start_monitor=False,
            )
        except Exception as e:
            self.fail(f"record_trade_outcome raised exception with no Slack notifier: {e}")

    def test_fill_echo_precision_formatting(self):
        """Test fill-price echo precision formatting for different price ranges."""
        test_cases = [
            {"premium": 0.05, "expected": "$0.05"},
            {"premium": 0.5, "expected": "$0.50"},
            {"premium": 1.0, "expected": "$1.00"},
            {"premium": 1.234, "expected": "$1.23"},
            {"premium": 10.567, "expected": "$10.57"},
            {"premium": 100.999, "expected": "$101.00"},
        ]
        
        for case in test_cases:
            with self.subTest(premium=case["premium"]):
                trade_details = {
                    "symbol": "SPY",
                    "direction": "CALL",
                    "strike": 580,
                    "quantity": 1,
                    "premium": 1.0,  # Base premium
                    "expiry": "2025-01-10",
                }
                
                # Mock dependencies
                self.mock_bankroll_manager.get_current_bankroll.return_value = 500.0
                self.mock_slack_notifier.reset_mock()
                
                # Call with specific actual premium
                self.trade_confirmation_manager.record_trade_outcome(
                    trade_details=trade_details,
                    decision="SUBMITTED",
                    actual_premium=case["premium"],
                    auto_start_monitor=False,
                )
                
                # Check precision formatting
                call_args = self.mock_slack_notifier.send_heartbeat.call_args[0][0]
                self.assertIn(case["expected"], call_args)

    def test_fill_echo_multi_contract_quantity(self):
        """Test fill-price echo with different contract quantities."""
        quantities = [1, 2, 5, 10]
        
        for qty in quantities:
            with self.subTest(quantity=qty):
                trade_details = {
                    "symbol": "SPY",
                    "direction": "CALL",
                    "strike": 580,
                    "quantity": qty,
                    "premium": 1.25,
                    "expiry": "2025-01-10",
                }
                
                # Mock dependencies
                self.mock_bankroll_manager.get_current_bankroll.return_value = 500.0
                self.mock_slack_notifier.reset_mock()
                
                # Call record_trade_outcome
                self.trade_confirmation_manager.record_trade_outcome(
                    trade_details=trade_details,
                    decision="SUBMITTED",
                    actual_premium=1.28,
                    auto_start_monitor=False,
                )
                
                # Check quantity in message
                call_args = self.mock_slack_notifier.send_heartbeat.call_args[0][0]
                expected_msg = f"✅ Trade recorded: CALL 580 @ $1.28 · Qty {qty}"
                
                self.assertEqual(call_args, expected_msg)

    @patch("utils.trade_confirmation.logger")
    def test_fill_echo_logging(self, mock_logger):
        """Test that fill-price echo is properly logged."""
        trade_details = {
            "symbol": "SPY",
            "direction": "CALL",
            "strike": 580,
            "quantity": 1,
            "premium": 1.25,
            "expiry": "2025-01-10",
        }
        
        # Mock dependencies
        self.mock_bankroll_manager.get_current_bankroll.return_value = 500.0
        
        # Call record_trade_outcome
        self.trade_confirmation_manager.record_trade_outcome(
            trade_details=trade_details,
            decision="SUBMITTED",
            actual_premium=1.28,
            auto_start_monitor=False,
        )
        
        # Verify S3-FILL-ECHO log message was written
        mock_logger.info.assert_called()
        
        # Check for S3-FILL-ECHO in log calls
        log_calls = [call[0][0] for call in mock_logger.info.call_args_list]
        s3_logs = [log for log in log_calls if "[S3-FILL-ECHO]" in log]
        
        self.assertTrue(len(s3_logs) > 0, "Expected S3-FILL-ECHO log message")
        
        # Verify log content
        s3_log = s3_logs[0]
        self.assertIn("Sent fill-price echo", s3_log)
        self.assertIn("CALL 580 @ $1.28", s3_log)


if __name__ == "__main__":
    unittest.main()
