#!/usr/bin/env python3
"""
Unit tests for pre-LLM hard gate functionality.

Tests the _pre_llm_hard_gate method in MultiSymbolScanner to ensure
it properly blocks trades under various conditions.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, time as dt_time
import pytz

from utils.multi_symbol_scanner import MultiSymbolScanner


class TestPreLLMHardGate:
    """Test cases for pre-LLM hard gate functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = {
            "TIMEFRAME": "5m",
            "LOOKBACK_BARS": 20,
            "MIN_TR_RANGE_PCT": 20.0,
            "SYMBOLS": ["SPY"]
        }
        self.scanner = MultiSymbolScanner(self.config, llm_client=None)

    def test_pre_llm_gate_blocks_low_range(self):
        """Test that gate blocks trades when true range is too low."""
        # Set absurdly high minimum to force block
        config = self.config.copy()
        config["MIN_TR_RANGE_PCT"] = 1000.0  # 1000% - impossible to meet
        
        market_data = {
            "symbol": "SPY",
            "current_price": 500.0,
            "timeframe": "5m",
            "lookback_bars": 20,
            "breakout_analysis": {},
            "ha_df": [{"HA_Open": 1, "HA_Close": 1, "HA_High": 1, "HA_Low": 1}] * 10,
            "today_true_range_pct": 10.0,  # Much lower than 1000%
            "room_to_next_pivot": 0.2,
            "iv_5m": 30.0,
            "candle_body_pct": 0.05,
            "trend_direction": "NEUTRAL",
            "volume_confirmation": False,
            "support_levels": [],
            "resistance_levels": [],
            "analysis_timestamp": "2024-01-01T10:00:00"
        }
        
        proceed, reason = self.scanner._pre_llm_hard_gate(market_data, config)
        
        assert proceed is False
        assert "true_range" in reason.lower() or "range" in reason.lower()

    @patch('utils.multi_symbol_scanner.datetime')
    def test_pre_llm_gate_blocks_after_cutoff(self, mock_datetime):
        """Test that gate blocks trades after 15:15 ET cutoff."""
        # Mock current time to 15:30 ET (after cutoff)
        et_tz = pytz.timezone('US/Eastern')
        mock_et_time = datetime(2024, 1, 15, 15, 30, 0, tzinfo=et_tz)  # Monday 3:30 PM ET
        mock_datetime.now.return_value = mock_et_time
        
        market_data = {
            "symbol": "SPY",
            "today_true_range_pct": 25.0,  # Above minimum
        }
        
        proceed, reason = self.scanner._pre_llm_hard_gate(market_data, self.config)
        
        assert proceed is False
        assert "cutoff" in reason.lower()

    @patch('utils.multi_symbol_scanner.datetime')
    def test_pre_llm_gate_blocks_weekend(self, mock_datetime):
        """Test that gate blocks trades on weekends."""
        # Mock current time to Saturday
        et_tz = pytz.timezone('US/Eastern')
        mock_et_time = datetime(2024, 1, 13, 10, 0, 0, tzinfo=et_tz)  # Saturday 10:00 AM ET
        mock_datetime.now.return_value = mock_et_time
        
        market_data = {
            "symbol": "SPY",
            "today_true_range_pct": 25.0,  # Above minimum
        }
        
        proceed, reason = self.scanner._pre_llm_hard_gate(market_data, self.config)
        
        assert proceed is False
        assert "weekend" in reason.lower() or "closed" in reason.lower()

    @patch('utils.multi_symbol_scanner.datetime')
    def test_pre_llm_gate_blocks_before_open(self, mock_datetime):
        """Test that gate blocks trades before market open."""
        # Mock current time to 8:00 AM ET (before 9:30 open)
        et_tz = pytz.timezone('US/Eastern')
        mock_et_time = datetime(2024, 1, 15, 8, 0, 0, tzinfo=et_tz)  # Monday 8:00 AM ET
        mock_datetime.now.return_value = mock_et_time
        
        market_data = {
            "symbol": "SPY",
            "today_true_range_pct": 25.0,  # Above minimum
        }
        
        proceed, reason = self.scanner._pre_llm_hard_gate(market_data, self.config)
        
        assert proceed is False
        assert "before" in reason.lower() and "open" in reason.lower()

    @patch('utils.multi_symbol_scanner.datetime')
    def test_pre_llm_gate_allows_valid_conditions(self, mock_datetime):
        """Test that gate allows trades under valid conditions."""
        # Mock current time to valid trading hours
        et_tz = pytz.timezone('US/Eastern')
        mock_et_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=et_tz)  # Monday 10:30 AM ET
        mock_datetime.now.return_value = mock_et_time
        
        market_data = {
            "symbol": "SPY",
            "today_true_range_pct": 25.0,  # Above minimum (20%)
        }
        
        proceed, reason = self.scanner._pre_llm_hard_gate(market_data, self.config)
        
        assert proceed is True
        assert "passed" in reason.lower()

    def test_pre_llm_gate_respects_trade_window(self):
        """Test that gate respects user-configured trade windows."""
        config = self.config.copy()
        config["TRADE_WINDOW"] = ["10:00", "14:00"]  # 10 AM to 2 PM ET
        
        with patch('utils.multi_symbol_scanner.datetime') as mock_datetime:
            # Mock current time to 15:00 ET (outside window)
            et_tz = pytz.timezone('US/Eastern')
            mock_et_time = datetime(2024, 1, 15, 15, 0, 0, tzinfo=et_tz)  # Monday 3:00 PM ET
            mock_datetime.now.return_value = mock_et_time
            
            market_data = {
                "symbol": "SPY",
                "today_true_range_pct": 25.0,  # Above minimum
            }
            
            proceed, reason = self.scanner._pre_llm_hard_gate(market_data, config)
            
            assert proceed is False
            assert "window" in reason.lower()

    def test_pre_llm_gate_handles_errors_gracefully(self):
        """Test that gate handles errors gracefully (fail-open)."""
        # Create malformed market data that will cause errors
        market_data = None  # This will cause AttributeError
        
        proceed, reason = self.scanner._pre_llm_hard_gate(market_data, self.config)
        
        # Should fail-open (allow trade) on errors
        assert proceed is True
        assert "error" in reason.lower()

    def test_pre_llm_gate_handles_missing_true_range(self):
        """Test that gate handles missing true range data."""
        market_data = {
            "symbol": "SPY",
            # Missing today_true_range_pct
        }
        
        proceed, reason = self.scanner._pre_llm_hard_gate(market_data, self.config)
        
        # Should block due to 0.0 < 20.0 minimum
        assert proceed is False
        assert "range" in reason.lower()


if __name__ == "__main__":
    pytest.main([__file__])
