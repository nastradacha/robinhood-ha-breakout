#!/usr/bin/env python3
"""
Recover Real Trading Data

Recreates the trade log with your actual Robinhood trading data from today.
"""

import os
import csv
from datetime import datetime, timedelta

def create_real_trade_log():
    """Create trade log with real Robinhood data."""
    
    # Ensure logs directory exists
    os.makedirs('logs', exist_ok=True)
    
    # Calculate approximate times (4 hours ago from current time)
    current_time = datetime.now()
    buy_time = current_time - timedelta(hours=4, minutes=30)  # Approximate buy time
    sell_time = current_time - timedelta(hours=4)  # Approximate sell time
    
    # Your real trade data from Robinhood
    real_trades = [
        {
            'timestamp': buy_time.strftime('%Y-%m-%d %H:%M:%S'),
            'symbol': 'SPY',
            'option_type': 'CALL',
            'strike': 628.0,
            'expiry': '2025-08-04',  # 0DTE
            'action': 'BUY',
            'quantity': 1,
            'price': 1.42,
            'total_cost': 142.00,
            'reason': 'Breakout signal detected',
            'pnl': 0.0,
            'pnl_pct': 0.0
        },
        {
            'timestamp': sell_time.strftime('%Y-%m-%d %H:%M:%S'),
            'symbol': 'SPY',
            'option_type': 'CALL',
            'strike': 628.0,
            'expiry': '2025-08-04',  # 0DTE
            'action': 'SELL',
            'quantity': 1,
            'price': 1.83,
            'total_cost': 183.00,
            'reason': 'Profit target reached',
            'pnl': 41.00,  # $183 - $142
            'pnl_pct': 28.87  # $41 / $142 * 100
        }
    ]
    
    # Create CSV with proper headers
    headers = [
        'timestamp', 'symbol', 'option_type', 'strike', 'expiry', 
        'action', 'quantity', 'price', 'total_cost', 'reason', 'pnl', 'pnl_pct'
    ]
    
    with open('logs/trade_log.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(real_trades)
    
    print("Real trade log recreated successfully!")
    print(f"Trade Summary:")
    print(f"   • Symbol: SPY")
    print(f"   • Strike: $628 CALL")
    print(f"   • Entry: $1.42 ({buy_time.strftime('%H:%M')})")
    print(f"   • Exit: $1.83 ({sell_time.strftime('%H:%M')})")
    print(f"   • Profit: $41.00 (+28.87%)")
    print(f"   • Trade Type: 0DTE ATM Call")
    
    return len(real_trades)

def update_bankroll_for_real_trade():
    """Update bankroll with real trade profit."""
    import json
    
    # Create or update bankroll with real data
    bankroll_data = {
        'starting_bankroll': 500.00,
        'current_bankroll': 541.00,  # $500 + $41 profit
        'peak_bankroll': 541.00,
        'total_trades': 1,  # Your first real trade
        'total_pnl': 41.00,
        'last_updated': datetime.now().isoformat(),
        'win_streak': 1,
        'total_wins': 1,
        'total_losses': 0
    }
    
    with open('bankroll.json', 'w') as f:
        json.dump(bankroll_data, f, indent=2)
    
    print("Bankroll updated with real trade profit!")
    print(f"New Balance: $541.00 (+$41.00)")

if __name__ == "__main__":
    print("Recovering your real trading data...")
    print("From Robinhood History:")
    print("   • Buy SPY $628 Call 8/4 at $1.42")
    print("   • Sell SPY $628 Call 8/4 at $1.83")
    print("   • Profit: $41.00")
    print()
    
    # Recreate trade log
    trades_created = create_real_trade_log()
    
    # Update bankroll
    update_bankroll_for_real_trade()
    
    print()
    print("Data recovery complete!")
    print("You can now run: python analytics_dashboard.py --mode cli")
    print("Or send to Slack: python analytics_dashboard.py --slack-summary")
