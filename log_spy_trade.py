#!/usr/bin/env python3
"""
Log the SPY $628 CALL trade that was submitted
"""

from datetime import datetime
from utils.portfolio import PortfolioManager, Position
from utils.bankroll import BankrollManager

def log_spy_trade():
    """Log the SPY $628 CALL trade."""
    
    print("=== LOGGING SPY $628 CALL TRADE ===")
    
    # Trade details from the system output
    symbol = "SPY"
    strike = 628.0
    side = "CALL"
    contracts = 1
    
    # You need to provide the actual fill price from Robinhood
    print(f"Trade: {contracts} {symbol} ${strike} {side}")
    print("What was your actual fill price per contract?")
    print("(Look at your Robinhood confirmation - e.g., $1.42)")
    
    entry_premium = float(input("Actual fill price: $"))
    
    # Calculate expiry (0DTE - today)
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
    
    # Record the trade (entry only, no exit yet)
    current_bankroll = bankroll_manager.get_current_bankroll()
    new_bankroll = current_bankroll - total_cost
    bankroll_manager.update_bankroll(new_bankroll)
    
    print()
    print("✅ TRADE LOGGED SUCCESSFULLY!")
    print(f"Position: {contracts} {symbol} ${strike} {side}")
    print(f"Entry Premium: ${entry_premium:.2f}")
    print(f"Total Cost: ${total_cost:.2f}")
    print(f"Bankroll: ${current_bankroll:.2f} → ${new_bankroll:.2f}")
    print(f"Position added to positions.csv")
    print()
    
    # Show monitoring instructions
    print("🎯 NEXT STEPS:")
    print("1. Monitor your position for profit target (15% = ${:.2f})".format(entry_premium * 1.15))
    print("2. Watch for stop loss (25% = ${:.2f})".format(entry_premium * 0.75))
    print("3. Plan to close by 3:45 PM ET to avoid overnight risk")
    print("4. Use the position monitoring mode when ready:")
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
