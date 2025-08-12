#!/usr/bin/env python3
"""
Integration tests for Alpaca options trading workflow.

Tests the complete end-to-end workflow including main.py integration,
safety interlocks, scoped ledgers, and broker branching logic.

Author: Robinhood HA Breakout System
Version: 2.0.0
License: MIT
"""

import pytest
import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import tempfile
import os
import yaml

# Import the modules to test
from main import execute_alpaca_options_trade
from utils.alpaca_options import ContractInfo, FillResult
from utils.llm import TradeDecision


class TestAlpacaIntegration(unittest.TestCase):
    """Integration tests for Alpaca options trading workflow."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            "BROKER": "alpaca",
            "ALPACA_ENV": "paper",
            "SYMBOL": "SPY",
            "RISK_FRACTION": 0.20,
            "SIZE_RULE": "fixed-qty",
            "CONTRACT_QTY": 1
        }
        
        self.args = Mock()
        self.args.i_understand_live_risk = False
        
        self.env_vars = {
            "ALPACA_API_KEY": "test_key",
            "ALPACA_SECRET_KEY": "test_secret"
        }
        
        self.bankroll_manager = Mock()
        self.bankroll_manager.calculate_position_size.return_value = 1
        
        self.portfolio_manager = Mock()
        self.slack_notifier = Mock()
        
        self.decision = TradeDecision(
            decision="CALL",
            confidence=0.75,
            reason="Strong bullish breakout"
        )
        
        self.analysis = {
            "symbol": "SPY",
            "current_price": 450.0,
            "trend_direction": "bullish"
        }

    @patch('main.create_alpaca_trader')
    @patch('main.TradeConfirmationManager')
    def test_paper_trading_safety_interlock(self, mock_confirmation_class, mock_create_trader):
        """Test that live trading without safety flag forces paper mode."""
        # Setup mocks
        mock_trader = Mock()
        mock_trader.is_market_open_and_valid_time.return_value = (True, "Market open")
        mock_trader.get_expiry_policy.return_value = ("0DTE", "2025-01-15")
        mock_trader.find_atm_contract.return_value = ContractInfo(
            symbol="SPY250115C00450000",
            underlying_symbol="SPY",
            strike=450.0,
            expiry="2025-01-15",
            option_type="CALL",
            bid=2.50,
            ask=2.60,
            mid=2.55,
            spread=0.10,
            spread_pct=3.92,
            open_interest=15000,
            volume=2000
        )
        mock_create_trader.return_value = mock_trader
        
        mock_confirmer = Mock()
        mock_confirmer.get_user_decision.return_value = ("CANCELLED", None)
        mock_confirmation_class.return_value = mock_confirmer
        
        # Test with live config but no safety flag
        live_config = self.config.copy()
        live_config["ALPACA_ENV"] = "live"
        
        result = execute_alpaca_options_trade(
            config=live_config,
            args=self.args,
            env_vars=self.env_vars,
            bankroll_manager=self.bankroll_manager,
            portfolio_manager=self.portfolio_manager,
            slack_notifier=self.slack_notifier,
            decision=self.decision,
            analysis=self.analysis,
            position_size=1
        )
        
        # Should force paper trading
        mock_create_trader.assert_called_once_with(paper=True)

    @patch('main.create_alpaca_trader')
    @patch('main.TradeConfirmationManager')
    def test_live_trading_with_safety_flag(self, mock_confirmation_class, mock_create_trader):
        """Test that live trading works with safety flag."""
        # Setup mocks
        mock_trader = Mock()
        mock_trader.is_market_open_and_valid_time.return_value = (True, "Market open")
        mock_trader.get_expiry_policy.return_value = ("0DTE", "2025-01-15")
        mock_trader.find_atm_contract.return_value = ContractInfo(
            symbol="SPY250115C00450000",
            underlying_symbol="SPY",
            strike=450.0,
            expiry="2025-01-15",
            option_type="CALL",
            bid=2.50,
            ask=2.60,
            mid=2.55,
            spread=0.10,
            spread_pct=3.92,
            open_interest=15000,
            volume=2000
        )
        mock_create_trader.return_value = mock_trader
        
        mock_confirmer = Mock()
        mock_confirmer.get_user_decision.return_value = ("CANCELLED", None)
        mock_confirmation_class.return_value = mock_confirmer
        
        # Test with live config and safety flag
        live_config = self.config.copy()
        live_config["ALPACA_ENV"] = "live"
        self.args.i_understand_live_risk = True
        
        result = execute_alpaca_options_trade(
            config=live_config,
            args=self.args,
            env_vars=self.env_vars,
            bankroll_manager=self.bankroll_manager,
            portfolio_manager=self.portfolio_manager,
            slack_notifier=self.slack_notifier,
            decision=self.decision,
            analysis=self.analysis,
            position_size=1
        )
        
        # Should use live trading
        mock_create_trader.assert_called_once_with(paper=False)

    @patch('main.create_alpaca_trader')
    def test_market_closed_no_trade(self, mock_create_trader):
        """Test NO_TRADE when market is closed."""
        mock_trader = Mock()
        mock_trader.is_market_open_and_valid_time.return_value = (False, "Market is closed")
        mock_create_trader.return_value = mock_trader
        
        result = execute_alpaca_options_trade(
            config=self.config,
            args=self.args,
            env_vars=self.env_vars,
            bankroll_manager=self.bankroll_manager,
            portfolio_manager=self.portfolio_manager,
            slack_notifier=self.slack_notifier,
            decision=self.decision,
            analysis=self.analysis,
            position_size=1
        )
        
        self.assertEqual(result["status"], "NO_TRADE")
        self.assertEqual(result["reason"], "Market is closed")

    @patch('main.create_alpaca_trader')
    def test_no_suitable_contract(self, mock_create_trader):
        """Test NO_TRADE when no suitable contract found."""
        mock_trader = Mock()
        mock_trader.is_market_open_and_valid_time.return_value = (True, "Market open")
        mock_trader.get_expiry_policy.return_value = ("0DTE", "2025-01-15")
        mock_trader.find_atm_contract.return_value = None  # No contract found
        mock_create_trader.return_value = mock_trader
        
        result = execute_alpaca_options_trade(
            config=self.config,
            args=self.args,
            env_vars=self.env_vars,
            bankroll_manager=self.bankroll_manager,
            portfolio_manager=self.portfolio_manager,
            slack_notifier=self.slack_notifier,
            decision=self.decision,
            analysis=self.analysis,
            position_size=1
        )
        
        self.assertEqual(result["status"], "NO_TRADE")
        self.assertEqual(result["reason"], "No suitable contract found")

    @patch('main.create_alpaca_trader')
    @patch('main.TradeConfirmationManager')
    def test_user_cancellation(self, mock_confirmation_class, mock_create_trader):
        """Test CANCELLED when user cancels trade."""
        # Setup mocks
        mock_trader = Mock()
        mock_trader.is_market_open_and_valid_time.return_value = (True, "Market open")
        mock_trader.get_expiry_policy.return_value = ("0DTE", "2025-01-15")
        mock_trader.find_atm_contract.return_value = ContractInfo(
            symbol="SPY250115C00450000",
            underlying_symbol="SPY",
            strike=450.0,
            expiry="2025-01-15",
            option_type="CALL",
            bid=2.50,
            ask=2.60,
            mid=2.55,
            spread=0.10,
            spread_pct=3.92,
            open_interest=15000,
            volume=2000
        )
        mock_create_trader.return_value = mock_trader
        
        mock_confirmer = Mock()
        mock_confirmer.get_user_decision.return_value = ("CANCELLED", None)
        mock_confirmation_class.return_value = mock_confirmer
        
        result = execute_alpaca_options_trade(
            config=self.config,
            args=self.args,
            env_vars=self.env_vars,
            bankroll_manager=self.bankroll_manager,
            portfolio_manager=self.portfolio_manager,
            slack_notifier=self.slack_notifier,
            decision=self.decision,
            analysis=self.analysis,
            position_size=1
        )
        
        self.assertEqual(result["status"], "CANCELLED")
        self.assertEqual(result["reason"], "Cancelled by user")

    @patch('main.create_alpaca_trader')
    @patch('main.TradeConfirmationManager')
    @patch('main.time')
    def test_successful_trade_execution(self, mock_time, mock_confirmation_class, mock_create_trader):
        """Test successful end-to-end trade execution."""
        # Mock time for client order ID
        mock_time.time.return_value = 1642262400  # Fixed timestamp
        
        # Setup trader mocks
        mock_trader = Mock()
        mock_trader.is_market_open_and_valid_time.return_value = (True, "Market open")
        mock_trader.get_expiry_policy.return_value = ("0DTE", "2025-01-15")
        mock_trader.find_atm_contract.return_value = ContractInfo(
            symbol="SPY250115C00450000",
            underlying_symbol="SPY",
            strike=450.0,
            expiry="2025-01-15",
            option_type="CALL",
            bid=2.50,
            ask=2.60,
            mid=2.55,
            spread=0.10,
            spread_pct=3.92,
            open_interest=15000,
            volume=2000
        )
        mock_trader.place_market_order.return_value = "order_123"
        mock_trader.poll_fill.return_value = FillResult(
            status="FILLED",
            filled_qty=1,
            avg_price=2.58,
            total_filled_qty=1,
            remaining_qty=0,
            order_id="order_123",
            client_order_id="rh-breakout-SPY-1642262400"
        )
        mock_create_trader.return_value = mock_trader
        
        # Setup confirmation manager
        mock_confirmer = Mock()
        mock_confirmer.get_user_decision.return_value = ("SUBMITTED", 2.55)
        mock_confirmation_class.return_value = mock_confirmer
        
        result = execute_alpaca_options_trade(
            config=self.config,
            args=self.args,
            env_vars=self.env_vars,
            bankroll_manager=self.bankroll_manager,
            portfolio_manager=self.portfolio_manager,
            slack_notifier=self.slack_notifier,
            decision=self.decision,
            analysis=self.analysis,
            position_size=1
        )
        
        # Verify successful execution
        self.assertEqual(result["status"], "SUBMITTED")
        self.assertEqual(result["strike"], 450.0)
        self.assertEqual(result["actual_premium"], 2.58)
        self.assertEqual(result["quantity"], 1)
        self.assertEqual(result["order_id"], "order_123")
        self.assertEqual(result["total_cost"], 258.0)  # 2.58 * 1 * 100
        
        # Verify trade was recorded
        mock_confirmer.record_trade_outcome.assert_called_once()

    @patch('main.create_alpaca_trader')
    @patch('main.TradeConfirmationManager')
    def test_order_placement_failure(self, mock_confirmation_class, mock_create_trader):
        """Test ERROR when order placement fails."""
        # Setup mocks
        mock_trader = Mock()
        mock_trader.is_market_open_and_valid_time.return_value = (True, "Market open")
        mock_trader.get_expiry_policy.return_value = ("0DTE", "2025-01-15")
        mock_trader.find_atm_contract.return_value = ContractInfo(
            symbol="SPY250115C00450000",
            underlying_symbol="SPY",
            strike=450.0,
            expiry="2025-01-15",
            option_type="CALL",
            bid=2.50,
            ask=2.60,
            mid=2.55,
            spread=0.10,
            spread_pct=3.92,
            open_interest=15000,
            volume=2000
        )
        mock_trader.place_market_order.return_value = None  # Order placement failed
        mock_create_trader.return_value = mock_trader
        
        mock_confirmer = Mock()
        mock_confirmer.get_user_decision.return_value = ("SUBMITTED", 2.55)
        mock_confirmation_class.return_value = mock_confirmer
        
        result = execute_alpaca_options_trade(
            config=self.config,
            args=self.args,
            env_vars=self.env_vars,
            bankroll_manager=self.bankroll_manager,
            portfolio_manager=self.portfolio_manager,
            slack_notifier=self.slack_notifier,
            decision=self.decision,
            analysis=self.analysis,
            position_size=1
        )
        
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["reason"], "Order placement failed")

    @patch('main.create_alpaca_trader')
    @patch('main.TradeConfirmationManager')
    def test_partial_fill_handling(self, mock_confirmation_class, mock_create_trader):
        """Test handling of partial fills with timeout."""
        # Setup trader mocks
        mock_trader = Mock()
        mock_trader.is_market_open_and_valid_time.return_value = (True, "Market open")
        mock_trader.get_expiry_policy.return_value = ("0DTE", "2025-01-15")
        mock_trader.find_atm_contract.return_value = ContractInfo(
            symbol="SPY250115C00450000",
            underlying_symbol="SPY",
            strike=450.0,
            expiry="2025-01-15",
            option_type="CALL",
            bid=2.50,
            ask=2.60,
            mid=2.55,
            spread=0.10,
            spread_pct=3.92,
            open_interest=15000,
            volume=2000
        )
        mock_trader.place_market_order.return_value = "order_123"
        mock_trader.poll_fill.return_value = FillResult(
            status="TIMEOUT",
            filled_qty=1,  # Partial fill
            avg_price=2.58,
            total_filled_qty=1,
            remaining_qty=1,
            order_id="order_123"
        )
        mock_create_trader.return_value = mock_trader
        
        # Setup confirmation manager
        mock_confirmer = Mock()
        mock_confirmer.get_user_decision.return_value = ("SUBMITTED", 2.55)
        mock_confirmation_class.return_value = mock_confirmer
        
        result = execute_alpaca_options_trade(
            config=self.config,
            args=self.args,
            env_vars=self.env_vars,
            bankroll_manager=self.bankroll_manager,
            portfolio_manager=self.portfolio_manager,
            slack_notifier=self.slack_notifier,
            decision=self.decision,
            analysis=self.analysis,
            position_size=2  # Requested 2 contracts
        )
        
        # Should record partial fill
        self.assertEqual(result["status"], "SUBMITTED")
        self.assertEqual(result["quantity"], 1)  # Only 1 filled
        self.assertEqual(result["actual_premium"], 2.58)

    def test_zero_position_size_no_trade(self):
        """Test NO_TRADE when position size calculation yields 0."""
        # Mock zero position size
        self.bankroll_manager.calculate_position_size.return_value = 0
        
        with patch('main.create_alpaca_trader') as mock_create_trader:
            mock_trader = Mock()
            mock_trader.is_market_open_and_valid_time.return_value = (True, "Market open")
            mock_trader.get_expiry_policy.return_value = ("0DTE", "2025-01-15")
            mock_trader.find_atm_contract.return_value = ContractInfo(
                symbol="SPY250115C00450000",
                underlying_symbol="SPY",
                strike=450.0,
                expiry="2025-01-15",
                option_type="CALL",
                bid=2.50,
                ask=2.60,
                mid=2.55,
                spread=0.10,
                spread_pct=3.92,
                open_interest=15000,
                volume=2000
            )
            mock_create_trader.return_value = mock_trader
            
            result = execute_alpaca_options_trade(
                config=self.config,
                args=self.args,
                env_vars=self.env_vars,
                bankroll_manager=self.bankroll_manager,
                portfolio_manager=self.portfolio_manager,
                slack_notifier=self.slack_notifier,
                decision=self.decision,
                analysis=self.analysis,
                position_size=0
            )
            
            self.assertEqual(result["status"], "NO_TRADE")
            self.assertEqual(result["reason"], "Risk calculation yielded 0 contracts")

    def test_slack_notifications_sent(self):
        """Test that appropriate Slack notifications are sent."""
        with patch('main.create_alpaca_trader') as mock_create_trader:
            mock_trader = Mock()
            mock_trader.is_market_open_and_valid_time.return_value = (False, "Market is closed")
            mock_create_trader.return_value = mock_trader
            
            result = execute_alpaca_options_trade(
                config=self.config,
                args=self.args,
                env_vars=self.env_vars,
                bankroll_manager=self.bankroll_manager,
                portfolio_manager=self.portfolio_manager,
                slack_notifier=self.slack_notifier,
                decision=self.decision,
                analysis=self.analysis,
                position_size=1
            )
            
            # Verify Slack notification was sent
            self.slack_notifier.send_heartbeat.assert_called_once()
            call_args = self.slack_notifier.send_heartbeat.call_args[0][0]
            self.assertIn("[ALPACA:PAPER]", call_args)
            self.assertIn("Market timing issue", call_args)


if __name__ == "__main__":
    unittest.main()
