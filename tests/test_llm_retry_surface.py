#!/usr/bin/env python3
"""
Unit tests for LLM retry and error handling functionality.

Tests the _robust_llm_decision method in MultiSymbolScanner to ensure
it properly handles LLM errors with retry logic and transparent reasons.
"""

import pytest
from unittest.mock import patch, MagicMock
from utils.multi_symbol_scanner import MultiSymbolScanner
from utils.llm import TradeDecision


class TestLLMRetryAndErrorHandling:
    """Test cases for LLM retry and error handling functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = {
            "TIMEFRAME": "5m",
            "LOOKBACK_BARS": 20,
            "SYMBOLS": ["SPY"]
        }
        self.scanner = MultiSymbolScanner(self.config, llm_client=None)

    def test_llm_error_returns_no_trade_not_exception(self):
        """Test that LLM errors return NO_TRADE instead of raising exceptions."""
        # Test market data with all required fields
        market_data = {
            "symbol": "SPY", 
            "current_price": 500.0,
            "today_true_range_pct": 25.0,
            "room_to_next_pivot": 1.0,
            "iv_5m": 30.0,
            "candle_body_pct": 15.0,
            "trend_direction": "BULLISH",
            "volume_confirmation": True,
            "support_levels": [495, 490],
            "resistance_levels": [505, 510]
        }
        
        # Should return TradeDecision with NO_TRADE, not raise exception
        result = self.scanner._robust_llm_decision(market_data, "SPY")
        
        # Verify it's a TradeDecision object with NO_TRADE
        assert hasattr(result, "decision")
        assert result.decision == "NO_TRADE"
        assert hasattr(result, "confidence")
        assert result.confidence == 0.0
        assert hasattr(result, "reason")
        assert "LLM_ERROR" in result.reason

    @patch('utils.multi_symbol_scanner.LLMClient')
    def test_llm_retry_logic_with_transient_errors(self, mock_llm_class):
        """Test that transient errors trigger retry logic."""
        # Mock LLM that fails twice then succeeds
        mock_llm = MagicMock()
        mock_llm_class.return_value = mock_llm
        
        call_count = 0
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise RuntimeError("Transient error")
            return TradeDecision(decision="CALL", confidence=0.75, reason="Success on retry")
        
        mock_llm.make_trade_decision.side_effect = side_effect
        
        market_data = {"symbol": "SPY", "current_price": 500.0}
        
        # Should succeed after retries
        result = self.scanner._robust_llm_decision(market_data, "SPY")
        
        assert result.decision == "CALL"
        assert result.confidence == 0.75
        assert call_count == 3  # Failed twice, succeeded on third attempt

    @patch('utils.multi_symbol_scanner.LLMClient')
    def test_llm_exhausted_retries_returns_no_trade(self, mock_llm_class):
        """Test that exhausted retries return NO_TRADE with transparent reason."""
        # Mock LLM that always fails
        mock_llm = MagicMock()
        mock_llm_class.return_value = mock_llm
        mock_llm.make_trade_decision.side_effect = RuntimeError("Persistent error")
        
        market_data = {"symbol": "SPY", "current_price": 500.0}
        
        # Should return NO_TRADE after exhausting retries
        result = self.scanner._robust_llm_decision(market_data, "SPY", retries=2)
        
        assert result.decision == "NO_TRADE"
        assert result.confidence == 0.0
        assert "LLM_ERROR" in result.reason
        assert "Persistent error" in result.reason
        assert "after 3 attempts" in result.reason

    @patch('utils.multi_symbol_scanner.LLMClient')
    @patch('utils.multi_symbol_scanner.time.sleep')
    def test_llm_rate_limit_handling(self, mock_sleep, mock_llm_class):
        """Test that rate limit errors trigger special handling."""
        # Mock LLM that raises rate limit error then succeeds
        mock_llm = MagicMock()
        mock_llm_class.return_value = mock_llm
        
        call_count = 0
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Rate limit exceeded")
            return TradeDecision(decision="PUT", confidence=0.65, reason="Success after rate limit")
        
        mock_llm.make_trade_decision.side_effect = side_effect
        
        market_data = {"symbol": "QQQ", "current_price": 400.0}
        
        # Should succeed after rate limit handling
        result = self.scanner._robust_llm_decision(market_data, "QQQ")
        
        assert result.decision == "PUT"
        assert result.confidence == 0.65
        
        # Should have called sleep for rate limit backoff
        assert mock_sleep.called

    @patch('utils.multi_symbol_scanner.LLMClient')
    def test_llm_successful_first_attempt(self, mock_llm_class):
        """Test that successful LLM calls work without retries."""
        # Mock LLM that succeeds immediately
        mock_llm = MagicMock()
        mock_llm_class.return_value = mock_llm
        mock_llm.make_trade_decision.return_value = TradeDecision(
            decision="CALL", confidence=0.80, reason="Strong bullish signal"
        )
        
        market_data = {"symbol": "IWM", "current_price": 220.0}
        
        # Should succeed on first attempt
        result = self.scanner._robust_llm_decision(market_data, "IWM")
        
        assert result.decision == "CALL"
        assert result.confidence == 0.80
        assert result.reason == "Strong bullish signal"
        
        # Should only be called once (no retries)
        assert mock_llm.make_trade_decision.call_count == 1

    @patch('utils.multi_symbol_scanner.LLMClient')
    def test_llm_error_reason_transparency(self, mock_llm_class):
        """Test that error reasons are transparent and properly formatted."""
        # Mock LLM that raises specific error
        mock_llm = MagicMock()
        mock_llm_class.return_value = mock_llm
        mock_llm.make_trade_decision.side_effect = ValueError("Invalid input format")
        
        market_data = {"symbol": "UVXY", "current_price": 15.0}
        
        # Should return NO_TRADE with transparent error reason
        result = self.scanner._robust_llm_decision(market_data, "UVXY", retries=1)
        
        assert result.decision == "NO_TRADE"
        assert result.confidence == 0.0
        
        # Check reason format: "LLM_ERROR: {error} (after X attempts)"
        assert result.reason.startswith("LLM_ERROR:")
        assert "Invalid input format" in result.reason
        assert "after 2 attempts" in result.reason

    def test_llm_robust_decision_used_in_scan_single_symbol(self):
        """Test that _robust_llm_decision is used in the main scanning path."""
        # This test verifies that the robust retry logic is actually used
        # by checking that _scan_single_symbol calls _robust_llm_decision
        
        # Mock the _robust_llm_decision method
        original_method = self.scanner._robust_llm_decision
        call_count = 0
        
        def mock_robust_decision(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return TradeDecision(decision="NO_TRADE", confidence=0.0, reason="Test")
        
        self.scanner._robust_llm_decision = mock_robust_decision
        
        # Mock other dependencies
        with patch('utils.multi_symbol_scanner.fetch_market_data') as mock_fetch, \
             patch('utils.multi_symbol_scanner.calculate_heikin_ashi') as mock_ha, \
             patch('utils.multi_symbol_scanner.analyze_breakout_pattern') as mock_breakout:
            
            # Setup mocks
            mock_fetch.return_value = MagicMock()
            mock_ha.return_value = MagicMock()
            mock_breakout.return_value = {"today_true_range_pct": 25.0}
            
            # Mock pre-LLM gates to allow through
            self.scanner._pre_llm_hard_gate = lambda *args: (True, "Test passed")
            self.scanner._apply_consecutive_loss_throttle = lambda *args: (True, "Test passed")
            self.scanner._recent_signal_guard = lambda *args: (True, "Test passed")
            
            try:
                # Call _scan_single_symbol
                result = self.scanner._scan_single_symbol("SPY")
                
                # Should have called _robust_llm_decision
                assert call_count > 0, "_robust_llm_decision was not called"
                
            except Exception as e:
                # Even if scan fails for other reasons, robust decision should be called
                assert call_count > 0, f"_robust_llm_decision was not called before error: {e}"
        
        # Restore original method
        self.scanner._robust_llm_decision = original_method


if __name__ == "__main__":
    pytest.main([__file__])
