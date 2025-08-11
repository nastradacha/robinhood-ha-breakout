#!/usr/bin/env python3
"""
Trade History Manager

Add manual trades to trade_log.csv and view complete trading history.
This helps with LLM decision making and performance analysis.
"""

import csv
from pathlib import Path
import pandas as pd
import yaml
from datetime import datetime
from typing import Dict, Optional
from utils.scoped_files import get_scoped_paths, ensure_scoped_files
from utils.logging_utils import log_trade_decision


def get_scoped_trade_log() -> Path:
    """Resolve the broker/env-scoped trade history CSV path and ensure it exists.
    
    Uses config.yaml to determine broker and environment, falls back to
    robinhood/live when unspecified. Ensures the scoped files and logs/
    directory are created with the 15-field header.
    """
    # Load config
    config_path = Path("config.yaml")
    if not config_path.exists():
        # Also check project root relative to this file
        candidate = Path(__file__).parent / "config.yaml"
        if candidate.exists():
            config_path = candidate
    cfg: Dict = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

    broker = (cfg.get("BROKER") or "robinhood").lower()
    if broker == "alpaca":
        env = (cfg.get("ALPACA_ENV") or "paper").lower()
    else:
        env = "live"

    paths = get_scoped_paths(broker, env)
    ensure_scoped_files(paths)

    trade_log = Path(cfg.get("TRADE_LOG_FILE", paths["trade_history"]))
    trade_log.parent.mkdir(parents=True, exist_ok=True)
    return trade_log


def add_manual_trades():
    """Add the manual SPY $628 CALL buy and sell to the scoped trade history CSV."""

    print("=== ADDING MANUAL TRADES TO TRADE LOG (SCOPED) ===")
    print()

    trade_log_file = get_scoped_trade_log()

    # Load existing entries (if any)
    existing_trades = []
    if trade_log_file.exists():
        try:
            df_existing = pd.read_csv(trade_log_file)
            existing_trades = df_existing.to_dict("records")
            print(f"Found {len(existing_trades)} existing trade entries in {trade_log_file.name}")
        except Exception:
            pass

    # Check if manual trades already exist (match by date/decision/price)
    def _price_equals(v: Optional[object], target: float) -> bool:
        try:
            return abs(float(v) - target) < 1e-6
        except Exception:
            return False

    manual_buy_exists = any(
        (str(t.get("timestamp", "")).startswith("2025-08-04")
         and str(t.get("decision", "")).upper() in ("BUY_CALL", "OPEN_CALL")
         and (_price_equals(t.get("premium"), 1.42) or _price_equals(t.get("fill_price"), 1.42)))
        for t in existing_trades
    )

    manual_sell_exists = any(
        (str(t.get("timestamp", "")).startswith("2025-08-04")
         and str(t.get("decision", "")).upper() in ("SELL_CALL", "CLOSE_CALL")
         and (_price_equals(t.get("premium"), 1.83) or _price_equals(t.get("fill_price"), 1.83)))
        for t in existing_trades
    )

    if manual_buy_exists and manual_sell_exists:
        print("[INFO] Manual trades already exist in scoped trade log")
        return

    # Prepare manual trade data (scoped 15-field schema)
    buy_time = "2025-08-04T09:55:00"  # When you submitted the buy order
    sell_time = "2025-08-04T10:22:00"  # When you sold

    new_trades = []

    if not manual_buy_exists:
        buy_trade = {
            "timestamp": buy_time,
            "symbol": "SPY",
            "decision": "BUY_CALL",
            "confidence": 0.85,
            "current_price": 628.67,
            "strike": 628.0,
            "premium": 1.42,
            "quantity": 1,
            "total_cost": 142.00,
            "reason": "Manual trade execution - SPY $628 CALL entry",
            "status": "SUBMITTED",
            "fill_price": 1.42,
            "pnl_pct": "",
            "pnl_amount": "",
            "exit_reason": "",
        }
        new_trades.append(buy_trade)

    if not manual_sell_exists:
        sell_trade = {
            "timestamp": sell_time,
            "symbol": "SPY",
            "decision": "CLOSE_CALL",
            "confidence": 1.00,
            "current_price": 629.15,
            "strike": 628.0,
            "premium": 1.42,  # Entry premium for reference
            "quantity": 1,
            "total_cost": 142.00,
            "reason": "Manual profit-taking - excellent timing at +28.9% gain",
            "status": "CLOSED_PROFIT",
            "fill_price": 1.83,   # Exit premium
            "pnl_pct": "",
            "pnl_amount": 41.00,  # Profit
            "exit_reason": "",
        }
        new_trades.append(sell_trade)

    # Append using shared logging utility (ensures headers and directory)
    if new_trades:
        for t in new_trades:
            log_trade_decision(str(trade_log_file), t)

        print(f"[OK] Added {len(new_trades)} manual trade(s) to {trade_log_file.name}")

        for t in new_trades:
            price = t.get("fill_price") or t.get("premium")
            print(f"  {t['decision']}: {t['symbol']} ${t['strike']} @ ${price}")

    print("\n[OK] Trade log is now complete and ready for analytics!")


def view_trade_history():
    """Display comprehensive trade history and statistics."""

    print("\n=== TRADE HISTORY ANALYSIS ===")
    print()
    trade_log_file = get_scoped_trade_log()

    if not trade_log_file.exists():
        print("No trade log found")
        return

    # Read trade data
    try:
        df = pd.read_csv(trade_log_file)
        print(f"Total entries in {trade_log_file.name}: {len(df)}")
        print()

        # Normalize columns across legacy/new schemas
        has_new = "pnl_amount" in df.columns
        pnl_col = "pnl_amount" if has_new else ("realized_pnl" if "realized_pnl" in df.columns else None)
        if pnl_col is not None:
            df[pnl_col] = pd.to_numeric(df[pnl_col], errors="coerce").fillna(0.0)
        if "strike" in df.columns:
            df["strike"] = pd.to_numeric(df["strike"], errors="coerce")
        if "premium" in df.columns:
            df["premium"] = pd.to_numeric(df["premium"], errors="coerce")
        if "fill_price" in df.columns:
            df["fill_price"] = pd.to_numeric(df["fill_price"], errors="coerce")

        # Filter to likely trade entries (exclude NO_TRADE)
        trades = df[df["decision"].astype(str).str.upper() != "NO_TRADE"].copy()
        if len(trades) == 0:
            print("No actual trades found in log")
            return

        print(f"Actual trades found: {len(trades)}")
        print()

        # Recent trades
        print("=== RECENT TRADES ===")
        recent_trades = trades.tail(10)
        for _, trade in recent_trades.iterrows():
            timestamp = (str(trade.get("timestamp", ""))[:16] or "N/A")
            decision = trade.get("decision", "")
            symbol = trade.get("symbol", "")
            strike = trade.get("strike", "")
            price = trade.get("fill_price") if pd.notna(trade.get("fill_price")) else trade.get("premium", "")
            pnl = 0.0
            if pnl_col is not None and pd.notna(trade.get(pnl_col)):
                pnl = float(trade.get(pnl_col))
            status = trade.get("status", "")

            pnl_str = f" (${pnl:+.2f})" if pnl != 0 else ""
            print(f"  {timestamp} | {decision} {symbol} ${strike} @ ${price}{pnl_str} | {status}")

        print()

        # Calculate statistics
        print("=== TRADE STATISTICS ===")

        # Closed trades (with realized P&L in either schema)
        if pnl_col is not None:
            closed_trades = trades[trades[pnl_col] != 0]
        else:
            closed_trades = trades.iloc[0:0]

        if len(closed_trades) > 0:
            total_pnl = float(closed_trades[pnl_col].sum()) if pnl_col else 0.0
            winning_trades = int((closed_trades[pnl_col] > 0).sum()) if pnl_col else 0
            losing_trades = int((closed_trades[pnl_col] < 0).sum()) if pnl_col else 0
            win_rate = (winning_trades / len(closed_trades) * 100.0) if len(closed_trades) > 0 else 0.0

            avg_win = float(closed_trades[closed_trades[pnl_col] > 0][pnl_col].mean()) if winning_trades > 0 else 0.0
            avg_loss = float(closed_trades[closed_trades[pnl_col] < 0][pnl_col].mean()) if losing_trades > 0 else 0.0

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

        # Open positions (simple view by status)
        if "status" in trades.columns:
            open_positions = trades[trades["status"].isin(["SUBMITTED", "OPEN"])].copy()
        else:
            open_positions = trades.iloc[0:0]
        if len(open_positions) > 0:
            print(f"\nOpen Positions: {len(open_positions)}")
            for _, pos in open_positions.iterrows():
                symbol = pos.get("symbol", "")
                strike = pos.get("strike", "")
                price = pos.get("premium", "")
                print(f"  {symbol} ${strike} @ ${price}")

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
                premium = trade.get("fill_price") or trade.get("premium", "N/A")
                pnl = trade.get("pnl_amount") or trade.get("realized_pnl", "0")
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
