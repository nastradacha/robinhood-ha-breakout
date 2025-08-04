#!/usr/bin/env python3
"""
Fix positions.csv - Windows compatible version
"""

import csv
from datetime import datetime
from pathlib import Path

def fix_positions():
    """Remove duplicate positions and keep only the correct one."""
    
    positions_file = Path("positions.csv")
    
    if not positions_file.exists():
        print("No positions.csv file found")
        return
    
    # Read current positions
    with open(positions_file, 'r') as f:
        reader = csv.DictReader(f)
        positions = list(reader)
    
    print(f"Found {len(positions)} positions")
    
    # Create the correct position
    correct_position = {
        'entry_time': datetime.now().isoformat(),
        'symbol': 'SPY',
        'expiry': datetime.now().strftime('%Y-%m-%d'),
        'strike': '628.0',
        'side': 'CALL',
        'contracts': '1',
        'entry_premium': '1.42'
    }
    
    # Write only the correct position
    with open(positions_file, 'w', newline='') as f:
        fieldnames = ['entry_time', 'symbol', 'expiry', 'strike', 'side', 'contracts', 'entry_premium']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(correct_position)
    
    print("[OK] Fixed positions.csv")
    print("Position: 1 SPY $628 CALL @ $1.42")
    print("Profit Target: $1.63 (15% gain)")
    print("Stop Loss: $1.06 (25% loss)")
    print()
    print("Now run: python monitor_positions.py --interval 2 --end-at 15:45 --slack-notify")

if __name__ == "__main__":
    fix_positions()
