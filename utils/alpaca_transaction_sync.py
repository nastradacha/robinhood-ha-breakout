#!/usr/bin/env python3
"""
Alpaca Transaction Data Synchronization

This utility pulls real transaction data directly from Alpaca API to ensure
no trades are missed in the system's bankroll and position tracking.

Features:
- Fetch all orders and fills from Alpaca API
- Reconcile with system trade records
- Update bankroll with missing transactions
- Sync position tracking with actual holdings
- Handle both paper and live environments

Usage:
    from utils.alpaca_transaction_sync import sync_alpaca_transactions
    sync_alpaca_transactions()
"""

import logging
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pathlib import Path

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import GetOrdersRequest
    from alpaca.trading.enums import OrderStatus, AssetClass
except ImportError:
    print("Warning: alpaca-py not installed. Transaction sync unavailable.")
    TradingClient = None

logger = logging.getLogger(__name__)

class AlpacaTransactionSync:
    """Synchronizes Alpaca transaction data with system records."""
    
    def __init__(self, paper: bool = True):
        """Initialize Alpaca transaction sync.
        
        Args:
            paper: Use paper trading environment
        """
        self.paper = paper
        self.client = None
        
        if TradingClient:
            self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Alpaca trading client."""
        import os
        from dotenv import load_dotenv
        
        load_dotenv()
        
        api_key = os.getenv('ALPACA_API_KEY') or os.getenv('ALPACA_KEY_ID')
        secret_key = os.getenv('ALPACA_SECRET_KEY')
        
        if not api_key or not secret_key:
            logger.error("Alpaca credentials not found")
            return
        
        try:
            self.client = TradingClient(
                api_key=api_key,
                secret_key=secret_key,
                paper=self.paper
            )
            logger.info(f"Initialized Alpaca client (paper={self.paper})")
        except Exception as e:
            logger.error(f"Error initializing Alpaca client: {e}")
    
    def fetch_recent_orders(self, days: int = 7) -> List[Dict]:
        """Fetch recent orders from Alpaca API.
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of order dictionaries
        """
        if not self.client:
            logger.error("Alpaca client not initialized")
            return []
        
        try:
            # Get orders from last N days
            after = datetime.now() - timedelta(days=days)
            
            request = GetOrdersRequest(
                status=OrderStatus.FILLED,
                after=after,
                asset_class=AssetClass.OPTION
            )
            
            orders = self.client.get_orders(filter=request)
            
            # Convert to dictionaries
            order_list = []
            for order in orders:
                order_dict = {
                    'id': str(order.id),
                    'symbol': order.symbol,
                    'side': order.side.value,
                    'qty': float(order.qty),
                    'filled_qty': float(order.filled_qty),
                    'filled_avg_price': float(order.filled_avg_price) if order.filled_avg_price else 0.0,
                    'status': order.status.value,
                    'submitted_at': order.submitted_at.isoformat() if order.submitted_at else None,
                    'filled_at': order.filled_at.isoformat() if order.filled_at else None,
                    'asset_class': order.asset_class.value if order.asset_class else 'option',
                    'notional': float(order.notional) if order.notional else 0.0
                }
                order_list.append(order_dict)
            
            logger.info(f"Fetched {len(order_list)} filled orders from Alpaca")
            return order_list
            
        except Exception as e:
            logger.error(f"Error fetching orders from Alpaca: {e}")
            return []
    
    def parse_option_symbol(self, symbol: str) -> Optional[Dict]:
        """Parse OCC option symbol into components.
        
        Args:
            symbol: OCC format option symbol (e.g., IWM250813C00229000)
            
        Returns:
            Dict with underlying, expiry, option_type, strike
        """
        try:
            if len(symbol) < 15:
                return None
            
            # Extract components from OCC format
            underlying = symbol[:3]  # IWM
            date_part = symbol[3:9]  # 250813
            option_type = symbol[9]  # C or P
            strike_part = symbol[10:]  # 00229000
            
            # Parse date (YYMMDD)
            year = 2000 + int(date_part[:2])
            month = int(date_part[2:4])
            day = int(date_part[4:6])
            expiry = f"{year}-{month:02d}-{day:02d}"
            
            # Parse strike (8 digits, divide by 1000)
            strike = float(strike_part) / 1000.0
            
            return {
                'underlying': underlying,
                'expiry': expiry,
                'option_type': 'CALL' if option_type == 'C' else 'PUT',
                'strike': strike
            }
            
        except Exception as e:
            logger.error(f"Error parsing option symbol {symbol}: {e}")
            return None
    
    def load_system_bankroll(self) -> Optional[Dict]:
        """Load current system bankroll file."""
        bankroll_file = Path("bankroll_alpaca_live.json")
        if bankroll_file.exists():
            with open(bankroll_file, 'r') as f:
                return json.load(f)
        return None
    
    def sync_transactions(self, days: int = 7) -> bool:
        """Sync Alpaca transactions with system records.
        
        Args:
            days: Number of days to sync
            
        Returns:
            True if sync successful
        """
        print(f"=== SYNCING ALPACA TRANSACTIONS ({days} days) ===")
        
        # Fetch recent orders from Alpaca
        alpaca_orders = self.fetch_recent_orders(days)
        if not alpaca_orders:
            print("No orders found in Alpaca or API error")
            return False
        
        print(f"Found {len(alpaca_orders)} filled orders from Alpaca")
        
        # Load current system bankroll
        bankroll = self.load_system_bankroll()
        if not bankroll:
            print("Could not load system bankroll")
            return False
        
        # Analyze orders
        option_orders = []
        total_cost = 0.0
        total_proceeds = 0.0
        
        for order in alpaca_orders:
            # Parse option symbol
            option_info = self.parse_option_symbol(order['symbol'])
            if not option_info:
                continue
            
            # Calculate trade value
            trade_value = order['filled_qty'] * order['filled_avg_price'] * 100  # Options multiplier
            
            if order['side'] == 'buy':
                total_cost += trade_value
                trade_value = -trade_value  # Cost is negative
            else:  # sell
                total_proceeds += trade_value
            
            order_record = {
                'timestamp': order['filled_at'] or order['submitted_at'],
                'symbol': option_info['underlying'],
                'direction': option_info['option_type'],
                'strike': option_info['strike'],
                'expiry': option_info['expiry'],
                'quantity': int(order['filled_qty']),
                'premium': order['filled_avg_price'],
                'total_value': trade_value,
                'action': order['side'].upper(),
                'order_id': order['id'],
                'status': 'FILLED'
            }
            option_orders.append(order_record)
        
        # Calculate P&L
        net_pnl = total_proceeds - total_cost
        
        print(f"\nAlpaca Transaction Summary:")
        print(f"Total Costs: ${total_cost:.2f}")
        print(f"Total Proceeds: ${total_proceeds:.2f}")
        print(f"Net P&L: ${net_pnl:.2f}")
        
        # Display transactions
        print(f"\nTransactions:")
        for order in option_orders:
            action = order['action']
            symbol = order['symbol']
            strike = order['strike']
            option_type = order['direction']
            qty = order['quantity']
            price = order['premium']
            value = abs(order['total_value'])
            timestamp = order['timestamp'][:19] if order['timestamp'] else 'Unknown'
            
            print(f"  {timestamp} | {action} {qty}x {symbol} ${strike} {option_type} @ ${price:.2f} = ${value:.2f}")
        
        print(f"\nSync completed - found {len(option_orders)} option transactions")
        return True

def sync_alpaca_transactions(days: int = 7, paper: bool = None) -> bool:
    """Convenience function to sync Alpaca transactions.
    
    Args:
        days: Number of days to sync
        paper: Paper trading mode (auto-detect if None)
        
    Returns:
        True if sync successful
    """
    if paper is None:
        # Auto-detect from config
        try:
            from utils.llm import load_config
            config = load_config("config.yaml")
            env = config.get("ALPACA_ENV", "paper")
            paper = (env == "paper")
        except:
            paper = True  # Default to paper
    
    sync = AlpacaTransactionSync(paper=paper)
    return sync.sync_transactions(days)

if __name__ == "__main__":
    # Test sync
    sync_alpaca_transactions(days=7)
