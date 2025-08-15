#!/usr/bin/env python3
"""
Unit tests for deterministic priority score functionality.

Tests the _calculate_priority_score method in MultiSymbolScanner to ensure
it produces consistent, deterministic rankings for multi-symbol trading.
"""

import pytest
from utils.multi_symbol_scanner import MultiSymbolScanner


class TestPriorityScore:
    """Test cases for deterministic priority score functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = {
            "TIMEFRAME": "5m",
            "LOOKBACK_BARS": 20,
            "SYMBOLS": ["SPY"]
        }
        self.scanner = MultiSymbolScanner(self.config, llm_client=None)

    def test_priority_score_determinism(self):
        """Test that priority score calculation is deterministic."""
        # Test data with all components
        breakout_analysis = {
            "vwap_deviation_pct": 0.6,
            "room_to_next_pivot": 0.7,
            "trend_direction": "STRONG_BULLISH",
            "volume_confirmation": True
        }
        
        # Calculate score multiple times
        score1 = self.scanner._calculate_priority_score("SPY", 0.7, breakout_analysis)
        score2 = self.scanner._calculate_priority_score("SPY", 0.7, breakout_analysis)
        
        # Should be identical (deterministic)
        assert abs(score1 - score2) < 1e-9
        
        # Should be in valid range
        assert 0.0 <= score1 <= 1.0
        assert 0.0 <= score2 <= 1.0

    def test_priority_score_formula_correctness(self):
        """Test that priority score follows the documented formula."""
        breakout_analysis = {
            "vwap_deviation_pct": 0.5,  # Will be capped at 1.0, contributes 0.20 * 0.5 = 0.10
            "room_to_next_pivot": 0.8,  # Contributes 0.15 * 0.8 = 0.12
            "trend_direction": "STRONG_BEARISH",  # Contributes 0.10 * 1.0 = 0.10
            "volume_confirmation": True  # Contributes 0.05 * 1.0 = 0.05
        }
        
        confidence = 0.6  # Contributes 0.50 * 0.6 = 0.30
        
        expected_score = 0.30 + 0.10 + 0.12 + 0.10 + 0.05  # = 0.67
        actual_score = self.scanner._calculate_priority_score("SPY", confidence, breakout_analysis)
        
        assert abs(actual_score - expected_score) < 1e-6

    def test_priority_score_component_weights(self):
        """Test that each component contributes the correct weight."""
        # Test confidence component (50% weight)
        breakout_analysis = {"vwap_deviation_pct": 0.0, "room_to_next_pivot": 0.0, 
                           "trend_direction": "NEUTRAL", "volume_confirmation": False}
        
        score_conf_0 = self.scanner._calculate_priority_score("SPY", 0.0, breakout_analysis)
        score_conf_1 = self.scanner._calculate_priority_score("SPY", 1.0, breakout_analysis)
        
        # Difference should be 0.50 (50% weight)
        assert abs((score_conf_1 - score_conf_0) - 0.50) < 1e-6

    def test_priority_score_vwap_deviation_capping(self):
        """Test that VWAP deviation is properly capped at 1.0."""
        breakout_analysis_normal = {
            "vwap_deviation_pct": 0.5,  # Normal deviation
            "room_to_next_pivot": 0.0,
            "trend_direction": "NEUTRAL",
            "volume_confirmation": False
        }
        
        breakout_analysis_extreme = {
            "vwap_deviation_pct": 5.0,  # Extreme deviation (should be capped)
            "room_to_next_pivot": 0.0,
            "trend_direction": "NEUTRAL",
            "volume_confirmation": False
        }
        
        score_normal = self.scanner._calculate_priority_score("SPY", 0.5, breakout_analysis_normal)
        score_extreme = self.scanner._calculate_priority_score("SPY", 0.5, breakout_analysis_extreme)
        
        # Extreme should be capped, so difference should be limited
        vwap_diff = score_extreme - score_normal
        expected_max_diff = 0.20 * (1.0 - 0.5)  # 20% weight * (1.0 - 0.5) = 0.10
        assert abs(vwap_diff - expected_max_diff) < 1e-6

    def test_priority_score_strong_trend_detection(self):
        """Test that strong trends are properly detected."""
        base_analysis = {
            "vwap_deviation_pct": 0.0,
            "room_to_next_pivot": 0.0,
            "volume_confirmation": False
        }
        
        # Test different trend strengths
        trends_and_expected = [
            ("NEUTRAL", 0.0),
            ("BULLISH", 0.0),  # Not strong
            ("BEARISH", 0.0),  # Not strong
            ("STRONG_BULLISH", 0.10),  # Strong = 10% weight
            ("STRONG_BEARISH", 0.10),  # Strong = 10% weight
        ]
        
        base_score = self.scanner._calculate_priority_score("SPY", 0.5, 
                                                          {**base_analysis, "trend_direction": "NEUTRAL"})
        
        for trend, expected_bonus in trends_and_expected:
            analysis = {**base_analysis, "trend_direction": trend}
            score = self.scanner._calculate_priority_score("SPY", 0.5, analysis)
            actual_bonus = score - base_score
            assert abs(actual_bonus - expected_bonus) < 1e-6, f"Trend {trend} bonus mismatch"

    def test_priority_score_volume_confirmation(self):
        """Test that volume confirmation contributes correct weight."""
        base_analysis = {
            "vwap_deviation_pct": 0.0,
            "room_to_next_pivot": 0.0,
            "trend_direction": "NEUTRAL"
        }
        
        score_no_volume = self.scanner._calculate_priority_score("SPY", 0.5, 
                                                               {**base_analysis, "volume_confirmation": False})
        score_with_volume = self.scanner._calculate_priority_score("SPY", 0.5, 
                                                                 {**base_analysis, "volume_confirmation": True})
        
        # Volume confirmation should add 5% weight
        volume_bonus = score_with_volume - score_no_volume
        assert abs(volume_bonus - 0.05) < 1e-6

    def test_priority_score_handles_missing_fields(self):
        """Test that missing fields are handled gracefully with defaults."""
        # Empty breakout analysis
        empty_analysis = {}
        
        score = self.scanner._calculate_priority_score("SPY", 0.7, empty_analysis)
        
        # Should only get confidence component (50% * 0.7 = 0.35)
        expected_score = 0.50 * 0.7
        assert abs(score - expected_score) < 1e-6
        
        # Should be in valid range
        assert 0.0 <= score <= 1.0

    def test_priority_score_handles_invalid_confidence(self):
        """Test that invalid confidence values are clamped."""
        breakout_analysis = {
            "vwap_deviation_pct": 0.0,
            "room_to_next_pivot": 0.0,
            "trend_direction": "NEUTRAL",
            "volume_confirmation": False
        }
        
        # Test confidence > 1.0 (should be clamped to 1.0)
        score_high = self.scanner._calculate_priority_score("SPY", 1.5, breakout_analysis)
        score_normal = self.scanner._calculate_priority_score("SPY", 1.0, breakout_analysis)
        assert abs(score_high - score_normal) < 1e-6
        
        # Test confidence < 0.0 (should be clamped to 0.0)
        score_low = self.scanner._calculate_priority_score("SPY", -0.5, breakout_analysis)
        score_zero = self.scanner._calculate_priority_score("SPY", 0.0, breakout_analysis)
        assert abs(score_low - score_zero) < 1e-6

    def test_priority_score_range_bounds(self):
        """Test that priority score is always in [0, 1] range."""
        # Test maximum possible score
        max_analysis = {
            "vwap_deviation_pct": 10.0,  # Will be capped
            "room_to_next_pivot": 10.0,  # Will be capped
            "trend_direction": "STRONG_BULLISH",
            "volume_confirmation": True
        }
        
        max_score = self.scanner._calculate_priority_score("SPY", 1.0, max_analysis)
        assert 0.0 <= max_score <= 1.0
        
        # Test minimum possible score
        min_analysis = {
            "vwap_deviation_pct": 0.0,
            "room_to_next_pivot": 0.0,
            "trend_direction": "NEUTRAL",
            "volume_confirmation": False
        }
        
        min_score = self.scanner._calculate_priority_score("SPY", 0.0, min_analysis)
        assert 0.0 <= min_score <= 1.0
        assert min_score == 0.0  # Should be exactly 0.0

    def test_priority_score_ordering_consistency(self):
        """Test that higher technical strength produces higher scores."""
        confidence = 0.7
        
        weak_analysis = {
            "vwap_deviation_pct": 0.1,
            "room_to_next_pivot": 0.2,
            "trend_direction": "NEUTRAL",
            "volume_confirmation": False
        }
        
        strong_analysis = {
            "vwap_deviation_pct": 0.8,
            "room_to_next_pivot": 0.9,
            "trend_direction": "STRONG_BULLISH",
            "volume_confirmation": True
        }
        
        weak_score = self.scanner._calculate_priority_score("SPY", confidence, weak_analysis)
        strong_score = self.scanner._calculate_priority_score("SPY", confidence, strong_analysis)
        
        # Strong setup should have higher score
        assert strong_score > weak_score


if __name__ == "__main__":
    pytest.main([__file__])
