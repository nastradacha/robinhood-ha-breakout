#!/usr/bin/env python3
"""
Add Current IWM Positions to Position Tracking

This script helps add your current IWM positions to the positions.csv file
so the monitoring system can track them properly.
"""

import csv
import os
from datetime import datetime, date
from pathlib import Path

def add_iwm_positions():
    """Add current IWM positions to positions.csv"""
    
    # Position file path
    positions_file = "positions.csv"
    
    # Current IWM position details (based on your Alpaca screenshot)
    # You have 2 contracts of IWM250812C00223000 at $0.865 entry
    current_positions = [
        {
            "entry_time": datetime.now().isoformat(),
            "symbol": "IWM",
            "expiry": "2025-08-12",  # Today's expiry (0DTE)
            "strike": 223.0,
            "side": "CALL",  # Changed from option_type to side
            "contracts": 2,
            "entry_premium": 0.865,  # From your Alpaca screenshot
        }
    ]
    
    # Check if file exists and has header
    file_exists = Path(positions_file).exists()
    
    # CSV headers (matching what the monitoring system expects)
    headers = [
        "entry_time", "symbol", "expiry", "strike", 
        "side", "contracts", "entry_premium"
    ]
    
    print(f"Adding {len(current_positions)} IWM position(s) to {positions_file}")
    
    # Clear old positions and add new ones
    with open(positions_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        
        for position in current_positions:
            writer.writerow(position)
            print(f"Added: {position['symbol']} ${position['strike']} {position['side']} "
                  f"x{position['contracts']} @ ${position['entry_premium']}")
    
    print(f"\nSuccessfully updated {positions_file}")
    print("Position monitoring will now track your current IWM positions!")
    
    # Show current positions
    print("\nCurrent positions in file:")
    with open(positions_file, "r") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, 1):
            print(f"{i}. {row['symbol']} ${row['strike']} {row['side']} "
                  f"x{row['contracts']} @ ${row['entry_premium']} (exp: {row['expiry']})")

if __name__ == "__main__":
    print("Adding Current IWM Positions to Position Tracking")
    print("=" * 60)
    
    try:
        add_iwm_positions()
    except Exception as e:
        print(f"Error: {e}")
        print("Please check the positions.csv file manually")
