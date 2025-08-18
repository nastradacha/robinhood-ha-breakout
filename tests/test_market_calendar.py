"""
Test suite for Market Calendar Integration (US-FA-003)

Tests comprehensive market hours validation including:
- Holiday detection
- Early close detection
- Market status validation
- Pre-market and after-hours handling
- Weekend detection
- API fallback behavior
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, date, time
import pytz
import json
from pathlib import Path

from utils.market_calendar import MarketCalendar, MarketHours, get_market_status, is_market_open, validate_trading_time


class TestMarketCalendar:
    """Test suite for MarketCalendar class"""
    
    def setup_method(self):
        """Setup test environment"""
        self.calendar = MarketCalendar(cache_dir=".test_cache")
        self.et_tz = pytz.timezone('US/Eastern')
    
    def teardown_method(self):
        """Cleanup test environment"""
        # Clean up test cache
        cache_file = Path(".test_cache/market_calendar.json")
        if cache_file.exists():
            cache_file.unlink()
        cache_dir = Path(".test_cache")
        if cache_dir.exists():
            cache_dir.rmdir()
    
    def test_market_hours_regular_trading_day(self):
        """Test market hours for regular trading day"""
        # Tuesday, January 10, 2024 (regular trading day)
        test_date = date(2024, 1, 10)
        
        market_hours = self.calendar.get_market_hours(test_date)
        
        assert market_hours.is_open is True
        assert market_hours.open_time == time(9, 30)
        assert market_hours.close_time == time(16, 0)
        assert market_hours.is_early_close is False
        assert market_hours.reason is None
    
    def test_market_hours_weekend(self):
        """Test market hours for weekend"""
        # Saturday, January 6, 2024
        test_date = date(2024, 1, 6)
        
        market_hours = self.calendar.get_market_hours(test_date)
        
        assert market_hours.is_open is False
        assert market_hours.open_time is None
        assert market_hours.close_time is None
        assert market_hours.is_early_close is False
        assert market_hours.reason == "Weekend"
    
    def test_market_hours_holiday(self):
        """Test market hours for holiday"""
        # New Year's Day 2024
        test_date = date(2024, 1, 1)
        
        market_hours = self.calendar.get_market_hours(test_date)
        
        assert market_hours.is_open is False
        assert market_hours.open_time is None
        assert market_hours.close_time is None
        assert market_hours.is_early_close is False
        assert market_hours.reason == "New Year's Day"
    
    def test_market_hours_early_close(self):
        """Test market hours for early close day"""
        # Christmas Eve 2024
        test_date = date(2024, 12, 24)
        
        market_hours = self.calendar.get_market_hours(test_date)
        
        assert market_hours.is_open is True
        assert market_hours.open_time == time(9, 30)
        assert market_hours.close_time == time(13, 0)  # 1:00 PM ET
        assert market_hours.is_early_close is True
        assert market_hours.reason == "Christmas Eve"
    
    def test_is_market_open_during_hours(self):
        """Test is_market_open during regular trading hours"""
        # Tuesday, January 10, 2024 at 2:00 PM ET (market open)
        test_time = datetime(2024, 1, 10, 14, 0, 0)
        test_time_et = self.et_tz.localize(test_time)
        
        is_open, reason = self.calendar.is_market_open(test_time_et)
        
        assert is_open is True
        assert reason == "Market open"
    
    def test_is_market_open_before_hours(self):
        """Test is_market_open before market hours"""
        # Tuesday, January 10, 2024 at 8:00 AM ET (pre-market)
        test_time = datetime(2024, 1, 10, 8, 0, 0)
        test_time_et = self.et_tz.localize(test_time)
        
        is_open, reason = self.calendar.is_market_open(test_time_et)
        
        assert is_open is False
        assert "Pre-market" in reason
        assert "09:30" in reason
    
    def test_is_market_open_after_hours(self):
        """Test is_market_open after market hours"""
        # Tuesday, January 10, 2024 at 5:00 PM ET (after-hours)
        test_time = datetime(2024, 1, 10, 17, 0, 0)
        test_time_et = self.et_tz.localize(test_time)
        
        is_open, reason = self.calendar.is_market_open(test_time_et)
        
        assert is_open is False
        assert "After-hours" in reason
        assert "16:00" in reason
    
    def test_is_market_open_holiday(self):
        """Test is_market_open on holiday"""
        # New Year's Day 2024 at 2:00 PM ET
        test_time = datetime(2024, 1, 1, 14, 0, 0)
        test_time_et = self.et_tz.localize(test_time)
        
        is_open, reason = self.calendar.is_market_open(test_time_et)
        
        assert is_open is False
        assert "Market closed: New Year's Day" in reason
    
    def test_is_market_open_early_close(self):
        """Test is_market_open on early close day after early close"""
        # Christmas Eve 2024 at 2:00 PM ET (after 1:00 PM early close)
        test_time = datetime(2024, 12, 24, 14, 0, 0)
        test_time_et = self.et_tz.localize(test_time)
        
        is_open, reason = self.calendar.is_market_open(test_time_et)
        
        assert is_open is False
        assert "After-hours" in reason
        assert "13:00" in reason
        assert "early close" in reason
    
    def test_is_market_open_early_close_during_hours(self):
        """Test is_market_open on early close day during trading hours"""
        # Christmas Eve 2024 at 11:00 AM ET (before 1:00 PM early close)
        test_time = datetime(2024, 12, 24, 11, 0, 0)
        test_time_et = self.et_tz.localize(test_time)
        
        is_open, reason = self.calendar.is_market_open(test_time_et)
        
        assert is_open is True
        assert reason == "Market open"
    
    def test_get_market_status_comprehensive(self):
        """Test comprehensive market status information"""
        # Tuesday, January 10, 2024 at 2:00 PM ET
        test_time = datetime(2024, 1, 10, 14, 0, 0)
        test_time_et = self.et_tz.localize(test_time)
        
        status = self.calendar.get_market_status(test_time_et)
        
        assert status["is_open"] is True
        assert status["reason"] == "Market open"
        assert status["date"] == "2024-01-10"
        assert "14:00:00 ET" in status["current_time_et"]
        assert status["market_hours"]["open"] == "09:30"
        assert status["market_hours"]["close"] == "16:00"
        assert status["market_hours"]["is_early_close"] is False
        assert "Closes in" in status["time_info"]
        assert status["holiday_reason"] is None
    
    def test_validate_trading_time_allowed(self):
        """Test validate_trading_time when trading is allowed"""
        # Tuesday, January 10, 2024 at 2:00 PM ET
        test_time = datetime(2024, 1, 10, 14, 0, 0)
        test_time_et = self.et_tz.localize(test_time)
        
        can_trade, reason = self.calendar.validate_trading_time(test_time_et)
        
        assert can_trade is True
        assert reason == "Market open - trading allowed"
    
    def test_validate_trading_time_blocked(self):
        """Test validate_trading_time when trading is blocked"""
        # New Year's Day 2024 at 2:00 PM ET
        test_time = datetime(2024, 1, 1, 14, 0, 0)
        test_time_et = self.et_tz.localize(test_time)
        
        can_trade, reason = self.calendar.validate_trading_time(test_time_et)
        
        assert can_trade is False
        assert "Trading blocked" in reason
        assert "New Year's Day" in reason
    
    def test_cache_functionality(self):
        """Test market calendar caching"""
        # First call should populate cache
        test_date = date(2024, 1, 10)
        market_hours1 = self.calendar.get_market_hours(test_date)
        
        # Second call should use cache
        market_hours2 = self.calendar.get_market_hours(test_date)
        
        assert market_hours1.is_open == market_hours2.is_open
        assert market_hours1.open_time == market_hours2.open_time
        assert market_hours1.close_time == market_hours2.close_time
        
        # Verify cache file exists
        cache_file = Path(".test_cache/market_calendar.json")
        assert cache_file.exists()
    
    def test_hardcoded_holidays_fallback(self):
        """Test fallback to hardcoded holidays when API fails"""
        with patch('requests.get') as mock_get:
            mock_get.side_effect = Exception("API failure")
            
            # Should still work with hardcoded holidays
            test_date = date(2024, 7, 4)  # Independence Day
            market_hours = self.calendar.get_market_hours(test_date)
            
            assert market_hours.is_open is False
            assert market_hours.reason == "Independence Day"
    
    def test_timezone_conversion(self):
        """Test timezone conversion handling"""
        # Test with UTC time
        utc_time = datetime(2024, 1, 10, 19, 0, 0, tzinfo=pytz.UTC)  # 2:00 PM ET
        
        is_open, reason = self.calendar.is_market_open(utc_time)
        
        assert is_open is True
        assert reason == "Market open"
    
    def test_convenience_functions(self):
        """Test convenience functions"""
        with patch('utils.market_calendar.market_calendar') as mock_calendar:
            mock_calendar.get_market_status.return_value = {"is_open": True}
            mock_calendar.is_market_open.return_value = (True, "Market open")
            mock_calendar.validate_trading_time.return_value = (True, "Trading allowed")
            
            # Test convenience functions
            status = get_market_status()
            is_open_result = is_market_open()
            can_trade_result = validate_trading_time()
            
            assert status["is_open"] is True
            assert is_open_result == (True, "Market open")
            assert can_trade_result == (True, "Trading allowed")


class TestMarketCalendarIntegration:
    """Integration tests for market calendar with trading system"""
    
    def test_integration_with_multi_symbol_scanner(self):
        """Test integration with multi-symbol scanner trading gate"""
        from utils.multi_symbol_scanner import MultiSymbolScanner
        
        # Mock configuration
        config = {
            "SYMBOLS": ["SPY"],
            "MIN_TR_RANGE_PCT": 1.0
        }
        
        scanner = MultiSymbolScanner(config, None, None)
        
        # Mock market data
        market_data = {
            "symbol": "SPY",
            "today_true_range_pct": 2.0
        }
        
        # Test during market hours
        with patch('utils.market_calendar.validate_trading_time') as mock_validate:
            mock_validate.return_value = (True, "Market open - trading allowed")
            
            # Should pass market hours gate
            proceed, reason = scanner._pre_llm_hard_gate(market_data, config)
            
            # Should proceed (assuming other gates pass)
            mock_validate.assert_called_once()
    
    def test_integration_holiday_blocking(self):
        """Test that holidays properly block trading"""
        from utils.multi_symbol_scanner import MultiSymbolScanner
        
        config = {
            "SYMBOLS": ["SPY"],
            "MIN_TR_RANGE_PCT": 1.0
        }
        
        scanner = MultiSymbolScanner(config, None, None)
        
        market_data = {
            "symbol": "SPY",
            "today_true_range_pct": 2.0
        }
        
        # Test on holiday
        with patch('utils.market_calendar.validate_trading_time') as mock_validate:
            mock_validate.return_value = (False, "Trading blocked: Market closed: New Year's Day")
            
            proceed, reason = scanner._pre_llm_hard_gate(market_data, config)
            
            assert proceed is False
            assert "Market hours validation" in reason
            assert "New Year's Day" in reason
    
    def test_integration_early_close_blocking(self):
        """Test that early close properly blocks trading after close"""
        from utils.multi_symbol_scanner import MultiSymbolScanner
        
        config = {
            "SYMBOLS": ["SPY"],
            "MIN_TR_RANGE_PCT": 1.0
        }
        
        scanner = MultiSymbolScanner(config, None, None)
        
        market_data = {
            "symbol": "SPY",
            "today_true_range_pct": 2.0
        }
        
        # Test after early close
        with patch('utils.market_calendar.validate_trading_time') as mock_validate:
            mock_validate.return_value = (False, "Trading blocked: After-hours: Market closed at 13:00 ET (early close)")
            
            proceed, reason = scanner._pre_llm_hard_gate(market_data, config)
            
            assert proceed is False
            assert "Market hours validation" in reason
            assert "early close" in reason
    
    def test_integration_fallback_behavior(self):
        """Test fallback behavior when market calendar fails"""
        from utils.multi_symbol_scanner import MultiSymbolScanner
        
        config = {
            "SYMBOLS": ["SPY"],
            "MIN_TR_RANGE_PCT": 1.0
        }
        
        scanner = MultiSymbolScanner(config, None, None)
        
        market_data = {
            "symbol": "SPY",
            "today_true_range_pct": 2.0
        }
        
        # Test when market calendar fails
        with patch('utils.market_calendar.validate_trading_time') as mock_validate:
            mock_validate.side_effect = Exception("Market calendar API failure")
            
            # Mock current time as Tuesday 2:00 PM ET (should pass fallback validation)
            with patch('datetime.datetime') as mock_datetime:
                mock_et_time = MagicMock()
                mock_et_time.weekday.return_value = 1  # Tuesday
                mock_et_time.time.return_value = time(14, 0)  # 2:00 PM
                mock_datetime.now.return_value = mock_et_time
                
                proceed, reason = scanner._pre_llm_hard_gate(market_data, config)
                
                # Should fall back to basic validation and proceed
                # (assuming other gates pass and it's during market hours)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
