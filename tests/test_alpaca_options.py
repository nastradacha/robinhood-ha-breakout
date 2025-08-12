#!/usr/bin/env python3
"""
Unit tests for Alpaca options trading functionality.

Tests contract selection, order placement, fill polling, and safety interlocks
for the AlpacaOptionsTrader class and related workflow functions.

Author: Robinhood HA Breakout System
Version: 2.0.0
License: MIT
"""

import pytest
import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from decimal import Decimal

# Import the modules to test
from utils.alpaca_options import (
    AlpacaOptionsTrader,
    ContractInfo,
    FillResult,
    create_alpaca_trader
)


class TestAlpacaOptionsTrader(unittest.TestCase):
    """Test cases for AlpacaOptionsTrader class."""

    def setUp(self):
        """Set up test fixtures."""
        self.api_key = "test_api_key"
        self.secret_key = "test_secret_key"
        
        # Mock TradingClient to avoid actual API calls
        with patch('utils.alpaca_options.TradingClient') as mock_client_class:
            self.mock_client = Mock()
            mock_client_class.return_value = self.mock_client
            self.trader = AlpacaOptionsTrader(
                api_key=self.api_key,
                secret_key=self.secret_key,
                paper=True
            )

    def test_initialization(self):
        """Test trader initialization."""
        self.assertTrue(self.trader.paper)
        self.assertEqual(self.trader.client, self.mock_client)

    def test_market_open_validation_closed(self):
        """Test market open validation when market is closed."""
        # Mock closed market
        mock_clock = Mock()
        mock_clock.is_open = False
        self.mock_client.get_clock.return_value = mock_clock
        
        is_valid, reason = self.trader.is_market_open_and_valid_time()
        
        self.assertFalse(is_valid)
        self.assertEqual(reason, "Market is closed")

    def test_market_open_validation_after_cutoff(self):
        """Test market open validation after 15:15 ET cutoff."""
        # Mock market open but after cutoff
        mock_clock = Mock()
        mock_clock.is_open = True
        mock_clock.timestamp = Mock()
        mock_clock.timestamp.astimezone.return_value = datetime(2025, 1, 15, 15, 30)  # 3:30 PM
        self.mock_client.get_clock.return_value = mock_clock
        
        is_valid, reason = self.trader.is_market_open_and_valid_time()
        
        self.assertFalse(is_valid)
        self.assertIn("After 15:15 ET cutoff", reason)

    def test_market_open_validation_valid_time(self):
        """Test market open validation during valid trading hours."""
        # Mock market open during valid hours
        mock_clock = Mock()
        mock_clock.is_open = True
        mock_clock.timestamp = Mock()
        mock_clock.timestamp.astimezone.return_value = datetime(2025, 1, 15, 14, 30)  # 2:30 PM
        self.mock_client.get_clock.return_value = mock_clock
        
        is_valid, reason = self.trader.is_market_open_and_valid_time()
        
        self.assertTrue(is_valid)
        self.assertIn("Market open and within valid time window", reason)

    def test_expiry_policy_0dte(self):
        """Test expiry policy selection for 0DTE during valid hours."""
        # Mock market clock for 0DTE hours
        mock_clock = Mock()
        mock_clock.timestamp = Mock()
        mock_clock.timestamp.astimezone.return_value = datetime(2025, 1, 15, 12, 0)  # 12:00 PM
        self.mock_client.get_clock.return_value = mock_clock
        
        policy, expiry_date = self.trader.get_expiry_policy()
        
        self.assertEqual(policy, "0DTE")
        self.assertEqual(expiry_date, "2025-01-15")

    def test_expiry_policy_weekly(self):
        """Test expiry policy selection for weekly outside 0DTE hours."""
        # Mock market clock for weekly hours
        mock_clock = Mock()
        mock_clock.timestamp = Mock()
        mock_clock.timestamp.astimezone.return_value = datetime(2025, 1, 15, 16, 0)  # 4:00 PM
        self.mock_client.get_clock.return_value = mock_clock
        
        policy, expiry_date = self.trader.get_expiry_policy()
        
        self.assertEqual(policy, "WEEKLY")
        # Should be next Friday (assuming Wednesday test date)
        self.assertRegex(expiry_date, r"\d{4}-\d{2}-\d{2}")

    @patch('utils.alpaca_options.AlpacaClient')
    def test_find_atm_contract_success(self, mock_alpaca_client_class):
        """Test successful ATM contract selection."""
        # Mock current price
        mock_alpaca_client = Mock()
        mock_alpaca_client.get_real_time_quote.return_value = 450.0
        mock_alpaca_client_class.return_value = mock_alpaca_client
        
        # Mock contract data
        mock_contract = Mock()
        mock_contract.symbol = "SPY250117C00450000"
        mock_contract.strike_price = 450.0
        mock_contract.open_interest = 15000
        mock_contract.volume = 2000
        
        # Mock quote data
        mock_quote = Mock()
        mock_quote.bid = 2.50
        mock_quote.ask = 2.60
        
        self.mock_client.get_option_contracts.return_value = [mock_contract]
        self.mock_client.get_latest_quote.return_value = mock_quote
        
        contract = self.trader.find_atm_contract(
            symbol="SPY",
            side="CALL",
            policy="0DTE",
            expiry_date="2025-01-17"
        )
        
        self.assertIsNotNone(contract)
        self.assertEqual(contract.symbol, "SPY250117C00450000")
        self.assertEqual(contract.strike, 450.0)
        self.assertEqual(contract.bid, 2.50)
        self.assertEqual(contract.ask, 2.60)
        self.assertEqual(contract.mid, 2.55)

    @patch('utils.alpaca_options.AlpacaClient')
    def test_find_atm_contract_no_liquidity(self, mock_alpaca_client_class):
        """Test ATM contract selection with insufficient liquidity."""
        # Mock current price
        mock_alpaca_client = Mock()
        mock_alpaca_client.get_real_time_quote.return_value = 450.0
        mock_alpaca_client_class.return_value = mock_alpaca_client
        
        # Mock contract with low liquidity
        mock_contract = Mock()
        mock_contract.symbol = "SPY250117C00450000"
        mock_contract.strike_price = 450.0
        mock_contract.open_interest = 500  # Below minimum
        mock_contract.volume = 100  # Below minimum
        
        # Mock quote data
        mock_quote = Mock()
        mock_quote.bid = 2.50
        mock_quote.ask = 2.60
        
        self.mock_client.get_option_contracts.return_value = [mock_contract]
        self.mock_client.get_latest_quote.return_value = mock_quote
        
        contract = self.trader.find_atm_contract(
            symbol="SPY",
            side="CALL",
            policy="0DTE",
            expiry_date="2025-01-17"
        )
        
        self.assertIsNone(contract)

    def test_place_market_order_success(self):
        """Test successful market order placement."""
        # Mock successful order
        mock_order = Mock()
        mock_order.id = "test_order_123"
        self.mock_client.submit_order.return_value = mock_order
        
        order_id = self.trader.place_market_order(
            contract_symbol="SPY250117C00450000",
            qty=1,
            side="BUY",
            client_order_id="test_client_123"
        )
        
        self.assertEqual(order_id, "test_order_123")
        self.mock_client.submit_order.assert_called_once()

    def test_place_market_order_failure(self):
        """Test market order placement failure."""
        # Mock API error
        from alpaca.common.exceptions import APIError
        self.mock_client.submit_order.side_effect = APIError("Order rejected")
        
        # Mock quote for limit fallback
        mock_quote = Mock()
        mock_quote.bid = 2.50
        mock_quote.ask = 2.60
        self.mock_client.get_latest_quote.return_value = mock_quote
        
        # Mock successful limit order
        mock_order = Mock()
        mock_order.id = "test_limit_order_123"
        self.mock_client.submit_order.side_effect = [
            APIError("Order rejected"),  # First call (market order)
            mock_order  # Second call (limit order fallback)
        ]
        
        order_id = self.trader.place_market_order(
            contract_symbol="SPY250117C00450000",
            qty=1,
            side="BUY"
        )
        
        self.assertEqual(order_id, "test_limit_order_123")
        self.assertEqual(self.mock_client.submit_order.call_count, 2)

    def test_poll_fill_success(self):
        """Test successful fill polling."""
        # Mock filled order
        mock_order = Mock()
        mock_order.id = "test_order_123"
        mock_order.status = "filled"
        mock_order.filled_qty = 1
        mock_order.qty = 1
        mock_order.filled_avg_price = 2.55
        mock_order.client_order_id = "test_client_123"
        
        self.mock_client.get_order_by_id.return_value = mock_order
        
        fill_result = self.trader.poll_fill(
            order_id="test_order_123",
            timeout_s=5,
            interval_s=1
        )
        
        self.assertEqual(fill_result.status, "FILLED")
        self.assertEqual(fill_result.filled_qty, 1)
        self.assertEqual(fill_result.avg_price, 2.55)

    def test_poll_fill_timeout(self):
        """Test fill polling timeout."""
        # Mock pending order that never fills
        mock_order = Mock()
        mock_order.id = "test_order_123"
        mock_order.status = "new"
        mock_order.filled_qty = 0
        mock_order.qty = 1
        mock_order.filled_avg_price = None
        
        self.mock_client.get_order_by_id.return_value = mock_order
        
        fill_result = self.trader.poll_fill(
            order_id="test_order_123",
            timeout_s=2,
            interval_s=1
        )
        
        self.assertEqual(fill_result.status, "TIMEOUT")
        self.assertEqual(fill_result.filled_qty, 0)

    def test_cancel_order_success(self):
        """Test successful order cancellation."""
        success = self.trader.cancel_order("test_order_123")
        
        self.assertTrue(success)
        self.mock_client.cancel_order_by_id.assert_called_once_with("test_order_123")

    def test_cancel_order_failure(self):
        """Test order cancellation failure."""
        self.mock_client.cancel_order_by_id.side_effect = Exception("Cancel failed")
        
        success = self.trader.cancel_order("test_order_123")
        
        self.assertFalse(success)

    def test_close_position(self):
        """Test position closing."""
        # Mock successful sell order
        mock_order = Mock()
        mock_order.id = "test_sell_order_123"
        self.mock_client.submit_order.return_value = mock_order
        
        order_id = self.trader.close_position("SPY250117C00450000", 1)
        
        self.assertEqual(order_id, "test_sell_order_123")


class TestCreateAlpacaTrader(unittest.TestCase):
    """Test cases for create_alpaca_trader function."""

    @patch.dict('os.environ', {
        'ALPACA_API_KEY': 'test_key',
        'ALPACA_SECRET_KEY': 'test_secret'
    })
    @patch('utils.alpaca_options.AlpacaOptionsTrader')
    def test_create_trader_success(self, mock_trader_class):
        """Test successful trader creation with environment variables."""
        mock_trader = Mock()
        mock_trader_class.return_value = mock_trader
        
        trader = create_alpaca_trader(paper=True)
        
        self.assertEqual(trader, mock_trader)
        mock_trader_class.assert_called_once_with('test_key', 'test_secret', paper=True)

    @patch.dict('os.environ', {}, clear=True)
    def test_create_trader_missing_credentials(self):
        """Test trader creation with missing credentials."""
        trader = create_alpaca_trader(paper=True)
        
        self.assertIsNone(trader)

    @patch.dict('os.environ', {
        'ALPACA_KEY_ID': 'test_key_id',
        'ALPACA_SECRET_KEY': 'test_secret'
    })
    @patch('utils.alpaca_options.AlpacaOptionsTrader')
    def test_create_trader_with_key_id(self, mock_trader_class):
        """Test trader creation with ALPACA_KEY_ID instead of ALPACA_API_KEY."""
        mock_trader = Mock()
        mock_trader_class.return_value = mock_trader
        
        trader = create_alpaca_trader(paper=True)
        
        self.assertEqual(trader, mock_trader)
        mock_trader_class.assert_called_once_with('test_key_id', 'test_secret', paper=True)


class TestContractInfo(unittest.TestCase):
    """Test cases for ContractInfo dataclass."""

    def test_contract_info_creation(self):
        """Test ContractInfo creation and attributes."""
        contract = ContractInfo(
            symbol="SPY250117C00450000",
            underlying_symbol="SPY",
            strike=450.0,
            expiry="2025-01-17",
            option_type="CALL",
            bid=2.50,
            ask=2.60,
            mid=2.55,
            spread=0.10,
            spread_pct=3.92,
            open_interest=15000,
            volume=2000,
            delta=0.52
        )
        
        self.assertEqual(contract.symbol, "SPY250117C00450000")
        self.assertEqual(contract.strike, 450.0)
        self.assertEqual(contract.mid, 2.55)
        self.assertEqual(contract.delta, 0.52)


class TestFillResult(unittest.TestCase):
    """Test cases for FillResult dataclass."""

    def test_fill_result_creation(self):
        """Test FillResult creation and attributes."""
        result = FillResult(
            status="FILLED",
            filled_qty=1,
            avg_price=2.55,
            total_filled_qty=1,
            remaining_qty=0,
            order_id="test_order_123",
            client_order_id="test_client_123"
        )
        
        self.assertEqual(result.status, "FILLED")
        self.assertEqual(result.filled_qty, 1)
        self.assertEqual(result.avg_price, 2.55)
        self.assertEqual(result.order_id, "test_order_123")


if __name__ == "__main__":
    unittest.main()
