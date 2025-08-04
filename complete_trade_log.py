#!/usr/bin/env python3
"""
Complete trade logging with full bankroll fix
"""

import json
from datetime import datetime
from pathlib import Path
from utils.portfolio import PortfolioManager, Position

def complete_fix_and_log():
    """Fix bankroll completely and log the SPY trade."""
    
    print("=== COMPLETE TRADE LOGGING ===")
    print()
    
    # Load or create complete bankroll data
    bankroll_file = Path("bankroll.json")
    
    if bankroll_file.exists():
        with open(bankroll_file, 'r') as f:
            data = json.load(f)
        print(f"Current bankroll: ${data.get('current_bankroll', 500.0):.2f}")
    else:
        data = {}
        print("Creating new bankroll file...")
    
    # Ensure all required fields exist
    current_bankroll = data.get('current_bankroll', 500.0)
    
    complete_data = {
        "current_bankroll": current_bankroll,
        "start_capital": data.get('start_capital', 500.0),
        "total_trades": data.get('total_trades', 0),
        "winning_trades": data.get('winning_trades', 0),
        "total_pnl": data.get('total_pnl', 0.0),
        "max_drawdown": data.get('max_drawdown', 0.0),
        "peak_bankroll": data.get('peak_bankroll', current_bankroll),
        "created_at": data.get('created_at', datetime.now().isoformat()),
        "last_updated": datetime.now().isoformat(),
        "trade_history": data.get('trade_history', []),
        "win_loss_history": data.get('win_loss_history', [])
    }
    
    print("[OK] Bankroll data structure complete")
    print()
    
    # Log the SPY trade
    print("Logging SPY $628 CALL trade:")
    print("- Premium: $1.42 per contract")
    print("- Total cost: $142.00")
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
    try:
        portfolio_manager = PortfolioManager("positions.csv")
        portfolio_manager.add_position(position)
        print("[OK] Added to positions.csv")
    except Exception as e:
        print(f"[WARNING] Portfolio error: {e}")
        print("Continuing with bankroll update...")
    
    # Update bankroll
    total_cost = 142.00  # $1.42 * 100
    new_bankroll = complete_data['current_bankroll'] - total_cost
    
    complete_data['current_bankroll'] = new_bankroll
    complete_data['total_trades'] += 1
    complete_data['last_updated'] = datetime.now().isoformat()
    
    # Update peak if necessary
    if new_bankroll > complete_data['peak_bankroll']:
        complete_data['peak_bankroll'] = new_bankroll
    
    # Save complete bankroll data
    with open(bankroll_file, 'w') as f:
        json.dump(complete_data, f, indent=2)
    
    print("[OK] TRADE LOGGED SUCCESSFULLY!")
    print()
    print("TRADE SUMMARY:")
    print(f"- Position: 1 SPY $628 CALL @ $1.42")
    print(f"- Total Cost: $142.00")
    print(f"- Previous Bankroll: ${complete_data['current_bankroll'] + total_cost:.2f}")
    print(f"- New Bankroll: ${new_bankroll:.2f}")
    print(f"- Total Trades: {complete_data['total_trades']}")
    print()
    
    # Show monitoring targets
    profit_target = 1.42 * 1.15  # 15% profit target
    stop_loss = 1.42 * 0.75      # 25% stop loss
    
    print("MONITORING TARGETS:")
    print(f"- Profit Target (15%): ${profit_target:.2f} = ${(profit_target - 1.42) * 100:.0f} profit")
    print(f"- Stop Loss (25%): ${stop_loss:.2f} = ${(stop_loss - 1.42) * 100:.0f} loss")
    print(f"- End-of-Day Exit: 3:45 PM ET (avoid overnight risk)")
    print()
    
    print("NEXT STEPS:")
    print("1. Monitor your position throughout the day")
    print("2. Take profits at 15% gain or cut losses at 25%")
    print("3. Close position by 3:45 PM ET")
    print("4. For automated monitoring:")
    print("   python main.py --monitor-positions --interval 2 --end-at 15:45 --slack-notify")
    print()
    print("Your conservative strategy is now active!")
    print("Priority: Avoid losses over maximizing daily profit")

if __name__ == "__main__":
    try:
        complete_fix_and_log()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
