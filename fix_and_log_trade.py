#!/usr/bin/env python3
"""
Fix bankroll.json and log the SPY $628 CALL trade
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
        
        print("✅ Fixed bankroll.json file")
        return data
    else:
        print("❌ bankroll.json not found")
        return None

def log_spy_trade():
    """Log the SPY $628 CALL trade with correct premium."""
    
    print("=== LOGGING SPY $628 CALL TRADE ===")
    print()
    
    # Fix bankroll file first
    bankroll_data = fix_bankroll_file()
    if not bankroll_data:
        print("Cannot proceed without bankroll file")
        return
    
    print()
    print("Trade Details:")
    print("- Symbol: SPY")
    print("- Strike: $628")
    print("- Type: CALL")
    print("- Quantity: 1 contract")
    print("- Expiry: Today (0DTE)")
    print()
    
    print("IMPORTANT: Enter the PREMIUM you paid per contract, NOT the strike price!")
    print("Examples:")
    print("- If you paid $142 total for 1 contract, enter: 1.42")
    print("- If you paid $174 total for 1 contract, enter: 1.74")
    print("- If you paid $200 total for 1 contract, enter: 2.00")
    print()
    
    while True:
        try:
            premium_input = input("Premium paid per contract (e.g., 1.42): $").strip()
            entry_premium = float(premium_input)
            
            if entry_premium > 50:
                print(f"⚠️  ${entry_premium:.2f} seems too high for a premium. Did you mean ${entry_premium/100:.2f}?")
                confirm = input("Continue with this amount? (y/n): ").strip().lower()
                if confirm != 'y':
                    continue
            
            break
        except ValueError:
            print("Please enter a valid number (e.g., 1.42)")
    
    # Calculate total cost
    total_cost = entry_premium * 100  # 1 contract = 100 shares
    
    print()
    print(f"Confirming trade:")
    print(f"- Premium per contract: ${entry_premium:.2f}")
    print(f"- Total cost: ${total_cost:.2f}")
    print(f"- Current bankroll: ${bankroll_data['current_bankroll']:.2f}")
    print(f"- New bankroll: ${bankroll_data['current_bankroll'] - total_cost:.2f}")
    print()
    
    confirm = input("Confirm this trade? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Trade logging cancelled")
        return
    
    # Create position
    position = Position(
        entry_time=datetime.now().isoformat(),
        symbol="SPY",
        expiry=datetime.now().strftime("%Y-%m-%d"),  # 0DTE
        strike=628.0,
        side="CALL",
        contracts=1,
        entry_premium=entry_premium
    )
    
    # Add to portfolio
    portfolio_manager = PortfolioManager("positions.csv")
    portfolio_manager.add_position(position)
    
    # Update bankroll manually (avoid the update_bankroll method that has issues)
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
    
    print()
    print("✅ TRADE LOGGED SUCCESSFULLY!")
    print(f"Position: 1 SPY $628 CALL @ ${entry_premium:.2f}")
    print(f"Total Cost: ${total_cost:.2f}")
    print(f"New Bankroll: ${new_bankroll:.2f}")
    print()
    
    # Show profit/loss targets
    profit_target = entry_premium * 1.15  # 15% profit
    stop_loss = entry_premium * 0.75      # 25% loss
    
    print("🎯 MONITORING TARGETS:")
    print(f"- Profit Target (15%): ${profit_target:.2f}")
    print(f"- Stop Loss (25%): ${stop_loss:.2f}")
    print(f"- End-of-Day Exit: 3:45 PM ET")
    print()
    print("📱 NEXT STEPS:")
    print("1. Monitor your position throughout the day")
    print("2. Take profits at 15% gain or stop loss at 25% loss")
    print("3. Close position by 3:45 PM to avoid overnight risk")
    print("4. When ready to monitor automatically:")
    print("   python main.py --monitor-positions --interval 2 --end-at 15:45")

if __name__ == "__main__":
    try:
        log_spy_trade()
    except KeyboardInterrupt:
        print("\nCancelled by user")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
