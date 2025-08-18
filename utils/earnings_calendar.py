"""
Earnings Calendar Integration (US-FA-002)

This module provides earnings calendar integration to block trades around earnings announcements.
Supports multiple providers (FMP primary, Alpha Vantage fallback) with caching and fail-safe behavior.

Key Features:
- Block trades within configurable window before/after earnings
- Support for BMO (Before Market Open) and AMC (After Market Close) timing
- Timezone-aware datetime handling (ET/UTC conversion)
- 12-hour caching to minimize API calls
- ETF handling (configurable whether to apply earnings blocking)
- Fail-safe design allows trading if earnings data unavailable
- Comprehensive logging with [EARNINGS-GATE] prefix

Usage:
    from utils.earnings_calendar import is_within_earnings_window
    
    blocked, info = is_within_earnings_window("AAPL")
    if blocked:
        print(f"AAPL blocked: {info['reason']}")
"""

import json
import logging
import os
import requests
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
import pytz
import yaml

# Configure logging
logger = logging.getLogger(__name__)

# Timezone constants
ET_TZ = pytz.timezone('US/Eastern')
UTC_TZ = pytz.UTC

class EarningsInfo:
    """Data class for earnings information"""
    def __init__(self, symbol: str, earnings_dt: datetime, source: str, session: str = ""):
        self.symbol = symbol
        self.earnings_dt = earnings_dt  # UTC datetime
        self.source = source
        self.session = session  # "BMO", "AMC", or ""
    
    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "earnings_dt_utc": self.earnings_dt.isoformat(),
            "source": self.source,
            "session": self.session
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'EarningsInfo':
        return cls(
            symbol=data["symbol"],
            earnings_dt=datetime.fromisoformat(data["earnings_dt_utc"].replace('Z', '+00:00')),
            source=data["source"],
            session=data.get("session", "")
        )

class BaseEarningsProvider(ABC):
    """Abstract base class for earnings data providers"""
    
    @abstractmethod
    def fetch_next_earnings(self, symbol: str) -> Optional[EarningsInfo]:
        """Fetch next earnings date for symbol. Returns None if no upcoming earnings."""
        pass

class FmpEarningsProvider(BaseEarningsProvider):
    """Financial Modeling Prep earnings provider"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://financialmodelingprep.com/api/v3"
    
    def fetch_next_earnings(self, symbol: str) -> Optional[EarningsInfo]:
        """Fetch next earnings from FMP API"""
        try:
            # Get earnings calendar for next 30 days
            url = f"{self.base_url}/earning_calendar"
            params = {
                "apikey": self.api_key,
                "from": datetime.now().strftime("%Y-%m-%d"),
                "to": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            earnings_data = response.json()
            
            # Find next earnings for this symbol
            for earning in earnings_data:
                if earning.get("symbol", "").upper() == symbol.upper():
                    date_str = earning.get("date")
                    time_str = earning.get("time", "")
                    
                    if not date_str:
                        continue
                    
                    # Parse earnings datetime
                    earnings_dt = self._parse_earnings_datetime(date_str, time_str)
                    if earnings_dt and earnings_dt > datetime.now(UTC_TZ):
                        session = self._determine_session(time_str)
                        return EarningsInfo(symbol, earnings_dt, "fmp", session)
            
            return None
            
        except Exception as e:
            logger.warning(f"[EARNINGS-GATE] FMP API error for {symbol}: {e}")
            return None
    
    def _parse_earnings_datetime(self, date_str: str, time_str: str) -> Optional[datetime]:
        """Parse earnings date and time to UTC datetime"""
        try:
            # Parse date
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            
            # Determine time based on session or explicit time
            if time_str:
                time_str = time_str.upper()
                if "BMO" in time_str or "BEFORE" in time_str:
                    # Before market open: 8:30 AM ET
                    time_obj = datetime.strptime("08:30", "%H:%M").time()
                elif "AMC" in time_str or "AFTER" in time_str:
                    # After market close: 4:15 PM ET
                    time_obj = datetime.strptime("16:15", "%H:%M").time()
                else:
                    # Try to parse explicit time
                    try:
                        time_obj = datetime.strptime(time_str, "%H:%M").time()
                    except:
                        # Default to AMC if can't parse
                        time_obj = datetime.strptime("16:15", "%H:%M").time()
            else:
                # Default to AMC (4:15 PM ET)
                time_obj = datetime.strptime("16:15", "%H:%M").time()
            
            # Combine date and time in ET, then convert to UTC
            et_dt = ET_TZ.localize(datetime.combine(date_obj, time_obj))
            utc_dt = et_dt.astimezone(UTC_TZ)
            
            return utc_dt
            
        except Exception as e:
            logger.warning(f"[EARNINGS-GATE] Failed to parse datetime {date_str} {time_str}: {e}")
            return None
    
    def _determine_session(self, time_str: str) -> str:
        """Determine earnings session from time string"""
        if not time_str:
            return "AMC"  # Default
        
        time_str = time_str.upper()
        if "BMO" in time_str or "BEFORE" in time_str:
            return "BMO"
        elif "AMC" in time_str or "AFTER" in time_str:
            return "AMC"
        else:
            return ""

class AlphaVantageEarningsProvider(BaseEarningsProvider):
    """Alpha Vantage earnings provider (fallback)"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://www.alphavantage.co/query"
    
    def fetch_next_earnings(self, symbol: str) -> Optional[EarningsInfo]:
        """Fetch next earnings from Alpha Vantage API"""
        try:
            params = {
                "function": "EARNINGS",
                "symbol": symbol,
                "apikey": self.api_key
            }
            
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # Check for API limit or error
            if "Error Message" in data or "Note" in data:
                logger.warning(f"[EARNINGS-GATE] Alpha Vantage API limit/error for {symbol}: {data}")
                return None
            
            # Look for upcoming earnings in quarterly earnings
            quarterly_earnings = data.get("quarterlyEarnings", [])
            now_utc = datetime.now(UTC_TZ)
            
            for earning in quarterly_earnings:
                reported_date = earning.get("reportedDate")
                if not reported_date:
                    continue
                
                try:
                    # Parse date (Alpha Vantage typically provides date only)
                    date_obj = datetime.strptime(reported_date, "%Y-%m-%d").date()
                    
                    # Default to AMC (4:15 PM ET) since Alpha Vantage doesn't provide time
                    time_obj = datetime.strptime("16:15", "%H:%M").time()
                    et_dt = ET_TZ.localize(datetime.combine(date_obj, time_obj))
                    utc_dt = et_dt.astimezone(UTC_TZ)
                    
                    if utc_dt > now_utc:
                        return EarningsInfo(symbol, utc_dt, "alpha_vantage", "AMC")
                        
                except Exception as e:
                    logger.warning(f"[EARNINGS-GATE] Failed to parse Alpha Vantage date {reported_date}: {e}")
                    continue
            
            return None
            
        except Exception as e:
            logger.warning(f"[EARNINGS-GATE] Alpha Vantage API error for {symbol}: {e}")
            return None

class EarningsCalendar:
    """Main earnings calendar service with caching and provider management"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.cache_file = ".cache/earnings_cache.json"
        self.cache_minutes = config.get("EARNINGS_CACHE_MINUTES", 720)  # 12 hours default
        
        # Initialize providers
        self.providers = []
        
        # Primary provider: FMP
        fmp_key = self._get_env_value(config.get("FMP_API_KEY", ""))
        if fmp_key:
            self.providers.append(FmpEarningsProvider(fmp_key))
        
        # Fallback provider: Alpha Vantage
        av_key = self._get_env_value(config.get("ALPHA_VANTAGE_API_KEY", ""))
        if av_key:
            self.providers.append(AlphaVantageEarningsProvider(av_key))
        
        if not self.providers:
            logger.warning("[EARNINGS-GATE] No earnings providers configured")
        
        # ETF handling
        self.apply_to_etfs = config.get("EARNINGS_APPLY_TO_ETFS", False)
        self.known_etfs = {
            "SPY", "QQQ", "IWM", "TLT", "GLD", "DIA", "XLK", "XLF", "XLE", 
            "UVXY", "SMH", "USO", "SLV", "VIX", "EFA", "EEM", "FXI", "VEA"
        }
    
    def _get_env_value(self, config_value: str) -> str:
        """Extract environment variable value from config"""
        if config_value.startswith("<env:") and config_value.endswith(">"):
            env_var = config_value[5:-1]
            return os.getenv(env_var, "")
        return config_value
    
    def _is_etf(self, symbol: str) -> bool:
        """Check if symbol is an ETF"""
        return symbol.upper() in self.known_etfs
    
    def _load_cache(self) -> Dict:
        """Load earnings cache from file"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"[EARNINGS-GATE] Failed to load cache: {e}")
        return {}
    
    def _save_cache(self, cache: Dict):
        """Save earnings cache to file"""
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(cache, f, indent=2)
        except Exception as e:
            logger.warning(f"[EARNINGS-GATE] Failed to save cache: {e}")
    
    def _is_cache_valid(self, cache_entry: Dict, now: datetime = None) -> bool:
        """Check if cache entry is still valid"""
        try:
            if now is None:
                now = datetime.now(UTC_TZ)
            fetched_at = datetime.fromisoformat(cache_entry["fetched_at_utc"])
            age_minutes = (now - fetched_at).total_seconds() / 60
            return age_minutes < self.cache_minutes
        except:
            return False
    
    def get_next_earnings(self, symbol: str, now: datetime = None) -> Optional[EarningsInfo]:
        """Get next earnings date for symbol with caching"""
        if now is None:
            now = datetime.now(UTC_TZ)
        
        symbol = symbol.upper()
        
        # Check if ETF and ETF blocking is disabled
        if self._is_etf(symbol) and not self.apply_to_etfs:
            logger.debug(f"[EARNINGS-GATE] Skipping ETF {symbol} (EARNINGS_APPLY_TO_ETFS=false)")
            return None
        
        # Check cache first
        cache = self._load_cache()
        cache_key = f"{symbol}_earnings"
        
        if cache_key in cache and self._is_cache_valid(cache[cache_key], now):
            logger.debug(f"[EARNINGS-GATE] Using cached earnings for {symbol}")
            earnings_data = cache[cache_key]
            if earnings_data.get("earnings_dt_utc"):
                return EarningsInfo.from_dict(earnings_data)
            else:
                # Cached "no earnings" result
                return None
        
        # Check if providers are available
        if not self.providers:
            logger.warning(f"[EARNINGS-GATE] No providers configured for {symbol}")
            # Cache negative result when no providers
            cache[cache_key] = {
                "symbol": symbol,
                "fetched_at_utc": now.isoformat(),
                "earnings_dt_utc": None,
                "source": "none"
            }
            self._save_cache(cache)
            return None
        
        # Fetch from providers
        
        for provider in self.providers:
            try:
                earnings_info = provider.fetch_next_earnings(symbol)
                
                # Cache the result (even if None)
                cache_entry = {
                    "symbol": symbol,
                    "fetched_at_utc": now.isoformat(),
                    "source": provider.__class__.__name__
                }
                
                if earnings_info:
                    cache_entry.update(earnings_info.to_dict())
                    logger.info(f"[EARNINGS-GATE] Found earnings for {symbol}: {earnings_info.earnings_dt} ({earnings_info.session})")
                else:
                    cache_entry["earnings_dt_utc"] = None
                    logger.debug(f"[EARNINGS-GATE] No upcoming earnings for {symbol}")
                
                cache[cache_key] = cache_entry
                self._save_cache(cache)
                
                return earnings_info
                
            except Exception as e:
                logger.warning(f"[EARNINGS-GATE] Provider {provider.__class__.__name__} failed for {symbol}: {e}")
                continue
        
        # No providers succeeded - cache negative result
        cache[cache_key] = {
            "symbol": symbol,
            "fetched_at_utc": now.isoformat(),
            "earnings_dt_utc": None,
            "source": "none"
        }
        self._save_cache(cache)
        
        logger.warning(f"[EARNINGS-GATE] All providers failed for {symbol}")
        return None
    
    def is_within_earnings_window(self, symbol: str, now: datetime = None) -> Tuple[bool, Dict]:
        """
        Check if symbol is within earnings blocking window
        
        Returns:
            (blocked, info_dict)
            
        info_dict contains:
            - symbol: str
            - blocked: bool
            - earnings_dt_local: str (if earnings found)
            - hours_until: float (if earnings found)
            - reason: str
            - source: str
            - cached: bool
        """
        if now is None:
            now = datetime.now(UTC_TZ)
        
        symbol = symbol.upper()
        
        # Get earnings info
        earnings_info = self.get_next_earnings(symbol, now)
        
        base_info = {
            "symbol": symbol,
            "blocked": False,
            "source": "none",
            "cached": False
        }
        
        if not earnings_info:
            base_info.update({
                "reason": "No upcoming earnings found",
                "blocked": False
            })
            return False, base_info
        
        # Calculate time until earnings
        hours_until = (earnings_info.earnings_dt - now).total_seconds() / 3600
        
        # Check if within blocking window
        pre_window_hours = self.config.get("EARNINGS_BLOCK_WINDOW_HOURS", 24)
        post_window_hours = self.config.get("EARNINGS_POST_WINDOW_HOURS", 0)
        
        # Convert earnings time to local ET for display
        earnings_et = earnings_info.earnings_dt.astimezone(ET_TZ)
        earnings_local_str = earnings_et.strftime("%Y-%m-%d %H:%M ET")
        
        info = {
            "symbol": symbol,
            "earnings_dt_local": earnings_local_str,
            "hours_until": round(hours_until, 1),
            "source": earnings_info.source,
            "cached": True,  # Since we use cache
            "session": earnings_info.session
        }
        
        # Check if within pre-earnings window
        if 0 <= hours_until <= pre_window_hours:
            info.update({
                "blocked": True,
                "reason": f"Earnings in {info['hours_until']}h ({info['session']}) - within {pre_window_hours}h window"
            })
            return True, info
        
        # Check if within post-earnings window (if configured)
        if post_window_hours > 0 and -post_window_hours <= hours_until < 0:
            info.update({
                "blocked": True,
                "reason": f"Earnings {abs(info['hours_until'])}h ago - within {post_window_hours}h post-window"
            })
            return True, info
        
        # Not within blocking window
        info.update({
            "blocked": False,
            "reason": f"Earnings in {info['hours_until']}h - outside {pre_window_hours}h window"
        })
        return False, info

# Global instance
_earnings_calendar = None

def _get_earnings_calendar():
    """Get or create global earnings calendar instance"""
    global _earnings_calendar
    if _earnings_calendar is None:
        try:
            with open("config.yaml", 'r') as f:
                config = yaml.safe_load(f)
            _earnings_calendar = EarningsCalendar(config)
        except Exception as e:
            logger.error(f"[EARNINGS-GATE] Failed to load config: {e}")
            _earnings_calendar = EarningsCalendar({})
    return _earnings_calendar

def is_within_earnings_window(symbol: str, now: datetime = None) -> Tuple[bool, Dict]:
    """
    Public API: Check if symbol is within earnings blocking window
    
    Args:
        symbol: Stock symbol to check
        now: Current time (UTC), defaults to datetime.now(UTC)
    
    Returns:
        (blocked, info_dict) where info_dict contains details about earnings timing
    """
    try:
        calendar = _get_earnings_calendar()
        return calendar.is_within_earnings_window(symbol, now)
    except Exception as e:
        logger.error(f"[EARNINGS-GATE] Error checking earnings window for {symbol}: {e}")
        # Fail-safe: allow trading if earnings check fails
        return False, {
            "symbol": symbol,
            "blocked": False,
            "reason": f"Earnings check failed: {e}",
            "source": "error",
            "cached": False
        }

def get_next_earnings(symbol: str, now: datetime = None) -> Optional[EarningsInfo]:
    """
    Public API: Get next earnings date for symbol
    
    Args:
        symbol: Stock symbol to check
        now: Current time (UTC), defaults to datetime.now(UTC)
    
    Returns:
        EarningsInfo object or None if no upcoming earnings
    """
    try:
        calendar = _get_earnings_calendar()
        return calendar.get_next_earnings(symbol, now)
    except Exception as e:
        logger.error(f"[EARNINGS-GATE] Error getting earnings for {symbol}: {e}")
        return None

def validate_earnings_blocking(symbol: str, now: datetime = None) -> Tuple[bool, str]:
    """
    Validate if trading should be blocked due to earnings
    
    Args:
        symbol: Stock symbol to check
        now: Current time (UTC), defaults to datetime.now(UTC)
    
    Returns:
        (can_trade, reason) - can_trade=False means trading should be blocked
    """
    try:
        # Check if earnings blocking is enabled
        with open("config.yaml", 'r') as f:
            config = yaml.safe_load(f)
        
        if not config.get("EARNINGS_ENABLED", True):
            return True, "Earnings blocking disabled"
        
        blocked, info = is_within_earnings_window(symbol, now)
        
        if blocked:
            return False, info["reason"]
        else:
            return True, info["reason"]
            
    except Exception as e:
        logger.error(f"[EARNINGS-GATE] Error validating earnings blocking for {symbol}: {e}")
        # Fail-safe: allow trading if validation fails
        return True, f"Earnings validation failed: {e}"
