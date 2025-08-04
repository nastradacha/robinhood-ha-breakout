#!/usr/bin/env python3
"""
Create a demo position to test enhanced monitoring with Alpaca data
"""

import csv
from datetime import datetime
from utils.alpaca_client import AlpacaClient

def create_demo_position():
    """Create a realistic demo position for monitoring test."""
    
    print("Creating demo position for monitoring test...")
    
    # Get current SPY price from Alpaca
    alpaca = AlpacaClient()
    current_spy_price = alpaca.get_current_price('SPY')
    
    if not current_spy_price:
        print("Could not get current SPY price, using fallback")
        current_spy_price = 629.50
    
    print(f"Current SPY price: ${current_spy_price:.2f}")
    
    # Create ATM call option position
    strike = round(current_spy_price)  # ATM strike
    entry_price = 1.50  # Realistic entry price for 0DTE ATM call
    
    demo_position = {
        'symbol': 'SPY',
        'strike': strike,
        'option_type': 'CALL',
        'expiry': datetime.now().strftime('%Y-%m-%d'),  # 0DTE
        'quantity': 1,
        'entry_price': entry_price,
        'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # Write to positions.csv
    with open('positions.csv', 'w', newline='') as file:
        fieldnames = ['symbol', 'strike', 'option_type', 'expiry', 'quantity', 'entry_price', 'entry_time']
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(demo_position)
    
    print(f"Demo position created:")
    print(f"  SPY ${strike} CALL (0DTE)")
    print(f"  Entry Price: ${entry_price:.2f}")
    print(f"  Quantity: 1 contract")
    print()
    print("Now run: python monitor_alpaca.py")
    print("The system will monitor this position with real-time Alpaca data!")

if __name__ == "__main__":
    create_demo_position()
