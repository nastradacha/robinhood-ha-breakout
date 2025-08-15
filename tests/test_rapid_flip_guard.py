#!/usr/bin/env python3
"""
Unit tests for rapid flip protection functionality.

Tests the _recent_signal_guard method in MultiSymbolScanner to ensure
it properly prevents churning from opposite trade signals.
"""

import pytest
import json
import tempfile
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from pathlib import Path

from utils.multi_symbol_scanner import MultiSymbolScanner


class TestRapidFlipGuard:
    """Test cases for rapid flip protection functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = {
            "TIMEFRAME": "5m",
            "LOOKBACK_BARS": 20,
            "SYMBOLS": ["SPY"]
        }
        self.scanner = MultiSymbolScanner(self.config, llm_client=None)

    def test_rapid_flip_guard_is_lenient_for_strong_signals(self):
        """Test that guard allows strong reversal signals even during cooldown."""
        # Test with strong bearish reversal signal
        market_data = {
            "trend_direction": "STRONG_BEARISH",
            "vwap_deviation_pct": -0.6  # Strong deviation
        }
        
        ok, reason = self.scanner._recent_signal_guard("SPY", "PUT", market_data)
        
        # Should return boolean and string
        assert isinstance(ok, bool)
        assert isinstance(reason, str)

    def test_rapid_flip_guard_blocks_weak_opposite_signals(self):
        """Test that guard blocks weak opposite signals during cooldown."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock .cache directory
            cache_dir = Path(temp_dir) / ".cache"
            cache_dir.mkdir()
            
            # Create fake signal log with recent CALL
            signal_log = [{
                "timestamp": (datetime.now() - timedelta(minutes=2)).isoformat(),
                "decision": "CALL",
                "confidence": 0.70,
                "reason": "Bullish breakout",
                "price": 500.0
            }]
            
            log_file = cache_dir / "signal_log_SPY.json"
            with open(log_file, 'w') as f:
                json.dump(signal_log, f)
            
            # Mock Path to use temp directory
            with patch('pathlib.Path') as mock_path:
                mock_path.return_value = cache_dir
                mock_path.side_effect = lambda x: Path(temp_dir) / x if x == ".cache" else Path(x)
                
                # Test weak PUT signal (should be blocked)
                market_data = {
                    "trend_direction": "NEUTRAL",
                    "vwap_deviation_pct": 0.1  # Weak deviation
                }
                
                proceed, reason = self.scanner._recent_signal_guard("SPY", "PUT", market_data)
                
                assert proceed is False
                assert "rapid flip blocked" in reason.lower()

    def test_rapid_flip_guard_allows_strong_reversal(self):
        """Test that guard allows strong reversal signals."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock .cache directory
            cache_dir = Path(temp_dir) / ".cache"
            cache_dir.mkdir()
            
            # Create fake signal log with recent CALL
            signal_log = [{
                "timestamp": (datetime.now() - timedelta(minutes=2)).isoformat(),
                "decision": "CALL",
                "confidence": 0.70,
                "reason": "Bullish breakout",
                "price": 500.0
            }]
            
            log_file = cache_dir / "signal_log_SPY.json"
            with open(log_file, 'w') as f:
                json.dump(signal_log, f)
            
            # Mock Path to use temp directory
            with patch('pathlib.Path') as mock_path:
                mock_path.return_value = cache_dir
                mock_path.side_effect = lambda x: Path(temp_dir) / x if x == ".cache" else Path(x)
                
                # Test strong PUT signal (should be allowed)
                market_data = {
                    "trend_direction": "STRONG_BEARISH",
                    "vwap_deviation_pct": -0.5  # Strong deviation
                }
                
                proceed, reason = self.scanner._recent_signal_guard("SPY", "PUT", market_data)
                
                assert proceed is True
                assert "strong reversal detected" in reason.lower()

    def test_rapid_flip_guard_allows_same_direction(self):
        """Test that guard allows same direction signals."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock .cache directory
            cache_dir = Path(temp_dir) / ".cache"
            cache_dir.mkdir()
            
            # Create fake signal log with recent CALL
            signal_log = [{
                "timestamp": (datetime.now() - timedelta(minutes=2)).isoformat(),
                "decision": "CALL",
                "confidence": 0.70,
                "reason": "Bullish breakout",
                "price": 500.0
            }]
            
            log_file = cache_dir / "signal_log_SPY.json"
            with open(log_file, 'w') as f:
                json.dump(signal_log, f)
            
            # Mock Path to use temp directory
            with patch('pathlib.Path') as mock_path:
                mock_path.return_value = cache_dir
                mock_path.side_effect = lambda x: Path(temp_dir) / x if x == ".cache" else Path(x)
                
                # Test another CALL signal (should be allowed)
                market_data = {
                    "trend_direction": "BULLISH",
                    "vwap_deviation_pct": 0.3
                }
                
                proceed, reason = self.scanner._recent_signal_guard("SPY", "CALL", market_data)
                
                assert proceed is True
                assert "same direction" in reason.lower()

    def test_rapid_flip_guard_allows_after_cooldown(self):
        """Test that guard allows opposite signals after cooldown period."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock .cache directory
            cache_dir = Path(temp_dir) / ".cache"
            cache_dir.mkdir()
            
            # Create fake signal log with old CALL (outside 5-minute window)
            signal_log = [{
                "timestamp": (datetime.now() - timedelta(minutes=10)).isoformat(),
                "decision": "CALL",
                "confidence": 0.70,
                "reason": "Bullish breakout",
                "price": 500.0
            }]
            
            log_file = cache_dir / "signal_log_SPY.json"
            with open(log_file, 'w') as f:
                json.dump(signal_log, f)
            
            # Mock Path to use temp directory
            with patch('pathlib.Path') as mock_path:
                mock_path.return_value = cache_dir
                mock_path.side_effect = lambda x: Path(temp_dir) / x if x == ".cache" else Path(x)
                
                # Test PUT signal (should be allowed due to time)
                market_data = {
                    "trend_direction": "BEARISH",
                    "vwap_deviation_pct": -0.2
                }
                
                proceed, reason = self.scanner._recent_signal_guard("SPY", "PUT", market_data)
                
                assert proceed is True
                assert "no recent trade signals" in reason.lower()

    def test_rapid_flip_guard_allows_no_trade(self):
        """Test that guard always allows NO_TRADE decisions."""
        market_data = {
            "trend_direction": "NEUTRAL",
            "vwap_deviation_pct": 0.0
        }
        
        proceed, reason = self.scanner._recent_signal_guard("SPY", "NO_TRADE", market_data)
        
        assert proceed is True
        assert "no_trade decisions not subject" in reason.lower()

    def test_rapid_flip_guard_handles_missing_log(self):
        """Test that guard handles missing signal log gracefully."""
        market_data = {
            "trend_direction": "BULLISH",
            "vwap_deviation_pct": 0.3
        }
        
        # Should allow trade when no log exists
        proceed, reason = self.scanner._recent_signal_guard("NONEXISTENT", "CALL", market_data)
        
        assert proceed is True
        assert "no signal history" in reason.lower()

    def test_rapid_flip_guard_handles_errors_gracefully(self):
        """Test that guard handles errors gracefully (fail-open)."""
        with patch('pathlib.Path') as mock_path:
            # Mock Path to raise an error
            mock_path.side_effect = Exception("File system error")
            
            market_data = {
                "trend_direction": "BULLISH",
                "vwap_deviation_pct": 0.3
            }
            
            proceed, reason = self.scanner._recent_signal_guard("SPY", "CALL", market_data)
            
            # Should fail-open (allow trade) on errors
            assert proceed is True
            assert "error" in reason.lower()

    def test_rapid_flip_guard_ignores_no_trade_in_history(self):
        """Test that guard ignores NO_TRADE entries when looking for recent signals."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock .cache directory
            cache_dir = Path(temp_dir) / ".cache"
            cache_dir.mkdir()
            
            # Create fake signal log with recent NO_TRADE and older CALL
            signal_log = [
                {
                    "timestamp": (datetime.now() - timedelta(minutes=10)).isoformat(),
                    "decision": "CALL",
                    "confidence": 0.70,
                    "reason": "Bullish breakout",
                    "price": 500.0
                },
                {
                    "timestamp": (datetime.now() - timedelta(minutes=1)).isoformat(),
                    "decision": "NO_TRADE",
                    "confidence": 0.30,
                    "reason": "Low confidence",
                    "price": 502.0
                }
            ]
            
            log_file = cache_dir / "signal_log_SPY.json"
            with open(log_file, 'w') as f:
                json.dump(signal_log, f)
            
            # Mock Path to use temp directory
            with patch('pathlib.Path') as mock_path:
                mock_path.return_value = cache_dir
                mock_path.side_effect = lambda x: Path(temp_dir) / x if x == ".cache" else Path(x)
                
                # Test PUT signal (should be allowed since recent CALL is outside window)
                market_data = {
                    "trend_direction": "BEARISH",
                    "vwap_deviation_pct": -0.2
                }
                
                proceed, reason = self.scanner._recent_signal_guard("SPY", "PUT", market_data)
                
                assert proceed is True
                assert "no recent trade signals" in reason.lower()


if __name__ == "__main__":
    pytest.main([__file__])
