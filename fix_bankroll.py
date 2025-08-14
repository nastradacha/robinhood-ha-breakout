#!/usr/bin/env python3
"""
Fix Current Bankroll Field

This script specifically fixes the current_bankroll field to match
the current_balance after a deposit.
"""

import json

def fix_bankroll():
    """Fix current_bankroll to match current_balance."""
    
    bankroll_file = "bankroll_alpaca_live.json"
    
    try:
        # Load bankroll data
        with open(bankroll_file, 'r') as f:
            bankroll_data = json.load(f)
        
        current_balance = bankroll_data.get("current_balance", 0.0)
        current_bankroll = bankroll_data.get("current_bankroll", 0.0)
        
        print(f"[BEFORE] Current Balance: ${current_balance:.2f}")
        print(f"[BEFORE] Current Bankroll: ${current_bankroll:.2f}")
        
        # Update current_bankroll to match current_balance
        bankroll_data["current_bankroll"] = current_balance
        
        # Save updated bankroll
        with open(bankroll_file, 'w') as f:
            json.dump(bankroll_data, f, indent=2)
        
        print(f"[AFTER] Current Balance: ${current_balance:.2f}")
        print(f"[AFTER] Current Bankroll: ${current_balance:.2f}")
        print(f"[SUCCESS] Bankroll field synchronized!")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Error fixing bankroll: {e}")
        return False

if __name__ == "__main__":
    print("Bankroll Field Fix Utility")
    print("=" * 30)
    
    success = fix_bankroll()
    
    if success:
        print(f"\n[SUCCESS] Your trading bankroll is now synchronized!")
        print(f"[INFO] You can now trade with your full account balance.")
    else:
        print(f"\n[ERROR] Failed to fix bankroll field.")
