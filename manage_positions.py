#!/usr/bin/env python3
"""
Position Management CLI Utility

This utility helps manage the positions ledger for the robinhood-ha-breakout trading system.
It provides commands to view, add, remove, and analyze current positions.

Usage:
    python manage_positions.py list                    # List all current positions
    python manage_positions.py add                     # Add a new position manually
    python manage_positions.py remove <position_id>    # Remove a position by ID
    python manage_positions.py stats                   # Show position statistics
    python manage_positions.py clear                   # Clear all positions (with confirmation)
"""

import argparse
import sys
import yaml
from datetime import datetime
from pathlib import Path

# Add utils to path
sys.path.append(str(Path(__file__).parent / "utils"))

from portfolio import PortfolioManager, Position


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    config_file = Path(config_path)
    if not config_file.exists():
        config_file = Path(__file__).parent / config_path

    with open(config_file, "r") as f:
        config = yaml.safe_load(f)

    # Add derived fields
    config["TRADE_LOG_FILE"] = config.get("TRADE_LOG_FILE", "logs/trade_log.csv")
    config["LOG_FILE"] = config.get("LOG_FILE", "logs/app.log")

    return config


def list_positions(portfolio_manager: PortfolioManager):
    """List all current positions."""
    positions = portfolio_manager.load_positions()

    if not positions:
        print("\n[INFO] No open positions found.")
        return

    print("\n" + "=" * 80)
    print("CURRENT POSITIONS")
    print("=" * 80)
    print(
        f"{'ID':<3} {'Entry Time':<20} {'Symbol':<6} {'Side':<4} {'Strike':<8} {'Qty':<3} {'Premium':<8} {'Total':<10}"
    )
    print("-" * 80)

    for i, pos in enumerate(positions, 1):
        entry_time = datetime.fromisoformat(pos.entry_time).strftime("%m/%d %H:%M")
        total_cost = pos.entry_premium * pos.contracts * 100
        print(
            f"{i:<3} {entry_time:<20} {pos.symbol:<6} {pos.side:<4} ${pos.strike:<7} "
            f"{pos.contracts:<3} ${pos.entry_premium:<7.2f} ${total_cost:<9.2f}"
        )

    print("-" * 80)
    print(f"Total Positions: {len(positions)}")

    # Calculate total exposure (apply $100 multiplier per contract)
    total_exposure = sum(pos.entry_premium * pos.contracts * 100 for pos in positions)
    print(f"Total Exposure: ${total_exposure:.2f}")


def add_position(portfolio_manager: PortfolioManager):
    """Add a new position manually."""
    print("\n[ADD POSITION] Enter position details:")

    try:
        symbol = input("Symbol (default: SPY): ").strip().upper() or "SPY"
        side = input("Side (CALL/PUT): ").strip().upper()
        if side not in ["CALL", "PUT"]:
            print("ERROR: Side must be CALL or PUT")
            return

        strike = float(input("Strike price: $"))
        contracts = int(input("Number of contracts: "))
        premium = float(input("Entry premium per contract: $"))
        expiry = input("Expiry (default: Today): ").strip() or "Today"

        # Create position
        position = Position(
            entry_time=datetime.now().isoformat(),
            symbol=symbol,
            expiry=expiry,
            strike=strike,
            side=side,
            contracts=contracts,
            entry_premium=premium,
        )

        # Add to portfolio
        portfolio_manager.add_position(position)

        print(
            f"\n[SUCCESS] Added position: {side} ${strike} x{contracts} @ ${premium:.2f}"
        )
        print(f"Total cost: ${premium * contracts * 100:.2f}")

    except ValueError as e:
        print(f"[ERROR] Invalid input: {e}")
    except Exception as e:
        print(f"[ERROR] Failed to add position: {e}")


def remove_position(portfolio_manager: PortfolioManager, position_id: int):
    """Remove a position by ID."""
    positions = portfolio_manager.load_positions()

    if not positions:
        print("\n[ERROR] No positions to remove.")
        return

    if position_id < 1 or position_id > len(positions):
        print(f"\n[ERROR] Invalid position ID. Must be between 1 and {len(positions)}")
        return

    position = positions[position_id - 1]

    print("\n[REMOVE] Position to remove:")
    print(
        f"  {position.side} ${position.strike} x{position.contracts} @ ${position.entry_premium:.2f}"
    )

    confirm = input("Are you sure? (y/N): ").strip().lower()
    if confirm == "y":
        portfolio_manager.remove_position(position)
        print("[SUCCESS] Position removed.")
    else:
        print("[CANCELLED] Position not removed.")


def show_stats(portfolio_manager: PortfolioManager):
    """Show position statistics."""
    positions = portfolio_manager.load_positions()

    if not positions:
        print("\n[INFO] No positions for statistics.")
        return

    # Calculate statistics
    total_positions = len(positions)
    call_positions = len([p for p in positions if p.side == "CALL"])
    put_positions = len([p for p in positions if p.side == "PUT"])
    total_contracts = sum(p.contracts for p in positions)
    total_exposure = sum(p.entry_premium * p.contracts * 100 for p in positions)
    avg_premium = sum(p.entry_premium for p in positions) / total_positions

    # Group by symbol
    symbols = {}
    for pos in positions:
        if pos.symbol not in symbols:
            symbols[pos.symbol] = {"count": 0, "exposure": 0}
        symbols[pos.symbol]["count"] += 1
        symbols[pos.symbol]["exposure"] += pos.entry_premium * pos.contracts * 100

    print("\n" + "=" * 50)
    print("POSITION STATISTICS")
    print("=" * 50)
    print(f"Total Positions: {total_positions}")
    print(f"  - CALL positions: {call_positions}")
    print(f"  - PUT positions: {put_positions}")
    print(f"Total Contracts: {total_contracts}")
    print(f"Total Exposure: ${total_exposure:.2f}")
    print(f"Average Premium: ${avg_premium:.2f}")

    print("\nBy Symbol:")
    for symbol, data in symbols.items():
        print(
            f"  {symbol}: {data['count']} positions, ${data['exposure']:.2f} exposure"
        )

    print("=" * 50)


def clear_positions(portfolio_manager: PortfolioManager):
    """Clear all positions with confirmation."""
    positions = portfolio_manager.load_positions()

    if not positions:
        print("\n[INFO] No positions to clear.")
        return

    print(f"\n[WARNING] This will remove ALL {len(positions)} positions!")
    print("This action cannot be undone.")

    confirm1 = input("Type 'CLEAR' to confirm: ").strip()
    if confirm1 != "CLEAR":
        print("[CANCELLED] Positions not cleared.")
        return

    confirm2 = input("Are you absolutely sure? (yes/no): ").strip().lower()
    if confirm2 != "yes":
        print("[CANCELLED] Positions not cleared.")
        return

    # Clear positions by removing the file
    portfolio_manager.positions = []
    portfolio_manager._save_positions()

    print("[SUCCESS] All positions cleared.")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Manage positions for robinhood-ha-breakout trading system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "command",
        choices=["list", "add", "remove", "stats", "clear"],
        help="Command to execute",
    )
    parser.add_argument(
        "position_id",
        type=int,
        nargs="?",
        help="Position ID (required for remove command)",
    )

    args = parser.parse_args()

    try:
        # Load configuration
        config = load_config()

        # Initialize portfolio manager
        portfolio_manager = PortfolioManager(config["POSITIONS_FILE"])

        # Execute command
        if args.command == "list":
            list_positions(portfolio_manager)
        elif args.command == "add":
            add_position(portfolio_manager)
        elif args.command == "remove":
            if args.position_id is None:
                print("[ERROR] Position ID required for remove command")
                print("Usage: python manage_positions.py remove <position_id>")
                sys.exit(1)
            remove_position(portfolio_manager, args.position_id)
        elif args.command == "stats":
            show_stats(portfolio_manager)
        elif args.command == "clear":
            clear_positions(portfolio_manager)

    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
