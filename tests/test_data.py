"""
Unit tests for data processing utilities.
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.data import (
    fetch_market_data,
    calculate_heikin_ashi,
    find_support_resistance,
    calculate_true_range,
    analyze_breakout_pattern,
    prepare_llm_payload
)


class TestFetchMarketData:
    """Test market data fetching functionality."""
    
    @patch('utils.data.yf.Ticker')
    def test_fetch_market_data_success(self, mock_ticker):
        """Test successful market data fetch."""
        # Mock data
        mock_data = pd.DataFrame({
            'Open': [100.0, 101.0, 102.0],
            'High': [101.0, 102.0, 103.0],
            'Low': [99.0, 100.0, 101.0],
            'Close': [100.5, 101.5, 102.5],
            'Volume': [1000000, 1100000, 1200000]
        }, index=pd.date_range('2023-01-01', periods=3, freq='5T'))
        
        mock_ticker_instance = MagicMock()
        mock_ticker_instance.history.return_value = mock_data
        mock_ticker.return_value = mock_ticker_instance
        
        result = fetch_market_data("SPY", "1d", "5m")
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 3
        assert all(col in result.columns for col in ['Open', 'High', 'Low', 'Close', 'Volume'])
        mock_ticker.assert_called_once_with("SPY")
        mock_ticker_instance.history.assert_called_once_with(period="1d", interval="5m")
    
    @patch('utils.data.yf.Ticker')
    def test_fetch_market_data_empty_response(self, mock_ticker):
        """Test handling of empty market data response."""
        mock_ticker_instance = MagicMock()
        mock_ticker_instance.history.return_value = pd.DataFrame()
        mock_ticker.return_value = mock_ticker_instance
        
        with pytest.raises(ValueError, match="No data returned for SPY"):
            fetch_market_data("SPY")
    
    @patch('utils.data.yf.Ticker')
    def test_fetch_market_data_missing_columns(self, mock_ticker):
        """Test handling of missing required columns."""
        mock_data = pd.DataFrame({
            'Open': [100.0, 101.0],
            'High': [101.0, 102.0]
            # Missing Low, Close, Volume
        })
        
        mock_ticker_instance = MagicMock()
        mock_ticker_instance.history.return_value = mock_data
        mock_ticker.return_value = mock_ticker_instance
        
        with pytest.raises(ValueError, match="Missing required columns"):
            fetch_market_data("SPY")


class TestCalculateHeikinAshi:
    """Test Heikin-Ashi calculation functionality."""
    
    def create_sample_data(self):
        """Create sample OHLC data for testing."""
        return pd.DataFrame({
            'Open': [100.0, 101.0, 102.0, 103.0, 104.0],
            'High': [101.0, 102.0, 103.0, 104.0, 105.0],
            'Low': [99.0, 100.0, 101.0, 102.0, 103.0],
            'Close': [100.5, 101.5, 102.5, 103.5, 104.5],
            'Volume': [1000, 1100, 1200, 1300, 1400]
        })
    
    def test_calculate_heikin_ashi_basic(self):
        """Test basic Heikin-Ashi calculation."""
        df = self.create_sample_data()
        result = calculate_heikin_ashi(df)
        
        # Check that HA columns are added
        ha_columns = ['HA_Open', 'HA_High', 'HA_Low', 'HA_Close']
        assert all(col in result.columns for col in ha_columns)
        
        # Check that we have the same number of rows
        assert len(result) == len(df)
        
        # Check first HA candle calculation
        expected_ha_close_0 = (df.iloc[0]['Open'] + df.iloc[0]['High'] + 
                              df.iloc[0]['Low'] + df.iloc[0]['Close']) / 4
        assert abs(result.iloc[0]['HA_Close'] - expected_ha_close_0) < 0.001
        
        expected_ha_open_0 = (df.iloc[0]['Open'] + df.iloc[0]['Close']) / 2
        assert abs(result.iloc[0]['HA_Open'] - expected_ha_open_0) < 0.001
    
    def test_calculate_heikin_ashi_subsequent_candles(self):
        """Test Heikin-Ashi calculation for subsequent candles."""
        df = self.create_sample_data()
        result = calculate_heikin_ashi(df)
        
        # Check second candle HA_Open calculation
        expected_ha_open_1 = (result.iloc[0]['HA_Open'] + result.iloc[0]['HA_Close']) / 2
        assert abs(result.iloc[1]['HA_Open'] - expected_ha_open_1) < 0.001
        
        # Check that HA_High is max of (High, HA_Open, HA_Close)
        expected_ha_high_1 = max(df.iloc[1]['High'], result.iloc[1]['HA_Open'], result.iloc[1]['HA_Close'])
        assert abs(result.iloc[1]['HA_High'] - expected_ha_high_1) < 0.001
        
        # Check that HA_Low is min of (Low, HA_Open, HA_Close)
        expected_ha_low_1 = min(df.iloc[1]['Low'], result.iloc[1]['HA_Open'], result.iloc[1]['HA_Close'])
        assert abs(result.iloc[1]['HA_Low'] - expected_ha_low_1) < 0.001
    
    def test_calculate_heikin_ashi_single_row(self):
        """Test Heikin-Ashi calculation with single row."""
        df = pd.DataFrame({
            'Open': [100.0],
            'High': [101.0],
            'Low': [99.0],
            'Close': [100.5],
            'Volume': [1000]
        })
        
        result = calculate_heikin_ashi(df)
        assert len(result) == 1
        assert 'HA_Close' in result.columns


class TestSupportResistance:
    """Test support and resistance identification."""
    
    def create_trending_data(self):
        """Create data with clear support/resistance levels."""
        # Create data with obvious pivot points
        highs = [100, 101, 102, 105, 104, 103, 106, 105, 104, 107, 106, 105]
        lows = [98, 99, 100, 103, 102, 101, 104, 103, 102, 105, 104, 103]
        
        return pd.DataFrame({
            'High': highs,
            'Low': lows,
            'Open': [h - 1 for h in highs],
            'Close': [l + 1 for l in lows],
            'Volume': [1000] * len(highs)
        })
    
    def test_find_support_resistance_basic(self):
        """Test basic support/resistance finding."""
        df = self.create_trending_data()
        result = find_support_resistance(df, lookback=3)
        
        assert 'support' in result
        assert 'resistance' in result
        assert isinstance(result['support'], list)
        assert isinstance(result['resistance'], list)
        assert len(result['resistance']) <= 5
        assert len(result['support']) <= 5
    
    def test_find_support_resistance_insufficient_data(self):
        """Test handling of insufficient data."""
        df = pd.DataFrame({
            'High': [100, 101],
            'Low': [99, 100],
            'Open': [99.5, 100.5],
            'Close': [100.5, 101.5]
        })
        
        result = find_support_resistance(df, lookback=5)
        assert result['support'] == []
        assert result['resistance'] == []
    
    def test_find_support_resistance_with_ha_data(self):
        """Test support/resistance with Heikin-Ashi data."""
        df = self.create_trending_data()
        ha_df = calculate_heikin_ashi(df)
        
        result = find_support_resistance(ha_df, lookback=3)
        assert 'support' in result
        assert 'resistance' in result


class TestTrueRange:
    """Test True Range calculation."""
    
    def create_sample_data(self):
        """Create sample data for True Range testing."""
        return pd.DataFrame({
            'High': [102, 104, 103, 105, 106],
            'Low': [100, 101, 100, 102, 103],
            'Close': [101, 103, 102, 104, 105],
            'Open': [100.5, 102.5, 101.5, 103.5, 104.5]
        })
    
    def test_calculate_true_range_basic(self):
        """Test basic True Range calculation."""
        df = self.create_sample_data()
        result = calculate_true_range(df)
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(df)
        
        # First TR should be High - Low (no previous close)
        expected_tr_0 = df.iloc[0]['High'] - df.iloc[0]['Low']
        assert abs(result.iloc[0] - expected_tr_0) < 0.001
    
    def test_calculate_true_range_with_gaps(self):
        """Test True Range calculation with price gaps."""
        df = pd.DataFrame({
            'High': [102, 110, 108],  # Gap up
            'Low': [100, 105, 103],
            'Close': [101, 107, 105],
            'Open': [100.5, 108.5, 106.5]
        })
        
        result = calculate_true_range(df)
        
        # Second TR should account for gap from previous close
        prev_close = df.iloc[0]['Close']
        current_high = df.iloc[1]['High']
        current_low = df.iloc[1]['Low']
        
        expected_tr_1 = max(
            current_high - current_low,
            abs(current_high - prev_close),
            abs(current_low - prev_close)
        )
        
        assert abs(result.iloc[1] - expected_tr_1) < 0.001
    
    def test_calculate_true_range_with_ha_data(self):
        """Test True Range with Heikin-Ashi data."""
        df = self.create_sample_data()
        ha_df = calculate_heikin_ashi(df)
        
        result = calculate_true_range(ha_df)
        assert isinstance(result, pd.Series)
        assert len(result) == len(ha_df)


class TestAnalyzeBreakoutPattern:
    """Test breakout pattern analysis."""
    
    def create_comprehensive_data(self):
        """Create comprehensive data for breakout analysis."""
        dates = pd.date_range('2023-01-01', periods=25, freq='5T')
        np.random.seed(42)  # For reproducible tests
        
        base_price = 100
        prices = []
        for i in range(25):
            price = base_price + i * 0.5 + np.random.normal(0, 0.5)
            prices.append(price)
        
        df = pd.DataFrame({
            'Open': [p - 0.2 for p in prices],
            'High': [p + 0.3 for p in prices],
            'Low': [p - 0.3 for p in prices],
            'Close': [p + 0.1 for p in prices],
            'Volume': [1000 + i * 50 for i in range(25)]
        }, index=dates)
        
        return calculate_heikin_ashi(df)
    
    def test_analyze_breakout_pattern_basic(self):
        """Test basic breakout pattern analysis."""
        df = self.create_comprehensive_data()
        result = analyze_breakout_pattern(df, lookback=20)
        
        required_keys = [
            'current_price', 'candle_body_pct', 'true_range_pct',
            'trend_direction', 'nearest_resistance', 'nearest_support',
            'room_to_resistance_pct', 'room_to_support_pct',
            'support_levels', 'resistance_levels', 'volume', 'timestamp'
        ]
        
        for key in required_keys:
            assert key in result, f"Missing key: {key}"
        
        assert isinstance(result['current_price'], (int, float))
        assert isinstance(result['candle_body_pct'], (int, float))
        assert result['trend_direction'] in ['BULLISH', 'BEARISH', 'NEUTRAL']
        assert isinstance(result['support_levels'], list)
        assert isinstance(result['resistance_levels'], list)
    
    def test_analyze_breakout_pattern_insufficient_data(self):
        """Test analysis with insufficient data."""
        df = pd.DataFrame({
            'HA_Open': [100],
            'HA_High': [101],
            'HA_Low': [99],
            'HA_Close': [100.5],
            'Volume': [1000]
        })
        
        with pytest.raises(ValueError, match="Insufficient data for analysis"):
            analyze_breakout_pattern(df, lookback=20)
    
    def test_analyze_breakout_pattern_trend_detection(self):
        """Test trend direction detection."""
        # Create bullish trend data
        df = pd.DataFrame({
            'HA_Open': [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110],
            'HA_High': [101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111],
            'HA_Low': [99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
            'HA_Close': [100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5, 107.5, 108.5, 109.5, 110.5],
            'Volume': [1000] * 11
        })
        
        result = analyze_breakout_pattern(df, lookback=10)
        assert result['trend_direction'] == 'BULLISH'


class TestPrepareLLMPayload:
    """Test LLM payload preparation."""
    
    def create_sample_analysis(self):
        """Create sample analysis data."""
        return {
            'current_price': 150.25,
            'candle_body_pct': 0.85,
            'true_range_pct': 1.2,
            'trend_direction': 'BULLISH',
            'room_to_resistance_pct': 0.75,
            'room_to_support_pct': 1.5,
            'resistance_levels': [151.0, 152.5, 154.0, 155.5, 157.0],
            'support_levels': [149.0, 147.5, 146.0, 144.5, 143.0],
            'volume': 1500000,
            'timestamp': '2023-01-01T10:30:00'
        }
    
    def test_prepare_llm_payload_basic(self):
        """Test basic LLM payload preparation."""
        analysis = self.create_sample_analysis()
        result = prepare_llm_payload(analysis)
        
        expected_keys = [
            'price', 'body_pct', 'tr_pct', 'trend', 'room_up', 'room_down',
            'resistance', 'support', 'volume', 'timestamp'
        ]
        
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"
        
        # Check data types and values
        assert result['price'] == 150.25
        assert result['body_pct'] == 0.85
        assert result['trend'] == 'BULLISH'
        assert len(result['resistance']) <= 3
        assert len(result['support']) <= 3
    
    def test_prepare_llm_payload_truncation(self):
        """Test that resistance/support lists are truncated."""
        analysis = self.create_sample_analysis()
        result = prepare_llm_payload(analysis)
        
        # Should only have top 3 resistance and support levels
        assert len(result['resistance']) == 3
        assert len(result['support']) == 3
        
        # Should be the first 3 resistance levels
        assert result['resistance'] == [151.0, 152.5, 154.0]
        # Should be the last 3 support levels
        assert result['support'] == [146.0, 144.5, 143.0]


if __name__ == '__main__':
    pytest.main([__file__])
