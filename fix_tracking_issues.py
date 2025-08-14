#!/usr/bin/env python3
"""
Comprehensive fix for position tracking and bankroll management issues.

This script addresses:
1. Position file format mismatch (wrong CSV headers)
2. BankrollManager method access issues
3. QQQ position tracking discrepancy (manual sale of 2 contracts recorded as 1)
"""

import csv
import json
from pathlib import Path
from datetime import datetime
from utils.portfolio import PortfolioManager, Position
from utils.bankroll import BankrollManager

def fix_position_files():
    """Fix position file format issues."""
    print("=== FIXING POSITION FILE FORMATS ===")
    
    # Check and fix positions_alpaca_live.csv
    positions_file = Path("positions_alpaca_live.csv")
    if positions_file.exists():
        print(f"Found {positions_file}")
        
        # Read current content
        with open(positions_file, 'r') as f:
            content = f.read().strip()
            
        print(f"Current content:\n{content}")
        
        # Check if it has the wrong format
        if "symbol,strike,option_type" in content:
            print("❌ Wrong format detected - fixing...")
            
            # Create new file with correct format
            pm = PortfolioManager("positions_alpaca_live.csv")
            print("✅ Created new positions file with correct headers")
            
            # The file is now empty and properly formatted
            positions = pm.load_positions()
            print(f"✅ Positions loaded: {len(positions)}")
        else:
            print("✅ Position file format is correct")
    else:
        print("No positions_alpaca_live.csv found - will be created when needed")

def fix_bankroll_access():
    """Fix bankroll manager access issues."""
    print("\n=== FIXING BANKROLL ACCESS ===")
    
    try:
        bm = BankrollManager('alpaca', 'live')
        
        # Test the methods that were failing
        current_balance = bm.get_current_bankroll()
        print(f"✅ Current bankroll: ${current_balance:.2f}")
        
        # Check if get_available_funds exists, if not use get_current_bankroll
        try:
            available_funds = bm.get_available_funds()
            print(f"✅ Available funds: ${available_funds:.2f}")
        except AttributeError:
            print("⚠️ get_available_funds() method not found, using get_current_bankroll()")
            available_funds = current_balance
            print(f"✅ Available funds (fallback): ${available_funds:.2f}")
            
        return bm, current_balance
        
    except Exception as e:
        print(f"❌ Bankroll manager error: {e}")
        return None, 0

def fix_qqq_position_tracking(bm, current_balance):
    """Fix the QQQ position tracking discrepancy."""
    print("\n=== FIXING QQQ POSITION TRACKING ===")
    
    if not bm:
        print("❌ Cannot fix QQQ tracking without working bankroll manager")
        return
    
    # Load positions
    pm = PortfolioManager("positions_alpaca_live.csv")
    positions = pm.load_positions()
    
    print(f"Current open positions: {len(positions)}")
    for pos in positions:
        print(f"- {pos.symbol} {pos.side} ${pos.strike} x{pos.contracts} @ ${pos.entry_premium}")
    
    # Look for QQQ position
    qqq_position = None
    for pos in positions:
        if pos.symbol == 'QQQ' and '579' in str(pos.strike):
            qqq_position = pos
            break
    
    if qqq_position:
        print(f"Found QQQ position: {qqq_position.symbol} {qqq_position.side} ${qqq_position.strike} x{qqq_position.contracts}")
        
        # Remove the position since user sold all contracts
        pm.remove_position(qqq_position)
        print("✅ Removed QQQ position from tracking")
        
        # Add missing $176 to bankroll (the second contract sold)
        try:
            # Use the record_trade method with proper parameters
            trade_details = {
                'symbol': 'QQQ',
                'action': 'SELL',
                'quantity': 1,
                'premium': 1.76,
                'total_cost': 176.00,
                'timestamp': datetime.now().isoformat(),
                'reason': 'Manual position correction - missing contract sale'
            }
            
            bm.record_trade(trade_details)
            print("✅ Added missing $176.00 to bankroll")
            
            # Update bankroll directly
            new_balance = current_balance + 176.00
            bm.update_bankroll(new_balance, "QQQ position tracking correction")
            print(f"✅ Updated bankroll to ${new_balance:.2f}")
            
        except Exception as e:
            print(f"⚠️ Could not update bankroll automatically: {e}")
            print("Manual correction needed: Add $176 to your bankroll")
        
        # Log the correction
        correction_log = Path("logs/position_corrections.csv")
        correction_log.parent.mkdir(exist_ok=True)
        
        # Create header if file doesn't exist
        if not correction_log.exists():
            with open(correction_log, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['timestamp', 'symbol', 'issue', 'correction', 'amount'])
        
        # Log the correction
        with open(correction_log, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().isoformat(),
                'QQQ',
                'Manual sale of 2 contracts recorded as 1',
                'Added missing contract sale',
                176.00
            ])
        print("✅ Logged correction to position_corrections.csv")
        
    else:
        print("⚠️ No QQQ position found to correct")

def verify_fixes():
    """Verify all fixes are working."""
    print("\n=== VERIFICATION ===")
    
    # Test position manager
    try:
        pm = PortfolioManager("positions_alpaca_live.csv")
        positions = pm.load_positions()
        print(f"✅ Position manager working: {len(positions)} positions")
        for pos in positions:
            print(f"  - {pos.symbol} {pos.side} ${pos.strike} x{pos.contracts}")
    except Exception as e:
        print(f"❌ Position manager error: {e}")
    
    # Test bankroll manager
    try:
        bm = BankrollManager('alpaca', 'live')
        balance = bm.get_current_bankroll()
        print(f"✅ Bankroll manager working: ${balance:.2f}")
    except Exception as e:
        print(f"❌ Bankroll manager error: {e}")

def main():
    """Run all fixes."""
    print("🔧 COMPREHENSIVE TRACKING SYSTEM FIX")
    print("=" * 50)
    
    # Fix position files
    fix_position_files()
    
    # Fix bankroll access
    bm, current_balance = fix_bankroll_access()
    
    # Fix QQQ position tracking
    fix_qqq_position_tracking(bm, current_balance)
    
    # Verify everything works
    verify_fixes()
    
    print("\n" + "=" * 50)
    print("🎯 FIX COMPLETE!")
    print("\nYou can now run:")
    print("python -c \"from utils.portfolio import PortfolioManager; pm = PortfolioManager('positions_alpaca_live.csv'); print('Positions:', len(pm.load_positions()))\"")
    print("python -c \"from utils.bankroll import BankrollManager; bm = BankrollManager('alpaca', 'live'); print('Bankroll:', bm.get_current_bankroll())\"")

if __name__ == "__main__":
    main()
