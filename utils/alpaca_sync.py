#!/usr/bin/env python3
"""
Alpaca Data Synchronization Module

Synchronizes local system state with Alpaca account data to handle manual trades
and maintain consistency between automation and manual operations.

Key Features:
- Bankroll synchronization from account balance
- Position synchronization to detect manual trades
- Transaction history reconciliation
- Conflict detection and resolution
- Automatic sync before trading operations
- Manual sync CLI commands

Usage:
    from utils.alpaca_sync import AlpacaSync
    
    sync = AlpacaSync(env="paper")
    sync.sync_all()  # Full synchronization
    sync.sync_bankroll()  # Bankroll only
    sync.sync_positions()  # Positions only
"""

import os
import logging
import json
import csv
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from decimal import Decimal
import pandas as pd
from dotenv import load_dotenv
import time
from pathlib import Path

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import OrderSide, OrderStatus, AssetClass
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# Support both package execution (python -m utils.alpaca_sync)
# and direct script execution (python utils/alpaca_sync.py)
try:
    from .scoped_files import get_scoped_paths
    from .llm import load_config
    from .slack import SlackNotifier
except ImportError:
    import sys as _sys
    import os as _os
    _sys.path.append(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from utils.scoped_files import get_scoped_paths  # type: ignore
    from utils.llm import load_config  # type: ignore
    from utils.slack import SlackNotifier  # type: ignore

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


def retry_with_backoff(max_retries=3, base_delay=1.0, max_delay=30.0, backoff_factor=2.0):
    """
    Decorator for retrying API calls with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        backoff_factor: Multiplier for delay on each retry
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            delay = base_delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt == max_retries:
                        logger.error(f"[ALPACA-SYNC] {func.__name__} failed after {max_retries} retries: {e}")
                        raise e
                    
                    logger.warning(f"[ALPACA-SYNC] {func.__name__} attempt {attempt + 1} failed: {e}, retrying in {delay:.1f}s")
                    time.sleep(delay)
                    delay = min(delay * backoff_factor, max_delay)
            
            raise last_exception
        return wrapper
    return decorator


class AlpacaSync:
    """
    Synchronizes local system state with Alpaca account data.
    
    Handles bankroll, positions, and transaction history synchronization
    to maintain consistency when manual trades occur outside automation.
    """
    
    def __init__(self, env: str = "paper", config: Optional[Dict] = None):
        """
        Initialize Alpaca synchronization.
        
        Args:
            env: Alpaca environment ("paper" or "live")
            config: Configuration dictionary (loaded if None)
        """
        self.env = env
        self.config = config or load_config()
        
        # Initialize Alpaca client
        self.trading_client = None
        self._init_alpaca_client()
        
        # Get scoped file paths
        scoped_paths = get_scoped_paths("alpaca", env)
        self.bankroll_file = scoped_paths["bankroll"]
        self.positions_file = scoped_paths["positions"]
        self.trade_history_file = scoped_paths["trade_history"]
        
        # Sync configuration
        self.sync_enabled = self.config.get("ALPACA_SYNC_ENABLED", True)
        self.auto_sync_before_trade = self.config.get("ALPACA_AUTO_SYNC_BEFORE_TRADE", True)
        self.sync_tolerance_pct = self.config.get("ALPACA_SYNC_TOLERANCE_PCT", 0.01)  # 1% tolerance
        self.sync_slack_alerts = self.config.get("ALPACA_SYNC_SLACK_ALERTS", True)
        
        logger.info(f"[ALPACA-SYNC] Initialized for {env} environment (enabled: {self.sync_enabled})")
    
    def _init_alpaca_client(self):
        """Initialize Alpaca trading client."""
        try:
            api_key = os.getenv("ALPACA_API_KEY")
            secret_key = os.getenv("ALPACA_SECRET_KEY")
            
            if not api_key or not secret_key:
                logger.warning("[ALPACA-SYNC] Missing API credentials - sync disabled")
                return
            
            paper = (self.env == "paper")
            self.trading_client = TradingClient(api_key, secret_key, paper=paper)
            
            # Test connection
            account = self.trading_client.get_account()
            logger.info(f"[ALPACA-SYNC] Connected to {self.env} account: {account.account_number}")
            
        except Exception as e:
            logger.error(f"[ALPACA-SYNC] Failed to initialize Alpaca client: {e}")
            self.trading_client = None
    
    def sync_all(self) -> Dict[str, bool]:
        """
        Perform full synchronization of all data.
        
        Returns:
            Dict with sync results for each component
        """
        if not self.sync_enabled or not self.trading_client:
            logger.warning("[ALPACA-SYNC] Sync disabled or client unavailable")
            return {"bankroll": False, "positions": False, "transactions": False}
        
        logger.info("[ALPACA-SYNC] Starting full synchronization...")
        
        results = {
            "bankroll": self.sync_bankroll(),
            "positions": self.sync_positions(),
            "transactions": self.sync_transactions()
        }
        
        # Send Slack notification for sync results
        if self.sync_slack_alerts:
            self._send_sync_notification(results)
        
        logger.info(f"[ALPACA-SYNC] Full sync completed: {results}")
        return results
    
    # --- Helper utilities for robust option matching ---
    def _parse_occ_symbol(self, occ: str) -> Optional[Dict]:
        """Parse an OCC option symbol (e.g., 'XLE250919C00089000') into components.
        Returns dict with keys: underlying, expiry (YYYY-MM-DD), option_type (CALL/PUT), strike (float).
        """
        try:
            if not occ or len(occ) < 10:
                return None
            # Underlying prefix until first digit
            i = 0
            while i < len(occ) and not occ[i].isdigit():
                i += 1
            underlying = occ[:i]
            rest = occ[i:]
            # YYMMDD
            y = int('20' + rest[0:2])
            m = int(rest[2:4])
            d = int(rest[4:6])
            expiry = f"{y:04d}-{m:02d}-{d:02d}"
            cp = rest[6].upper()
            option_type = 'CALL' if cp == 'C' else 'PUT'
            strike_pennies = rest[7:]
            strike = float(int(strike_pennies) / 1000.0)
            return {
                'underlying': underlying,
                'expiry': expiry,
                'option_type': option_type,
                'strike': strike,
            }
        except Exception:
            return None

    def _safe_float(self, v: Optional[object]) -> Optional[float]:
        try:
            if v in (None, ""):
                return None
            return float(v)
        except Exception:
            return None

    def _is_nonempty(self, v: Optional[object]) -> bool:
        """Return True when v is meaningfully filled (not None/empty/NaN-like)."""
        try:
            if v is None:
                return False
            s = str(v).strip()
            if s == "":
                return False
            if s.lower() in ("nan", "none", "null", "nat", "na", "n/a"):
                return False
            return True
        except Exception:
            return False

    def _local_matches_alpaca(self, local_pos: Dict, alpaca_symbol: str) -> bool:
        """Determine if a local position row represents the given Alpaca OCC symbol."""
        try:
            parsed = self._parse_occ_symbol(alpaca_symbol)
            sym = str(local_pos.get("symbol", "")).strip()
            if sym == alpaca_symbol:
                return True

            if not parsed:
                return False

            # If local symbol is itself OCC, parse it; else treat as underlying
            local_underlying = sym
            local_strike = self._safe_float(local_pos.get("strike"))
            local_expiry = str(local_pos.get("expiry", "")).strip()
            local_type = str(local_pos.get("option_type", "")).upper().strip()

            if len(sym) > 8 and any(c.isdigit() for c in sym):
                parsed_local = self._parse_occ_symbol(sym)
                if parsed_local:
                    local_underlying = parsed_local['underlying']
                    local_strike = parsed_local['strike']
                    local_expiry = parsed_local['expiry']
                    local_type = parsed_local['option_type']

            # Compare components (allow matching when local fields are missing)
            if local_underlying != parsed['underlying']:
                return False
            if local_strike is not None and abs(local_strike - parsed['strike']) > 1e-6:
                return False
            if local_expiry and local_expiry != parsed['expiry']:
                return False
            if local_type and local_type[0] != parsed['option_type'][0]:
                return False
            return True
        except Exception:
            return False

    def sync_bankroll(self) -> bool:
        """
        Synchronize bankroll with Alpaca account balance.
        
        Returns:
            True if sync successful, False otherwise
        """
        try:
            # Get Alpaca account info with retry logic
            account = self._get_account_with_retry()
            alpaca_equity = float(account.equity)
            alpaca_cash = float(account.cash)
            alpaca_buying_power = float(account.buying_power)
            
            logger.info(f"[ALPACA-SYNC] Alpaca account - Equity: ${alpaca_equity:.2f}, Cash: ${alpaca_cash:.2f}, Buying Power: ${alpaca_buying_power:.2f}")
            
            # Load current local bankroll
            local_bankroll = self._load_local_bankroll()
            local_balance = local_bankroll.get("balance", 0.0)
            
            # Calculate difference
            balance_diff = abs(alpaca_equity - local_balance)
            balance_diff_pct = (balance_diff / max(alpaca_equity, 1)) * 100
            
            logger.info(f"[ALPACA-SYNC] Balance comparison - Local: ${local_balance:.2f}, Alpaca: ${alpaca_equity:.2f}, Diff: ${balance_diff:.2f} ({balance_diff_pct:.2f}%)")
            
            # Check if sync is needed (always sync if bankroll file is missing required fields)
            needs_format_update = not all(key in local_bankroll for key in ["current_bankroll", "start_capital", "total_trades"])
            
            if balance_diff_pct <= self.sync_tolerance_pct and not needs_format_update:
                logger.info("[ALPACA-SYNC] Bankroll sync not needed - within tolerance")
                return True
            
            if needs_format_update:
                logger.info("[ALPACA-SYNC] Bankroll format update needed - adding missing fields")
            
            # Update local bankroll with compatible format
            updated_bankroll = {
                "current_bankroll": alpaca_equity,  # Compatible with BankrollManager
                "balance": alpaca_equity,           # Alpaca sync tracking
                "cash": alpaca_cash,
                "buying_power": alpaca_buying_power,
                "start_capital": local_bankroll.get("start_capital", alpaca_equity),
                "total_trades": local_bankroll.get("total_trades", 0),
                "winning_trades": local_bankroll.get("winning_trades", 0),
                "losing_trades": local_bankroll.get("losing_trades", 0),
                "total_pnl": local_bankroll.get("total_pnl", 0.0),
                "max_drawdown": local_bankroll.get("max_drawdown", 0.0),
                "peak_bankroll": max(local_bankroll.get("peak_bankroll", alpaca_equity), alpaca_equity),
                "created_at": local_bankroll.get("created_at", datetime.now().isoformat()),
                "last_updated": datetime.now().isoformat(),
                "trade_history": local_bankroll.get("trade_history", []),
                "win_loss_history": local_bankroll.get("win_loss_history", []),
                "last_sync": datetime.now().isoformat(),
                "sync_source": "alpaca_account",
                "previous_balance": local_balance,
                "sync_adjustment": alpaca_equity - local_balance
            }
            
            # Save updated bankroll
            bankroll_dir = os.path.dirname(self.bankroll_file) if os.path.dirname(self.bankroll_file) else "."
            os.makedirs(bankroll_dir, exist_ok=True)
            with open(self.bankroll_file, 'w') as f:
                json.dump(updated_bankroll, f, indent=2)
            
            logger.info(f"[ALPACA-SYNC] Bankroll synchronized - Updated from ${local_balance:.2f} to ${alpaca_equity:.2f}")
            
            # Log the sync event
            self._log_sync_event("bankroll", {
                "previous_balance": local_balance,
                "new_balance": alpaca_equity,
                "adjustment": alpaca_equity - local_balance,
                "source": "alpaca_account"
            })
            
            return True
            
        except Exception as e:
            logger.error(f"[ALPACA-SYNC] Bankroll sync failed: {e}")
            return False
    
    def sync_positions(self) -> bool:
        """
        Synchronize positions with Alpaca account.
        
        Detects manual trades and updates local position tracking.
        
        Returns:
            True if sync successful, False otherwise
        """
        try:
            # Get current Alpaca positions with retry logic
            positions = self._get_positions_with_retry()
            
            # Filter for options positions
            # Robust detection of option positions across SDK variations
            def _is_option_position(pos) -> bool:
                try:
                    ac = getattr(pos, 'asset_class', None)
                    return (ac == AssetClass.US_OPTION) or ('OPTION' in str(ac).upper())
                except Exception:
                    return False

            options_positions = [pos for pos in positions if _is_option_position(pos)]
            
            logger.info(f"[ALPACA-SYNC] Found {len(options_positions)} options positions in Alpaca account")
            
            # Load current local positions
            local_positions = self._load_local_positions()
            
            # Compare and sync positions
            sync_needed = False
            new_positions = []
            
            for alpaca_pos in options_positions:
                symbol = alpaca_pos.symbol
                quantity = float(alpaca_pos.qty)
                market_value = float(alpaca_pos.market_value) if getattr(alpaca_pos, 'market_value', None) else 0.0
                # Alpaca SDK uses 'unrealized_pl' (not 'unrealized_pnl'); handle both and intraday variant
                _upl = (
                    getattr(alpaca_pos, 'unrealized_pl', None)
                    or getattr(alpaca_pos, 'unrealized_pnl', None)
                    or getattr(alpaca_pos, 'unrealized_intraday_pl', None)
                )
                unrealized_pnl = float(_upl) if _upl is not None else 0.0

                # Try to find a matching local row (prefer open rows; fall back to closed rows to reopen)
                local_pos_open = None
                local_pos_closed = None
                for p in local_positions:
                    if self._local_matches_alpaca(p, symbol):
                        status_str = str(p.get("status", "")).strip().lower()
                        close_time_val = p.get("close_time", "")
                        is_closed = status_str.startswith("closed") or self._is_nonempty(close_time_val)
                        if is_closed:
                            if local_pos_closed is None:
                                local_pos_closed = p
                        else:
                            local_pos_open = p
                            break

                if local_pos_open is None and local_pos_closed is None:
                    # New position detected (manual trade)
                    logger.warning(f"[ALPACA-SYNC] Detected manual position: {symbol} (qty: {quantity})")
                    sync_needed = True

                    # Derive components to help downstream monitoring
                    parsed = self._parse_occ_symbol(symbol)
                    new_rec = {
                        "symbol": symbol,
                        "quantity": quantity,
                        "market_value": market_value,
                        "unrealized_pnl": unrealized_pnl,
                        "entry_time": datetime.now().isoformat(),
                        "source": "manual_trade_detected",
                        "sync_detected": True,
                    }
                    if parsed:
                        new_rec.update({
                            "underlying": parsed["underlying"],
                            "strike": parsed["strike"],
                            "expiry": parsed["expiry"],
                            "option_type": parsed["option_type"],
                            "occ_symbol": symbol,
                        })
                    new_positions.append(new_rec)

                else:
                    # Update existing local position (re-open if it was previously marked closed)
                    target = local_pos_open or local_pos_closed
                    was_closed = (local_pos_open is None)
                    if was_closed:
                        logger.info(f"[ALPACA-SYNC] Reopening position from closed state: {symbol}")
                        target["status"] = ""
                        target["close_time"] = ""
                        target["reopened_by_sync"] = True
                    # Update core fields
                    if abs(float(target.get("quantity", 0)) - quantity) > 0.01 or was_closed:
                        logger.warning(f"[ALPACA-SYNC] Position update for {symbol}: LocalQty={target.get('quantity')}, AlpacaQty={quantity}")
                        sync_needed = True
                    target["quantity"] = quantity
                    target["market_value"] = market_value
                    target["unrealized_pnl"] = unrealized_pnl
                    target["last_sync"] = datetime.now().isoformat()
                    target["occ_symbol"] = symbol
                    target["sync_adjusted"] = True
            
            # Close local positions that are OPEN but have no matching Alpaca position
            alpaca_symbols = [pos.symbol for pos in options_positions]
            for local_pos in local_positions:
                status_str = str(local_pos.get("status", "")).strip().lower()
                close_time_val = local_pos.get("close_time", "")
                is_closed = status_str.startswith("closed") or self._is_nonempty(close_time_val)
                if is_closed:
                    continue  # already closed
                # If this local row doesn't match any current Alpaca position, mark closed
                if not any(self._local_matches_alpaca(local_pos, s) for s in alpaca_symbols):
                    logger.warning(f"[ALPACA-SYNC] Position closed (detected via Alpaca): {local_pos.get('symbol')} {local_pos.get('strike')} {local_pos.get('option_type')} {local_pos.get('expiry')}")
                    sync_needed = True
                    local_pos["status"] = "closed_sync"
                    local_pos["close_time"] = datetime.now().isoformat()
            
            if sync_needed:
                # Add new positions to local tracking
                local_positions.extend(new_positions)
                
                # Save updated positions
                self._save_local_positions(local_positions)
                
                logger.info(f"[ALPACA-SYNC] Positions synchronized - {len(new_positions)} new positions detected")
                
                # Log sync events
                for pos in new_positions:
                    self._log_sync_event("position_detected", pos)
            else:
                logger.info("[ALPACA-SYNC] Position sync not needed - all positions match")
            
            return True
            
        except Exception as e:
            logger.error(f"[ALPACA-SYNC] Position sync failed: {e}")
            return False
    
    def sync_transactions(self) -> bool:
        """
        Synchronize transaction history with Alpaca orders.
        
        Returns:
            True if sync successful, False otherwise
        """
        try:
            # Get recent Alpaca orders (last 7 days)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=7)
            
            orders_request = GetOrdersRequest(
                status="closed",  # Use string instead of enum
                after=start_date,
                until=end_date,
                asset_class=AssetClass.US_OPTION
            )
            
            alpaca_orders = self.trading_client.get_orders(orders_request)
            
            logger.info(f"[ALPACA-SYNC] Found {len(alpaca_orders)} filled orders in last 7 days")
            
            # Load local trade history
            local_trades = self._load_local_trades()
            local_order_ids = {trade.get("alpaca_order_id") for trade in local_trades if trade.get("alpaca_order_id")}
            
            # Find missing trades
            missing_trades = []
            for order in alpaca_orders:
                if order.id not in local_order_ids:
                    # Missing trade detected
                    logger.warning(f"[ALPACA-SYNC] Detected untracked order: {order.id} ({order.symbol})")
                    
                    trade_record = {
                        "timestamp": order.filled_at.isoformat() if getattr(order, 'filled_at', None) else getattr(order, 'created_at', datetime.now()).isoformat(),
                        "symbol": getattr(order, 'symbol', ''),
                        "action": (order.side.value.upper() if hasattr(getattr(order, 'side', ''), 'value') else str(getattr(order, 'side', '')).upper()),
                        "quantity": float(getattr(order, 'qty', 0) or 0),
                        "price": float(getattr(order, 'filled_avg_price', 0.0) or 0.0),
                        "total_cost": float(getattr(order, 'filled_qty', 0) or 0) * float(getattr(order, 'filled_avg_price', 0.0) or 0.0),
                        "alpaca_order_id": getattr(order, 'id', ''),
                        "source": "sync_detected",
                        "broker": "alpaca",
                        "environment": self.env,
                        "sync_imported": True
                    }
                    
                    missing_trades.append(trade_record)
            
            if missing_trades:
                # Add missing trades to local history
                self._save_missing_trades(missing_trades)
                
                logger.info(f"[ALPACA-SYNC] Transaction sync completed - {len(missing_trades)} missing trades imported")
                
                # Log sync events
                for trade in missing_trades:
                    self._log_sync_event("transaction_imported", trade)
            else:
                logger.info("[ALPACA-SYNC] Transaction sync not needed - all orders tracked")
            
            return True
            
        except Exception as e:
            logger.error(f"[ALPACA-SYNC] Positions sync failed: {e}")
            return False
    
    def sync_transactions_v2(self) -> bool:
        """
        Legacy transaction sync method (not used). Kept for reference but disabled
        by renaming to avoid overriding primary sync_transactions.
        """
        logger.debug("[ALPACA-SYNC] sync_transactions_v2 is disabled (legacy)")
        return True
    
    @retry_with_backoff(max_retries=3, base_delay=1.0)
    def _get_account_with_retry(self):
        """Get Alpaca account info with retry logic."""
        return self.trading_client.get_account()
    
    @retry_with_backoff(max_retries=3, base_delay=1.0)
    def _get_positions_with_retry(self):
        """Get Alpaca positions with retry logic."""
        return self.trading_client.get_all_positions()
    
    @retry_with_backoff(max_retries=3, base_delay=1.0)
    def _get_orders_with_retry(self, request):
        """Get Alpaca orders with retry logic."""
        return self.trading_client.get_orders(request)
    
    def _load_local_bankroll(self) -> Dict:
        """Load local bankroll data."""
        try:
            if os.path.exists(self.bankroll_file):
                with open(self.bankroll_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"[ALPACA-SYNC] Failed to load local bankroll: {e}")
        
        return {"balance": 0.0}
    
    def _load_local_positions(self) -> List[Dict]:
        """Load local positions data."""
        try:
            if os.path.exists(self.positions_file):
                df = pd.read_csv(self.positions_file)
                return df.to_dict('records')
        except Exception as e:
            logger.warning(f"[ALPACA-SYNC] Failed to load local positions: {e}")
        
        return []
    
    def _save_local_positions(self, positions: List[Dict]):
        """Save local positions data."""
        try:
            positions_dir = os.path.dirname(self.positions_file) if os.path.dirname(self.positions_file) else "."
            os.makedirs(positions_dir, exist_ok=True)
            df = pd.DataFrame(positions)
            # Enforce canonical column order for compatibility with monitor/loader
            CANONICAL_COLUMNS = [
                'symbol','occ_symbol','strike','option_type','expiry','quantity','contracts','entry_price',
                'current_price','pnl_pct','pnl_amount','timestamp','status','close_time',
                'market_value','unrealized_pnl','entry_time','source','sync_detected'
            ]
            
            # Fix rows that were written with a legacy/timestamp-first mapping
            # Example bad row under canonical header:
            #   symbol=<ISO timestamp>, strike=UNDERLYING, option_type=EXPIRY, expiry=STRIKE, quantity=CALL/PUT, contracts=QTY, entry_price=ENTRY
            def _is_iso_like(val: str) -> bool:
                try:
                    datetime.fromisoformat(str(val))
                    return True
                except Exception:
                    return False
            
            if not df.empty and 'symbol' in df.columns:
                # Ensure target columns can hold strings
                for col in ['symbol', 'option_type', 'expiry', 'status', 'close_time']:
                    if col in df.columns:
                        try:
                            df[col] = df[col].astype('object')
                        except Exception:
                            pass
                mask = df['symbol'].apply(_is_iso_like)
                if mask.any():
                    # Prepare safe accessors
                    def _safe_num(x):
                        try:
                            return float(x)
                        except Exception:
                            return None
                    def _safe_int(x):
                        try:
                            return int(float(x))
                        except Exception:
                            return None
                    # Perform remap for affected rows using original values
                    idx = df[mask].index
                    old_underlying = df.loc[idx, 'strike'] if 'strike' in df.columns else None
                    old_expiry = df.loc[idx, 'option_type'] if 'option_type' in df.columns else None
                    old_strike = df.loc[idx, 'expiry'] if 'expiry' in df.columns else None
                    old_opt_from_qty = df.loc[idx, 'quantity'] if 'quantity' in df.columns else None
                    old_contracts = df.loc[idx, 'contracts'] if 'contracts' in df.columns else None
                    
                    # underlying (symbol)
                    if old_underlying is not None:
                        df.loc[idx, 'symbol'] = old_underlying
                    # expiry
                    if old_expiry is not None:
                        df.loc[idx, 'expiry'] = old_expiry
                    # strike
                    if old_strike is not None:
                        df.loc[idx, 'strike'] = old_strike.apply(_safe_num)
                    # option_type (from quantity column, which holds CALL/PUT)
                    if old_opt_from_qty is not None:
                        df.loc[idx, 'option_type'] = old_opt_from_qty.astype(str).str.upper().str[:1].map({'C':'CALL','P':'PUT'}).fillna(old_opt_from_qty)
                    # quantity (from contracts)
                    if old_contracts is not None:
                        df.loc[idx, 'quantity'] = old_contracts.apply(_safe_int).fillna(1)
                    # mark normalized status
                    df.loc[idx, 'status'] = df.loc[idx, 'status'].where(~df.loc[idx, 'status'].isna(), other='normalized')
                    # Optional: clear close_time if it's not meaningful
                    # df.loc[idx, 'close_time'] = None
            # Ensure all canonical columns exist (incl. new occ_symbol column)
            for col in CANONICAL_COLUMNS:
                if col not in df.columns:
                    df[col] = None
            df = df[CANONICAL_COLUMNS]
            df.to_csv(self.positions_file, index=False, columns=CANONICAL_COLUMNS)
        except Exception as e:
            logger.error(f"[ALPACA-SYNC] Failed to save local positions: {e}")
    
    def _load_local_trades(self) -> List[Dict]:
        """Load local trade history."""
        try:
            if os.path.exists(self.trade_history_file):
                df = pd.read_csv(self.trade_history_file)
                return df.to_dict('records')
        except Exception as e:
            logger.warning(f"[ALPACA-SYNC] Failed to load local trades: {e}")
        
        return []
    
    def _save_missing_trades(self, missing_trades: List[Dict]):
        """Append missing trades to local trade history."""
        try:
            trade_history_dir = os.path.dirname(self.trade_history_file) if os.path.dirname(self.trade_history_file) else "."
            os.makedirs(trade_history_dir, exist_ok=True)
            
            # Load existing trades
            existing_trades = self._load_local_trades()
            
            # Append missing trades
            all_trades = existing_trades + missing_trades
            
            # Save updated trade history
            df = pd.DataFrame(all_trades)
            df.to_csv(self.trade_history_file, index=False)
            
        except Exception as e:
            logger.error(f"[ALPACA-SYNC] Failed to save missing trades: {e}")
    
    def _log_sync_event(self, event_type: str, data: Dict):
        """Log synchronization events for audit trail."""
        try:
            sync_log_file = f"logs/alpaca_sync_{self.env}.log"
            os.makedirs(os.path.dirname(sync_log_file), exist_ok=True)
            
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "event_type": event_type,
                "environment": self.env,
                "data": data
            }
            
            with open(sync_log_file, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
                
        except Exception as e:
            logger.warning(f"[ALPACA-SYNC] Failed to log sync event: {e}")
    
    def _send_sync_notification(self, results: Dict[str, bool]):
        """Send Slack notification about sync results."""
        try:
            slack_notifier = SlackNotifier()
            
            success_count = sum(results.values())
            total_count = len(results)
            
            if success_count == total_count:
                status_emoji = "✅"
                status_text = "SUCCESS"
            elif success_count > 0:
                status_emoji = "⚠️"
                status_text = "PARTIAL"
            else:
                status_emoji = "❌"
                status_text = "FAILED"
            
            message = f"{status_emoji} **Alpaca Sync {status_text}** [{self.env.upper()}]\n"
            message += f"Bankroll: {'✅' if results['bankroll'] else '❌'} | "
            message += f"Positions: {'✅' if results['positions'] else '❌'} | "
            message += f"Transactions: {'✅' if results['transactions'] else '❌'}"
            
            # Use the error alert method for sync notifications
            slack_notifier.send_error_alert("Alpaca Sync", message)
            
        except Exception as e:
            logger.warning(f"[ALPACA-SYNC] Failed to send Slack notification: {e}")
    
    def check_sync_needed(self) -> Dict[str, bool]:
        """
        Check if synchronization is needed without performing sync.
        
        Returns:
            Dict indicating which components need sync
        """
        if not self.sync_enabled or not self.trading_client:
            return {"bankroll": False, "positions": False, "transactions": False}
        
        try:
            # Quick bankroll check
            account = self.trading_client.get_account()
            alpaca_equity = float(account.equity)
            local_bankroll = self._load_local_bankroll()
            local_balance = local_bankroll.get("balance", 0.0)
            
            balance_diff_pct = (abs(alpaca_equity - local_balance) / max(alpaca_equity, 1)) * 100
            bankroll_needs_sync = balance_diff_pct > self.sync_tolerance_pct
            
            # Quick position check
            alpaca_positions = self.trading_client.get_all_positions()
            def _is_option_position_quick(pos):
                ac = getattr(pos, 'asset_class', None)
                return (ac == AssetClass.US_OPTION) or ('OPTION' in str(ac).upper())
            options_positions = [pos for pos in alpaca_positions if _is_option_position_quick(pos)]
            local_positions = self._load_local_positions()
            
            # Treat any status starting with 'closed' as closed
            open_local_positions = [
                p for p in local_positions
                if not str(p.get("status", "")).lower().startswith("closed")
            ]
            positions_need_sync = len(options_positions) != len(open_local_positions)
            
            return {
                "bankroll": bankroll_needs_sync,
                "positions": positions_need_sync,
                "transactions": False  # Skip transaction check for quick check
            }
            
        except Exception as e:
            logger.warning(f"[ALPACA-SYNC] Sync check failed: {e}")
            return {"bankroll": True, "positions": True, "transactions": True}  # Assume sync needed on error


def sync_before_trade(env: str = "paper") -> bool:
    """
    Convenience function to sync before trading operations.
    
    Args:
        env: Alpaca environment
        
    Returns:
        True if sync successful or not needed, False if sync failed
    """
    try:
        sync = AlpacaSync(env=env)
        
        if not sync.auto_sync_before_trade:
            logger.debug("[ALPACA-SYNC] Auto-sync before trade disabled")
            return True
        
        # Check if sync is needed
        sync_needed = sync.check_sync_needed()
        
        if not any(sync_needed.values()):
            logger.debug("[ALPACA-SYNC] No sync needed before trade")
            return True
        
        # Perform sync
        logger.info("[ALPACA-SYNC] Syncing before trade execution...")
        results = sync.sync_all()
        
        # Return True if all critical syncs succeeded
        return results.get("bankroll", False) and results.get("positions", False)
        
    except Exception as e:
        logger.error(f"[ALPACA-SYNC] Pre-trade sync failed: {e}")
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Alpaca Data Synchronization")
    parser.add_argument("--env", choices=["paper", "live"], default="paper", help="Alpaca environment")
    parser.add_argument("--sync-type", choices=["all", "bankroll", "positions", "transactions"], default="all", help="Sync type")
    parser.add_argument("--check-only", action="store_true", help="Check if sync needed without performing sync")
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Create sync instance
    sync = AlpacaSync(env=args.env)
    
    if args.check_only:
        # Check sync status
        sync_needed = sync.check_sync_needed()
        print(f"Sync needed: {sync_needed}")
    else:
        # Perform sync
        if args.sync_type == "all":
            results = sync.sync_all()
        elif args.sync_type == "bankroll":
            results = {"bankroll": sync.sync_bankroll()}
        elif args.sync_type == "positions":
            results = {"positions": sync.sync_positions()}
        elif args.sync_type == "transactions":
            results = {"transactions": sync.sync_transactions()}
        
        print(f"Sync results: {results}")
