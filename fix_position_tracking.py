#!/usr/bin/env python3
"""
Manual Position Tracking Correction Tool

This tool fixes position tracking discrepancies when manual trades
are executed but not properly recorded by the system.
"""

import os
import sys
import json
import csv
from datetime import datetime
from typing import Dict, List

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.portfolio import PortfolioManager
from utils.bankroll import BankrollManager
from utils.logging_utils import setup_logging

setup_logging(log_level="INFO", log_file="logs/position_fix.log")

def fix_qqq_position_tracking():
    """Fix the QQQ position tracking discrepancy."""
    print("=== POSITION TRACKING CORRECTION ===")
    print()
    
    # Initialize managers
    pm = PortfolioManager()
    bm = BankrollManager('alpaca', 'live')
    
    print("Current position status:")
    positions = pm.get_open_positions()
    for pos in positions:
        print(f"- {pos}")
    
    print(f"\nCurrent bankroll: ${bm.get_current_balance():.2f}")
    
    # Correction details
    print("\n=== CORRECTION NEEDED ===")
    print("Issue: You manually sold 2 QQQ contracts, but system only recorded 1")
    print("Actual trade: SELL 2 QQQ $579 CALL @ $1.76 each")
    print("System recorded: SELL 1 QQQ $579 CALL @ $1.76")
    print("Missing: 1 additional contract sale worth $176.00")
    
    # Ask for confirmation
    confirm = input("\nApply correction? (y/N): ").strip().lower()
    if confirm != 'y':
        print("Correction cancelled.")
        return
    
    # Apply correction
    print("\n=== APPLYING CORRECTION ===")
    
    # 1. Remove the remaining QQQ position (since you sold all 2 contracts)
    try:
        # Find QQQ position
        qqq_position = None
        for pos in positions:
            if 'QQQ' in str(pos) and '579' in str(pos):
                qqq_position = pos
                break
        
        if qqq_position:
            print(f"Removing remaining QQQ position: {qqq_position}")
            pm.close_position(qqq_position.symbol, qqq_position.strike, qqq_position.expiry)
            print("✅ QQQ position removed from tracking")
        else:
            print("⚠️ No QQQ position found to remove")
    except Exception as e:
        print(f"❌ Error removing position: {e}")
    
    # 2. Add the missing $176 to bankroll
    try:
        current_balance = bm.get_current_balance()
        corrected_balance = current_balance + 176.00
        
        # Record the correction in trade history
        correction_record = {
            'timestamp': datetime.now().isoformat(),
            'symbol': 'QQQ',
            'action': 'CORRECTION',
            'quantity': 1,  # The missing contract
            'price': 1.76,
            'total': 176.00,
            'reason': 'Manual sale not recorded by system'
        }
        
        # Update bankroll
        bm.record_trade(
            symbol='QQQ',
            action='SELL',
            quantity=1,
            price=1.76,
            total_cost=176.00
        )
        
        print(f"✅ Added missing $176.00 to bankroll")
        print(f"Previous balance: ${current_balance:.2f}")
        print(f"Corrected balance: ${bm.get_current_balance():.2f}")
        
    except Exception as e:
        print(f"❌ Error updating bankroll: {e}")
    
    # 3. Log the correction
    try:
        with open('logs/position_corrections.csv', 'a', newline='') as f:
            writer = csv.writer(f)
            # Write header if file is new
            if f.tell() == 0:
                writer.writerow(['timestamp', 'symbol', 'issue', 'correction', 'amount'])
            
            writer.writerow([
                datetime.now().isoformat(),
                'QQQ',
                'Manual sale of 2 contracts recorded as 1',
                'Added missing contract sale',
                176.00
            ])
        
        print("✅ Correction logged to position_corrections.csv")
        
    except Exception as e:
        print(f"❌ Error logging correction: {e}")
    
    print("\n=== CORRECTION COMPLETE ===")
    print("Your position tracking should now be accurate!")
    print(f"Final bankroll: ${bm.get_current_balance():.2f}")
    
    # Show updated positions
    print("\nUpdated positions:")
    updated_positions = pm.get_open_positions()
    if updated_positions:
        for pos in updated_positions:
            print(f"- {pos}")
    else:
        print("- No open positions")

if __name__ == "__main__":
    fix_qqq_position_tracking()
