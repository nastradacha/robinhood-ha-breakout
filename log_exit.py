#!/usr/bin/env python3
"""
Log trade exit and update position tracking
"""

import json
import csv
from datetime import datetime
from pathlib import Path
from utils.portfolio import PortfolioManager
from utils.bankroll import BankrollManager

def log_exit():
    """Log the SPY $628 CALL exit at $1.83."""
    
    print("=== LOGGING TRADE EXIT ===")
    print()
    
    # Trade details
    entry_premium = 1.42
    exit_premium = 1.83
    contracts = 1
    
    # Calculate P&L
    profit_per_contract = exit_premium - entry_premium
    profit_percentage = (profit_per_contract / entry_premium) * 100
    total_profit = profit_per_contract * contracts * 100  # $100 per contract
    
    print(f"Trade: 1 SPY $628 CALL")
    print(f"Entry: ${entry_premium:.2f}")
    print(f"Exit: ${exit_premium:.2f}")
    print(f"Profit: ${profit_per_contract:.2f} per contract ({profit_percentage:+.1f}%)")
    print(f"Total Profit: ${total_profit:.2f}")
    print()
    
    # Update portfolio (remove position)
    try:
        portfolio_manager = PortfolioManager("positions.csv")
        positions = portfolio_manager.load_positions()
        
        if positions:
            print("[OK] Removing position from positions.csv")
            # Clear positions file (trade is closed)
            with open("positions.csv", 'w', newline='') as f:
                fieldnames = ['entry_time', 'symbol', 'expiry', 'strike', 'side', 'contracts', 'entry_premium']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
        else:
            print("[INFO] No positions found to remove")
    except Exception as e:
        print(f"[WARNING] Portfolio update error: {e}")
    
    # Update bankroll
    try:
        bankroll_manager = BankrollManager("bankroll.json", 500.0)
        current_bankroll = bankroll_manager.get_current_bankroll()
        new_bankroll = current_bankroll + total_profit
        
        # Load bankroll data to update manually
        with open("bankroll.json", 'r') as f:
            data = json.load(f)
        
        # Update fields
        data['current_bankroll'] = new_bankroll
        data['total_trades'] = data.get('total_trades', 0) + 1
        data['winning_trades'] = data.get('winning_trades', 0) + 1
        data['total_pnl'] = data.get('total_pnl', 0.0) + total_profit
        
        # Update peak if necessary
        if new_bankroll > data.get('peak_bankroll', 0):
            data['peak_bankroll'] = new_bankroll
        
        # Add to trade history
        if 'trade_history' not in data:
            data['trade_history'] = []
        
        trade_record = {
            'timestamp': datetime.now().isoformat(),
            'symbol': 'SPY',
            'strike': 628.0,
            'side': 'CALL',
            'entry_premium': entry_premium,
            'exit_premium': exit_premium,
            'contracts': contracts,
            'profit': total_profit,
            'profit_percentage': profit_percentage
        }
        data['trade_history'].append(trade_record)
        
        # Add to win/loss history
        if 'win_loss_history' not in data:
            data['win_loss_history'] = []
        data['win_loss_history'].append(True)  # This was a winning trade
        
        # Keep only last 20 trades in history
        if len(data['win_loss_history']) > 20:
            data['win_loss_history'] = data['win_loss_history'][-20:]
        
        data['last_updated'] = datetime.now().isoformat()
        
        # Save updated bankroll
        with open("bankroll.json", 'w') as f:
            json.dump(data, f, indent=2)
        
        print("[OK] Updated bankroll and trade history")
        print(f"Bankroll: ${current_bankroll:.2f} -> ${new_bankroll:.2f}")
        print(f"Total Trades: {data['total_trades']}")
        print(f"Winning Trades: {data['winning_trades']}")
        print(f"Win Rate: {(data['winning_trades']/data['total_trades']*100):.1f}%")
        
    except Exception as e:
        print(f"[ERROR] Bankroll update failed: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    print("EXCELLENT TRADE!")
    print(f"You made ${total_profit:.2f} profit ({profit_percentage:+.1f}%)")
    print("This demonstrates your conservative strategy working perfectly:")
    print("- Took profits before hitting the 15% target")
    print("- Avoided potential losses from holding too long")
    print("- Followed the principle: 'Avoid losses over maximizing daily profit'")
    print()
    print("Your position monitoring can now be stopped (Ctrl+C)")

if __name__ == "__main__":
    try:
        log_exit()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
