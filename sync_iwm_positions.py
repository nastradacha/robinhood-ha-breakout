#!/usr/bin/env python3
"""
Sync IWM positions from Alpaca screenshot to tracking system.

Based on user's screenshot showing:
- IWM $229 CALL x1 @ $0.80 (+15.00%, $12.00 profit)
- IWM $230 CALL x1 @ $0.34 (+5.88%, $2.00 profit)
"""

import csv
from datetime import datetime
from pathlib import Path

def sync_iwm_positions():
    """Sync actual IWM positions to tracking system."""
    print("=== SYNCING IWM POSITIONS FROM ALPACA ===")
    
    # Define positions file
    positions_file = Path("positions_alpaca_live.csv")
    
    # Create proper CSV headers
    fieldnames = [
        "entry_time",
        "symbol", 
        "expiry",
        "strike",
        "side",
        "contracts",
        "entry_premium"
    ]
    
    # Your actual IWM positions from the screenshot
    iwm_positions = [
        {
            "entry_time": datetime.now().isoformat(),
            "symbol": "IWM",
            "expiry": "2025-08-13", 
            "strike": 229.0,
            "side": "CALL",
            "contracts": 1,
            "entry_premium": 0.80
        },
        {
            "entry_time": datetime.now().isoformat(),
            "symbol": "IWM",
            "expiry": "2025-08-13",
            "strike": 230.0, 
            "side": "CALL",
            "contracts": 1,
            "entry_premium": 0.34
        }
    ]
    
    # Write positions to CSV file
    with open(positions_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for position in iwm_positions:
            writer.writerow(position)
    
    print(f"✓ Created {positions_file} with correct format")
    print("✓ Added IWM $229 CALL x1 @ $0.80")
    print("✓ Added IWM $230 CALL x1 @ $0.34")
    
    # Verify the positions
    print("\n=== VERIFICATION ===")
    try:
        from utils.portfolio import PortfolioManager
        pm = PortfolioManager('positions_alpaca_live.csv')
        positions = pm.load_positions()
        
        print(f"Total positions: {len(positions)}")
        for pos in positions:
            print(f"- {pos.symbol} {pos.side} ${pos.strike} x{pos.contracts} @ ${pos.entry_premium}")
            
        print("\n✓ Position tracking is now synchronized!")
        
    except Exception as e:
        print(f"Error verifying positions: {e}")

if __name__ == "__main__":
    sync_iwm_positions()
