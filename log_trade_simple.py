#!/usr/bin/env python3
"""
Simple trade logging script - Windows compatible
"""

import json
from datetime import datetime
from pathlib import Path
from utils.portfolio import PortfolioManager, Position

def fix_bankroll_file():
    """Fix missing peak_bankroll field in bankroll.json"""
    bankroll_file = Path("bankroll.json")
    
    if bankroll_file.exists():
        with open(bankroll_file, 'r') as f:
            data = json.load(f)
        
        # Add missing fields if they don't exist
        if "peak_bankroll" not in data:
            data["peak_bankroll"] = data.get("current_bankroll", 500.0)
            print(f"Added missing peak_bankroll: ${data['peak_bankroll']:.2f}")
        
        if "max_drawdown" not in data:
            data["max_drawdown"] = 0.0
            print("Added missing max_drawdown: 0.0")
        
        if "trade_history" not in data:
            data["trade_history"] = []
            print("Added missing trade_history")
        
        if "win_loss_history" not in data:
            data["win_loss_history"] = []
            print("Added missing win_loss_history")
        
        # Save the fixed file
        data["last_updated"] = datetime.now().isoformat()
        with open(bankroll_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        print("[OK] Fixed bankroll.json file")
        return data
    else:
        print("[ERROR] bankroll.json not found")
        return None

def log_spy_trade():
    """Log the SPY $628 CALL trade with $1.42 premium."""
    
    print("=== LOGGING SPY $628 CALL TRADE ===")
    print()
    
    # Fix bankroll file first
    bankroll_data = fix_bankroll_file()
    if not bankroll_data:
        print("Cannot proceed without bankroll file")
        return
    
    print()
    print("Logging your trade:")
    print("- Symbol: SPY")
    print("- Strike: $628")
    print("- Type: CALL")
    print("- Quantity: 1 contract")
    print("- Premium: $1.42 per contract")
    print("- Total Cost: $142.00")
    print()
    
    # Create position
    position = Position(
        entry_time=datetime.now().isoformat(),
        symbol="SPY",
        expiry=datetime.now().strftime("%Y-%m-%d"),  # 0DTE
        strike=628.0,
        side="CALL",
        contracts=1,
        entry_premium=1.42
    )
    
    # Add to portfolio
    portfolio_manager = PortfolioManager("positions.csv")
    portfolio_manager.add_position(position)
    
    # Update bankroll manually
    total_cost = 142.00  # $1.42 * 100
    new_bankroll = bankroll_data['current_bankroll'] - total_cost
    bankroll_data['current_bankroll'] = new_bankroll
    bankroll_data['total_trades'] += 1
    
    # Update peak if necessary
    if new_bankroll > bankroll_data['peak_bankroll']:
        bankroll_data['peak_bankroll'] = new_bankroll
    
    # Save updated bankroll
    bankroll_data['last_updated'] = datetime.now().isoformat()
    with open("bankroll.json", 'w') as f:
        json.dump(bankroll_data, f, indent=2)
    
    print("[OK] TRADE LOGGED SUCCESSFULLY!")
    print(f"Position: 1 SPY $628 CALL @ $1.42")
    print(f"Total Cost: $142.00")
    print(f"Bankroll: ${bankroll_data['current_bankroll'] + total_cost:.2f} -> ${new_bankroll:.2f}")
    print()
    
    # Show profit/loss targets
    profit_target = 1.42 * 1.15  # 15% profit
    stop_loss = 1.42 * 0.75      # 25% loss
    
    print("MONITORING TARGETS:")
    print(f"- Profit Target (15%): ${profit_target:.2f}")
    print(f"- Stop Loss (25%): ${stop_loss:.2f}")
    print(f"- End-of-Day Exit: 3:45 PM ET")
    print()
    print("NEXT STEPS:")
    print("1. Monitor position for profit/loss targets")
    print("2. Close by 3:45 PM to avoid overnight risk")
    print("3. Use position monitoring when ready:")
    print("   python main.py --monitor-positions --interval 2 --end-at 15:45")

if __name__ == "__main__":
    try:
        log_spy_trade()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
