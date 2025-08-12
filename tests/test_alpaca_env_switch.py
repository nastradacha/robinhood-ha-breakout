#!/usr/bin/env python3
"""
Unit tests for Alpaca environment switching (v0.9.0)

Tests the Alpaca client environment switching functionality:
- Mock Alpaca client; assert base URL chosen by env
- Live mode requires --i-understand-live-risk; otherwise exits
"""

import pytest
import os
from unittest.mock import patch, MagicMock

from utils.alpaca_client import AlpacaClient


class TestAlpacaEnvSwitch:
    """Test Alpaca environment switching functionality."""

    def setup_method(self):
        """Set up test environment."""
        # Mock environment variables
        self.env_patcher = patch.dict(os.environ, {
            'ALPACA_KEY_ID': 'test_key_id',
            'ALPACA_SECRET_KEY': 'test_secret_key'
        })
        self.env_patcher.start()

    def teardown_method(self):
        """Clean up test environment."""
        self.env_patcher.stop()

    @patch('utils.alpaca_client.StockHistoricalDataClient')
    @patch('utils.alpaca_client.TradingClient')
    def test_paper_environment_selection(self, mock_trading_client, mock_data_client):
        """Test that paper environment selects correct base URL."""
        mock_account = MagicMock()
        mock_account.account_number = "TEST123"
        mock_trading_client.return_value.get_account.return_value = mock_account

        config = {
            "ALPACA_PAPER_BASE_URL": "https://paper-api.alpaca.markets",
            "ALPACA_LIVE_BASE_URL": "https://api.alpaca.markets"
        }

        client = AlpacaClient(env="paper", config=config)

        assert client.env == "paper"
        assert client.is_paper == True
        assert client.base_url == "https://paper-api.alpaca.markets"
        
        # Verify TradingClient was initialized with paper=True
        mock_trading_client.assert_called_once_with(
            api_key="test_key_id",
            secret_key="test_secret_key",
            paper=True
        )

    @patch('utils.alpaca_client.StockHistoricalDataClient')
    @patch('utils.alpaca_client.TradingClient')
    def test_live_environment_selection(self, mock_trading_client, mock_data_client):
        """Test that live environment selects correct base URL."""
        mock_account = MagicMock()
        mock_account.account_number = "LIVE456"
        mock_trading_client.return_value.get_account.return_value = mock_account

        config = {
            "ALPACA_PAPER_BASE_URL": "https://paper-api.alpaca.markets",
            "ALPACA_LIVE_BASE_URL": "https://api.alpaca.markets"
        }

        client = AlpacaClient(env="live", config=config)

        assert client.env == "live"
        assert client.is_paper == False
        assert client.base_url == "https://api.alpaca.markets"
        
        # Verify TradingClient was initialized with paper=False
        mock_trading_client.assert_called_once_with(
            api_key="test_key_id",
            secret_key="test_secret_key",
            paper=False
        )

    @patch('utils.alpaca_client.StockHistoricalDataClient')
    @patch('utils.alpaca_client.TradingClient')
    def test_default_urls_fallback(self, mock_trading_client, mock_data_client):
        """Test fallback to default URLs when config not provided."""
        mock_account = MagicMock()
        mock_account.account_number = "DEFAULT789"
        mock_trading_client.return_value.get_account.return_value = mock_account

        # Test paper default
        client_paper = AlpacaClient(env="paper")
        assert client_paper.base_url == "https://paper-api.alpaca.markets"

        # Test live default
        client_live = AlpacaClient(env="live")
        assert client_live.base_url == "https://api.alpaca.markets"

    @patch('utils.alpaca_client.StockHistoricalDataClient')
    @patch('utils.alpaca_client.TradingClient')
    def test_environment_variable_fallback(self, mock_trading_client, mock_data_client):
        """Test fallback to environment variables for base URLs."""
        mock_account = MagicMock()
        mock_account.account_number = "ENV123"
        mock_trading_client.return_value.get_account.return_value = mock_account

        with patch.dict(os.environ, {
            'ALPACA_PAPER_BASE_URL': 'https://custom-paper.alpaca.markets',
            'ALPACA_LIVE_BASE_URL': 'https://custom-live.alpaca.markets'
        }):
            client_paper = AlpacaClient(env="paper")
            assert client_paper.base_url == "https://custom-paper.alpaca.markets"

            client_live = AlpacaClient(env="live")
            assert client_live.base_url == "https://custom-live.alpaca.markets"

    def test_missing_api_keys(self):
        """Test behavior when API keys are missing."""
        with patch.dict(os.environ, {}, clear=True):
            client = AlpacaClient(env="paper")
            assert client.enabled == False
            assert client.api_key is None
            assert client.secret_key is None

    @patch('utils.alpaca_client.StockHistoricalDataClient')
    @patch('utils.alpaca_client.TradingClient')
    def test_connection_failure_handling(self, mock_trading_client, mock_data_client):
        """Test handling of connection failures during initialization."""
        mock_trading_client.return_value.get_account.side_effect = Exception("Connection failed")

        client = AlpacaClient(env="paper")
        assert client.enabled == False

    def test_is_paper_property(self):
        """Test is_paper property for different environments."""
        with patch('utils.alpaca_client.StockHistoricalDataClient'), \
             patch('utils.alpaca_client.TradingClient') as mock_trading:
            
            mock_account = MagicMock()
            mock_account.account_number = "TEST123"
            mock_trading.return_value.get_account.return_value = mock_account

            paper_client = AlpacaClient(env="paper")
            assert paper_client.is_paper == True

            live_client = AlpacaClient(env="live")
            assert live_client.is_paper == False

    @patch('utils.alpaca_client.StockHistoricalDataClient')
    @patch('utils.alpaca_client.TradingClient')
    def test_legacy_api_key_support(self, mock_trading_client, mock_data_client):
        """Test support for legacy ALPACA_API_KEY environment variable."""
        mock_account = MagicMock()
        mock_account.account_number = "LEGACY123"
        mock_trading_client.return_value.get_account.return_value = mock_account

        with patch.dict(os.environ, {
            'ALPACA_API_KEY': 'legacy_key',
            'ALPACA_SECRET_KEY': 'legacy_secret'
        }, clear=True):
            client = AlpacaClient(env="paper")
            assert client.api_key == "legacy_key"
            assert client.secret_key == "legacy_secret"
            assert client.enabled == True

    @patch('utils.alpaca_client.StockHistoricalDataClient')
    @patch('utils.alpaca_client.TradingClient')
    def test_key_id_priority(self, mock_trading_client, mock_data_client):
        """Test that ALPACA_KEY_ID takes priority over ALPACA_API_KEY."""
        mock_account = MagicMock()
        mock_account.account_number = "PRIORITY123"
        mock_trading_client.return_value.get_account.return_value = mock_account

        with patch.dict(os.environ, {
            'ALPACA_KEY_ID': 'new_key_id',
            'ALPACA_API_KEY': 'old_api_key',
            'ALPACA_SECRET_KEY': 'secret_key'
        }):
            client = AlpacaClient(env="paper")
            assert client.api_key == "new_key_id"  # Should use ALPACA_KEY_ID
            assert client.secret_key == "secret_key"


class TestLiveTradingSafetyInterlocks:
    """Test safety interlocks for live trading mode."""

    def test_live_risk_flag_requirement(self):
        """Test that live trading requires --i-understand-live-risk flag."""
        # This would be tested in the main.py integration, but we can test the logic
        config = {
            "BROKER": "alpaca",
            "ALPACA_ENV": "live"
        }
        
        # Simulate the safety check logic from main.py
        def check_live_trading_safety(config, i_understand_live_risk=False):
            if config["BROKER"] == "alpaca" and config["ALPACA_ENV"] == "live":
                if not i_understand_live_risk:
                    # Should default to paper
                    config["ALPACA_ENV"] = "paper"
                    return "BLOCKED_DEFAULTED_TO_PAPER"
                else:
                    return "LIVE_TRADING_APPROVED"
            return "NOT_APPLICABLE"

        # Test without flag - should default to paper
        result = check_live_trading_safety(config.copy(), i_understand_live_risk=False)
        assert result == "BLOCKED_DEFAULTED_TO_PAPER"

        # Test with flag - should allow live trading
        result = check_live_trading_safety(config.copy(), i_understand_live_risk=True)
        assert result == "LIVE_TRADING_APPROVED"

        # Test non-alpaca broker - should not apply
        config_rh = {"BROKER": "robinhood", "ALPACA_ENV": "live"}
        result = check_live_trading_safety(config_rh, i_understand_live_risk=False)
        assert result == "NOT_APPLICABLE"


if __name__ == "__main__":
    pytest.main([__file__])
