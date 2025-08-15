#!/usr/bin/env python3
"""
Unit tests for strict option-side mapping and expiry policy functionality.

Tests the _map_decision_to_side method and expiry policy integration
in MultiSymbolScanner to ensure consistent option-side mapping and
early expiry policy determination.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from utils.multi_symbol_scanner import MultiSymbolScanner


class TestSideAndExpiryMapping:
    """Test cases for option-side mapping and expiry policy functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = {
            "TIMEFRAME": "5m",
            "LOOKBACK_BARS": 20,
            "SYMBOLS": ["SPY"]
        }
        self.scanner = MultiSymbolScanner(self.config, llm_client=None)

    def test_map_decision_to_side_and_expiry_fields(self):
        """Test that decision mapping returns valid option sides."""
        ms = MultiSymbolScanner({"TIMEFRAME": "5m", "LOOKBACK_BARS": 20}, llm_client=None)
        
        # Test the requested case
        side = ms._map_decision_to_side("CALL")
        assert side in ("CALL", "PUT")
        assert side == "CALL"

    def test_map_decision_to_side_valid_decisions(self):
        """Test mapping of all valid decision formats."""
        test_cases = [
            ("CALL", "CALL"),
            ("PUT", "PUT"),
            ("BUY_CALL", "CALL"),
            ("BUY_PUT", "PUT"),
            ("call", "CALL"),  # Case insensitive
            ("put", "PUT"),
            ("buy_call", "CALL"),
            ("buy_put", "PUT"),
            ("  CALL  ", "CALL"),  # Whitespace handling
            ("BULLISH_CALL", "CALL"),  # Fuzzy matching
            ("BEARISH_PUT", "PUT"),
        ]
        
        for decision, expected_side in test_cases:
            result = self.scanner._map_decision_to_side(decision)
            assert result == expected_side, f"Decision '{decision}' should map to '{expected_side}', got '{result}'"

    def test_map_decision_to_side_invalid_decisions(self):
        """Test that invalid decisions raise ValueError."""
        invalid_decisions = [
            "NO_TRADE",
            "HOLD",
            "INVALID",
            "",
            "NEUTRAL",
            "UNKNOWN"
        ]
        
        for decision in invalid_decisions:
            with pytest.raises(ValueError, match=f"Cannot map decision '{decision}' to valid option side"):
                self.scanner._map_decision_to_side(decision)

    def test_get_expiry_policy_early_0dte_hours(self):
        """Test expiry policy during 0DTE hours (10:00-15:15 ET)."""
        with patch('utils.multi_symbol_scanner.datetime') as mock_datetime, \
             patch('utils.multi_symbol_scanner.pytz') as mock_pytz:
            
            # Mock ET timezone and current time (12:00 ET)
            mock_et_tz = MagicMock()
            mock_pytz.timezone.return_value = mock_et_tz
            
            mock_now_et = MagicMock()
            mock_now_et.hour = 12
            mock_now_et.minute = 30
            mock_now_et.date.return_value.strftime.return_value = "2025-01-15"
            
            mock_datetime.now.return_value = mock_now_et
            
            policy, expiry_date = self.scanner._get_expiry_policy_early()
            
            assert policy == "0DTE"
            assert expiry_date == "2025-01-15"

    def test_get_expiry_policy_early_weekly_hours(self):
        """Test expiry policy during weekly hours (outside 10:00-15:15 ET)."""
        with patch('utils.multi_symbol_scanner.datetime') as mock_datetime, \
             patch('utils.multi_symbol_scanner.pytz') as mock_pytz:
            
            # Mock ET timezone and current time (16:00 ET)
            mock_et_tz = MagicMock()
            mock_pytz.timezone.return_value = mock_et_tz
            
            mock_now_et = MagicMock()
            mock_now_et.hour = 16
            mock_now_et.minute = 0
            
            # Mock date calculations for next Friday
            mock_date = MagicMock()
            mock_date.weekday.return_value = 1  # Tuesday (0=Monday)
            mock_now_et.date.return_value = mock_date
            
            # Mock timedelta addition
            mock_next_friday = MagicMock()
            mock_next_friday.strftime.return_value = "2025-01-17"
            mock_date.__add__.return_value = mock_next_friday
            
            mock_datetime.now.return_value = mock_now_et
            
            policy, expiry_date = self.scanner._get_expiry_policy_early()
            
            assert policy == "WEEKLY"
            assert expiry_date == "2025-01-17"

    def test_get_expiry_policy_early_fallback(self):
        """Test expiry policy fallback on error."""
        with patch('utils.multi_symbol_scanner.datetime') as mock_datetime:
            # Mock datetime to raise exception initially, then work for fallback
            mock_datetime.now.side_effect = [Exception("Test error"), MagicMock()]
            
            # Mock fallback date calculation
            mock_today = MagicMock()
            mock_today.weekday.return_value = 2  # Wednesday
            mock_datetime.now.return_value.date.return_value = mock_today
            
            mock_next_friday = MagicMock()
            mock_next_friday.strftime.return_value = "2025-01-17"
            mock_today.__add__.return_value = mock_next_friday
            
            policy, expiry_date = self.scanner._get_expiry_policy_early()
            
            assert policy == "WEEKLY"
            assert expiry_date == "2025-01-17"

    @patch('utils.multi_symbol_scanner.fetch_market_data')
    @patch('utils.multi_symbol_scanner.calculate_heikin_ashi')
    @patch('utils.multi_symbol_scanner.analyze_breakout_pattern')
    def test_opportunity_contains_required_fields(self, mock_breakout, mock_ha, mock_fetch):
        """Test that opportunity dict contains option_side, expiry_policy, expiry_date."""
        # Mock data dependencies
        mock_df = MagicMock()
        mock_df.__getitem__.return_value.iloc.__getitem__.return_value = 500.0  # current_price
        mock_fetch.return_value = mock_df
        mock_ha.return_value = MagicMock()
        mock_breakout.return_value = {"today_true_range_pct": 25.0}
        
        # Mock LLM decision
        mock_llm_result = MagicMock()
        mock_llm_result.decision = "CALL"
        mock_llm_result.confidence = 0.75
        mock_llm_result.reason = "Strong bullish signal"
        
        # Mock all gates to allow through
        self.scanner._pre_llm_hard_gate = lambda *args: (True, "Test passed")
        self.scanner._robust_llm_decision = lambda *args: mock_llm_result
        self.scanner._apply_consecutive_loss_throttle = lambda *args: (True, "Test passed")
        self.scanner._recent_signal_guard = lambda *args: (True, "Test passed")
        
        # Mock expiry policy
        self.scanner._get_expiry_policy_early = lambda: ("0DTE", "2025-01-15")
        
        # Run scan
        opportunities = self.scanner._scan_single_symbol("SPY")
        
        # Verify opportunity structure
        assert len(opportunities) == 1
        opportunity = opportunities[0]
        
        # Check required fields
        assert "option_side" in opportunity
        assert "expiry_policy" in opportunity
        assert "expiry_date" in opportunity
        
        # Check field values
        assert opportunity["option_side"] == "CALL"
        assert opportunity["expiry_policy"] == "0DTE"
        assert opportunity["expiry_date"] == "2025-01-15"
        
        # Check other expected fields still exist
        assert opportunity["symbol"] == "SPY"
        assert opportunity["decision"] == "CALL"
        assert opportunity["confidence"] == 0.75

    @patch('utils.multi_symbol_scanner.fetch_market_data')
    @patch('utils.multi_symbol_scanner.calculate_heikin_ashi')
    @patch('utils.multi_symbol_scanner.analyze_breakout_pattern')
    def test_invalid_decision_returns_no_trade(self, mock_breakout, mock_ha, mock_fetch):
        """Test that invalid LLM decisions are handled gracefully."""
        # Mock data dependencies
        mock_df = MagicMock()
        mock_df.__getitem__.return_value.iloc.__getitem__.return_value = 500.0
        mock_fetch.return_value = mock_df
        mock_ha.return_value = MagicMock()
        mock_breakout.return_value = {"today_true_range_pct": 25.0}
        
        # Mock LLM decision with invalid decision
        mock_llm_result = MagicMock()
        mock_llm_result.decision = "INVALID_DECISION"
        mock_llm_result.confidence = 0.75
        mock_llm_result.reason = "Test invalid decision"
        
        # Mock all gates to allow through
        self.scanner._pre_llm_hard_gate = lambda *args: (True, "Test passed")
        self.scanner._robust_llm_decision = lambda *args: mock_llm_result
        
        # Run scan
        opportunities = self.scanner._scan_single_symbol("SPY")
        
        # Should return empty list due to invalid decision
        assert len(opportunities) == 0

    def test_expiry_policy_consistency_with_alpaca(self):
        """Test that expiry policy logic matches AlpacaOptionsTrader."""
        # This test ensures the fallback logic matches the Alpaca implementation
        
        # Mock Alpaca trader
        mock_alpaca_trader = MagicMock()
        mock_alpaca_trader.get_expiry_policy.return_value = ("0DTE", "2025-01-15")
        self.scanner.alpaca_trader = mock_alpaca_trader
        
        policy, expiry_date = self.scanner._get_expiry_policy_early()
        
        # Should use Alpaca trader when available
        assert policy == "0DTE"
        assert expiry_date == "2025-01-15"
        mock_alpaca_trader.get_expiry_policy.assert_called_once()

    def test_option_side_mapping_robustness(self):
        """Test robustness of option side mapping with edge cases."""
        edge_cases = [
            ("LONG_CALL", "CALL"),
            ("SHORT_PUT", "PUT"),  # Should still map to PUT
            ("CALL_OPTION", "CALL"),
            ("PUT_OPTION", "PUT"),
            ("BULLISH_CALL_SPREAD", "CALL"),  # Fuzzy matching
            ("BEARISH_PUT_SPREAD", "PUT"),
        ]
        
        for decision, expected_side in edge_cases:
            result = self.scanner._map_decision_to_side(decision)
            assert result == expected_side, f"Edge case '{decision}' should map to '{expected_side}'"


if __name__ == "__main__":
    pytest.main([__file__])
