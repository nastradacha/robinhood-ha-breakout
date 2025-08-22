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
from alpaca.trading.enums import OrderSide, OrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from .scoped_files import get_scoped_paths
from .llm import load_config

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
            options_positions = [
                pos for pos in positions 
                if hasattr(pos, 'asset_class') and 'OPTION' in str(pos.asset_class)
            ]
            
            logger.info(f"[ALPACA-SYNC] Found {len(options_positions)} options positions in Alpaca account")
            
            # Load current local positions
            local_positions = self._load_local_positions()
            
            # Compare and sync positions
            sync_needed = False
            new_positions = []
            
            for alpaca_pos in options_positions:
                symbol = alpaca_pos.symbol
                quantity = float(alpaca_pos.qty)
                market_value = float(alpaca_pos.market_value) if alpaca_pos.market_value else 0.0
                unrealized_pnl = float(alpaca_pos.unrealized_pnl) if alpaca_pos.unrealized_pnl else 0.0
                
                # Check if position exists locally
                local_pos = next((p for p in local_positions if p.get("symbol") == symbol), None)
                
                if not local_pos:
                    # New position detected (manual trade)
                    logger.warning(f"[ALPACA-SYNC] Detected manual position: {symbol} (qty: {quantity})")
                    sync_needed = True
                    
                    new_positions.append({
                        "symbol": symbol,
                        "quantity": quantity,
                        "market_value": market_value,
                        "unrealized_pnl": unrealized_pnl,
                        "entry_time": datetime.now().isoformat(),
                        "source": "manual_trade_detected",
                        "sync_detected": True
                    })
                
                elif abs(float(local_pos.get("quantity", 0)) - quantity) > 0.01:
                    # Quantity mismatch
                    logger.warning(f"[ALPACA-SYNC] Position quantity mismatch for {symbol}: Local={local_pos.get('quantity')}, Alpaca={quantity}")
                    sync_needed = True
                    
                    # Update local position
                    local_pos["quantity"] = quantity
                    local_pos["market_value"] = market_value
                    local_pos["unrealized_pnl"] = unrealized_pnl
                    local_pos["last_sync"] = datetime.now().isoformat()
                    local_pos["sync_adjusted"] = True
            
            # Check for positions that exist locally but not in Alpaca (closed manually)
            alpaca_symbols = {pos.symbol for pos in options_positions}
            for local_pos in local_positions:
                if local_pos.get("symbol") not in alpaca_symbols:
                    logger.warning(f"[ALPACA-SYNC] Position closed manually: {local_pos.get('symbol')}")
                    sync_needed = True
                    local_pos["status"] = "closed_manually"
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
                        "timestamp": order.filled_at.isoformat() if order.filled_at else order.created_at.isoformat(),
                        "symbol": order.symbol,
                        "action": order.side.value.upper(),
                        "quantity": float(order.qty),
                        "price": float(order.filled_avg_price) if order.filled_avg_price else 0.0,
                        "total_cost": float(order.filled_qty) * float(order.filled_avg_price) if order.filled_avg_price else 0.0,
                        "alpaca_order_id": order.id,
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
    
    def sync_transactions(self) -> bool:
        """
        Synchronize transaction history with Alpaca orders.
        
        Returns:
            True if sync successful, False otherwise
        """
        try:
            # Get recent orders from Alpaca with retry logic
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)  # Last 30 days
            
            request = GetOrdersRequest(
                status="closed",  # Use string instead of OrderStatus enum
                limit=500,
                nested=True
            )
            
            orders = self._get_orders_with_retry(request)
            logger.info(f"[ALPACA-SYNC] Retrieved {len(orders)} filled orders from Alpaca")
            
            # Load existing trade history
            trade_history = self._load_trade_history()
            existing_order_ids = set(trade.get('alpaca_order_id') for trade in trade_history if trade.get('alpaca_order_id'))
            
            # Process new orders
            new_trades = []
            for order in orders:
                if order.id not in existing_order_ids:
                    # Convert Alpaca order to trade record
                    trade = self._convert_order_to_trade(order)
                    if trade:
                        new_trades.append(trade)
                        logger.info(f"[ALPACA-SYNC] New trade detected: {trade['symbol']} {trade['action']} {trade['quantity']} @ ${trade['price']}")
            
            if new_trades:
                # Append new trades to history
                self._save_new_trades(new_trades)
                logger.info(f"[ALPACA-SYNC] Imported {len(new_trades)} new trades")
                
                # Log sync events
                for trade in new_trades:
                    self._log_sync_event("transaction_imported", trade)
            else:
                logger.info("[ALPACA-SYNC] Transaction sync not needed - all orders tracked")
            
            return True
            
        except Exception as e:
            logger.error(f"[ALPACA-SYNC] Transaction sync failed: {e}")
            return False
    
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
            df.to_csv(self.positions_file, index=False)
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
            options_positions = [pos for pos in alpaca_positions if pos.asset_class == AssetClass.US_OPTION]
            local_positions = self._load_local_positions()
            
            positions_need_sync = len(options_positions) != len([p for p in local_positions if p.get("status") != "closed_manually"])
            
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
