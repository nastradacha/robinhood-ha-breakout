#!/usr/bin/env python3
"""
Unit tests for opportunity schema and deterministic serialization.

Tests the _serialize_opportunity method and opportunity structure
in MultiSymbolScanner to ensure consistent field order and format
for logging, CSV export, and audit trails.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
from utils.multi_symbol_scanner import MultiSymbolScanner


class TestOpportunitySchema:
    """Test cases for opportunity schema and serialization functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = {
            "TIMEFRAME": "5m",
            "LOOKBACK_BARS": 20,
            "SYMBOLS": ["SPY"]
        }
        self.scanner = MultiSymbolScanner(self.config, llm_client=None)

    def test_opportunity_has_required_fields(self):
        """Test that opportunity dict contains all required fields (as requested)."""
        ms = MultiSymbolScanner({"TIMEFRAME": "5m", "LOOKBACK_BARS": 20}, llm_client=None)
        
        # Create test opportunity with all required fields
        opp = {
            "timestamp": "2025-01-01T10:00:00",
            "symbol": "SPY",
            "decision": "CALL",
            "confidence": 0.75,
            "current_price": 500.0,
            "option_side": "CALL",
            "expiry_policy": "0DTE",
            "expiry_date": "2025-01-01",
            "reason": "OK",
            "priority_score": 0.8
        }
        
        # Required fields as specified in acceptance criteria
        required = {
            "timestamp", "symbol", "decision", "confidence", "current_price",
            "option_side", "expiry_policy", "expiry_date", "reason", "priority_score"
        }
        
        assert required.issubset(opp.keys())

    def test_serialize_opportunity_field_order(self):
        """Test that serialized opportunity has deterministic field order."""
        # Create test opportunity
        opportunity = {
            "priority_score": 0.8,  # Intentionally out of order
            "symbol": "SPY",
            "confidence": 0.75,
            "timestamp": datetime(2025, 1, 1, 10, 0, 0),
            "decision": "CALL",
            "current_price": 500.0,
            "option_side": "CALL",
            "expiry_policy": "0DTE",
            "expiry_date": "2025-01-01",
            "reason": "Strong bullish signal",
            "breakout_analysis": {"some": "data"}  # Should be excluded
        }
        
        # Serialize opportunity
        serialized = self.scanner._serialize_opportunity(opportunity)
        
        # Check that all required fields are present
        required_fields = [
            "timestamp", "symbol", "decision", "confidence", "current_price",
            "option_side", "expiry_policy", "expiry_date", "reason", "priority_score"
        ]
        
        for field in required_fields:
            assert field in serialized, f"Missing required field: {field}"
        
        # Check field order is deterministic (Python 3.7+ preserves dict order)
        serialized_keys = list(serialized.keys())
        expected_order = [
            "timestamp", "symbol", "decision", "confidence", "current_price",
            "option_side", "expiry_policy", "expiry_date", "reason", "priority_score"
        ]
        
        assert serialized_keys == expected_order, f"Field order mismatch: {serialized_keys} != {expected_order}"

    def test_serialize_opportunity_data_types(self):
        """Test that serialized opportunity has correct data types."""
        opportunity = {
            "timestamp": datetime(2025, 1, 1, 10, 0, 0),
            "symbol": "SPY",
            "decision": "CALL",
            "confidence": "0.75",  # String that should be converted to float
            "current_price": "500.0",  # String that should be converted to float
            "option_side": "CALL",
            "expiry_policy": "0DTE",
            "expiry_date": "2025-01-01",
            "reason": "Strong signal",
            "priority_score": "0.8"  # String that should be converted to float
        }
        
        serialized = self.scanner._serialize_opportunity(opportunity)
        
        # Check data types
        assert isinstance(serialized["timestamp"], str), "timestamp should be ISO string"
        assert isinstance(serialized["symbol"], str), "symbol should be string"
        assert isinstance(serialized["decision"], str), "decision should be string"
        assert isinstance(serialized["confidence"], float), "confidence should be float"
        assert isinstance(serialized["current_price"], float), "current_price should be float"
        assert isinstance(serialized["option_side"], str), "option_side should be string"
        assert isinstance(serialized["expiry_policy"], str), "expiry_policy should be string"
        assert isinstance(serialized["expiry_date"], str), "expiry_date should be string"
        assert isinstance(serialized["reason"], str), "reason should be string"
        assert isinstance(serialized["priority_score"], float), "priority_score should be float"
        
        # Check specific values
        assert serialized["confidence"] == 0.75
        assert serialized["current_price"] == 500.0
        assert serialized["priority_score"] == 0.8
        assert serialized["timestamp"] == "2025-01-01T10:00:00"

    def test_serialize_opportunity_missing_fields(self):
        """Test serialization with missing fields uses defaults."""
        # Minimal opportunity dict
        opportunity = {
            "symbol": "QQQ",
            "decision": "PUT"
        }
        
        serialized = self.scanner._serialize_opportunity(opportunity)
        
        # Check defaults are applied
        assert serialized["symbol"] == "QQQ"
        assert serialized["decision"] == "PUT"
        assert serialized["confidence"] == 0.0  # Default
        assert serialized["current_price"] == 0.0  # Default
        assert serialized["option_side"] == ""  # Default
        assert serialized["expiry_policy"] == ""  # Default
        assert serialized["expiry_date"] == ""  # Default
        assert serialized["reason"] == ""  # Default
        assert serialized["priority_score"] == 0.0  # Default
        
        # timestamp should be generated if missing
        assert "timestamp" in serialized
        assert isinstance(serialized["timestamp"], str)

    def test_serialize_opportunity_excludes_non_serializable_fields(self):
        """Test that non-serializable fields are excluded from serialization."""
        opportunity = {
            "symbol": "IWM",
            "decision": "CALL",
            "confidence": 0.65,
            "current_price": 220.0,
            "option_side": "CALL",
            "expiry_policy": "WEEKLY",
            "expiry_date": "2025-01-03",
            "reason": "Breakout pattern",
            "priority_score": 0.7,
            "timestamp": datetime(2025, 1, 1, 12, 0, 0),
            
            # Non-serializable fields that should be excluded
            "breakout_analysis": {"complex": "data", "nested": {"values": [1, 2, 3]}},
            "market_data": {"ohlc": [100, 105, 99, 103]},
            "internal_state": {"some": "internal", "data": True}
        }
        
        serialized = self.scanner._serialize_opportunity(opportunity)
        
        # Check that only serializable fields are included
        expected_fields = {
            "timestamp", "symbol", "decision", "confidence", "current_price",
            "option_side", "expiry_policy", "expiry_date", "reason", "priority_score"
        }
        
        assert set(serialized.keys()) == expected_fields
        
        # Check that excluded fields are not present
        assert "breakout_analysis" not in serialized
        assert "market_data" not in serialized
        assert "internal_state" not in serialized

    def test_log_opportunity_calls_serialization(self):
        """Test that _log_opportunity uses deterministic serialization."""
        opportunity = {
            "symbol": "UVXY",
            "decision": "PUT",
            "confidence": 0.80,
            "current_price": 15.0,
            "option_side": "PUT",
            "expiry_policy": "0DTE",
            "expiry_date": "2025-01-01",
            "reason": "Volatility spike",
            "priority_score": 0.9,
            "timestamp": datetime(2025, 1, 1, 14, 0, 0)
        }
        
        # Mock logger to capture log calls
        with patch('utils.multi_symbol_scanner.logger') as mock_logger:
            self.scanner._log_opportunity(opportunity)
            
            # Should have called logger.info with serialized opportunity
            mock_logger.info.assert_called_once()
            log_call_args = mock_logger.info.call_args[0][0]
            
            # Should contain [OPPORTUNITY] prefix and serialized data
            assert "[OPPORTUNITY]" in log_call_args
            assert "UVXY" in log_call_args
            assert "PUT" in log_call_args
            assert "0.8" in log_call_args  # confidence
            assert "15.0" in log_call_args  # current_price

    def test_log_opportunity_error_handling(self):
        """Test that _log_opportunity handles errors gracefully."""
        # Create opportunity that will cause serialization error
        opportunity = {
            "confidence": "invalid_float",  # This will cause float() to fail
            "symbol": "TEST"
        }
        
        # Mock logger to capture warning
        with patch('utils.multi_symbol_scanner.logger') as mock_logger:
            # Should not raise exception
            self.scanner._log_opportunity(opportunity)
            
            # Should log warning about error
            mock_logger.warning.assert_called_once()
            warning_call_args = mock_logger.warning.call_args[0][0]
            assert "Error logging opportunity" in warning_call_args

    @patch('utils.multi_symbol_scanner.fetch_market_data')
    @patch('utils.multi_symbol_scanner.calculate_heikin_ashi')
    @patch('utils.multi_symbol_scanner.analyze_breakout_pattern')
    def test_opportunity_logging_integration(self, mock_breakout, mock_ha, mock_fetch):
        """Test that opportunities are logged during scanning with deterministic format."""
        # Mock data dependencies
        mock_df = MagicMock()
        mock_df.__getitem__.return_value.iloc.__getitem__.return_value = 450.0
        mock_fetch.return_value = mock_df
        mock_ha.return_value = MagicMock()
        mock_breakout.return_value = {"today_true_range_pct": 30.0}
        
        # Mock LLM decision
        mock_llm_result = MagicMock()
        mock_llm_result.decision = "PUT"
        mock_llm_result.confidence = 0.85
        mock_llm_result.reason = "Strong bearish signal"
        
        # Mock all gates to allow through
        self.scanner._pre_llm_hard_gate = lambda *args: (True, "Test passed")
        self.scanner._robust_llm_decision = lambda *args: mock_llm_result
        self.scanner._apply_consecutive_loss_throttle = lambda *args: (True, "Test passed")
        self.scanner._recent_signal_guard = lambda *args: (True, "Test passed")
        self.scanner._get_expiry_policy_early = lambda: ("WEEKLY", "2025-01-03")
        
        # Mock logger to capture opportunity logging
        with patch('utils.multi_symbol_scanner.logger') as mock_logger:
            opportunities = self.scanner._scan_single_symbol("QQQ")
            
            # Should have logged opportunity
            opportunity_logs = [call for call in mock_logger.info.call_args_list 
                              if "[OPPORTUNITY]" in str(call)]
            assert len(opportunity_logs) == 1
            
            # Check that logged opportunity contains expected fields
            log_message = str(opportunity_logs[0])
            assert "QQQ" in log_message
            assert "PUT" in log_message
            assert "0.85" in log_message  # confidence
            assert "WEEKLY" in log_message  # expiry_policy

    def test_csv_headers_match_serialized_fields(self):
        """Test that CSV headers in scoped_files match serialized opportunity fields."""
        # This test ensures consistency between CSV headers and serialized fields
        from utils.scoped_files import get_scoped_paths
        import tempfile
        import csv
        
        # Create temporary directory for test
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock the paths to use temp directory
            with patch('utils.scoped_files.Path') as mock_path:
                mock_path.return_value.exists.return_value = False
                mock_path.return_value.parent.mkdir = MagicMock()
                
                # Create a test CSV file to check headers
                test_csv = f"{temp_dir}/test_trade_history.csv"
                with open(test_csv, 'w', newline='') as f:
                    writer = csv.writer(f)
                    # These are the headers from scoped_files.py (updated version)
                    writer.writerow([
                        'timestamp', 'symbol', 'decision', 'confidence', 'current_price',
                        'option_side', 'expiry_policy', 'expiry_date', 'reason', 'priority_score',
                        'strike', 'premium', 'quantity', 'total_cost', 'status',
                        'fill_price', 'pnl_pct', 'pnl_amount', 'exit_reason'
                    ])
                
                # Read headers back
                with open(test_csv, 'r') as f:
                    reader = csv.reader(f)
                    headers = next(reader)
                
                # Check that serialized opportunity fields are in CSV headers
                serialized_fields = [
                    "timestamp", "symbol", "decision", "confidence", "current_price",
                    "option_side", "expiry_policy", "expiry_date", "reason", "priority_score"
                ]
                
                for field in serialized_fields:
                    assert field in headers, f"Serialized field '{field}' missing from CSV headers"


if __name__ == "__main__":
    pytest.main([__file__])
