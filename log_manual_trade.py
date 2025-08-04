#!/usr/bin/env python3
"""
Manual Trade Logging Script

Use this to manually log trades when the automated confirmation workflow fails.
"""

import sys
from datetime import datetime
from utils.portfolio import PortfolioManager, Position
from utils.bankroll import BankrollManager

def log_trade():
    """Log a manual trade entry."""
    
    print("=== MANUAL TRADE LOGGING ===")
    print()
    
    # Get trade details
    symbol = input("Symbol (e.g., SPY): ").strip().upper() or "SPY"
    strike = float(input("Strike price (e.g., 628.0): ").strip())
    side = input("Side (CALL/PUT): ").strip().upper()
    contracts = int(input("Number of contracts (e.g., 1): ").strip() or "1")
    
    # Get actual fill price
    while True:
        try:
            entry_premium = float(input("Actual fill price per contract (e.g., 1.42): ").strip())
            break
        except ValueError:
            print("Please enter a valid price (e.g., 1.42)")
    
    # Calculate expiry (assume today for 0DTE)
    expiry = datetime.now().strftime("%Y-%m-%d")
    
    # Create position
    position = Position(
        entry_time=datetime.now().isoformat(),
        symbol=symbol,
        expiry=expiry,
        strike=strike,
        side=side,
        contracts=contracts,
        entry_premium=entry_premium
    )
    
    # Add to portfolio
    portfolio_manager = PortfolioManager("positions.csv")
    portfolio_manager.add_position(position)
    
    # Update bankroll
    bankroll_manager = BankrollManager("bankroll.json", 500.0)
    total_cost = entry_premium * contracts * 100  # Options are $100 per contract
    bankroll_manager.record_trade(
        symbol=symbol,
        quantity=contracts,
        entry_price=entry_premium,
        exit_price=None,  # Still open
        trade_type=side
    )
    
    print()
    print("✅ TRADE LOGGED SUCCESSFULLY!")
    print(f"Position: {contracts} {symbol} ${strike} {side}")
    print(f"Entry Premium: ${entry_premium:.2f}")
    print(f"Total Cost: ${total_cost:.2f}")
    print(f"Added to positions.csv")
    print()
    
    # Show current positions
    positions = portfolio_manager.load_positions()
    print(f"Current open positions: {len(positions)}")
    for pos in positions:
        print(f"  - {pos.contracts} {pos.symbol} ${pos.strike} {pos.side} @ ${pos.entry_premium:.2f}")

if __name__ == "__main__":
    try:
        log_trade()
    except KeyboardInterrupt:
        print("\nCancelled by user")
    except Exception as e:
        print(f"Error: {e}")
