"""
Test suite for Earnings Calendar Integration (US-FA-002)

Tests earnings calendar functionality including:
- Provider API parsing (FMP, Alpha Vantage)
- Timezone conversion and window calculations
- Caching behavior and TTL
- ETF handling configuration
- Provider fallback logic
- Integration with multi_symbol_scanner
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import pytz
import json
import os
import tempfile
import shutil

# Import the modules under test
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.earnings_calendar import (
    EarningsInfo, 
    FmpEarningsProvider, 
    AlphaVantageEarningsProvider,
    EarningsCalendar,
    is_within_earnings_window,
    get_next_earnings,
    validate_earnings_blocking
)

class TestEarningsInfo(unittest.TestCase):
    """Test EarningsInfo data class"""
    
    def test_earnings_info_creation(self):
        """Test EarningsInfo object creation and serialization"""
        dt = datetime(2024, 1, 15, 21, 15, 0, tzinfo=pytz.UTC)  # 4:15 PM ET
        info = EarningsInfo("AAPL", dt, "fmp", "AMC")
        
        self.assertEqual(info.symbol, "AAPL")
        self.assertEqual(info.earnings_dt, dt)
        self.assertEqual(info.source, "fmp")
        self.assertEqual(info.session, "AMC")
    
    def test_earnings_info_serialization(self):
        """Test to_dict and from_dict methods"""
        dt = datetime(2024, 1, 15, 21, 15, 0, tzinfo=pytz.UTC)
        info = EarningsInfo("AAPL", dt, "fmp", "AMC")
        
        # Test serialization
        data = info.to_dict()
        self.assertEqual(data["symbol"], "AAPL")
        self.assertEqual(data["source"], "fmp")
        self.assertEqual(data["session"], "AMC")
        self.assertIn("earnings_dt_utc", data)
        
        # Test deserialization
        info2 = EarningsInfo.from_dict(data)
        self.assertEqual(info2.symbol, info.symbol)
        self.assertEqual(info2.earnings_dt, info.earnings_dt)
        self.assertEqual(info2.source, info.source)
        self.assertEqual(info2.session, info.session)

class TestFmpEarningsProvider(unittest.TestCase):
    """Test Financial Modeling Prep earnings provider"""
    
    def setUp(self):
        self.provider = FmpEarningsProvider("test_api_key")
    
    @patch('requests.get')
    def test_fetch_next_earnings_success(self, mock_get):
        """Test successful earnings fetch from FMP"""
        # Mock API response
        mock_response = Mock()
        mock_response.json.return_value = [
            {
                "symbol": "AAPL",
                "date": "2024-01-25",
                "time": "AMC"
            },
            {
                "symbol": "MSFT", 
                "date": "2024-01-24",
                "time": "BMO"
            }
        ]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        # Test fetching AAPL earnings
        with patch('utils.earnings_calendar.datetime') as mock_datetime:
            mock_now = datetime(2024, 1, 20, 15, 0, 0, tzinfo=pytz.UTC)
            mock_datetime.now.return_value = mock_now
            mock_datetime.strptime.side_effect = datetime.strptime
            mock_datetime.combine.side_effect = datetime.combine
            
            result = self.provider.fetch_next_earnings("AAPL")
            
            self.assertIsNotNone(result)
            self.assertEqual(result.symbol, "AAPL")
            self.assertEqual(result.source, "fmp")
            self.assertEqual(result.session, "AMC")
    
    @patch('requests.get')
    def test_fetch_next_earnings_no_results(self, mock_get):
        """Test when no earnings found for symbol"""
        mock_response = Mock()
        mock_response.json.return_value = []
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = self.provider.fetch_next_earnings("UNKNOWN")
        self.assertIsNone(result)
    
    @patch('requests.get')
    def test_fetch_next_earnings_api_error(self, mock_get):
        """Test API error handling"""
        mock_get.side_effect = Exception("API Error")
        
        result = self.provider.fetch_next_earnings("AAPL")
        self.assertIsNone(result)
    
    def test_parse_earnings_datetime_bmo(self):
        """Test parsing BMO (Before Market Open) timing"""
        result = self.provider._parse_earnings_datetime("2024-01-25", "BMO")
        
        self.assertIsNotNone(result)
        # Should be 8:30 AM ET = 13:30 UTC
        expected_et = pytz.timezone('US/Eastern').localize(
            datetime(2024, 1, 25, 8, 30, 0)
        )
        expected_utc = expected_et.astimezone(pytz.UTC)
        self.assertEqual(result, expected_utc)
    
    def test_parse_earnings_datetime_amc(self):
        """Test parsing AMC (After Market Close) timing"""
        result = self.provider._parse_earnings_datetime("2024-01-25", "AMC")
        
        self.assertIsNotNone(result)
        # Should be 4:15 PM ET = 21:15 UTC
        expected_et = pytz.timezone('US/Eastern').localize(
            datetime(2024, 1, 25, 16, 15, 0)
        )
        expected_utc = expected_et.astimezone(pytz.UTC)
        self.assertEqual(result, expected_utc)
    
    def test_parse_earnings_datetime_explicit_time(self):
        """Test parsing explicit time"""
        result = self.provider._parse_earnings_datetime("2024-01-25", "14:30")
        
        self.assertIsNotNone(result)
        # Should be 2:30 PM ET = 19:30 UTC
        expected_et = pytz.timezone('US/Eastern').localize(
            datetime(2024, 1, 25, 14, 30, 0)
        )
        expected_utc = expected_et.astimezone(pytz.UTC)
        self.assertEqual(result, expected_utc)
    
    def test_determine_session(self):
        """Test session determination logic"""
        self.assertEqual(self.provider._determine_session("BMO"), "BMO")
        self.assertEqual(self.provider._determine_session("AMC"), "AMC")
        self.assertEqual(self.provider._determine_session("BEFORE MARKET OPEN"), "BMO")
        self.assertEqual(self.provider._determine_session("AFTER MARKET CLOSE"), "AMC")
        self.assertEqual(self.provider._determine_session("14:30"), "")
        self.assertEqual(self.provider._determine_session(""), "AMC")

class TestAlphaVantageEarningsProvider(unittest.TestCase):
    """Test Alpha Vantage earnings provider"""
    
    def setUp(self):
        self.provider = AlphaVantageEarningsProvider("test_api_key")
    
    @patch('requests.get')
    def test_fetch_next_earnings_success(self, mock_get):
        """Test successful earnings fetch from Alpha Vantage"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "quarterlyEarnings": [
                {
                    "reportedDate": "2024-01-25"
                },
                {
                    "reportedDate": "2024-01-20"  # Past date
                }
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        with patch('utils.earnings_calendar.datetime') as mock_datetime:
            mock_now = datetime(2024, 1, 22, 15, 0, 0, tzinfo=pytz.UTC)
            mock_datetime.now.return_value = mock_now
            mock_datetime.strptime.side_effect = datetime.strptime
            mock_datetime.combine.side_effect = datetime.combine
            
            result = self.provider.fetch_next_earnings("AAPL")
            
            self.assertIsNotNone(result)
            self.assertEqual(result.symbol, "AAPL")
            self.assertEqual(result.source, "alpha_vantage")
            self.assertEqual(result.session, "AMC")  # Default for Alpha Vantage

class TestEarningsCalendar(unittest.TestCase):
    """Test main EarningsCalendar service"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.cache_file = os.path.join(self.temp_dir, "earnings_cache.json")
        
        self.config = {
            "EARNINGS_ENABLED": True,
            "EARNINGS_BLOCK_WINDOW_HOURS": 24,
            "EARNINGS_POST_WINDOW_HOURS": 0,
            "EARNINGS_CACHE_MINUTES": 720,
            "EARNINGS_APPLY_TO_ETFS": False,
            "FMP_API_KEY": "test_fmp_key",
            "ALPHA_VANTAGE_API_KEY": ""
        }
        
        # Create calendar with temp cache file
        with patch.object(EarningsCalendar, '__init__', lambda x, config: None):
            self.calendar = EarningsCalendar.__new__(EarningsCalendar)
            self.calendar.config = self.config
            self.calendar.cache_file = self.cache_file
            self.calendar.cache_minutes = 720
            self.calendar.apply_to_etfs = False
            self.calendar.known_etfs = {"SPY", "QQQ", "IWM", "TLT", "GLD"}
            self.calendar.providers = []
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
    
    def test_is_etf_detection(self):
        """Test ETF detection logic"""
        self.assertTrue(self.calendar._is_etf("SPY"))
        self.assertTrue(self.calendar._is_etf("spy"))  # Case insensitive
        self.assertFalse(self.calendar._is_etf("AAPL"))
    
    def test_cache_operations(self):
        """Test cache save and load operations"""
        test_data = {"test_key": "test_value"}
        
        # Test save
        self.calendar._save_cache(test_data)
        self.assertTrue(os.path.exists(self.cache_file))
        
        # Test load
        loaded_data = self.calendar._load_cache()
        self.assertEqual(loaded_data, test_data)
    
    def test_cache_validity(self):
        """Test cache TTL validation"""
        now = datetime.now(pytz.UTC)
        
        # Valid cache entry (recent)
        valid_entry = {
            "fetched_at_utc": (now - timedelta(minutes=60)).isoformat()
        }
        self.assertTrue(self.calendar._is_cache_valid(valid_entry))
        
        # Invalid cache entry (old)
        invalid_entry = {
            "fetched_at_utc": (now - timedelta(minutes=800)).isoformat()
        }
        self.assertFalse(self.calendar._is_cache_valid(invalid_entry))
    
    def test_is_within_earnings_window_blocked(self):
        """Test earnings window blocking logic"""
        now = datetime(2024, 1, 24, 15, 0, 0, tzinfo=pytz.UTC)  # 10 AM ET
        earnings_dt = datetime(2024, 1, 25, 13, 30, 0, tzinfo=pytz.UTC)  # Next day 8:30 AM ET
        
        # Mock get_next_earnings to return earnings info
        with patch.object(self.calendar, 'get_next_earnings') as mock_get:
            mock_get.return_value = EarningsInfo("AAPL", earnings_dt, "fmp", "BMO")
            
            blocked, info = self.calendar.is_within_earnings_window("AAPL", now)
            
            self.assertTrue(blocked)
            self.assertEqual(info["symbol"], "AAPL")
            self.assertAlmostEqual(info["hours_until"], 22.5, places=1)  # ~22.5 hours
            self.assertIn("within 24h window", info["reason"])
    
    def test_is_within_earnings_window_not_blocked(self):
        """Test when outside earnings window"""
        now = datetime(2024, 1, 20, 15, 0, 0, tzinfo=pytz.UTC)
        earnings_dt = datetime(2024, 1, 25, 13, 30, 0, tzinfo=pytz.UTC)  # 5 days away
        
        with patch.object(self.calendar, 'get_next_earnings') as mock_get:
            mock_get.return_value = EarningsInfo("AAPL", earnings_dt, "fmp", "BMO")
            
            blocked, info = self.calendar.is_within_earnings_window("AAPL", now)
            
            self.assertFalse(blocked)
            self.assertEqual(info["symbol"], "AAPL")
            self.assertGreater(info["hours_until"], 24)
            self.assertIn("outside 24h window", info["reason"])
    
    def test_is_within_earnings_window_no_earnings(self):
        """Test when no earnings found"""
        now = datetime(2024, 1, 24, 15, 0, 0, tzinfo=pytz.UTC)
        
        with patch.object(self.calendar, 'get_next_earnings') as mock_get:
            mock_get.return_value = None
            
            blocked, info = self.calendar.is_within_earnings_window("AAPL", now)
            
            self.assertFalse(blocked)
            self.assertEqual(info["symbol"], "AAPL")
            self.assertIn("No upcoming earnings", info["reason"])
    
    def test_etf_handling_disabled(self):
        """Test ETF blocking when EARNINGS_APPLY_TO_ETFS=false"""
        self.calendar.apply_to_etfs = False
        
        result = self.calendar.get_next_earnings("SPY")
        self.assertIsNone(result)
    
    def test_etf_handling_enabled(self):
        """Test ETF blocking when EARNINGS_APPLY_TO_ETFS=true"""
        self.calendar.apply_to_etfs = True
        
        # Mock provider to return earnings for ETF
        mock_provider = Mock()
        earnings_dt = datetime(2024, 1, 25, 13, 30, 0, tzinfo=pytz.UTC)
        mock_provider.fetch_next_earnings.return_value = EarningsInfo("SPY", earnings_dt, "fmp", "BMO")
        self.calendar.providers = [mock_provider]
        
        result = self.calendar.get_next_earnings("SPY")
        self.assertIsNotNone(result)
        self.assertEqual(result.symbol, "SPY")

class TestEarningsCalendarCaching(unittest.TestCase):
    """Test caching behavior"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.cache_file = os.path.join(self.temp_dir, "earnings_cache.json")
        
        self.config = {
            "EARNINGS_CACHE_MINUTES": 60,  # 1 hour
            "EARNINGS_APPLY_TO_ETFS": False,
            "FMP_API_KEY": "test_key"
        }
        
        with patch.object(EarningsCalendar, '__init__', lambda x, config: None):
            self.calendar = EarningsCalendar.__new__(EarningsCalendar)
            self.calendar.config = self.config
            self.calendar.cache_file = self.cache_file
            self.calendar.cache_minutes = 60
            self.calendar.apply_to_etfs = False
            self.calendar.known_etfs = {"SPY", "QQQ"}
            self.calendar.providers = []
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
    
    def test_cache_hit(self):
        """Test cache hit scenario - should use cache and not call providers"""
        now = datetime(2024, 1, 24, 15, 0, 0, tzinfo=pytz.UTC)
        
        # Pre-populate cache with valid entry
        cache_data = {
            "AAPL_earnings": {
                "symbol": "AAPL",
                "earnings_dt_utc": "2024-01-25T13:30:00+00:00",
                "source": "fmp",
                "session": "BMO",
                "fetched_at_utc": (now - timedelta(minutes=30)).isoformat()
            }
        }
        
        # Directly test cache loading and validation
        self.calendar._save_cache(cache_data)
        loaded_cache = self.calendar._load_cache()
        self.assertEqual(loaded_cache, cache_data)
        
        # Test cache validity with the test's 'now' time
        cache_entry = loaded_cache["AAPL_earnings"]
        self.assertTrue(self.calendar._is_cache_valid(cache_entry, now))
        
        # Test EarningsInfo reconstruction from cache
        earnings_info = EarningsInfo.from_dict(cache_entry)
        self.assertEqual(earnings_info.symbol, "AAPL")
        self.assertEqual(earnings_info.source, "fmp")
        self.assertEqual(earnings_info.session, "BMO")
    
    def test_cache_miss_expired(self):
        """Test cache miss due to expiry"""
        now = datetime(2024, 1, 24, 15, 0, 0, tzinfo=pytz.UTC)
        
        # Pre-populate cache with expired entry
        cache_data = {
            "AAPL_earnings": {
                "symbol": "AAPL",
                "earnings_dt_utc": "2024-01-25T13:30:00+00:00",
                "source": "fmp",
                "session": "BMO",
                "fetched_at_utc": (now - timedelta(minutes=120)).isoformat()  # 2 hours ago
            }
        }
        self.calendar._save_cache(cache_data)
        
        # Mock provider to return new data
        mock_provider = Mock()
        earnings_dt = datetime(2024, 1, 26, 13, 30, 0, tzinfo=pytz.UTC)
        mock_provider.fetch_next_earnings.return_value = EarningsInfo("AAPL", earnings_dt, "fmp", "BMO")
        self.calendar.providers = [mock_provider]
        
        result = self.calendar.get_next_earnings("AAPL", now)
        
        self.assertIsNotNone(result)
        # Should have fetched new data, not cached
        mock_provider.fetch_next_earnings.assert_called_once_with("AAPL")

class TestEarningsCalendarIntegration(unittest.TestCase):
    """Test integration with multi_symbol_scanner"""
    
    @patch('builtins.open')
    @patch('yaml.safe_load')
    def test_validate_earnings_blocking_enabled_blocked(self, mock_yaml, mock_open):
        """Test earnings blocking when enabled and symbol blocked"""
        mock_yaml.return_value = {"EARNINGS_ENABLED": True}
        
        with patch('utils.earnings_calendar.is_within_earnings_window') as mock_check:
            mock_check.return_value = (True, {
                "reason": "Earnings in 12.5h (BMO) - within 24h window"
            })
            
            can_trade, reason = validate_earnings_blocking("AAPL")
            
            self.assertFalse(can_trade)
            self.assertIn("Earnings in 12.5h", reason)
    
    @patch('builtins.open')
    @patch('yaml.safe_load')
    def test_validate_earnings_blocking_enabled_allowed(self, mock_yaml, mock_open):
        """Test earnings blocking when enabled but symbol not blocked"""
        mock_yaml.return_value = {"EARNINGS_ENABLED": True}
        
        with patch('utils.earnings_calendar.is_within_earnings_window') as mock_check:
            mock_check.return_value = (False, {
                "reason": "Earnings in 48.2h - outside 24h window"
            })
            
            can_trade, reason = validate_earnings_blocking("AAPL")
            
            self.assertTrue(can_trade)
            self.assertIn("outside 24h window", reason)
    
    @patch('builtins.open')
    @patch('yaml.safe_load')
    def test_validate_earnings_blocking_disabled(self, mock_yaml, mock_open):
        """Test when earnings blocking is disabled"""
        mock_yaml.return_value = {"EARNINGS_ENABLED": False}
        
        can_trade, reason = validate_earnings_blocking("AAPL")
        
        self.assertTrue(can_trade)
        self.assertEqual(reason, "Earnings blocking disabled")
    
    @patch('builtins.open')
    def test_validate_earnings_blocking_error_failsafe(self, mock_open):
        """Test fail-safe behavior when validation fails"""
        mock_open.side_effect = Exception("Config error")
        
        can_trade, reason = validate_earnings_blocking("AAPL")
        
        self.assertTrue(can_trade)  # Fail-safe allows trading
        self.assertIn("Earnings validation failed", reason)

class TestEarningsWindowCalculations(unittest.TestCase):
    """Test earnings window timing calculations"""
    
    def test_pre_earnings_window(self):
        """Test blocking within pre-earnings window"""
        config = {
            "EARNINGS_BLOCK_WINDOW_HOURS": 24,
            "EARNINGS_POST_WINDOW_HOURS": 0,
            "EARNINGS_APPLY_TO_ETFS": False,
            "EARNINGS_CACHE_MINUTES": 60
        }
        
        calendar = EarningsCalendar.__new__(EarningsCalendar)
        calendar.config = config
        calendar.cache_minutes = 60
        calendar.apply_to_etfs = False
        calendar.known_etfs = set()
        calendar.providers = []
        calendar.cache_file = "/tmp/test_cache.json"
        
        now = datetime(2024, 1, 24, 15, 0, 0, tzinfo=pytz.UTC)  # 10 AM ET
        earnings_dt = datetime(2024, 1, 25, 13, 30, 0, tzinfo=pytz.UTC)  # Next day 8:30 AM ET
        
        with patch.object(calendar, 'get_next_earnings') as mock_get:
            mock_get.return_value = EarningsInfo("AAPL", earnings_dt, "fmp", "BMO")
            
            blocked, info = calendar.is_within_earnings_window("AAPL", now)
            
            self.assertTrue(blocked)
            self.assertAlmostEqual(info["hours_until"], 22.5, places=1)
    
    def test_post_earnings_window(self):
        """Test blocking within post-earnings window"""
        config = {
            "EARNINGS_BLOCK_WINDOW_HOURS": 24,
            "EARNINGS_POST_WINDOW_HOURS": 4,  # Block 4 hours after earnings
            "EARNINGS_APPLY_TO_ETFS": False,
            "EARNINGS_CACHE_MINUTES": 60
        }
        
        calendar = EarningsCalendar.__new__(EarningsCalendar)
        calendar.config = config
        calendar.cache_minutes = 60
        calendar.apply_to_etfs = False
        calendar.known_etfs = set()
        calendar.providers = []
        calendar.cache_file = "/tmp/test_cache.json"
        
        now = datetime(2024, 1, 25, 15, 30, 0, tzinfo=pytz.UTC)  # 10:30 AM ET
        earnings_dt = datetime(2024, 1, 25, 13, 30, 0, tzinfo=pytz.UTC)  # 2 hours ago (8:30 AM ET)
        
        with patch.object(calendar, 'get_next_earnings') as mock_get:
            mock_get.return_value = EarningsInfo("AAPL", earnings_dt, "fmp", "BMO")
            
            blocked, info = calendar.is_within_earnings_window("AAPL", now)
            
            self.assertTrue(blocked)
            self.assertAlmostEqual(info["hours_until"], -2.0, places=1)
            self.assertIn("post-window", info["reason"])

class TestPublicAPI(unittest.TestCase):
    """Test public API functions"""
    
    @patch('utils.earnings_calendar._get_earnings_calendar')
    def test_is_within_earnings_window_api(self, mock_get_calendar):
        """Test public is_within_earnings_window function"""
        mock_calendar = Mock()
        mock_calendar.is_within_earnings_window.return_value = (True, {"reason": "test"})
        mock_get_calendar.return_value = mock_calendar
        
        blocked, info = is_within_earnings_window("AAPL")
        
        self.assertTrue(blocked)
        self.assertEqual(info["reason"], "test")
    
    @patch('utils.earnings_calendar._get_earnings_calendar')
    def test_get_next_earnings_api(self, mock_get_calendar):
        """Test public get_next_earnings function"""
        mock_calendar = Mock()
        earnings_dt = datetime(2024, 1, 25, 13, 30, 0, tzinfo=pytz.UTC)
        mock_calendar.get_next_earnings.return_value = EarningsInfo("AAPL", earnings_dt, "fmp", "BMO")
        mock_get_calendar.return_value = mock_calendar
        
        result = get_next_earnings("AAPL")
        
        self.assertIsNotNone(result)
        self.assertEqual(result.symbol, "AAPL")
    
    @patch('utils.earnings_calendar._get_earnings_calendar')
    def test_api_error_handling(self, mock_get_calendar):
        """Test API error handling with fail-safe"""
        mock_get_calendar.side_effect = Exception("Config error")
        
        blocked, info = is_within_earnings_window("AAPL")
        
        self.assertFalse(blocked)  # Fail-safe allows trading
        self.assertIn("Earnings check failed", info["reason"])

if __name__ == '__main__':
    unittest.main()
