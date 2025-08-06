#!/usr/bin/env python3
"""
Trade History Manager

Add manual trades to trade_log.csv and view complete trading history.
This helps with LLM decision making and performance analysis.
"""

import csv
from pathlib import Path
import pandas as pd


def add_manual_trades():
    """Add the manual SPY $628 CALL buy and sell to trade_log.csv."""

    print("=== ADDING MANUAL TRADES TO TRADE LOG ===")
    print()

    # Ensure logs directory exists
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    trade_log_file = logs_dir / "trade_log.csv"

    # Check if file exists and read current entries
    existing_trades = []
    if trade_log_file.exists():
        with open(trade_log_file, "r") as f:
            reader = csv.DictReader(f)
            existing_trades = list(reader)
        print(f"Found {len(existing_trades)} existing trade entries")
    else:
        print("Creating new trade_log.csv...")
        # Create with headers
        headers = [
            "timestamp",
            "symbol",
            "decision",
            "confidence",
            "reason",
            "current_price",
            "strike",
            "expiry",
            "direction",
            "quantity",
            "premium",
            "total_cost",
            "llm_tokens",
            "bankroll_before",
            "bankroll_after",
            "realized_pnl",
            "status",
        ]

        with open(trade_log_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)

    # Check if manual trades already exist
    manual_buy_exists = any(
        trade.get("timestamp", "").startswith("2025-08-04")
        and trade.get("decision") == "BUY_CALL"
        and trade.get("premium") == "1.42"
        for trade in existing_trades
    )

    manual_sell_exists = any(
        trade.get("timestamp", "").startswith("2025-08-04")
        and trade.get("decision") == "SELL_CALL"
        and trade.get("premium") == "1.83"
        for trade in existing_trades
    )

    if manual_buy_exists and manual_sell_exists:
        print("[INFO] Manual trades already exist in trade log")
        return

    # Prepare manual trade data
    buy_time = "2025-08-04T09:55:00"  # When you submitted the buy order
    sell_time = "2025-08-04T10:22:00"  # When you sold

    new_trades = []

    if not manual_buy_exists:
        # BUY trade entry
        buy_trade = {
            "timestamp": buy_time,
            "symbol": "SPY",
            "decision": "BUY_CALL",
            "confidence": "0.85",  # Manual decision confidence
            "reason": "Manual trade execution - SPY $628 CALL entry",
            "current_price": "628.67",  # From monitoring logs
            "strike": "628.0",
            "expiry": "2025-08-04",  # 0DTE
            "direction": "CALL",
            "quantity": "1",
            "premium": "1.42",
            "total_cost": "142.00",
            "llm_tokens": "0",  # Manual trade
            "bankroll_before": "500.00",
            "bankroll_after": "358.00",
            "realized_pnl": "0.00",  # Not realized yet
            "status": "SUBMITTED",
        }
        new_trades.append(buy_trade)

    if not manual_sell_exists:
        # SELL trade entry
        sell_trade = {
            "timestamp": sell_time,
            "symbol": "SPY",
            "decision": "SELL_CALL",
            "confidence": "1.00",  # Manual profit-taking decision
            "reason": "Manual profit-taking - excellent timing at +28.9% gain",
            "current_price": "629.15",  # Last monitoring reading
            "strike": "628.0",
            "expiry": "2025-08-04",
            "direction": "CALL",
            "quantity": "1",
            "premium": "1.83",
            "total_cost": "183.00",  # Proceeds
            "llm_tokens": "0",  # Manual trade
            "bankroll_before": "358.00",
            "bankroll_after": "399.00",
            "realized_pnl": "41.00",  # Profit!
            "status": "CLOSED_PROFIT",
        }
        new_trades.append(sell_trade)

    # Add new trades to log
    if new_trades:
        with open(trade_log_file, "a", newline="") as f:
            fieldnames = [
                "timestamp",
                "symbol",
                "decision",
                "confidence",
                "reason",
                "current_price",
                "strike",
                "expiry",
                "direction",
                "quantity",
                "premium",
                "total_cost",
                "llm_tokens",
                "bankroll_before",
                "bankroll_after",
                "realized_pnl",
                "status",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)

            for trade in new_trades:
                writer.writerow(trade)

        print(f"[OK] Added {len(new_trades)} manual trade(s) to trade_log.csv")

        for trade in new_trades:
            print(
                f"  {trade['decision']}: {trade['symbol']} ${trade['strike']} {trade['direction']} @ ${trade['premium']}"
            )

    print("\n[OK] Trade log is now complete and ready for LLM analysis!")


def view_trade_history():
    """Display comprehensive trade history and statistics."""

    print("\n=== TRADE HISTORY ANALYSIS ===")
    print()

    trade_log_file = Path("logs/trade_log.csv")

    if not trade_log_file.exists():
        print("No trade log found")
        return

    # Read trade data
    try:
        df = pd.read_csv(trade_log_file)
        print(f"Total entries in trade log: {len(df)}")
        print()

        # Filter for actual trades (not just analysis)
        trades = df[
            df["decision"].isin(["BUY_CALL", "BUY_PUT", "SELL_CALL", "SELL_PUT"])
        ].copy()

        if len(trades) == 0:
            print("No actual trades found in log")
            return

        print(f"Actual trades found: {len(trades)}")
        print()

        # Recent trades
        print("=== RECENT TRADES ===")
        recent_trades = trades.tail(10)
        for _, trade in recent_trades.iterrows():
            timestamp = (
                trade["timestamp"][:16] if pd.notna(trade["timestamp"]) else "N/A"
            )
            decision = trade["decision"]
            symbol = trade["symbol"]
            strike = trade["strike"]
            direction = trade["direction"]
            premium = trade["premium"]
            pnl = trade["realized_pnl"] if pd.notna(trade["realized_pnl"]) else 0
            status = trade["status"]

            pnl_str = f" (${pnl:+.2f})" if pnl != 0 else ""
            print(
                f"  {timestamp} | {decision} {symbol} ${strike} {direction} @ ${premium}{pnl_str} | {status}"
            )

        print()

        # Calculate statistics
        print("=== TRADE STATISTICS ===")

        # Closed trades (with realized P&L)
        closed_trades = trades[
            trades["realized_pnl"].notna() & (trades["realized_pnl"] != 0)
        ]

        if len(closed_trades) > 0:
            total_pnl = closed_trades["realized_pnl"].sum()
            winning_trades = len(closed_trades[closed_trades["realized_pnl"] > 0])
            losing_trades = len(closed_trades[closed_trades["realized_pnl"] < 0])
            win_rate = (
                (winning_trades / len(closed_trades)) * 100
                if len(closed_trades) > 0
                else 0
            )

            avg_win = (
                closed_trades[closed_trades["realized_pnl"] > 0]["realized_pnl"].mean()
                if winning_trades > 0
                else 0
            )
            avg_loss = (
                closed_trades[closed_trades["realized_pnl"] < 0]["realized_pnl"].mean()
                if losing_trades > 0
                else 0
            )

            print(f"Closed Trades: {len(closed_trades)}")
            print(f"Winning Trades: {winning_trades}")
            print(f"Losing Trades: {losing_trades}")
            print(f"Win Rate: {win_rate:.1f}%")
            print(f"Total P&L: ${total_pnl:.2f}")
            print(f"Average Win: ${avg_win:.2f}")
            print(f"Average Loss: ${avg_loss:.2f}")

            if avg_loss != 0:
                profit_factor = abs(avg_win / avg_loss) if avg_loss < 0 else 0
                print(f"Profit Factor: {profit_factor:.2f}")

        # Open positions
        open_positions = trades[trades["status"].isin(["SUBMITTED", "OPEN"])]
        if len(open_positions) > 0:
            print(f"\nOpen Positions: {len(open_positions)}")
            for _, pos in open_positions.iterrows():
                print(
                    f"  {pos['symbol']} ${pos['strike']} {pos['direction']} @ ${pos['premium']}"
                )

        print()

        # LLM vs Manual analysis
        manual_trades = trades[trades["llm_tokens"] == 0]
        llm_trades = trades[trades["llm_tokens"] > 0]

        print("=== DECISION MAKING ANALYSIS ===")
        print(f"Manual Trades: {len(manual_trades)}")
        print(f"LLM-Assisted Trades: {len(llm_trades)}")

        # Manual trade performance
        manual_closed = manual_trades[
            manual_trades["realized_pnl"].notna() & (manual_trades["realized_pnl"] != 0)
        ]
        if len(manual_closed) > 0:
            manual_pnl = manual_closed["realized_pnl"].sum()
            manual_wins = len(manual_closed[manual_closed["realized_pnl"] > 0])
            manual_win_rate = (manual_wins / len(manual_closed)) * 100
            print(
                f"Manual Trade Performance: ${manual_pnl:.2f} ({manual_win_rate:.1f}% win rate)"
            )

        # LLM trade performance
        llm_closed = llm_trades[
            llm_trades["realized_pnl"].notna() & (llm_trades["realized_pnl"] != 0)
        ]
        if len(llm_closed) > 0:
            llm_pnl = llm_closed["realized_pnl"].sum()
            llm_wins = len(llm_closed[llm_closed["realized_pnl"] > 0])
            llm_win_rate = (llm_wins / len(llm_closed)) * 100
            print(
                f"LLM-Assisted Performance: ${llm_pnl:.2f} ({llm_win_rate:.1f}% win rate)"
            )

    except Exception as e:
        print(f"Error reading trade history: {e}")
        # Fallback to simple CSV reading
        with open(trade_log_file, "r") as f:
            reader = csv.DictReader(f)
            trades = list(reader)
            print(f"Trade log entries: {len(trades)}")

            # Show last 5 trades
            print("\nRecent trades:")
            for trade in trades[-5:]:
                timestamp = trade.get("timestamp", "N/A")[:16]
                decision = trade.get("decision", "N/A")
                symbol = trade.get("symbol", "N/A")
                premium = trade.get("premium", "N/A")
                pnl = trade.get("realized_pnl", "0")
                print(f"  {timestamp} | {decision} {symbol} @ ${premium} (${pnl})")


def main():
    """Main function to add trades and show history."""
    add_manual_trades()
    view_trade_history()

    print()
    print("=== BENEFITS FOR LLM DECISION MAKING ===")
    print("[OK] Complete trade history helps LLM learn from past decisions")
    print("[OK] Pattern recognition improves with more trade data")
    print("[OK] Win/loss analysis guides future risk management")
    print("[OK] Manual vs automated performance comparison available")
    print("[OK] Strategy refinement based on actual results")
    print()
    print("Your excellent manual trade (+28.9%) is now part of the learning data!")


if __name__ == "__main__":
    main()
