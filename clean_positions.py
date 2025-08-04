#!/usr/bin/env python3
"""
Clean up duplicate positions and fix entry premiums
"""

import csv
from datetime import datetime
from pathlib import Path

def clean_positions():
    """Remove duplicate positions and fix entry premiums."""
    
    positions_file = Path("positions.csv")
    
    if not positions_file.exists():
        print("No positions.csv file found")
        return
    
    # Read current positions
    with open(positions_file, 'r') as f:
        reader = csv.DictReader(f)
        positions = list(reader)
    
    print(f"Found {len(positions)} positions:")
    for i, pos in enumerate(positions, 1):
        print(f"  {i}. {pos.get('symbol', 'N/A')} ${pos.get('strike', 'N/A')} {pos.get('side', 'N/A')} @ ${pos.get('entry_premium', 'N/A')}")
    
    print()
    
    # Keep only the correct position (SPY $628 CALL @ $1.42)
    correct_position = None
    for pos in positions:
        if (pos.get('symbol') == 'SPY' and 
            pos.get('strike') == '628.0' and 
            pos.get('side') == 'CALL' and 
            pos.get('entry_premium') == '1.42'):
            correct_position = pos
            break
    
    if correct_position:
        print("✅ Found correct position:")
        print(f"   SPY $628 CALL @ $1.42")
        
        # Write only the correct position
        with open(positions_file, 'w', newline='') as f:
            fieldnames = ['entry_time', 'symbol', 'expiry', 'strike', 'side', 'contracts', 'entry_premium']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(correct_position)
        
        print("✅ Cleaned positions.csv - kept only the correct position")
    else:
        print("❌ No correct position found (SPY $628 CALL @ $1.42)")
        print("Creating the correct position...")
        
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
        
        with open(positions_file, 'w', newline='') as f:
            fieldnames = ['entry_time', 'symbol', 'expiry', 'strike', 'side', 'contracts', 'entry_premium']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(correct_position)
        
        print("✅ Created correct position: SPY $628 CALL @ $1.42")
    
    print()
    print("🎯 Your position is now clean and ready for monitoring!")
    print("   Position: 1 SPY $628 CALL @ $1.42")
    print("   Profit Target: $1.63 (15% gain)")
    print("   Stop Loss: $1.06 (25% loss)")

if __name__ == "__main__":
    clean_positions()
