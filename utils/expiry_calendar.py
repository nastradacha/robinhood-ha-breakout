"""
Per-Symbol Expiry Calendar and DTE Policy (v1.0.0)

Implements symbol-specific expiry availability and DTE constraints to prevent
trading on symbols without same-day options availability.

Key Features:
- Per-symbol expiry calendar (0DTE availability by symbol)
- Configurable max DTE per symbol type
- Fallback to weekly expiries with time constraints
- Prevents silent "search forward" behavior
"""

from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

# Per-symbol expiry availability calendar
SYMBOL_EXPIRY_CALENDAR = {
    # Liquid ETFs with M/W/F 0DTE availability
    "SPY": {
        "0dte_days": [0, 2, 4],  # Monday, Wednesday, Friday
        "max_dte": 2,
        "tier": "liquid"
    },
    "QQQ": {
        "0dte_days": [0, 2, 4],  # Monday, Wednesday, Friday
        "max_dte": 2,
        "tier": "liquid"
    },
    
    # Standard ETFs with Friday-only 0DTE
    "IWM": {
        "0dte_days": [4],  # Friday only
        "max_dte": 2,
        "tier": "standard"
    },
    "DIA": {
        "0dte_days": [4],  # Friday only
        "max_dte": 2,
        "tier": "standard"
    },
    "GLD": {
        "0dte_days": [4],  # Friday only
        "max_dte": 2,
        "tier": "standard"
    },
    "TLT": {
        "0dte_days": [4],  # Friday only
        "max_dte": 2,
        "tier": "standard"
    },
    
    # Sector ETFs with Friday-only and higher max DTE
    "XLF": {
        "0dte_days": [4],  # Friday only
        "max_dte": 3,  # Allow up to 3 DTE for sector ETFs
        "tier": "sector"
    },
    "XLK": {
        "0dte_days": [4],  # Friday only
        "max_dte": 3,
        "tier": "sector"
    },
    "XLE": {
        "0dte_days": [4],  # Friday only
        "max_dte": 3,
        "tier": "sector"
    },
    
    # Volatility products with special handling
    "UVXY": {
        "0dte_days": [4],  # Friday only
        "max_dte": 1,  # Strict DTE for volatility
        "tier": "volatility"
    },
    "VIX": {
        "0dte_days": [2, 4],  # Wednesday, Friday
        "max_dte": 1,
        "tier": "volatility"
    }
}

# Default configuration for unknown symbols
DEFAULT_SYMBOL_CONFIG = {
    "0dte_days": [4],  # Friday only
    "max_dte": 2,
    "tier": "unknown"
}

def get_symbol_expiry_config(symbol: str) -> Dict:
    """Get expiry configuration for a symbol."""
    return SYMBOL_EXPIRY_CALENDAR.get(symbol, DEFAULT_SYMBOL_CONFIG)

def is_0dte_available(symbol: str, target_date: datetime = None) -> bool:
    """Check if 0DTE is available for symbol on target date."""
    if target_date is None:
        target_date = datetime.now()
    
    config = get_symbol_expiry_config(symbol)
    weekday = target_date.weekday()  # 0=Monday, 6=Sunday
    
    return weekday in config["0dte_days"]

def get_valid_expiry_dates(symbol: str, max_dte_override: int = None) -> list:
    """Get list of valid expiry dates for symbol within DTE constraints."""
    config = get_symbol_expiry_config(symbol)
    max_dte = max_dte_override or config["max_dte"]
    
    today = datetime.now().date()
    valid_dates = []
    
    # Check each day within max_dte range
    for days_ahead in range(max_dte + 1):
        check_date = today + timedelta(days=days_ahead)
        check_datetime = datetime.combine(check_date, datetime.min.time())
        
        if is_0dte_available(symbol, check_datetime):
            valid_dates.append(check_date.strftime("%Y-%m-%d"))
    
    return valid_dates

def get_expiry_policy_with_calendar(symbol: str, current_time: datetime = None) -> Tuple[str, Optional[str]]:
    """
    Get expiry policy respecting per-symbol calendar constraints.
    
    Returns:
        Tuple of (policy, expiry_date) or (None, None) if no valid expiry
    """
    if current_time is None:
        current_time = datetime.now()
    
    config = get_symbol_expiry_config(symbol)
    hour = current_time.hour
    minute = current_time.minute
    
    # Check if we're in trading hours for same-day expiry
    in_trading_hours = (10 <= hour < 15) or (hour == 15 and minute <= 15)
    
    if in_trading_hours:
        # Check if 0DTE is available today for this symbol
        if is_0dte_available(symbol, current_time):
            today = current_time.date()
            return "0DTE", today.strftime("%Y-%m-%d")
    
    # Look for next available expiry within max_dte constraint
    valid_dates = get_valid_expiry_dates(symbol)
    
    if not valid_dates:
        logger.warning(f"No valid expiry dates found for {symbol} within {config['max_dte']} DTE limit")
        return None, None
    
    # Use the nearest valid expiry
    nearest_expiry = valid_dates[0]
    
    # Calculate DTE for the selected expiry
    expiry_date = datetime.strptime(nearest_expiry, "%Y-%m-%d").date()
    dte = (expiry_date - current_time.date()).days
    
    if dte == 0:
        return "0DTE", nearest_expiry
    elif dte <= 2:
        return "SHORT_DTE", nearest_expiry
    else:
        return "WEEKLY", nearest_expiry

def validate_expiry_constraints(symbol: str, expiry_date_str: str) -> Tuple[bool, str]:
    """
    Validate that expiry date meets symbol-specific constraints.
    
    Returns:
        Tuple of (is_valid, reason)
    """
    try:
        config = get_symbol_expiry_config(symbol)
        expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
        today = datetime.now().date()
        
        dte = (expiry_date - today).days
        
        # Check max DTE constraint
        if dte > config["max_dte"]:
            return False, f"DTE {dte} exceeds max {config['max_dte']} for {symbol}"
        
        # Check if expiry day is valid for this symbol
        expiry_weekday = expiry_date.weekday()
        if expiry_weekday not in config["0dte_days"] and dte <= 2:
            return False, f"Expiry weekday {expiry_weekday} not available for {symbol}"
        
        # Additional time constraint for same-day expiry
        if dte == 0:
            now = datetime.now()
            if now.hour >= 15 and now.minute > 15:
                return False, "Too late for 0DTE entry (after 15:15 ET)"
        
        return True, "Valid expiry"
        
    except Exception as e:
        return False, f"Expiry validation error: {e}"

def get_trading_time_remaining(expiry_date_str: str) -> float:
    """
    Calculate trading time remaining until expiry in fractional days.
    
    Returns:
        Float representing trading days remaining (e.g., 0.25 = 6 hours)
    """
    try:
        expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
        now = datetime.now()
        
        # Market close time (4:00 PM ET)
        market_close = datetime.combine(expiry_date, datetime.min.time().replace(hour=16))
        
        if now >= market_close:
            return 0.0
        
        time_diff = market_close - now
        hours_remaining = time_diff.total_seconds() / 3600
        
        # Convert to fractional trading days (assuming 6.5 hour trading day)
        trading_days_remaining = hours_remaining / 6.5
        
        return max(0.0, trading_days_remaining)
        
    except Exception as e:
        logger.error(f"Error calculating trading time remaining: {e}")
        return 0.0
