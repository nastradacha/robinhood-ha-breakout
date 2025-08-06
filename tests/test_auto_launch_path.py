#!/usr/bin/env python3
"""
Unit tests for auto-launch path integration.

Tests that ensure_monitor_running is called when auto_start_monitor is True
and NOT called when False during trade submission.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.trade_confirmation import TradeConfirmationManager


class TestAutoLaunchPath:
    """Test auto-launch integration path."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_portfolio_manager = Mock()
        self.mock_bankroll_manager = Mock()
        self.mock_slack_notifier = Mock()

        self.trade_confirmation = TradeConfirmationManager(
            portfolio_manager=self.mock_portfolio_manager,
            bankroll_manager=self.mock_bankroll_manager,
            slack_notifier=self.mock_slack_notifier,
        )

        self.sample_trade_details = {
            "symbol": "SPY",
            "strike": 635.0,
            "direction": "CALL",
            "premium": 2.50,
            "quantity": 1,
            "expiry": "2025-08-05",
        }

    @patch("utils.monitor_launcher.ensure_monitor_running")
    @patch("utils.portfolio.Position")
    def test_submitted_trade_with_auto_start_enabled(
        self, mock_position_class, mock_ensure_monitor
    ):
        """Test that monitor is auto-started when auto_start_monitor=True."""
        # Setup mocks
        mock_position = Mock()
        mock_position_class.return_value = mock_position
        mock_ensure_monitor.return_value = True

        # Mock portfolio manager
        self.mock_portfolio_manager.add_position.return_value = None

        # Mock bankroll manager
        self.mock_bankroll_manager.apply_fill.return_value = {}
        self.mock_bankroll_manager.record_trade.return_value = None

        # Execute with auto_start_monitor=True (default)
        self.trade_confirmation.record_trade_outcome(
            trade_details=self.sample_trade_details,
            decision="SUBMITTED",
            actual_premium=2.75,
            auto_start_monitor=True,
        )

        # Verify monitor was started
        mock_ensure_monitor.assert_called_once_with("SPY")

        # Verify other operations occurred
        self.mock_portfolio_manager.add_position.assert_called_once()
        self.mock_bankroll_manager.apply_fill.assert_called_once()
        self.mock_bankroll_manager.record_trade.assert_called_once()

    @patch("utils.monitor_launcher.ensure_monitor_running")
    @patch("utils.portfolio.Position")
    def test_submitted_trade_with_auto_start_disabled(
        self, mock_position_class, mock_ensure_monitor
    ):
        """Test that monitor is NOT auto-started when auto_start_monitor=False."""
        # Setup mocks
        mock_position = Mock()
        mock_position_class.return_value = mock_position
        mock_ensure_monitor.return_value = True

        # Mock portfolio manager
        self.mock_portfolio_manager.add_position.return_value = None

        # Mock bankroll manager
        self.mock_bankroll_manager.apply_fill.return_value = {}
        self.mock_bankroll_manager.record_trade.return_value = None

        # Execute with auto_start_monitor=False
        self.trade_confirmation.record_trade_outcome(
            trade_details=self.sample_trade_details,
            decision="SUBMITTED",
            actual_premium=2.75,
            auto_start_monitor=False,
        )

        # Verify monitor was NOT started
        mock_ensure_monitor.assert_not_called()

        # Verify other operations still occurred
        self.mock_portfolio_manager.add_position.assert_called_once()
        self.mock_bankroll_manager.apply_fill.assert_called_once()
        self.mock_bankroll_manager.record_trade.assert_called_once()

    @patch("utils.monitor_launcher.ensure_monitor_running")
    @patch("utils.portfolio.Position")
    def test_cancelled_trade_no_auto_start(
        self, mock_position_class, mock_ensure_monitor
    ):
        """Test that monitor is NOT auto-started for cancelled trades."""
        # Setup mocks
        mock_position = Mock()
        mock_position_class.return_value = mock_position
        mock_ensure_monitor.return_value = True

        # Mock bankroll manager
        self.mock_bankroll_manager.record_trade.return_value = None

        # Execute with CANCELLED decision
        self.trade_confirmation.record_trade_outcome(
            trade_details=self.sample_trade_details,
            decision="CANCELLED",
            auto_start_monitor=True,  # Should be ignored for cancelled trades
        )

        # Verify monitor was NOT started
        mock_ensure_monitor.assert_not_called()

        # Verify portfolio was NOT updated (no position added for cancelled trade)
        self.mock_portfolio_manager.add_position.assert_not_called()

        # Verify trade was still recorded for statistics
        self.mock_bankroll_manager.record_trade.assert_called_once()

    @patch("utils.monitor_launcher.ensure_monitor_running")
    @patch("utils.portfolio.Position")
    def test_auto_start_monitor_failure_handling(
        self, mock_position_class, mock_ensure_monitor
    ):
        """Test graceful handling when monitor auto-start fails."""
        # Setup mocks
        mock_position = Mock()
        mock_position_class.return_value = mock_position
        mock_ensure_monitor.return_value = False  # Monitor start failed

        # Mock portfolio manager
        self.mock_portfolio_manager.add_position.return_value = None

        # Mock bankroll manager
        self.mock_bankroll_manager.apply_fill.return_value = {}
        self.mock_bankroll_manager.record_trade.return_value = None

        # Execute - should not raise exception even if monitor start fails
        self.trade_confirmation.record_trade_outcome(
            trade_details=self.sample_trade_details,
            decision="SUBMITTED",
            actual_premium=2.75,
            auto_start_monitor=True,
        )

        # Verify monitor start was attempted
        mock_ensure_monitor.assert_called_once_with("SPY")

        # Verify other operations still completed successfully
        self.mock_portfolio_manager.add_position.assert_called_once()
        self.mock_bankroll_manager.apply_fill.assert_called_once()
        self.mock_bankroll_manager.record_trade.assert_called_once()

    @patch("utils.monitor_launcher.ensure_monitor_running")
    @patch("utils.portfolio.Position")
    def test_auto_start_monitor_exception_handling(
        self, mock_position_class, mock_ensure_monitor
    ):
        """Test graceful handling when monitor auto-start raises exception."""
        # Setup mocks
        mock_position = Mock()
        mock_position_class.return_value = mock_position
        mock_ensure_monitor.side_effect = Exception("Monitor launcher error")

        # Mock portfolio manager
        self.mock_portfolio_manager.add_position.return_value = None

        # Mock bankroll manager
        self.mock_bankroll_manager.apply_fill.return_value = {}
        self.mock_bankroll_manager.record_trade.return_value = None

        # Execute - should not raise exception even if monitor launcher fails
        self.trade_confirmation.record_trade_outcome(
            trade_details=self.sample_trade_details,
            decision="SUBMITTED",
            actual_premium=2.75,
            auto_start_monitor=True,
        )

        # Verify monitor start was attempted
        mock_ensure_monitor.assert_called_once_with("SPY")

        # Verify other operations still completed successfully
        self.mock_portfolio_manager.add_position.assert_called_once()
        self.mock_bankroll_manager.apply_fill.assert_called_once()
        self.mock_bankroll_manager.record_trade.assert_called_once()

    @patch("utils.monitor_launcher.ensure_monitor_running")
    @patch("utils.portfolio.Position")
    def test_multi_symbol_auto_start(self, mock_position_class, mock_ensure_monitor):
        """Test auto-start with different symbols."""
        # Setup mocks
        mock_position = Mock()
        mock_position_class.return_value = mock_position
        mock_ensure_monitor.return_value = True

        # Mock managers
        self.mock_portfolio_manager.add_position.return_value = None
        self.mock_bankroll_manager.apply_fill.return_value = {}
        self.mock_bankroll_manager.record_trade.return_value = None

        # Test different symbols
        symbols = ["SPY", "QQQ", "IWM"]

        for symbol in symbols:
            trade_details = {**self.sample_trade_details, "symbol": symbol}

            self.trade_confirmation.record_trade_outcome(
                trade_details=trade_details,
                decision="SUBMITTED",
                actual_premium=2.75,
                auto_start_monitor=True,
            )

        # Verify monitor was started for each symbol
        assert mock_ensure_monitor.call_count == len(symbols)
        for symbol in symbols:
            mock_ensure_monitor.assert_any_call(symbol)

    @patch("utils.monitor_launcher.ensure_monitor_running")
    @patch("utils.portfolio.Position")
    def test_default_auto_start_behavior(
        self, mock_position_class, mock_ensure_monitor
    ):
        """Test that auto_start_monitor defaults to True when not specified."""
        # Setup mocks
        mock_position = Mock()
        mock_position_class.return_value = mock_position
        mock_ensure_monitor.return_value = True

        # Mock managers
        self.mock_portfolio_manager.add_position.return_value = None
        self.mock_bankroll_manager.apply_fill.return_value = {}
        self.mock_bankroll_manager.record_trade.return_value = None

        # Execute without specifying auto_start_monitor (should default to True)
        self.trade_confirmation.record_trade_outcome(
            trade_details=self.sample_trade_details,
            decision="SUBMITTED",
            actual_premium=2.75,
            # auto_start_monitor not specified - should default to True
        )

        # Verify monitor was started (default behavior)
        mock_ensure_monitor.assert_called_once_with("SPY")


if __name__ == "__main__":
    pytest.main([__file__])
