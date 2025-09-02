"""
Market Calendar Integration for Enhanced Market Hours Validation

Provides comprehensive market hours validation including:
- Holiday detection
- Early close detection  
- Market status validation
- Pre-market and after-hours handling
"""

import logging
import requests
from datetime import datetime, time, date
from typing import Dict, Optional, Tuple, List
import pytz
from dataclasses import dataclass
import json
import os
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class MarketHours:
    """Market hours information for a specific date"""
    date: date
    is_open: bool
    open_time: Optional[time]
    close_time: Optional[time]
    is_early_close: bool
    reason: Optional[str]  # Holiday name or early close reason

class MarketCalendar:
    """Market calendar with holiday and early close detection"""
    _instance = None
    _initialized = False
    
    def __new__(cls, cache_dir: str = ".cache"):
        if cls._instance is None:
            cls._instance = super(MarketCalendar, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, cache_dir: str = ".cache"):
        if self._initialized:
            return
            
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_file = self.cache_dir / "market_calendar.json"
        self.et_tz = pytz.timezone('US/Eastern')
        
        # Standard market hours (Eastern Time)
        self.standard_open = time(9, 30)  # 9:30 AM ET
        self.standard_close = time(16, 0)  # 4:00 PM ET
        self.early_close = time(13, 0)    # 1:00 PM ET (early close days)
        
        # Load cached data
        self._cache = self._load_cache()
        self._initialized = True
    
    def _load_cache(self) -> Dict:
        """Load cached market calendar data"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                    # Check if cache is from today (refresh daily)
                    cache_date = datetime.fromisoformat(data.get('updated', '2000-01-01'))
                    if cache_date.date() == datetime.now().date():
                        return data
        except Exception as e:
            logger.warning(f"Failed to load market calendar cache: {e}")
        
        return {"updated": datetime.now().isoformat(), "holidays": {}, "early_closes": {}}
    
    def _save_cache(self):
        """Save market calendar data to cache"""
        try:
            self._cache["updated"] = datetime.now().isoformat()
            with open(self.cache_file, 'w') as f:
                json.dump(self._cache, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save market calendar cache: {e}")
    
    def _fetch_market_calendar(self, year: int) -> Dict:
        """Fetch market calendar data from API"""
        try:
            # Try multiple API sources for market calendar data
            
            # Primary: Alpha Vantage (if API key available)
            alpha_vantage_key = os.getenv('ALPHA_VANTAGE_API_KEY')
            if alpha_vantage_key:
                url = f"https://www.alphavantage.co/query"
                params = {
                    'function': 'MARKET_STATUS',
                    'apikey': alpha_vantage_key
                }
                response = requests.get(url, params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    return self._parse_alpha_vantage_calendar(data)
            
            # Fallback: Use hardcoded US market holidays
            return self._get_hardcoded_holidays(year)
            
        except Exception as e:
            logger.warning(f"Failed to fetch market calendar from API: {e}")
            return self._get_hardcoded_holidays(year)
    
    def _parse_alpha_vantage_calendar(self, data: Dict) -> Dict:
        """Parse Alpha Vantage market status response"""
        # This would parse the actual API response
        # For now, return hardcoded data as fallback
        return self._get_hardcoded_holidays(datetime.now().year)
    
    def _get_hardcoded_holidays(self, year: int) -> Dict:
        """Get hardcoded US market holidays and early closes"""
        
        # Calculate actual holiday dates for the year
        holidays = {}
        
        # Fixed date holidays
        holidays[f"{year}-01-01"] = "New Year's Day"
        holidays[f"{year}-06-19"] = "Juneteenth"
        holidays[f"{year}-07-04"] = "Independence Day"
        holidays[f"{year}-12-25"] = "Christmas Day"
        
        # Calculate floating holidays
        from datetime import date, timedelta
        
        # Martin Luther King Jr. Day - 3rd Monday in January
        jan_1 = date(year, 1, 1)
        days_to_monday = (7 - jan_1.weekday()) % 7
        first_monday_jan = jan_1 + timedelta(days=days_to_monday)
        mlk_day = first_monday_jan + timedelta(days=14)  # 3rd Monday
        holidays[mlk_day.isoformat()] = "Martin Luther King Jr. Day"
        
        # Presidents' Day - 3rd Monday in February
        feb_1 = date(year, 2, 1)
        days_to_monday = (7 - feb_1.weekday()) % 7
        first_monday_feb = feb_1 + timedelta(days=days_to_monday)
        presidents_day = first_monday_feb + timedelta(days=14)  # 3rd Monday
        holidays[presidents_day.isoformat()] = "Presidents' Day"
        
        # Memorial Day - Last Monday in May
        may_31 = date(year, 5, 31)
        days_back_to_monday = (may_31.weekday() + 1) % 7
        memorial_day = may_31 - timedelta(days=days_back_to_monday)
        holidays[memorial_day.isoformat()] = "Memorial Day"
        
        # Labor Day - 1st Monday in September
        sep_1 = date(year, 9, 1)
        days_to_monday = (7 - sep_1.weekday()) % 7
        labor_day = sep_1 + timedelta(days=days_to_monday)
        holidays[labor_day.isoformat()] = "Labor Day"
        
        # Thanksgiving - 4th Thursday in November
        nov_1 = date(year, 11, 1)
        days_to_thursday = (3 - nov_1.weekday()) % 7
        first_thursday_nov = nov_1 + timedelta(days=days_to_thursday)
        thanksgiving = first_thursday_nov + timedelta(days=21)  # 4th Thursday
        holidays[thanksgiving.isoformat()] = "Thanksgiving"
        
        # Good Friday - Calculate based on Easter (simplified approximation)
        # Using a basic Easter calculation for common years
        easter_dates = {
            2024: date(2024, 3, 31),
            2025: date(2025, 4, 20),
            2026: date(2026, 4, 5),
            2027: date(2027, 3, 28),
            2028: date(2028, 4, 16)
        }
        if year in easter_dates:
            good_friday = easter_dates[year] - timedelta(days=2)
            holidays[good_friday.isoformat()] = "Good Friday"
        
        # Early close days (1:00 PM ET close) - calculate dynamically
        early_closes = {}
        
        # Day before Independence Day (if July 4th falls on weekday)
        july_4 = date(year, 7, 4)
        if july_4.weekday() < 5:  # Monday-Friday
            july_3 = date(year, 7, 3)
            if july_3.weekday() < 5:  # July 3rd is also a weekday
                early_closes[july_3.isoformat()] = "Day before Independence Day"
        
        # Day after Thanksgiving (Black Friday)
        black_friday = thanksgiving + timedelta(days=1)
        early_closes[black_friday.isoformat()] = "Day after Thanksgiving"
        
        # Christmas Eve (if it falls on a weekday)
        christmas_eve = date(year, 12, 24)
        if christmas_eve.weekday() < 5:  # Monday-Friday
            early_closes[christmas_eve.isoformat()] = "Christmas Eve"
        
        return {
            "holidays": holidays,
            "early_closes": early_closes
        }
    
    def get_market_hours(self, target_date: date = None) -> MarketHours:
        """Get market hours for a specific date"""
        if target_date is None:
            target_date = datetime.now().date()
        
        date_str = target_date.isoformat()
        
        # Check if we need to fetch calendar data for this year
        year = target_date.year
        year_key = str(year)
        
        if year_key not in self._cache:
            logger.info(f"Fetching market calendar data for {year}")
            calendar_data = self._fetch_market_calendar(year)
            self._cache[year_key] = calendar_data
            self._save_cache()
        else:
            logger.debug(f"Using cached market calendar data for {year}")
        
        year_data = self._cache[year_key]
        holidays = year_data.get("holidays", {})
        early_closes = year_data.get("early_closes", {})
        
        # Check if it's a weekend
        if target_date.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return MarketHours(
                date=target_date,
                is_open=False,
                open_time=None,
                close_time=None,
                is_early_close=False,
                reason="Weekend"
            )
        
        # Check if it's a holiday
        if date_str in holidays:
            return MarketHours(
                date=target_date,
                is_open=False,
                open_time=None,
                close_time=None,
                is_early_close=False,
                reason=holidays[date_str]
            )
        
        # Check if it's an early close day
        if date_str in early_closes:
            return MarketHours(
                date=target_date,
                is_open=True,
                open_time=self.standard_open,
                close_time=self.early_close,
                is_early_close=True,
                reason=early_closes[date_str]
            )
        
        # Regular trading day
        return MarketHours(
            date=target_date,
            is_open=True,
            open_time=self.standard_open,
            close_time=self.standard_close,
            is_early_close=False,
            reason=None
        )
    
    def is_market_open(self, check_time: datetime = None) -> Tuple[bool, str]:
        """
        Check if market is currently open
        
        Returns:
            Tuple of (is_open, reason)
        """
        if check_time is None:
            check_time = datetime.now(self.et_tz)
        
        # Convert to ET if not already
        if check_time.tzinfo is None:
            check_time = self.et_tz.localize(check_time)
        elif check_time.tzinfo != self.et_tz:
            check_time = check_time.astimezone(self.et_tz)
        
        market_hours = self.get_market_hours(check_time.date())
        
        # Market closed for holiday/weekend
        if not market_hours.is_open:
            return False, f"Market closed: {market_hours.reason}"
        
        current_time = check_time.time()
        
        # Before market open
        if current_time < market_hours.open_time:
            return False, f"Pre-market: Opens at {market_hours.open_time.strftime('%H:%M')} ET"
        
        # After market close
        if current_time >= market_hours.close_time:
            close_reason = "early close" if market_hours.is_early_close else "regular close"
            return False, f"After-hours: Market closed at {market_hours.close_time.strftime('%H:%M')} ET ({close_reason})"
        
        # Market is open
        return True, "Market open"
    
    def get_market_status(self, check_time: datetime = None) -> Dict:
        """Get comprehensive market status information"""
        if check_time is None:
            check_time = datetime.now(self.et_tz)
        
        # Convert to ET if not already
        if check_time.tzinfo is None:
            check_time = self.et_tz.localize(check_time)
        elif check_time.tzinfo != self.et_tz:
            check_time = check_time.astimezone(self.et_tz)
        
        market_hours = self.get_market_hours(check_time.date())
        is_open, reason = self.is_market_open(check_time)
        
        # Calculate time to next open/close
        current_time = check_time.time()
        time_info = ""
        
        if market_hours.is_open:
            if is_open:
                # Market is open, show time to close
                close_dt = datetime.combine(check_time.date(), market_hours.close_time)
                close_dt = self.et_tz.localize(close_dt)
                time_diff = close_dt - check_time
                hours, remainder = divmod(time_diff.total_seconds(), 3600)
                minutes = remainder // 60
                time_info = f"Closes in {int(hours)}h {int(minutes)}m"
            else:
                if current_time < market_hours.open_time:
                    # Pre-market
                    open_dt = datetime.combine(check_time.date(), market_hours.open_time)
                    open_dt = self.et_tz.localize(open_dt)
                    time_diff = open_dt - check_time
                    hours, remainder = divmod(time_diff.total_seconds(), 3600)
                    minutes = remainder // 60
                    time_info = f"Opens in {int(hours)}h {int(minutes)}m"
        
        return {
            "is_open": is_open,
            "reason": reason,
            "date": check_time.date().isoformat(),
            "current_time_et": check_time.strftime("%H:%M:%S ET"),
            "market_hours": {
                "open": market_hours.open_time.strftime("%H:%M") if market_hours.open_time else None,
                "close": market_hours.close_time.strftime("%H:%M") if market_hours.close_time else None,
                "is_early_close": market_hours.is_early_close
            },
            "time_info": time_info,
            "holiday_reason": market_hours.reason if not market_hours.is_open else None
        }
    
    def validate_trading_time(self, check_time: datetime = None) -> Tuple[bool, str]:
        """
        Validate if it's appropriate to attempt trading
        
        Returns:
            Tuple of (can_trade, reason)
        """
        is_open, reason = self.is_market_open(check_time)
        
        if not is_open:
            return False, f"Trading blocked: {reason}"
        
        return True, "Market open - trading allowed"

# Global instance for easy import
market_calendar = MarketCalendar()

def get_market_status() -> Dict:
    """Convenience function to get current market status"""
    return market_calendar.get_market_status()

def is_market_open() -> Tuple[bool, str]:
    """Convenience function to check if market is open"""
    return market_calendar.is_market_open()

def validate_trading_time(check_time: datetime = None) -> Tuple[bool, str]:
    """Convenience function to validate trading time"""
    return market_calendar.validate_trading_time(check_time)
