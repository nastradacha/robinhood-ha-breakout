#!/usr/bin/env python3
"""
Comprehensive Trading Dashboard

Shows all important financial data including:
- Current bankroll and portfolio value
- Transaction history and P&L
- Win/loss statistics
- Risk metrics and performance analysis
- Position tracking and exposure
"""

import json
import csv
from typing import Dict, List


def load_bankroll_data() -> Dict:
    """Load current bankroll and financial data."""
    try:
        with open("bankroll.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "current_bankroll": 500.0,
            "start_capital": 500.0,
            "total_trades": 0,
            "winning_trades": 0,
            "total_pnl": 0.0,
            "peak_bankroll": 500.0,
        }
    except Exception as e:
        print(f"Error loading bankroll: {e}")
        return {}


def load_positions() -> List[Dict]:
    """Load current open positions."""
    positions = []
    try:
        with open("positions.csv", "r", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                row["quantity"] = int(row["quantity"])
                row["entry_price"] = float(row["entry_price"])
                row["strike"] = float(row["strike"])
                positions.append(row)
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"Error loading positions: {e}")

    return positions


def load_trade_history() -> List[Dict]:
    """Load trade history from CSV."""
    trades = []
    try:
        with open("logs/trade_log.csv", "r", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row.get("action") in [
                    "BUY_CALL",
                    "SELL_CALL",
                    "BUY_PUT",
                    "SELL_PUT",
                ]:
                    trades.append(row)
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"Error loading trade history: {e}")

    return trades


def calculate_portfolio_value(positions: List[Dict]) -> float:
    """Calculate current portfolio value (simplified)."""
    total_value = 0.0
    for position in positions:
        # Simplified calculation - in reality you'd get current option prices
        position_value = position["entry_price"] * position["quantity"] * 100
        total_value += position_value
    return total_value


def analyze_trades(trades: List[Dict]) -> Dict:
    """Analyze trade performance."""
    closed_trades = []
    total_pnl = 0.0
    winning_trades = 0
    losing_trades = 0

    # Group trades by position
    trade_pairs = {}

    for trade in trades:
        if (
            trade.get("status") == "CLOSED_PROFIT"
            or trade.get("status") == "CLOSED_LOSS"
        ):
            try:
                pnl = float(trade.get("pnl", 0))
                total_pnl += pnl
                closed_trades.append(trade)

                if pnl > 0:
                    winning_trades += 1
                else:
                    losing_trades += 1
            except (ValueError, TypeError):
                continue

    total_closed = len(closed_trades)
    win_rate = (winning_trades / total_closed * 100) if total_closed > 0 else 0

    return {
        "total_closed": total_closed,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "avg_win": total_pnl / winning_trades if winning_trades > 0 else 0,
        "avg_loss": 0,  # Simplified for now
        "closed_trades": closed_trades,
    }


def display_dashboard():
    """Display comprehensive trading dashboard."""
    print("=" * 60)
    print("         COMPREHENSIVE TRADING DASHBOARD")
    print("=" * 60)
    print()

    # Load all data
    bankroll_data = load_bankroll_data()
    positions = load_positions()
    trades = load_trade_history()

    # Calculate metrics
    portfolio_value = calculate_portfolio_value(positions)
    trade_analysis = analyze_trades(trades)

    # Current Financial Status
    print("=== FINANCIAL OVERVIEW ===")
    current_bankroll = bankroll_data.get("current_bankroll", 0)
    start_capital = bankroll_data.get("start_capital", 500)
    peak_bankroll = bankroll_data.get("peak_bankroll", current_bankroll)

    print(f"Current Bankroll: ${current_bankroll:,.2f}")
    print(f"Starting Capital: ${start_capital:,.2f}")
    print(f"Peak Bankroll: ${peak_bankroll:,.2f}")
    print(
        f"Total Return: ${current_bankroll - start_capital:+,.2f} ({((current_bankroll - start_capital) / start_capital * 100):+.1f}%)"
    )
    print(f"Portfolio Value: ${portfolio_value:,.2f}")
    print(f"Total Account Value: ${current_bankroll + portfolio_value:,.2f}")
    print()

    # Trading Performance
    print("=== TRADING PERFORMANCE ===")
    print(f"Total Trades: {trade_analysis['total_closed']}")
    print(f"Winning Trades: {trade_analysis['winning_trades']}")
    print(f"Losing Trades: {trade_analysis['losing_trades']}")
    print(f"Win Rate: {trade_analysis['win_rate']:.1f}%")
    print(f"Total P&L: ${trade_analysis['total_pnl']:+,.2f}")
    if trade_analysis["avg_win"] > 0:
        print(f"Average Win: ${trade_analysis['avg_win']:,.2f}")
    print()

    # Current Positions
    print("=== CURRENT POSITIONS ===")
    if positions:
        total_invested = 0
        for pos in positions:
            position_cost = pos["entry_price"] * pos["quantity"] * 100
            total_invested += position_cost
            print(
                f"  {pos['symbol']} ${pos['strike']} {pos['option_type']} x{pos['quantity']}"
            )
            print(f"    Entry: ${pos['entry_price']:.2f} | Cost: ${position_cost:,.2f}")
            print(f"    Expiry: {pos['expiry']}")

        print(f"\nTotal Invested: ${total_invested:,.2f}")
        print(f"Available Cash: ${current_bankroll:,.2f}")
        print(
            f"Buying Power Used: {(total_invested / (current_bankroll + total_invested) * 100):.1f}%"
        )
    else:
        print("  No open positions")
        print(f"  Available Cash: ${current_bankroll:,.2f}")
    print()

    # Recent Activity
    print("=== RECENT TRANSACTIONS ===")
    recent_trades = sorted(trades, key=lambda x: x.get("timestamp", ""), reverse=True)[
        :5
    ]

    if recent_trades:
        for trade in recent_trades:
            timestamp = trade.get("timestamp", "Unknown")[:16]  # YYYY-MM-DD HH:MM
            action = trade.get("action", "Unknown")
            symbol = trade.get("symbol", "Unknown")
            strike = trade.get("strike", "Unknown")
            option_type = trade.get("option_type", "Unknown")
            price = trade.get("price", "Unknown")
            status = trade.get("status", "Unknown")

            pnl_str = ""
            if trade.get("pnl"):
                try:
                    pnl = float(trade["pnl"])
                    pnl_str = f" (${pnl:+.2f})"
                except:
                    pass

            print(
                f"  {timestamp} | {action} {symbol} ${strike} {option_type} @ ${price}{pnl_str}"
            )
            print(f"    Status: {status}")
    else:
        print("  No recent transactions")
    print()

    # Risk Metrics
    print("=== RISK ANALYSIS ===")
    if positions:
        total_at_risk = sum(
            pos["entry_price"] * pos["quantity"] * 100 for pos in positions
        )
        risk_percentage = (total_at_risk / (current_bankroll + total_at_risk)) * 100
        print(
            f"Capital at Risk: ${total_at_risk:,.2f} ({risk_percentage:.1f}% of account)"
        )
    else:
        print("No capital currently at risk")

    max_drawdown = (
        start_capital - bankroll_data.get("min_bankroll", start_capital)
        if "min_bankroll" in bankroll_data
        else 0
    )
    if max_drawdown > 0:
        print(
            f"Max Drawdown: ${max_drawdown:,.2f} ({(max_drawdown / start_capital * 100):.1f}%)"
        )
    else:
        print("Max Drawdown: $0.00 (0.0%)")

    print()

    # Performance Summary
    print("=== PERFORMANCE SUMMARY ===")
    if trade_analysis["total_closed"] > 0:
        print(
            f"[OK] {trade_analysis['total_closed']} completed trades with {trade_analysis['win_rate']:.1f}% win rate"
        )
        print(f"[OK] Total profit: ${trade_analysis['total_pnl']:+,.2f}")
        print(
            f"[OK] Account growth: {((current_bankroll - start_capital) / start_capital * 100):+.1f}%"
        )
    else:
        print("[INFO] No completed trades yet")

    if positions:
        print(f"[INFO] {len(positions)} open position(s) being monitored")

    print()
    print("=" * 60)
    print("Run 'python trading_dashboard.py' anytime to see updated data")
    print("=" * 60)


if __name__ == "__main__":
    display_dashboard()
