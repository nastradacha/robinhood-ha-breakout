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

    def is_market_open_and_valid_time(self) -> Tuple[bool, str]:
        """Check if market is open and within valid trading window.
        
        Returns:
            Tuple of (is_valid, reason)
        """
        try:
            # Get market clock
            clock = self.client.get_clock()
            
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

    def get_expiry_policy(self) -> Tuple[str, str]:
        """Determine expiry policy based on current time.
        
        Returns:
            Tuple of (policy, expiry_date) where policy is '0DTE' or 'WEEKLY'
        """
        try:
            clock = self.client.get_clock()
            now_et = clock.timestamp.astimezone()
            hour = now_et.hour
            minute = now_et.minute
            
            # Use 0DTE between 10:00-15:15 ET
            if 10 <= hour < 15 or (hour == 15 and minute <= 15):
                # Today's date for 0DTE
                today = now_et.date()
                return "0DTE", today.strftime("%Y-%m-%d")
            else:
                # Find nearest weekly Friday
                today = now_et.date()
                days_until_friday = (4 - today.weekday()) % 7
                if days_until_friday == 0:  # Today is Friday
                    days_until_friday = 7  # Next Friday
                
                next_friday = today + timedelta(days=days_until_friday)
                return "WEEKLY", next_friday.strftime("%Y-%m-%d")
                
        except Exception as e:
            logger.error(f"Error determining expiry policy: {e}")
            # Fallback to weekly
            today = datetime.now().date()
            days_until_friday = (4 - today.weekday()) % 7
            if days_until_friday == 0:
                days_until_friday = 7
            next_friday = today + timedelta(days=days_until_friday)
            return "WEEKLY", next_friday.strftime("%Y-%m-%d")

    def find_atm_contract(
        self,
        symbol: str,
        side: str,  # 'CALL' or 'PUT'
        policy: str,  # '0DTE' or 'WEEKLY'
        expiry_date: str,
        min_oi: int = None,
        min_vol: int = None,
        max_spread_pct: float = None
    ) -> Optional[ContractInfo]:
        """Find ATM option contract meeting liquidity requirements.
        
        Args:
            symbol: Underlying symbol (e.g., 'SPY')
            side: Option type ('CALL' or 'PUT')
            policy: Expiry policy ('0DTE' or 'WEEKLY')
            expiry_date: Target expiry date (YYYY-MM-DD)
            min_oi: Minimum open interest (auto-determined if None)
            min_vol: Minimum daily volume (auto-determined if None)
            max_spread_pct: Maximum bid-ask spread as % of mid (auto-determined if None)
            
        Returns:
            ContractInfo if suitable contract found, None otherwise
        """
        try:
            # Set symbol-aware filtering criteria
            if min_oi is None or min_vol is None or max_spread_pct is None:
                # High-liquidity symbols (SPY, QQQ, IWM)
                if symbol in ['SPY', 'QQQ', 'IWM']:
                    min_oi = min_oi or 5000
                    min_vol = min_vol or 500
                    max_spread_pct = max_spread_pct or 8.0
                # Medium-liquidity symbols (UVXY, VIX, etc.)
                elif symbol in ['UVXY', 'VIX', 'SQQQ', 'TQQQ']:
                    min_oi = min_oi or 1000
                    min_vol = min_vol or 100
                    max_spread_pct = max_spread_pct or 15.0
                # Default for other symbols
                else:
                    min_oi = min_oi or 2000
                    min_vol = min_vol or 200
                    max_spread_pct = max_spread_pct or 12.0
            
            logger.info(f"Using filtering criteria for {symbol}: min_oi={min_oi}, min_vol={min_vol}, max_spread={max_spread_pct}%")
            # Get current stock price for ATM calculation
            from utils.alpaca_client import AlpacaClient
            alpaca_data = AlpacaClient()
            current_price = alpaca_data.get_current_price(symbol)
            
            if not current_price:
                logger.error(f"Could not get current price for {symbol}")
                return None
            
            logger.info(f"Finding {side} contract for {symbol} @ ${current_price:.2f} (policy: {policy}, expiry: {expiry_date})")
            
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
            
            contracts = self.client.get_option_contracts(request)
            
            if not contracts or not hasattr(contracts, 'option_contracts') or not contracts.option_contracts:
                logger.warning(f"No {side} contracts found for {symbol} expiring {expiry_date}")
                return None
            
            contract_list = contracts.option_contracts
            logger.info(f"Found {len(contract_list)} {side} contracts for {symbol}")
            
            # Filter and score contracts
            candidates = []
            
            for contract in contract_list:
                try:
                    # Get quote data using correct Alpaca API
                    quote_request = OptionLatestQuoteRequest(symbol_or_symbols=contract.symbol)
                    quote_response = self.data_client.get_option_latest_quote(quote_request)
                    
                    # Extract quote data (response is keyed by symbol)
                    if not quote_response or contract.symbol not in quote_response:
                        logger.info(f"Filtered {contract.symbol}: No quote response")
                        continue
                    
                    quote = quote_response[contract.symbol]
                    if not quote or not quote.bid_price or not quote.ask_price:
                        logger.info(f"Filtered {contract.symbol}: Missing bid/ask prices")
                        continue
                    
                    bid = float(quote.bid_price)
                    ask = float(quote.ask_price)
                    
                    # Skip stale or crossed quotes
                    if bid <= 0 or ask <= 0 or bid >= ask:
                        logger.info(f"Filtered {contract.symbol}: Invalid quotes - bid=${bid:.2f}, ask=${ask:.2f}")
                        continue
                    
                    mid = (bid + ask) / 2
                    spread = ask - bid
                    spread_pct = (spread / mid) * 100 if mid > 0 else 999
                    
                    # Apply liquidity filters (with type conversion and debugging)
                    oi = int(contract.open_interest or 0)
                    vol = int(getattr(contract, 'volume', 0) or 0)
                    
                    if oi < min_oi:
                        logger.info(f"Filtered {contract.symbol}: OI {oi} < {min_oi}")
                        continue
                    if vol < min_vol:
                        logger.info(f"Filtered {contract.symbol}: Vol {vol} < {min_vol}")
                        continue
                    if spread_pct > max_spread_pct and spread > 0.10:
                        logger.info(f"Filtered {contract.symbol}: Spread {spread_pct:.1f}% > {max_spread_pct}%")
                        continue
                    
                    logger.info(f"Candidate {contract.symbol}: OI={oi}, Vol={vol}, Spread={spread_pct:.1f}%, Strike=${float(contract.strike_price):.2f}")
                    
                    # Calculate distance from ATM
                    strike = float(contract.strike_price)
                    atm_distance = abs(strike - current_price)
                    
                    # Delta sanity check (if available)
                    delta = None
                    if hasattr(contract, 'greeks') and contract.greeks:
                        delta = contract.greeks.delta
                        if delta and not (0.45 <= abs(delta) <= 0.55):
                            # Allow some flexibility for ATM contracts
                            if atm_distance > current_price * 0.02:  # > 2% from ATM
                                logger.info(f"Filtered {contract.symbol}: Delta {delta:.3f} not ATM (distance {atm_distance:.2f})")
                                continue
                    
                    candidates.append({
                        'contract': contract,
                        'bid': bid,
                        'ask': ask,
                        'mid': mid,
                        'spread': spread,
                        'spread_pct': spread_pct,
                        'atm_distance': atm_distance,
                        'delta': delta,
                        'volume': getattr(contract, 'volume', 0)
                    })
                    
                except Exception as e:
                    logger.warning(f"Error processing contract {contract.symbol}: {e}")
                    continue
            
            if not candidates:
                logger.warning(f"No suitable {side} contracts found after filtering {len(contract_list)} total contracts")
                logger.info(f"Consider relaxing filtering criteria for {symbol} if this persists")
                return None
            
            logger.info(f"Found {len(candidates)} suitable {side} candidates for {symbol} after filtering")
            
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
                       f"spread={best['spread_pct']:.1f}% OI={contract.open_interest}")
            
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
                volume=best['volume'],
                delta=best['delta']
            )
            
        except Exception as e:
            logger.error(f"Error finding ATM contract: {e}")
            return None

    def place_market_order(
        self,
        contract_symbol: str,
        qty: int,
        side: str = "BUY",
        client_order_id: Optional[str] = None
    ) -> Optional[str]:
        """Place market order for option contract.
        
        Args:
            contract_symbol: OCC-formatted contract symbol
            qty: Number of contracts
            side: Order side ('BUY' or 'SELL')
            client_order_id: Optional client order ID
            
        Returns:
            Order ID if successful, None otherwise
        """
        try:
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
            
        except APIError as e:
            logger.error(f"API error placing market order: {e}")
            
            # Try limit order fallback if market order rejected
            if "rejected" in str(e).lower():
                logger.info("Market order rejected, trying limit order fallback")
                return self._place_limit_fallback(contract_symbol, qty, side, client_order_id)
            
            return None
        except Exception as e:
            logger.error(f"Error placing market order: {e}")
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
            if not quote or not quote.bid or not quote.ask:
                logger.error("Cannot get quote for limit order fallback")
                return None
            
            bid = float(quote.bid)
            ask = float(quote.ask)
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
