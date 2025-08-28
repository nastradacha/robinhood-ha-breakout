"""
Tiered Option Filters by Symbol Type (v1.0.0)

Implements symbol-specific option liquidity filters to prevent trading
on illiquid contracts while allowing appropriate flexibility per symbol tier.

Key Features:
- Tiered filters: liquid ETFs, standard ETFs, sector ETFs, volatility products
- Fallback logic with size reduction for marginal liquidity
- Explicit abort when no contracts meet minimum standards
- Prevents silent trading on poor liquidity
"""

from typing import Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

# Tiered option filter configurations by symbol type
OPTION_FILTER_TIERS = {
    "liquid": {
        # SPY, QQQ - highest liquidity requirements
        "min_open_interest": 5000,
        "min_volume": 50,
        "max_spread_abs": 0.10,
        "max_spread_pct": 8.0,
        "fallback_enabled": True,
        "fallback_min_oi": 2000,
        "fallback_max_spread_abs": 0.15,
        "fallback_max_spread_pct": 12.0
    },
    "standard": {
        # IWM, DIA, GLD, TLT - standard requirements
        "min_open_interest": 2000,
        "min_volume": 10,
        "max_spread_abs": 0.15,
        "max_spread_pct": 12.0,
        "fallback_enabled": True,
        "fallback_min_oi": 1000,
        "fallback_max_spread_abs": 0.20,
        "fallback_max_spread_pct": 18.0
    },
    "sector": {
        # XLF, XLK, XLE - relaxed for sector ETFs
        "min_open_interest": 1000,
        "min_volume": 0,  # Volume not required
        "max_spread_abs": 0.25,
        "max_spread_pct": 20.0,
        "fallback_enabled": True,
        "fallback_min_oi": 500,
        "fallback_max_spread_abs": 0.35,
        "fallback_max_spread_pct": 30.0
    },
    "volatility": {
        # UVXY, VIX - special handling for volatility products
        "min_open_interest": 1500,
        "min_volume": 20,
        "max_spread_abs": 0.20,
        "max_spread_pct": 15.0,
        "fallback_enabled": False,  # No fallback for volatility
        "fallback_min_oi": None,
        "fallback_max_spread_abs": None,
        "fallback_max_spread_pct": None
    },
    "unknown": {
        # Default conservative settings for unknown symbols
        "min_open_interest": 2000,
        "min_volume": 10,
        "max_spread_abs": 0.15,
        "max_spread_pct": 15.0,
        "fallback_enabled": False,
        "fallback_min_oi": None,
        "fallback_max_spread_abs": None,
        "fallback_max_spread_pct": None
    }
}

def get_symbol_tier(symbol: str) -> str:
    """Determine the tier for a given symbol."""
    from utils.expiry_calendar import get_symbol_expiry_config
    
    config = get_symbol_expiry_config(symbol)
    return config.get("tier", "unknown")

def get_option_filters(symbol: str, use_fallback: bool = False) -> Dict:
    """Get option filters for a symbol, optionally using fallback settings."""
    tier = get_symbol_tier(symbol)
    tier_config = OPTION_FILTER_TIERS.get(tier, OPTION_FILTER_TIERS["unknown"])
    
    if use_fallback and tier_config.get("fallback_enabled", False):
        return {
            "min_open_interest": tier_config["fallback_min_oi"],
            "min_volume": tier_config["min_volume"],  # Keep same volume requirement
            "max_spread_abs": tier_config["fallback_max_spread_abs"],
            "max_spread_pct": tier_config["fallback_max_spread_pct"]
        }
    else:
        return {
            "min_open_interest": tier_config["min_open_interest"],
            "min_volume": tier_config["min_volume"],
            "max_spread_abs": tier_config["max_spread_abs"],
            "max_spread_pct": tier_config["max_spread_pct"]
        }

def validate_contract_liquidity(
    symbol: str,
    bid: float,
    ask: float,
    open_interest: int,
    volume: int,
    use_fallback: bool = False
) -> Tuple[bool, str]:
    """
    Validate contract liquidity against symbol-specific filters.
    
    Args:
        symbol: Trading symbol
        bid: Bid price
        ask: Ask price
        open_interest: Open interest
        volume: Daily volume
        use_fallback: Whether to use fallback (relaxed) criteria
    
    Returns:
        Tuple of (passes_filter, reason)
    """
    filters = get_option_filters(symbol, use_fallback)
    tier = get_symbol_tier(symbol)
    
    # Calculate spread metrics
    if bid <= 0 or ask <= 0:
        return False, "Invalid bid/ask prices"
    
    spread_abs = ask - bid
    mid_price = (bid + ask) / 2
    spread_pct = (spread_abs / mid_price) * 100 if mid_price > 0 else 1000
    
    # Check open interest
    if open_interest < filters["min_open_interest"]:
        return False, f"OI {open_interest} < min {filters['min_open_interest']} ({tier} tier)"
    
    # Check volume (if required)
    if filters["min_volume"] > 0 and volume < filters["min_volume"]:
        return False, f"Volume {volume} < min {filters['min_volume']} ({tier} tier)"
    
    # Check absolute spread
    if spread_abs > filters["max_spread_abs"]:
        return False, f"Spread ${spread_abs:.3f} > max ${filters['max_spread_abs']:.3f} ({tier} tier)"
    
    # Check percentage spread
    if spread_pct > filters["max_spread_pct"]:
        return False, f"Spread {spread_pct:.1f}% > max {filters['max_spread_pct']:.1f}% ({tier} tier)"
    
    filter_type = "fallback" if use_fallback else "primary"
    return True, f"Passes {tier} tier {filter_type} filters (OI:{open_interest}, Vol:{volume}, Spread:${spread_abs:.3f}/{spread_pct:.1f}%)"

def should_attempt_fallback(symbol: str) -> bool:
    """Check if fallback filters are available for this symbol."""
    tier = get_symbol_tier(symbol)
    tier_config = OPTION_FILTER_TIERS.get(tier, OPTION_FILTER_TIERS["unknown"])
    return tier_config.get("fallback_enabled", False)

def get_filter_summary(symbol: str) -> str:
    """Get human-readable summary of filters for a symbol."""
    tier = get_symbol_tier(symbol)
    primary_filters = get_option_filters(symbol, use_fallback=False)
    
    summary = f"{symbol} ({tier} tier): OI≥{primary_filters['min_open_interest']}"
    
    if primary_filters['min_volume'] > 0:
        summary += f", Vol≥{primary_filters['min_volume']}"
    
    summary += f", Spread≤${primary_filters['max_spread_abs']:.2f} or {primary_filters['max_spread_pct']:.1f}%"
    
    if should_attempt_fallback(symbol):
        fallback_filters = get_option_filters(symbol, use_fallback=True)
        summary += f" (fallback: OI≥{fallback_filters['min_open_interest']}, Spread≤${fallback_filters['max_spread_abs']:.2f})"
    
    return summary
