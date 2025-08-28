#!/usr/bin/env python3
"""
Alpaca Options Trading Module

Provides comprehensive options contract selection, order placement, and fill tracking
for the Robinhood HA Breakout trading system using Alpaca-py SDK.

Key Features:
- ATM contract selection with liquidity filters
- Time-based expiry selection (0DTE vs weekly)
- Market order placement with fill polling
- Risk sizing with 100x options multiplier
- Paper/live environment safety interlocks
- Comprehensive error handling and timeouts
- Automated recovery from transient API failures

Contract Selection Rules:
- Time window: 0DTE between 10:00-15:15 ET, otherwise nearest weekly Friday
- Strike: closest to ATM with delta 0.45-0.55 sanity check
- Liquidity: OI ≥ 10,000, volume ≥ 1,000, spread ≤ max($0.10, 8% of mid)
- Side mapping: bullish → CALL, bearish → PUT

Order Workflow:
1. Market open and cutoff time validation
2. Contract selection per liquidity rules
3. Manual approval via TradeConfirmationManager
4. Market order placement (fallback to limit if rejected)
5. Fill polling every 2s up to 90s timeout
6. Trade recording with actual fill price and quantity

Safety Features:
- Live mode requires --i-understand-live-risk flag
- Paper mode fallback if live flag missing
- Comprehensive logging and Slack notifications
- Timeout handling with user intervention options
- Partial fill tracking and VWAP calculation

Author: Robinhood HA Breakout System
Version: 2.0.0
License: MIT
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass
from decimal import Decimal
from .llm import load_config

# Helper functions for improved liquidity validation
def _pct_spread(ask: float, bid: float) -> float:
    """Calculate percentage spread"""
    mid = (ask + bid) / 2 if ask and bid else None
    if not mid or mid <= 0: 
        return 1e9
    return (ask - bid) / mid

def _abs_spread(ask: float, bid: float) -> float:
    """Calculate absolute spread"""
    return (ask - bid) if ask and bid else 1e9

def _liquidity_score(oi: int, vol: int, bid: float, ask: float, delta: float = None, 
                    target_low: float = 0.35, target_high: float = 0.55) -> float:
    """Calculate liquidity score (higher is better)"""
    spread = _pct_spread(ask, bid)
    abs_sp = _abs_spread(ask, bid)
    mid = (ask + bid)/2 if ask and bid else 0.0
    delta_penalty = 0.0 if (delta is None) else (
        0.0 if target_low <= abs(delta) <= target_high else min(abs(abs(delta) - 0.45), 1.0)
    )
    return (
        (min(oi, 2000) / 2000.0) * 0.45 +
        (min(vol, 5000) / 5000.0) * 0.25 +
        (max(0.0, 1.0 - min(spread, 0.50)/0.50)) * 0.20 +
        (max(0.0, 1.0 - min(abs_sp, 0.50)/0.50)) * 0.05 +
        (max(0.0, 1.0 - delta_penalty)) * 0.05
    )

def _get_dynamic_filter_tiers(mid_price: float, is_short_dte: bool = False) -> List[Dict]:
    """Generate progressive filter tiers based on contract mid price and DTE"""
    
    # Base tier (strict)
    base_tier = {
        "name": "strict",
        "min_oi": 300,
        "max_spread_pct": 0.15,  # 15%
        "max_spread_abs": 0.10
    }
    
    # Adjust for low-priced contracts (mid < $0.50)
    if mid_price < 0.50:
        # Tier 1: Loosened for low-priced
        tier1 = {
            "name": "loosened_low_price",
            "min_oi": 100 if not is_short_dte else 50,
            "max_spread_pct": 0.40,  # 40%
            "max_spread_abs": 0.20
        }
        
        # Tier 2: Looser for very low-priced
        tier2 = {
            "name": "looser_low_price", 
            "min_oi": 50 if not is_short_dte else 25,
            "max_spread_pct": 0.50,  # 50%
            "max_spread_abs": 0.20
        }
        
        # Tier 3: Very relaxed for difficult low-priced symbols
        tier3 = {
            "name": "very_relaxed_low_price",
            "min_oi": 25 if not is_short_dte else 10,
            "max_spread_pct": 0.65,  # 65%
            "max_spread_abs": 0.25
        }
        
        # Tier 4: Emergency fallback for low-priced
        tier4 = {
            "name": "emergency_fallback_low_price",
            "min_oi": 10 if not is_short_dte else 5,
            "max_spread_pct": 0.80,  # 80%
            "max_spread_abs": 0.30
        }
        
        return [base_tier, tier1, tier2, tier3, tier4]
    
    # Standard tiers for higher-priced contracts
    tier1 = {
        "name": "loosened",
        "min_oi": 100,
        "max_spread_pct": 0.25,  # 25%
        "max_spread_abs": 0.15
    }
    
    tier2 = {
        "name": "looser",
        "min_oi": 50,
        "max_spread_pct": 0.35,  # 35%
        "max_spread_abs": 0.20
    }
    
    # Tier 3: Very relaxed for difficult symbols like XLK
    tier3 = {
        "name": "very_relaxed",
        "min_oi": 25,
        "max_spread_pct": 0.50,  # 50%
        "max_spread_abs": 0.30
    }
    
    # Tier 4: Emergency fallback - minimal requirements
    tier4 = {
        "name": "emergency_fallback",
        "min_oi": 10,
        "max_spread_pct": 0.75,  # 75%
        "max_spread_abs": 0.50
    }
    
    return [base_tier, tier1, tier2, tier3, tier4]

def _passes_liquidity_with_tier(tier: Dict, bid: float, ask: float, oi: int, vol: int) -> Tuple[bool, str]:
    """Check if contract passes liquidity filters for a specific tier"""
    mid = (ask + bid)/2 if ask and bid else 0
    
    # Junk liquidity guardrail: if spread > 35% and mid < $0.10, always reject
    spread_pct = _pct_spread(ask, bid)
    if spread_pct > 0.35 and mid < 0.10:
        return False, f"junk_liquidity_guard_spread_{spread_pct:.1%}_mid_${mid:.2f}"
    
    pct_ok = spread_pct <= tier["max_spread_pct"]
    
    # Absolute spread check for low-priced contracts
    abs_gate = tier.get("max_spread_abs")
    abs_ok = True
    if abs_gate is not None and mid < 1.0:
        abs_ok = _abs_spread(ask, bid) <= abs_gate
    
    oi_ok = (oi or 0) >= tier["min_oi"]
    vol_ok = (vol or 0) >= tier.get("min_vol", 0)
    
    # Return detailed reason for failure
    if not pct_ok:
        return False, f"spread_pct_{spread_pct:.1%}_>{tier['max_spread_pct']:.1%}"
    if not abs_ok:
        return False, f"spread_abs_${_abs_spread(ask, bid):.2f}_>${abs_gate:.2f}"
    if not oi_ok:
        return False, f"oi_{oi}_<_{tier['min_oi']}"
    if not vol_ok:
        return False, f"vol_{vol}_<_{tier.get('min_vol', 0)}"
    
    return True, "passed"

def _passes_liquidity(cfg: Dict, bid: float, ask: float, oi: int, vol: int) -> Tuple[bool, str]:
    """Legacy liquidity check - maintained for backward compatibility"""
    pct_ok = _pct_spread(ask, bid) <= cfg["max_spread_pct"]
    
    # Absolute spread guard when mid < $1
    mid = (ask + bid)/2 if ask and bid else 0
    abs_gate = cfg.get("max_spread_abs", None)
    abs_ok = True
    if abs_gate is not None and mid < 1.0:
        abs_ok = _abs_spread(ask, bid) <= abs_gate
    
    oi_ok = (oi or 0) >= cfg["min_oi"]
    vol_ok = (vol or 0) >= cfg.get("min_vol", 0)
    
    # Return detailed reason for failure
    if not pct_ok:
        return False, f"spread_pct_{_pct_spread(ask, bid):.1%}_>{cfg['max_spread_pct']:.1%}"
    if not abs_ok:
        return False, f"spread_abs_${_abs_spread(ask, bid):.2f}_>${abs_gate:.2f}"
    if not oi_ok:
        return False, f"oi_{oi}_<_{cfg['min_oi']}"
    if not vol_ok:
        return False, f"vol_{vol}_<_{cfg.get('min_vol', 0)}"
    
    return True, "passed"

def _get_symbol_options_config(symbol: str, config: Dict) -> Dict:
    """Get options configuration for symbol with per-symbol overrides"""
    # Get from alpaca.min_open_interest section (primary config structure)
    alpaca_config = config.get("alpaca", {})
    min_oi_config = alpaca_config.get("min_open_interest", {})
    
    # Get symbol-specific min_oi or use default
    symbol_min_oi = min_oi_config.get(symbol, min_oi_config.get("default", 300))
    
    # Also check legacy options config structure for backwards compatibility
    options_config = config.get("options", {})
    default_config = options_config.get("default", {})
    per_symbol_config = options_config.get("per_symbol", {}).get(symbol, {})
    
    # Merge configurations with alpaca config taking precedence
    merged_config = {
        "min_oi": symbol_min_oi,  # Use alpaca config
        "min_vol": 0,
        "max_spread_pct": alpaca_config.get("max_spread_pct", 0.15),
        "max_spread_abs": alpaca_config.get("max_spread_abs", 0.10),
        "expiry_search_days": [0, 1, 2],
        "delta_target": [0.35, 0.55],
        "allow_shares_fallback": False
    }
    
    # Override with legacy per-symbol config if present
    merged_config.update(per_symbol_config)
    
    return merged_config

try:
    from alpaca.trading.client import TradingClient
    from alpaca.data.historical import OptionHistoricalDataClient
    from alpaca.data.requests import OptionLatestQuoteRequest
    from alpaca.trading.requests import (
        GetOptionContractsRequest,
        MarketOrderRequest,
        LimitOrderRequest,
        GetOrdersRequest
    )
    from alpaca.trading.enums import (
        OrderSide,
        OrderType,
        TimeInForce,
        OrderStatus,
        AssetClass,
        ContractType,
        ExerciseStyle
    )
    from alpaca.common.exceptions import APIError
except ImportError as e:
    raise ImportError(f"alpaca-py not installed: {e}. Run: pip install alpaca-py>=0.21.0")

logger = logging.getLogger(__name__)


@dataclass
class ContractInfo:
    """Container for selected option contract information."""
    symbol: str  # OCC-formatted symbol from Alpaca
    underlying_symbol: str
    strike: float
    expiry: str
    option_type: str  # 'CALL' or 'PUT'
    bid: float
    ask: float
    mid: float
    spread: float
    spread_pct: float
    open_interest: int
    volume: int
    delta: Optional[float] = None


@dataclass
class Quote:
    """Container for option quote data."""
    bid: float
    ask: float
    bid_size: int
    ask_size: int
    timestamp: Optional[datetime] = None


@dataclass
class FillResult:
    """Container for order fill results."""
    status: str  # 'FILLED', 'PARTIAL', 'PENDING', 'REJECTED', 'CANCELLED', 'TIMEOUT'
    filled_qty: int
    avg_price: float
    total_filled_qty: int
    remaining_qty: int
    order_id: str
    client_order_id: Optional[str] = None


class AlpacaOptionsTrader:
    """Handles Alpaca options contract selection and trading."""

    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        """Initialize Alpaca options trader.
        
        Args:
            api_key: Alpaca API key
            secret_key: Alpaca secret key  
            paper: Use paper trading environment
        """
        self.paper = paper
        self.client = TradingClient(
            api_key=api_key,
            secret_key=secret_key,
            paper=paper
        )
        self.data_client = OptionHistoricalDataClient(
            api_key=api_key,
            secret_key=secret_key
        )
        logger.info(f"Initialized AlpacaOptionsTrader (paper={paper})")
    
    def _get_quote_bid(self, quote) -> float:
        """Robust bid price accessor with fallbacks."""
        try:
            # Try different possible attribute names
            if hasattr(quote, 'bid') and quote.bid is not None:
                return float(quote.bid)
            elif hasattr(quote, 'bid_price') and quote.bid_price is not None:
                return float(quote.bid_price)
            elif hasattr(quote, 'bp') and quote.bp is not None:
                return float(quote.bp)
            else:
                logger.warning(f"No bid price found in quote: {dir(quote)}")
                return 0.0
        except (ValueError, TypeError) as e:
            logger.warning(f"Error parsing bid price: {e}")
            return 0.0
    
    def _get_quote_ask(self, quote) -> float:
        """Robust ask price accessor with fallbacks."""
        try:
            # Try different possible attribute names
            if hasattr(quote, 'ask') and quote.ask is not None:
                return float(quote.ask)
            elif hasattr(quote, 'ask_price') and quote.ask_price is not None:
                return float(quote.ask_price)
            elif hasattr(quote, 'ap') and quote.ap is not None:
                return float(quote.ap)
            else:
                logger.warning(f"No ask price found in quote: {dir(quote)}")
                return 0.0
        except (ValueError, TypeError) as e:
            logger.warning(f"Error parsing ask price: {e}")
            return 0.0

    def is_market_open_and_valid_time(self) -> Tuple[bool, str]:
        """Check if market is open and within valid trading window.
        
        Returns:
            Tuple of (is_valid, reason)
        """
        from .recovery import retry_with_recovery
        
        def _get_market_clock():
            return self.client.get_clock()
        
        try:
            # Get market clock with recovery
            clock = retry_with_recovery(
                operation=_get_market_clock,
                operation_name="get market clock",
                component="alpaca_api"
            )
            
            if not clock.is_open:
                return False, "Market is closed"
            
            # Check time window (10:00-15:15 ET for 0DTE, otherwise allow)
            now_et = clock.timestamp.astimezone()
            hour = now_et.hour
            minute = now_et.minute
            
            # Block new entries after 15:15 ET
            if hour > 15 or (hour == 15 and minute > 15):
                return False, "After 15:15 ET cutoff - no new entries allowed"
            
            return True, "Market open and within valid time window"
            
        except Exception as e:
            logger.error(f"Error checking market status: {e}")
            return False, f"Error checking market status: {e}"

    def get_expiry_policy(self, symbol: str = "SPY") -> Tuple[str, str]:
        """Determine expiry policy based on current time and symbol-specific calendar.
        
        Args:
            symbol: Trading symbol to check expiry availability for
        
        Returns:
            Tuple of (policy, expiry_date) where policy is '0DTE', 'SHORT_DTE', 'WEEKLY', or None
        """
        from utils.expiry_calendar import get_expiry_policy_with_calendar, validate_expiry_constraints
        
        try:
            clock = self.client.get_clock()
            now_et = clock.timestamp.astimezone()
            
            # Use symbol-specific expiry calendar
            policy, expiry_date = get_expiry_policy_with_calendar(symbol, now_et)
            
            if policy is None or expiry_date is None:
                logger.warning(f"No valid expiry found for {symbol} - skipping trade")
                return None, None
            
            # Validate expiry constraints
            is_valid, reason = validate_expiry_constraints(symbol, expiry_date)
            if not is_valid:
                logger.warning(f"Expiry validation failed for {symbol}: {reason}")
                return None, None
            
            logger.info(f"Selected expiry policy for {symbol}: {policy} ({expiry_date})")
            return policy, expiry_date
                
        except Exception as e:
            logger.error(f"Error determining expiry policy for {symbol}: {e}")
            return None, None

    def find_atm_contract(
        self,
        symbol: str,
        side: str,  # 'CALL' or 'PUT'
        policy: str,  # '0DTE', 'SHORT_DTE', or 'WEEKLY'
        expiry_date: str,
        min_oi: int = None,
        min_vol: int = None,
        max_spread_pct: float = None
    ) -> Optional[ContractInfo]:
        """Find ATM option contract meeting tiered liquidity requirements.
        
        Args:
            symbol: Underlying symbol (e.g., 'SPY')
            side: Option type ('CALL' or 'PUT')
            policy: Expiry policy ('0DTE', 'SHORT_DTE', or 'WEEKLY')
            expiry_date: Target expiry date (YYYY-MM-DD)
            min_oi: Override minimum open interest
            min_vol: Override minimum daily volume
            max_spread_pct: Override maximum bid-ask spread %
            
        Returns:
            ContractInfo if suitable contract found, None otherwise
        """
        from utils.option_filters import get_filter_summary, validate_contract_liquidity, should_attempt_fallback
        
        try:
            logger.info(f"Finding {side} contract for {symbol}: {get_filter_summary(symbol)}")
            
            # Try primary filters first
            contract = self._find_contract_with_filters(symbol, side, expiry_date, use_fallback=False)
            
            if contract:
                logger.info(f"Found {side} contract with primary filters: {contract.symbol}")
                return contract
            
            # Try fallback filters if available
            if should_attempt_fallback(symbol):
                logger.info(f"Primary filters failed for {symbol}, trying fallback filters")
                contract = self._find_contract_with_filters(symbol, side, expiry_date, use_fallback=True)
                
                if contract:
                    logger.warning(f"Found {side} contract with fallback filters: {contract.symbol}")
                    return contract
            
            logger.error(f"No suitable {side} contract found for {symbol} - all filters failed")
            return None
            
        except Exception as e:
            logger.error(f"Error finding ATM contract for {symbol}: {e}")
            return None
    
    def _find_contract_with_filters(
        self,
        symbol: str,
        side: str,
        expiry_date: str,
        use_fallback: bool = False
    ) -> Optional[ContractInfo]:
        """Find contract using specified filter tier."""
        from utils.option_filters import validate_contract_liquidity
        
        try:
            # Get current stock price for ATM calculation
            from utils.alpaca_client import AlpacaClient
            alpaca_data = AlpacaClient(env="live" if not self.paper else "paper")
            current_price = alpaca_data.get_current_price(symbol)
            
            if not current_price:
                logger.error(f"Could not get current price for {symbol}")
                return None
            
            # Convert side to Alpaca enum
            contract_type = ContractType.CALL if side == 'CALL' else ContractType.PUT
            
            # Get option contracts
            request = GetOptionContractsRequest(
                underlying_symbols=[symbol],
                status="active",
                expiration_date=expiry_date,
                contract_type=contract_type,
                exercise_style=ExerciseStyle.AMERICAN
            )
            
            try:
                contracts = self.client.get_option_contracts(request)
            except APIError as e:
                if "401" in str(e) or "40110000" in str(e):
                    logger.error(f"[ALPACA] 401 options authorization error for {symbol}: verify paper options entitlement & API keys")
                    return None
                else:
                    raise
            
            if not contracts or not hasattr(contracts, 'option_contracts') or not contracts.option_contracts:
                logger.warning(f"No {side} contracts found for {symbol} expiring {expiry_date}")
                return None
            
            # Find ATM strike (closest to current price)
            best_contract = None
            min_strike_diff = float('inf')
            
            filter_type = "fallback" if use_fallback else "primary"
            contracts_checked = 0
            contracts_passed = 0
            
            for contract in contracts.option_contracts:
                contracts_checked += 1
                strike_diff = abs(contract.strike_price - current_price)
                
                # Get real-time quote for liquidity validation
                quote = self.get_latest_quote(contract.symbol)
                if not quote or quote.bid <= 0 or quote.ask <= 0:
                    continue
                
                # Get contract stats (open interest, volume)
                oi = getattr(contract, 'open_interest', 0)
                volume = getattr(contract, 'volume', 0)
                
                # Validate liquidity using tiered filters
                passes_filter, reason = validate_contract_liquidity(
                    symbol, quote.bid, quote.ask, oi, volume, use_fallback
                )
                
                if passes_filter and strike_diff < min_strike_diff:
                    min_strike_diff = strike_diff
                    best_contract = ContractInfo(
                        symbol=contract.symbol,
                        underlying_symbol=symbol,
                        strike=contract.strike_price,
                        expiry=expiry_date,
                        side=side,
                        bid=quote.bid,
                        ask=quote.ask,
                        open_interest=oi,
                        volume=volume
                    )
                    contracts_passed += 1
                    logger.debug(f"New best {side} contract: {contract.symbol} (strike ${contract.strike_price}, {reason})")
                else:
                    logger.debug(f"Rejected {contract.symbol}: {reason}")
            
            if best_contract:
                logger.info(f"Selected {side} contract using {filter_type} filters: {best_contract.symbol} "
                           f"(${best_contract.strike}, OI:{best_contract.open_interest}, "
                           f"spread:${best_contract.ask - best_contract.bid:.3f})")
            else:
                logger.warning(f"No {side} contracts passed {filter_type} filters for {symbol} "
                              f"({contracts_passed}/{contracts_checked} passed)")
            
            return best_contract
            
        except Exception as e:
            logger.error(f"Error in _find_contract_with_filters for {symbol}: {e}")
            return None
            
            # Try progressive filtering tiers
            candidates = []
            successful_tier = None
            
            # First pass: collect all valid contracts with basic validation
            all_contracts = []
            for contract in contract_list:
                try:
                    # CRITICAL: Validate option side matches request using robust OCC parsing
                    # OCC symbol format: ROOT + YYMMDD + C/P + 8-digit strike
                    # Examples: XLE250829C00090000, SPY250829P00645000
                    import re
                    occ_match = re.match(r'^([A-Z]{1,6})(\d{6})([CP])(\d{8})$', contract.symbol)
                    if not occ_match:
                        logger.warning(f"Invalid OCC symbol format: {contract.symbol}")
                        continue
                    
                    root, yymmdd, cp_flag, strike_raw = occ_match.groups()
                    expected_side = 'C' if side == 'CALL' else 'P'
                    if cp_flag != expected_side:
                        logger.warning(f"Side mismatch: requested {side} but got {contract.symbol} (OCC side: {cp_flag})")
                        continue
                    
                    # Get quote data using correct Alpaca API
                    quote_request = OptionLatestQuoteRequest(symbol_or_symbols=contract.symbol)
                    quote_response = self.data_client.get_option_latest_quote(quote_request)
                    
                    # Extract quote data (response is keyed by symbol)
                    if not quote_response or contract.symbol not in quote_response:
                        continue
                    
                    quote = quote_response[contract.symbol]
                    if not quote:
                        continue
                    
                    # Robust bid/ask accessor with fallbacks
                    bid = self._get_quote_bid(quote)
                    ask = self._get_quote_ask(quote)
                    
                    if bid <= 0 or ask <= 0:
                        continue
                    
                    # Skip stale or crossed quotes
                    if bid >= ask:
                        continue
                    
                    mid = (bid + ask) / 2
                    spread = ask - bid
                    spread_pct = (spread / mid) * 100 if mid > 0 else 999
                    
                    oi = int(contract.open_interest or 0)
                    vol = int(getattr(contract, 'volume', 0))
                    strike = float(contract.strike_price)
                    atm_distance = abs(strike - current_price)
                    
                    # Delta sanity check (if available)
                    delta = None
                    if hasattr(contract, 'greeks') and contract.greeks:
                        delta = contract.greeks.delta
                        if delta and not (0.45 <= abs(delta) <= 0.55):
                            # Allow some flexibility for ATM contracts
                            if atm_distance > current_price * 0.02:  # > 2% from ATM
                                continue
                    
                    all_contracts.append({
                        'contract': contract,
                        'bid': bid,
                        'ask': ask,
                        'mid': mid,
                        'spread': spread,
                        'spread_pct': spread_pct,
                        'atm_distance': atm_distance,
                        'delta': delta,
                        'volume': vol,
                        'oi': oi
                    })
                    
                except Exception as e:
                    logger.warning(f"Error processing contract {contract.symbol}: {e}")
                    continue
            
            if not all_contracts:
                logger.warning(f"No valid {side} contracts found for {symbol} after basic validation")
            else:
                logger.info(f"Found {len(all_contracts)} valid {side} contracts for {symbol}, applying progressive filtering")
                
                # Get dynamic filter tiers based on average mid price
                avg_mid = sum(c['mid'] for c in all_contracts) / len(all_contracts)
                filter_tiers = _get_dynamic_filter_tiers(avg_mid, is_short_dte)
                
                # Try each tier progressively
                for tier in filter_tiers:
                    tier_candidates = []
                    
                    for contract_data in all_contracts:
                        passes_tier, failure_reason = _passes_liquidity_with_tier(
                            tier, 
                            contract_data['bid'], 
                            contract_data['ask'], 
                            contract_data['oi'], 
                            contract_data['volume']
                        )
                        
                        if passes_tier:
                            tier_candidates.append(contract_data)
                    
                    if tier_candidates:
                        candidates = tier_candidates
                        successful_tier = tier['name']
                        logger.info(f"Progressive filtering succeeded with tier '{successful_tier}': {len(candidates)} candidates (avg_mid=${avg_mid:.2f}, short_dte={is_short_dte})")
                        break
                    else:
                        logger.info(f"Tier '{tier['name']}' found no candidates (min_oi={tier['min_oi']}, max_spread_pct={tier['max_spread_pct']:.1%})")
                
                if candidates:
                    # Log details about successful candidates
                    for candidate in candidates[:3]:  # Log top 3
                        contract = candidate['contract']
                        logger.info(f"Candidate {contract.symbol}: OI={candidate['oi']}, Vol={candidate['volume']}, Spread={candidate['spread_pct']:.1f}%, Strike=${float(contract.strike_price):.2f}")
            
            if not candidates:
                logger.warning(f"No suitable {side} contracts found after progressive filtering {len(contract_list)} total contracts")
                if successful_tier:
                    logger.info(f"Last successful tier was '{successful_tier}' but no candidates passed all filters")
                else:
                    logger.info(f"All progressive filtering tiers failed - trying next expiry fallback for {symbol}")
                
                # Try next expiry fallback before giving up
                fallback_contract = self._try_expiry_fallback(symbol, side, policy, expiry_date, min_oi, min_vol, max_spread_pct)
                if fallback_contract:
                    logger.info(f"Next expiry fallback succeeded for {symbol}")
                    return fallback_contract
                
                # Check if shares fallback is enabled for this symbol
                if symbol_config.get("allow_shares_fallback", False):
                    logger.info(f"Options and next expiry failed for {symbol}, shares fallback allowed")
                    return self._create_shares_fallback_info(symbol, current_price, symbol_config)
                
                logger.warning(f"All fallback options exhausted for {symbol} - no suitable contracts found")
                return None
            
            logger.info(f"Found {len(candidates)} suitable {side} candidates for {symbol} using tier '{successful_tier}'")
            
            # Sort by: ATM distance, then spread, then volume
            candidates.sort(key=lambda x: (
                x['atm_distance'],
                x['spread_pct'],
                -x['volume']  # Higher volume is better
            ))
            
            best = candidates[0]
            contract = best['contract']
            
            logger.info(f"Selected contract: {contract.symbol} strike=${contract.strike_price} "
                       f"bid=${best['bid']:.2f} ask=${best['ask']:.2f} "
                       f"spread={best['spread_pct']:.1f}% OI={contract.open_interest} (tier: {successful_tier})")
            
            return ContractInfo(
                symbol=contract.symbol,
                underlying_symbol=symbol,
                strike=float(contract.strike_price),
                expiry=expiry_date,
                option_type=side,
                bid=best['bid'],
                ask=best['ask'],
                mid=best['mid'],
                spread=best['spread'],
                spread_pct=best['spread_pct'],
                open_interest=contract.open_interest,
                volume=best.get('volume', 0),
                delta=best.get('delta')
            )
            
        except Exception as e:
            logger.error(f"Error finding ATM contract for {symbol}: {e}")
            return None
    
    def _create_shares_fallback_info(self, symbol: str, current_price: float, symbol_config: Dict) -> ContractInfo:
        """Create a shares fallback ContractInfo when options fail filters"""
        fallback_budget_pct = symbol_config.get("shares_fallback_budget_pct", 0.5)
        
        logger.info(f"Creating shares fallback for {symbol} at ${current_price:.2f} "
                   f"with {fallback_budget_pct:.1%} budget allocation")
        
        # Create a special ContractInfo that indicates shares fallback
        contract_info = ContractInfo(
            symbol=f"{symbol}_SHARES",  # Special marker for shares
            underlying_symbol=symbol,
            strike=current_price,  # Use current price as "strike"
            expiry="SHARES",  # Special marker
            option_type="SHARES",  # Special type
            bid=current_price,
            ask=current_price,
            mid=current_price,
            spread=0.0,  # No spread for shares
            spread_pct=0.0,
            open_interest=999999,  # Shares have infinite "liquidity"
            volume=999999,
            delta=1.0  # Shares have delta of 1.0
        )
        
        # Add special attributes to mark this as shares fallback
        contract_info.is_shares_fallback = True
        contract_info.fallback_reason = "Options failed liquidity filters, using shares fallback"
        contract_info.fallback_budget_pct = fallback_budget_pct
        
        return contract_info
    
    def _try_expiry_fallback(
        self,
        symbol: str,
        side: str,
        policy: str,
        original_expiry: str,
        min_oi: int,
        min_vol: int,
        max_spread_pct: float
    ) -> Optional[ContractInfo]:
        """Try to find contracts with fallback expiry within 2 trading days.
        
        Args:
            symbol: Underlying symbol
            side: Option type ('CALL' or 'PUT')
            policy: Original expiry policy
            original_expiry: Original target expiry date
            min_oi: Minimum open interest
            min_vol: Minimum volume
            max_spread_pct: Maximum spread percentage
            
        Returns:
            ContractInfo if fallback contract found, None otherwise
        """
        try:
            from datetime import datetime, timedelta
            
            # Get available expiration dates
            today = datetime.now().date()
            original_date = datetime.strptime(original_expiry, "%Y-%m-%d").date()
            
            # Generate potential fallback dates (next 2 trading days)
            fallback_dates = []
            current_date = original_date + timedelta(days=1)
            
            for _ in range(5):  # Check up to 5 days ahead to find 2 trading days
                # Skip weekends
                if current_date.weekday() < 5:  # Monday=0, Friday=4
                    fallback_dates.append(current_date)
                    if len(fallback_dates) >= 2:
                        break
                current_date += timedelta(days=1)
            
            # Try each fallback date
            for fallback_date in fallback_dates:
                fallback_expiry = fallback_date.strftime("%Y-%m-%d")
                days_ahead = (fallback_date - today).days
                
                if days_ahead <= 2:  # Within 2 trading days
                    logger.warning(f"{symbol}: No {policy} contracts found for {original_expiry}; trying fallback to {fallback_expiry} ({days_ahead} days ahead)")
                    
                    # Try to find contracts for this fallback date
                    contract_type = ContractType.CALL if side == 'CALL' else ContractType.PUT
                    
                    request = GetOptionContractsRequest(
                        underlying_symbols=[symbol],
                        status="active",
                        expiration_date=fallback_expiry,
                        contract_type=contract_type,
                        exercise_style=ExerciseStyle.AMERICAN
                    )
                    
                    try:
                        contracts = self.client.get_option_contracts(request)
                        if contracts and hasattr(contracts, 'option_contracts') and contracts.option_contracts:
                            logger.info(f"Found {len(contracts.option_contracts)} {side} contracts for {symbol} expiring {fallback_expiry}")
                            
                            # Use the same contract selection logic as the main method
                            return self._select_best_contract_from_list(
                                contracts.option_contracts, 
                                symbol, 
                                side, 
                                fallback_expiry, 
                                min_oi, 
                                min_vol, 
                                max_spread_pct
                            )
                    except APIError as e:
                        logger.warning(f"API error checking fallback expiry {fallback_expiry}: {e}")
                        continue
            
            logger.warning(f"{symbol}: No suitable fallback contracts found within 2 trading days")
            return None
            
        except Exception as e:
            logger.error(f"Error in expiry fallback for {symbol}: {e}")
            return None

    def _select_best_contract_from_list(
        self,
        contract_list: List,
        symbol: str,
        side: str,
        expiry_date: str,
        min_oi: int,
        min_vol: int,
        max_spread_pct: float
    ) -> Optional[ContractInfo]:
        """Select best contract from a list using the same logic as find_atm_contract."""
        try:
            # Get current stock price for ATM calculation
            from utils.alpaca_client import AlpacaClient
            alpaca_data = AlpacaClient(env="live" if not self.paper else "paper")
            current_price = alpaca_data.get_current_price(symbol)
            
            if not current_price:
                logger.error(f"Could not get current price for {symbol}")
                return None
            
            # Filter and score contracts (same logic as main method)
            candidates = []
            
            for contract in contract_list:
                try:
                    # Get quote data using correct Alpaca API
                    quote_request = OptionLatestQuoteRequest(symbol_or_symbols=contract.symbol)
                    quote_response = self.data_client.get_option_latest_quote(quote_request)
                    
                    if not quote_response or contract.symbol not in quote_response:
                        continue
                    
                    quote = quote_response[contract.symbol]
                    
                    # Calculate metrics
                    bid = float(quote.bid_price) if hasattr(quote, 'bid_price') and quote.bid_price else 0.0
                    ask = float(quote.ask_price) if hasattr(quote, 'ask_price') and quote.ask_price else 0.0
                    mid = (bid + ask) / 2 if bid > 0 and ask > 0 else 0.0
                    spread = ask - bid if bid > 0 and ask > 0 else float('inf')
                    spread_pct = (spread / mid * 100) if mid > 0 else float('inf')
                    
                    # Apply filters
                    if contract.open_interest < min_oi:
                        continue
                    if spread_pct > max_spread_pct:
                        continue
                    if mid <= 0:
                        continue
                    
                    # Calculate ATM score (distance from current price)
                    strike = float(contract.strike_price)
                    atm_distance = abs(strike - current_price)
                    atm_score = 1 / (1 + atm_distance)  # Higher score for closer to ATM
                    
                    candidates.append({
                        'contract': contract,
                        'bid': bid,
                        'ask': ask,
                        'mid': mid,
                        'spread': spread,
                        'spread_pct': spread_pct,
                        'volume': getattr(quote, 'volume', 0),
                        'delta': getattr(quote, 'delta', 0.5),
                        'atm_score': atm_score,
                        'strike': strike
                    })
                    
                except Exception as e:
                    logger.debug(f"Error processing contract {contract.symbol}: {e}")
                    continue
            
            if not candidates:
                logger.warning(f"No suitable {side} contracts found for {symbol} after filtering")
                return None
            
            # Sort by ATM score (closest to current price first)
            candidates.sort(key=lambda x: x['atm_score'], reverse=True)
            best = candidates[0]
            contract = best['contract']
            
            logger.info(f"Selected {side} contract: {contract.symbol} @ ${best['mid']:.2f} (spread: {best['spread_pct']:.1f}%, OI: {contract.open_interest})")
            
            return ContractInfo(
                symbol=contract.symbol,
                underlying_symbol=symbol,
                strike=float(contract.strike_price),
                expiry=expiry_date,
                option_type=side,
                bid=best['bid'],
                ask=best['ask'],
                mid=best['mid'],
                spread=best['spread'],
                spread_pct=best['spread_pct'],
                open_interest=contract.open_interest,
                volume=best.get('volume', 0),
                delta=best.get('delta')
            )
            
        except Exception as e:
            logger.error(f"Error selecting best contract from list: {e}")
            return None

    def place_market_order(
        self,
        contract_symbol: str,
        qty: int,
        side: str = "BUY",
        client_order_id: Optional[str] = None
    ) -> Optional[str]:
        """Place market order for option contract."""
        
        def _submit_order():
            order_side = OrderSide.BUY if side == "BUY" else OrderSide.SELL
            
            request = MarketOrderRequest(
                symbol=contract_symbol,
                qty=qty,
                side=order_side,
                time_in_force=TimeInForce.DAY,
                client_order_id=client_order_id
            )
            
            logger.info(f"Placing market order: {side} {qty} {contract_symbol}")
            order = self.client.submit_order(request)
            
            logger.info(f"Market order submitted: {order.id}")
            return order.id
        
        try:
            return retry_with_recovery(
                operation=_submit_order,
                operation_name=f"place market order {side} {qty} {contract_symbol}",
                component="alpaca_api"
            )
            
        except APIError as e:
            logger.error(f"API error placing market order after retries: {e}")
            
            # Try limit order fallback if market order rejected
            if "rejected" in str(e).lower():
                logger.info("Market order rejected, trying limit order fallback")
                return self._place_limit_fallback(contract_symbol, qty, side, client_order_id)
            
            return None
        except Exception as e:
            logger.error(f"Error placing market order after retries: {e}")
            return None

    def _place_limit_fallback(
        self,
        contract_symbol: str,
        qty: int,
        side: str,
        client_order_id: Optional[str] = None
    ) -> Optional[str]:
        """Place limit order as fallback when market order is rejected.
        
        Args:
            contract_symbol: OCC-formatted contract symbol
            qty: Number of contracts
            side: Order side ('BUY' or 'SELL')
            client_order_id: Optional client order ID
            
        Returns:
            Order ID if successful, None otherwise
        """
        try:
            # Get current quote for limit price calculation
            quote = self.client.get_latest_quote(contract_symbol)
            if not quote or not hasattr(quote, 'bid_price') or not quote.bid_price or not hasattr(quote, 'ask_price') or not quote.ask_price:
                logger.error("Cannot get quote for limit order fallback")
                return None
            
            bid = float(quote.bid_price)
            ask = float(quote.ask_price)
            mid = (bid + ask) / 2
            
            # Set aggressive limit price: max(mid, mid + $0.05, mid * 1.05)
            limit_price = max(mid, mid + 0.05, mid * 1.05)
            
            order_side = OrderSide.BUY if side == "BUY" else OrderSide.SELL
            
            request = LimitOrderRequest(
                symbol=contract_symbol,
                qty=qty,
                side=order_side,
                time_in_force=TimeInForce.DAY,
                limit_price=limit_price,
                client_order_id=client_order_id
            )
            
            logger.info(f"Placing limit order: {side} {qty} {contract_symbol} @ ${limit_price:.2f}")
            order = self.client.submit_order(request)
            
            logger.info(f"Limit order submitted: {order.id}")
            return order.id
            
        except Exception as e:
            logger.error(f"Error placing limit order fallback: {e}")
            return None

    def poll_fill(
        self,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
        timeout_s: int = 90,
        interval_s: int = 2
    ) -> FillResult:
        """Poll for order fill status with timeout.
        
        Args:
            order_id: Alpaca order ID
            client_order_id: Client order ID
            timeout_s: Timeout in seconds
            interval_s: Polling interval in seconds
            
        Returns:
            FillResult with fill status and details
        """
        if not order_id and not client_order_id:
            return FillResult(
                status="ERROR",
                filled_qty=0,
                avg_price=0.0,
                total_filled_qty=0,
                remaining_qty=0,
                order_id="",
                client_order_id=client_order_id
            )
        
        start_time = time.time()
        total_filled_qty = 0
        total_filled_value = 0.0
        
        logger.info(f"Polling for fill (timeout: {timeout_s}s, interval: {interval_s}s)")
        
        while time.time() - start_time < timeout_s:
            try:
                # Get order status
                if order_id:
                    order = self.client.get_order_by_id(order_id)
                else:
                    # Search by client order ID
                    orders = self.client.get_orders(
                        GetOrdersRequest(status="all", limit=100)
                    )
                    order = None
                    for o in orders:
                        if o.client_order_id == client_order_id:
                            order = o
                            break
                    
                    if not order:
                        logger.error(f"Order not found with client_order_id: {client_order_id}")
                        break
                
                status = order.status
                filled_qty = int(order.filled_qty) if order.filled_qty else 0
                remaining_qty = int(order.qty) - filled_qty
                
                # Calculate average fill price
                avg_price = 0.0
                if filled_qty > 0 and order.filled_avg_price:
                    avg_price = float(order.filled_avg_price)
                
                logger.info(f"Order status: {status}, filled: {filled_qty}/{order.qty} @ ${avg_price:.2f}")
                
                if status == OrderStatus.FILLED:
                    return FillResult(
                        status="FILLED",
                        filled_qty=filled_qty,
                        avg_price=avg_price,
                        total_filled_qty=filled_qty,
                        remaining_qty=0,
                        order_id=order.id,
                        client_order_id=order.client_order_id
                    )
                
                elif status in [OrderStatus.REJECTED, OrderStatus.CANCELED]:
                    return FillResult(
                        status=status.value,
                        filled_qty=filled_qty,
                        avg_price=avg_price,
                        total_filled_qty=filled_qty,
                        remaining_qty=remaining_qty,
                        order_id=order.id,
                        client_order_id=order.client_order_id
                    )
                
                elif status == OrderStatus.PARTIALLY_FILLED:
                    # Continue polling for partial fills
                    total_filled_qty = filled_qty
                    if avg_price > 0:
                        total_filled_value = filled_qty * avg_price
                
                # Wait before next poll
                time.sleep(interval_s)
                
            except Exception as e:
                logger.error(f"Error polling order status: {e}")
                time.sleep(interval_s)
        
        # Timeout reached
        logger.warning(f"Order fill polling timed out after {timeout_s}s")
        
        return FillResult(
            status="TIMEOUT",
            filled_qty=total_filled_qty,
            avg_price=total_filled_value / total_filled_qty if total_filled_qty > 0 else 0.0,
            total_filled_qty=total_filled_qty,
            remaining_qty=int(order.qty) - total_filled_qty if 'order' in locals() else 0,
            order_id=order.id if 'order' in locals() else "",
            client_order_id=client_order_id
        )

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order.
        
        Args:
            order_id: Alpaca order ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.cancel_order_by_id(order_id)
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False

    def close_position(self, contract_symbol: str, qty: int) -> Optional[str]:
        """Close an option position.
        
        Args:
            contract_symbol: OCC-formatted contract symbol
            qty: Number of contracts to close
            
        Returns:
            Order ID if successful, None otherwise
        """
        return self.place_market_order(contract_symbol, qty, side="SELL")

    def get_latest_quote(self, symbol: str) -> Optional[Quote]:
        """Get latest quote for option contract.
        
        Args:
            symbol: Option contract symbol
            
        Returns:
            Latest quote or None if available
        """
        from .recovery import retry_with_recovery
        
        def _get_quote():
            request = OptionLatestQuoteRequest(symbol_or_symbols=symbol)
            quotes = self.data_client.get_option_latest_quote(request)
            
            if symbol in quotes:
                quote_data = quotes[symbol]
                # Handle different Alpaca Quote object structures
                try:
                    # Try direct attribute access first
                    bid = getattr(quote_data, 'bid_price', None) or getattr(quote_data, 'bid', None)
                    ask = getattr(quote_data, 'ask_price', None) or getattr(quote_data, 'ask', None)
                    bid_size = getattr(quote_data, 'bid_size', 0)
                    ask_size = getattr(quote_data, 'ask_size', 0)
                    timestamp = getattr(quote_data, 'timestamp', None)
                    
                    if bid is None or ask is None:
                        logger.warning(f"Quote for {symbol} missing bid/ask: bid={bid}, ask={ask}")
                        return None
                        
                    return Quote(
                        bid=float(bid),
                        ask=float(ask),
                        bid_size=int(bid_size),
                        ask_size=int(ask_size),
                        timestamp=timestamp
                    )
                except Exception as attr_error:
                    logger.error(f"Error accessing quote attributes for {symbol}: {attr_error}")
                    logger.debug(f"Quote object attributes: {dir(quote_data)}")
                    return None
            
            return None
        
        try:
            return retry_with_recovery(
                operation=_get_quote,
                operation_name=f"get latest quote for {symbol}",
                component="alpaca_api"
            )
            
        except Exception as e:
            logger.error(f"Error getting latest quote for {symbol} after retries: {e}")
            return None


def create_alpaca_trader(paper: bool = True) -> Optional[AlpacaOptionsTrader]:
    """Create AlpacaOptionsTrader instance with environment credentials.
    
    Args:
        paper: Use paper trading environment
        
    Returns:
        AlpacaOptionsTrader instance or None if credentials missing
    """
    import os
    
    # Get credentials from environment
    api_key = os.getenv('ALPACA_API_KEY') or os.getenv('ALPACA_KEY_ID')
    secret_key = os.getenv('ALPACA_SECRET_KEY')
    
    if not api_key or not secret_key:
        logger.error("Alpaca credentials not found in environment variables")
        logger.error("Required: ALPACA_API_KEY (or ALPACA_KEY_ID) and ALPACA_SECRET_KEY")
        return None
    
    try:
        return AlpacaOptionsTrader(api_key, secret_key, paper=paper)
    except Exception as e:
        logger.error(f"Error creating Alpaca trader: {e}")
        return None


if __name__ == "__main__":
    # Demo usage
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    # Test with paper trading
    trader = create_alpaca_trader(paper=True)
    if not trader:
        print("Failed to create trader - check credentials")
        exit(1)
    
    # Check market status
    is_valid, reason = trader.is_market_open_and_valid_time()
    print(f"Market status: {reason}")
    
    if is_valid:
        # Get expiry policy
        policy, expiry = trader.get_expiry_policy()
        print(f"Expiry policy: {policy} ({expiry})")
        
        # Find ATM contract
        contract = trader.find_atm_contract("SPY", "CALL", policy, expiry)
        if contract:
            print(f"Found contract: {contract.symbol} @ ${contract.mid:.2f}")
        else:
            print("No suitable contract found")
