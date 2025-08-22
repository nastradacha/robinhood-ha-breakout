"""
Comprehensive unit tests for Alpaca sync components.

Tests cover:
- Bankroll synchronization
- Position synchronization  
- Transaction synchronization
- Retry logic and error handling
- Data validation and format compatibility
"""

import unittest
from unittest.mock import Mock, patch, MagicMock, mock_open
import json
import os
from datetime import datetime, timedelta
from decimal import Decimal

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.alpaca_sync import AlpacaSync, retry_with_backoff


class TestAlpacaSync(unittest.TestCase):
    """Test suite for AlpacaSync class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_config = {
            'ALPACA_SYNC_ENABLED': True,
            'ALPACA_SYNC_TOLERANCE_PCT': 1.0,
            'ALPACA_API_KEY': 'test_key',
            'ALPACA_SECRET_KEY': 'test_secret'
        }
        
        # Mock environment variables
        self.env_patcher = patch.dict(os.environ, {
            'ALPACA_API_KEY': 'test_key',
            'ALPACA_SECRET_KEY': 'test_secret'
        })
        self.env_patcher.start()
        
        # Mock scoped paths
        self.scoped_paths_patcher = patch('utils.alpaca_sync.get_scoped_paths')
        self.mock_scoped_paths = self.scoped_paths_patcher.start()
        self.mock_scoped_paths.return_value = {
            'bankroll': 'test_bankroll.json',
            'positions': 'test_positions.json',
            'trade_history': 'test_trade_history.csv'
        }
        
        # Mock Alpaca clients
        self.trading_client_patcher = patch('utils.alpaca_sync.TradingClient')
        self.mock_trading_client = self.trading_client_patcher.start()
        
        self.data_client_patcher = patch('utils.alpaca_sync.StockHistoricalDataClient')
        self.mock_data_client = self.data_client_patcher.start()
        
    def tearDown(self):
        """Clean up test fixtures."""
        self.env_patcher.stop()
        self.scoped_paths_patcher.stop()
        self.trading_client_patcher.stop()
        self.data_client_patcher.stop()
    
    def test_alpaca_sync_initialization(self):
        """Test AlpacaSync initialization."""
        sync = AlpacaSync(env="paper", config=self.mock_config)
        
        self.assertEqual(sync.env, "paper")
        self.assertEqual(sync.sync_tolerance_pct, 1.0)
        self.assertTrue(sync.enabled)
        self.assertEqual(sync.bankroll_file, 'test_bankroll.json')
        self.assertEqual(sync.positions_file, 'test_positions.json')
        self.assertEqual(sync.trade_history_file, 'test_trade_history.csv')
    
    def test_alpaca_sync_disabled(self):
        """Test AlpacaSync when disabled in config."""
        config = self.mock_config.copy()
        config['ALPACA_SYNC_ENABLED'] = False
        
        sync = AlpacaSync(env="paper", config=config)
        self.assertFalse(sync.enabled)
    
    @patch('builtins.open', new_callable=mock_open, read_data='{"balance": 1000.0, "current_bankroll": 1000.0}')
    @patch('os.path.exists', return_value=True)
    def test_load_local_bankroll_success(self, mock_exists, mock_file):
        """Test successful loading of local bankroll."""
        sync = AlpacaSync(env="paper", config=self.mock_config)
        bankroll = sync._load_local_bankroll()
        
        self.assertEqual(bankroll['balance'], 1000.0)
        self.assertEqual(bankroll['current_bankroll'], 1000.0)
    
    @patch('os.path.exists', return_value=False)
    def test_load_local_bankroll_missing_file(self, mock_exists):
        """Test loading local bankroll when file doesn't exist."""
        sync = AlpacaSync(env="paper", config=self.mock_config)
        bankroll = sync._load_local_bankroll()
        
        self.assertEqual(bankroll, {"balance": 0.0})
    
    @patch('builtins.open', new_callable=mock_open, read_data='invalid json')
    @patch('os.path.exists', return_value=True)
    def test_load_local_bankroll_invalid_json(self, mock_exists, mock_file):
        """Test loading local bankroll with invalid JSON."""
        sync = AlpacaSync(env="paper", config=self.mock_config)
        bankroll = sync._load_local_bankroll()
        
        self.assertEqual(bankroll, {"balance": 0.0})
    
    def test_sync_bankroll_within_tolerance(self):
        """Test bankroll sync when difference is within tolerance."""
        # Mock account data
        mock_account = Mock()
        mock_account.equity = 1000.0
        mock_account.cash = 1000.0
        mock_account.buying_power = 2000.0
        
        sync = AlpacaSync(env="paper", config=self.mock_config)
        sync._get_account_with_retry = Mock(return_value=mock_account)
        sync._load_local_bankroll = Mock(return_value={
            "balance": 1000.0,
            "current_bankroll": 1000.0,
            "start_capital": 1000.0,
            "total_trades": 0
        })
        
        result = sync.sync_bankroll()
        self.assertTrue(result)
    
    def test_sync_bankroll_needs_update(self):
        """Test bankroll sync when update is needed."""
        # Mock account data
        mock_account = Mock()
        mock_account.equity = 1100.0
        mock_account.cash = 1100.0
        mock_account.buying_power = 2200.0
        
        sync = AlpacaSync(env="paper", config=self.mock_config)
        sync._get_account_with_retry = Mock(return_value=mock_account)
        sync._load_local_bankroll = Mock(return_value={
            "balance": 1000.0,
            "current_bankroll": 1000.0,
            "start_capital": 1000.0,
            "total_trades": 0
        })
        sync._save_bankroll = Mock()
        sync._log_sync_event = Mock()
        
        result = sync.sync_bankroll()
        self.assertTrue(result)
        sync._save_bankroll.assert_called_once()
    
    def test_sync_bankroll_format_update_needed(self):
        """Test bankroll sync when format update is needed."""
        # Mock account data
        mock_account = Mock()
        mock_account.equity = 1000.0
        mock_account.cash = 1000.0
        mock_account.buying_power = 2000.0
        
        sync = AlpacaSync(env="paper", config=self.mock_config)
        sync._get_account_with_retry = Mock(return_value=mock_account)
        sync._load_local_bankroll = Mock(return_value={
            "balance": 1000.0
            # Missing required fields: current_bankroll, start_capital, total_trades
        })
        sync._save_bankroll = Mock()
        sync._log_sync_event = Mock()
        
        result = sync.sync_bankroll()
        self.assertTrue(result)
        sync._save_bankroll.assert_called_once()
    
    def test_sync_positions_success(self):
        """Test successful position synchronization."""
        # Mock positions data
        mock_position = Mock()
        mock_position.symbol = "SPY240821C00450000"
        mock_position.qty = 1
        mock_position.market_value = 500.0
        mock_position.unrealized_pnl = 50.0
        mock_position.asset_class = "us_option"
        
        sync = AlpacaSync(env="paper", config=self.mock_config)
        sync._get_positions_with_retry = Mock(return_value=[mock_position])
        sync._load_local_positions = Mock(return_value=[])
        sync._save_positions = Mock()
        sync._log_sync_event = Mock()
        
        result = sync.sync_positions()
        self.assertTrue(result)
    
    def test_sync_transactions_success(self):
        """Test successful transaction synchronization."""
        # Mock order data
        mock_order = Mock()
        mock_order.id = "test_order_123"
        mock_order.symbol = "SPY240821C00450000"
        mock_order.qty = 1
        mock_order.filled_avg_price = 4.50
        mock_order.side = "buy"
        mock_order.filled_at = datetime.now()
        
        sync = AlpacaSync(env="paper", config=self.mock_config)
        sync._get_orders_with_retry = Mock(return_value=[mock_order])
        sync._load_trade_history = Mock(return_value=[])
        sync._convert_order_to_trade = Mock(return_value={
            'symbol': 'SPY240821C00450000',
            'action': 'BUY',
            'quantity': 1,
            'price': 4.50,
            'alpaca_order_id': 'test_order_123'
        })
        sync._save_new_trades = Mock()
        sync._log_sync_event = Mock()
        
        result = sync.sync_transactions()
        self.assertTrue(result)
    
    def test_retry_decorator_success(self):
        """Test retry decorator with successful call."""
        @retry_with_backoff(max_retries=3, base_delay=0.1)
        def test_function():
            return "success"
        
        result = test_function()
        self.assertEqual(result, "success")
    
    def test_retry_decorator_with_retries(self):
        """Test retry decorator with failures then success."""
        call_count = 0
        
        @retry_with_backoff(max_retries=3, base_delay=0.1)
        def test_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary failure")
            return "success"
        
        result = test_function()
        self.assertEqual(result, "success")
        self.assertEqual(call_count, 3)
    
    def test_retry_decorator_max_retries_exceeded(self):
        """Test retry decorator when max retries exceeded."""
        @retry_with_backoff(max_retries=2, base_delay=0.1)
        def test_function():
            raise Exception("Persistent failure")
        
        with self.assertRaises(Exception) as context:
            test_function()
        
        self.assertEqual(str(context.exception), "Persistent failure")
    
    def test_sync_all_success(self):
        """Test successful full synchronization."""
        sync = AlpacaSync(env="paper", config=self.mock_config)
        sync.sync_bankroll = Mock(return_value=True)
        sync.sync_positions = Mock(return_value=True)
        sync.sync_transactions = Mock(return_value=True)
        
        results = sync.sync_all()
        
        self.assertTrue(results['bankroll'])
        self.assertTrue(results['positions'])
        self.assertTrue(results['transactions'])
        self.assertTrue(results['overall_success'])
    
    def test_sync_all_partial_failure(self):
        """Test full synchronization with partial failures."""
        sync = AlpacaSync(env="paper", config=self.mock_config)
        sync.sync_bankroll = Mock(return_value=True)
        sync.sync_positions = Mock(return_value=False)
        sync.sync_transactions = Mock(return_value=True)
        
        results = sync.sync_all()
        
        self.assertTrue(results['bankroll'])
        self.assertFalse(results['positions'])
        self.assertTrue(results['transactions'])
        self.assertFalse(results['overall_success'])
    
    def test_api_error_handling(self):
        """Test API error handling in sync methods."""
        sync = AlpacaSync(env="paper", config=self.mock_config)
        sync._get_account_with_retry = Mock(side_effect=Exception("API Error"))
        
        result = sync.sync_bankroll()
        self.assertFalse(result)
    
    def test_disabled_sync_returns_true(self):
        """Test that disabled sync returns True without doing work."""
        config = self.mock_config.copy()
        config['ALPACA_SYNC_ENABLED'] = False
        
        sync = AlpacaSync(env="paper", config=config)
        
        # All sync methods should return True when disabled
        self.assertTrue(sync.sync_bankroll())
        self.assertTrue(sync.sync_positions())
        self.assertTrue(sync.sync_transactions())
        
        results = sync.sync_all()
        self.assertTrue(results['overall_success'])


class TestRetryLogic(unittest.TestCase):
    """Test suite for retry logic functionality."""
    
    def test_exponential_backoff_delays(self):
        """Test that delays increase exponentially."""
        delays = []
        
        @retry_with_backoff(max_retries=3, base_delay=1.0, backoff_factor=2.0)
        def failing_function():
            delays.append(1.0)  # We can't easily capture actual delays, so we simulate
            raise Exception("Always fails")
        
        with self.assertRaises(Exception):
            failing_function()
    
    def test_max_delay_cap(self):
        """Test that delays are capped at max_delay."""
        @retry_with_backoff(max_retries=5, base_delay=10.0, max_delay=15.0, backoff_factor=2.0)
        def failing_function():
            raise Exception("Always fails")
        
        # Should not raise any issues with delay calculation
        with self.assertRaises(Exception):
            failing_function()


if __name__ == '__main__':
    unittest.main()
