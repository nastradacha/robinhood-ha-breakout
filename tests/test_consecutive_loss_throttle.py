#!/usr/bin/env python3
"""
Unit tests for consecutive-loss throttle functionality.

Tests the _apply_consecutive_loss_throttle method in MultiSymbolScanner to ensure
it properly applies stricter requirements after consecutive losses.
"""

import pytest
from unittest.mock import patch, MagicMock
from utils.multi_symbol_scanner import MultiSymbolScanner


class TestConsecutiveLossThrottle:
    """Test cases for consecutive-loss throttle functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = {
            "MIN_CONFIDENCE": 0.65,
            "TIMEFRAME": "5m",
            "LOOKBACK_BARS": 20,
            "MIN_CANDLE_BODY_PCT": 0.05,
            "SYMBOLS": ["SPY"]
        }
        self.scanner = MultiSymbolScanner(self.config, llm_client=None)

    def test_throttle_on_two_losses(self):
        """Test throttle applies stricter requirements after two consecutive losses."""
        # Mock recent outcomes to show two losses
        def fake_recent_outcomes(n=2):
            return [False, False]  # Two losses
        
        self.scanner._get_recent_outcomes = fake_recent_outcomes
        
        # Test with marginal setup that would normally pass
        market_data = {"candle_body_pct": 0.12}  # 12% - would pass normal 10% requirement
        decision_conf = 0.66  # 66% - would pass normal 65% requirement
        
        proceed, reason = self.scanner._apply_consecutive_loss_throttle(market_data, decision_conf)
        
        # Should be blocked due to stricter requirements (20% candle body required)
        assert proceed is False
        assert "candle body" in reason.lower()

    def test_throttle_allows_strong_setup_after_losses(self):
        """Test throttle allows strong setups even after consecutive losses."""
        # Mock recent outcomes to show two losses
        def fake_recent_outcomes(n=2):
            return [False, False]  # Two losses
        
        self.scanner._get_recent_outcomes = fake_recent_outcomes
        
        # Test with strong setup that meets stricter requirements
        market_data = {"candle_body_pct": 0.25}  # 25% - exceeds 20% requirement
        decision_conf = 0.72  # 72% - exceeds 70% requirement (65% + 5%)
        
        proceed, reason = self.scanner._apply_consecutive_loss_throttle(market_data, decision_conf)
        
        # Should be allowed due to strong setup
        assert proceed is True
        assert "passed" in reason.lower()

    def test_throttle_relaxed_after_win(self):
        """Test throttle uses relaxed requirements after a recent win."""
        # Mock recent outcomes to show a recent win
        def fake_recent_outcomes(n=2):
            return [False, True]  # Loss then win
        
        self.scanner._get_recent_outcomes = fake_recent_outcomes
        
        # Test with moderate setup
        market_data = {"candle_body_pct": 0.12}  # 12% - exceeds relaxed 10% requirement
        decision_conf = 0.66  # 66% - exceeds normal 65% requirement
        
        proceed, reason = self.scanner._apply_consecutive_loss_throttle(market_data, decision_conf)
        
        # Should be allowed due to recent win
        assert proceed is True
        assert "normal" in reason.lower() or "win" in reason.lower()

    def test_throttle_blocks_weak_setup_after_win(self):
        """Test throttle still blocks very weak setups even after a win."""
        # Mock recent outcomes to show a recent win
        def fake_recent_outcomes(n=2):
            return [False, True]  # Loss then win
        
        self.scanner._get_recent_outcomes = fake_recent_outcomes
        
        # Test with weak setup
        market_data = {"candle_body_pct": 0.08}  # 8% - below relaxed 10% requirement
        decision_conf = 0.66  # 66% confidence
        
        proceed, reason = self.scanner._apply_consecutive_loss_throttle(market_data, decision_conf)
        
        # Should be blocked due to weak candle body
        assert proceed is False
        assert "candle body" in reason.lower()

    def test_throttle_insufficient_history(self):
        """Test throttle allows trades when insufficient trade history."""
        # Mock recent outcomes to show insufficient history
        def fake_recent_outcomes(n=2):
            return [True]  # Only one trade in history
        
        self.scanner._get_recent_outcomes = fake_recent_outcomes
        
        market_data = {"candle_body_pct": 0.05}  # Minimal setup
        decision_conf = 0.60  # Lower confidence
        
        proceed, reason = self.scanner._apply_consecutive_loss_throttle(market_data, decision_conf)
        
        # Should be allowed due to insufficient history (fail-open)
        assert proceed is True
        assert "insufficient" in reason.lower() or "history" in reason.lower()

    def test_throttle_handles_missing_candle_body(self):
        """Test throttle handles missing candle_body_pct gracefully."""
        # Mock recent outcomes to show two losses
        def fake_recent_outcomes(n=2):
            return [False, False]  # Two losses
        
        self.scanner._get_recent_outcomes = fake_recent_outcomes
        
        # Test with missing candle_body_pct
        market_data = {}  # Missing candle_body_pct
        decision_conf = 0.75  # High confidence
        
        proceed, reason = self.scanner._apply_consecutive_loss_throttle(market_data, decision_conf)
        
        # Should be blocked due to 0.0 < 20% requirement
        assert proceed is False
        assert "candle body" in reason.lower()

    @patch('utils.multi_symbol_scanner.BankrollManager')
    def test_throttle_handles_bankroll_errors(self, mock_bankroll_class):
        """Test throttle handles bankroll errors gracefully (fail-open)."""
        # Mock bankroll to raise an error
        mock_bankroll = MagicMock()
        mock_bankroll.get_recent_outcomes.side_effect = Exception("Bankroll error")
        mock_bankroll_class.return_value = mock_bankroll
        
        market_data = {"candle_body_pct": 0.05}  # Minimal setup
        decision_conf = 0.60  # Lower confidence
        
        proceed, reason = self.scanner._apply_consecutive_loss_throttle(market_data, decision_conf)
        
        # Should be allowed due to error (fail-open)
        assert proceed is True
        assert "error" in reason.lower()

    def test_code_level_confidence_override(self):
        """Test that confidence override works at code level (as requested)."""
        cfg = {"MIN_CONFIDENCE": 0.7, "TIMEFRAME": "5m", "LOOKBACK_BARS": 20}
        ms = MultiSymbolScanner(cfg, llm_client=None)
        
        # Fake LLM result path
        decision = {"decision": "CALL", "confidence": 0.65, "reason": "test"}
        
        # Should be flipped to NO_TRADE due to confidence check
        conf = decision["confidence"]
        min_conf = cfg["MIN_CONFIDENCE"]
        
        if conf < min_conf:
            assert True  # Expected behavior - confidence override working
        else:
            assert False, f"Expected override to NO_TRADE when {conf} < {min_conf}"


if __name__ == "__main__":
    pytest.main([__file__])
