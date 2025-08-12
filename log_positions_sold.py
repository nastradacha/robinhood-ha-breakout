#!/usr/bin/env python3
"""
Interactive logger for closing option positions using broker/env-scoped ledgers.

What it does:
- Reads the scoped positions CSV (header: entry_time,symbol,expiry,strike,side,contracts,entry_premium)
- Prompts you for the fill price and (optionally) overrides for strike/expiry if needed
- Computes P&L per position and appends a CLOSE_... record to the scoped trade history (15-field schema)
- Makes timestamped backups and removes the closed rows from the scoped positions file

Safe by design:
- Creates backups of positions and trade history (if exist) before writing
- No emojis (Windows console safe)

Usage:
  python log_positions_sold.py [--broker robinhood|alpaca] [--env paper|live] [--positions-file PATH] [--trade-log-file PATH]

Tip: If you sold multiple lines, just enter the corresponding fill prices when prompted.
"""

from __future__ import annotations
import csv
import os
import argparse
import logging
from datetime import datetime
from typing import List, Dict
from pathlib import Path

from utils.llm import load_config
from utils.scoped_files import get_scoped_paths, ensure_scoped_files
from utils.logging_utils import log_trade_decision

logger = logging.getLogger(__name__)

DATE_FMT = "%Y-%m-%dT%H:%M:%S"

REQUIRED_POS_HEADERS = [
    "entry_time",
    "symbol",
    "expiry",
    "strike",
    "side",
    "contracts",
    "entry_premium",
]

TRADE_LOG_HEADERS = [  # Legacy header kept only for backup readability
    "timestamp",
    "symbol",
    "expiry",
    "option_type",
    "strike",
    "action",
    "quantity",
    "price",
    "gross_amount",
    "entry_price",
    "pnl_dollars",
    "pnl_percent",
    "source",
]


def ensure_dirs(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def backup(path: str) -> str:
    if not os.path.exists(path):
        return ""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{os.path.splitext(path)[0]}_backup_{ts}{os.path.splitext(path)[1]}"
    with open(path, "r", encoding="utf-8", newline="") as src:
        with open(backup_path, "w", encoding="utf-8", newline="") as dst:
            dst.write(src.read())
    return backup_path


def read_positions(positions_file: str) -> List[Dict[str, str]]:
    if not os.path.exists(positions_file):
        raise FileNotFoundError(f"{positions_file} not found. Nothing to log.")

    with open(positions_file, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        # Minimal schema validation
        missing = [h for h in REQUIRED_POS_HEADERS if h not in headers]
        if missing:
            raise ValueError(
                f"positions file missing required columns: {missing}. Found: {headers}"
            )
        return list(reader)

def resolve_paths(args) -> (str, str):
    """Resolve positions and trade log paths using CLI overrides or config scoped paths."""
    cfg = {}
    try:
        cfg = load_config("config.yaml")
    except Exception:
        cfg = {}

    broker = (args.broker or cfg.get("BROKER") or "robinhood").lower()
    env = (
        (args.env or cfg.get("ALPACA_ENV") or "paper").lower()
        if broker == "alpaca"
        else "live"
    )

    if args.positions_file and args.trade_log_file:
        positions_file = args.positions_file
        trade_log_file = args.trade_log_file
    else:
        paths = get_scoped_paths(broker, env)
        try:
            ensure_scoped_files(paths)
        except Exception:
            pass

        positions_file = args.positions_file or cfg.get("POSITIONS_FILE", paths["positions"])
        trade_log_file = args.trade_log_file or cfg.get("TRADE_LOG_FILE", paths["trade_history"])

    return positions_file, trade_log_file


def prompt(msg: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    val = input(f"{msg}{suffix}: ").strip()
    return default if (not val and default is not None) else val


def to_float(val: str, fallback: float = 0.0) -> float:
    try:
        return float(val)
    except Exception:
        return fallback


def log_sales(positions_file: str, trade_log_file: str):
    rows = read_positions(positions_file)
    if not rows:
        print(f"No open positions found in {Path(positions_file).name}")
        return

    print("Positions to consider for closing/logging:\n")
    for i, r in enumerate(rows, start=1):
        print(
            f"[{i}] {r['symbol']} {r['side']} ${r['strike']} {r['expiry']} x{r['contracts']} @ ${r['entry_premium']} (opened {r['entry_time']})"
        )
    print()

    ensure_dirs(trade_log_file)
    tl_backup = backup(trade_log_file)
    if tl_backup:
        print(f"Backed up {trade_log_file} -> {tl_backup}")

    # We'll rebuild remaining positions after logging
    remaining: List[Dict[str, str]] = []

    for r in rows:
        sym = r.get("symbol", "")
        side = r.get("side", "")
        default_sell = "y"
        answer = prompt(
            f"Log SELL for {sym} {side} ${r.get('strike')} {r.get('expiry')} x{r.get('contracts')}? (y/n)",
            default_sell,
        ).lower()
        if answer not in ("y", "yes"):
            remaining.append(r)
            continue

        # Allow override for strike/expiry if broker shows a different strike
        strike_in = prompt("Confirm strike", r.get("strike", ""))
        expiry_in = prompt("Confirm expiry (YYYY-MM-DD)", r.get("expiry", ""))

        # Required: fill price
        while True:
            sell_str = prompt("Enter SELL fill price (e.g., 0.84)")
            sell_px = to_float(sell_str, -1)
            if sell_px > 0:
                break
            print("Invalid price, please enter a positive number like 0.84")

        # Quantity override (fix cases where CSV had 0)
        qty_str = prompt("Confirm quantity (contracts)", r.get("contracts", "1"))
        qty = int(to_float(qty_str, 1))

        # Entry price override (if positions file had wrong premium)
        entry_px_str = prompt("Confirm entry price (your fill when opened)", r.get("entry_premium", "0"))
        entry_px = to_float(entry_px_str, 0)

        gross = round(sell_px * qty * 100, 2)
        pnl_d = round((sell_px - entry_px) * qty * 100, 2)
        pnl_p = 0.0 if entry_px == 0 else round(((sell_px - entry_px) / entry_px) * 100.0, 2)

        # Map to scoped 15-field trade schema
        trade_data = {
            "timestamp": datetime.now().isoformat(),
            "symbol": sym,
            "decision": f"CLOSE_{side}",  # CALL or PUT
            "confidence": 1.0,
            "current_price": "",
            "strike": float(strike_in) if str(strike_in) else "",
            "premium": entry_px,  # entry premium
            "quantity": qty,
            "total_cost": entry_px * qty * 100,
            "reason": "Manual SELL logging",
            "status": "CLOSED",
            "fill_price": sell_px,
            "pnl_pct": pnl_p,
            "pnl_amount": pnl_d,
            "exit_reason": "",
        }
        log_trade_decision(trade_log_file, trade_data)
        print(
            f"Logged SELL: {sym} {side} ${strike_in} {expiry_in} x{qty} @ ${sell_px} | P&L ${pnl_d} ({pnl_p}%)"
        )

    # Backup and rewrite positions with only remaining
    pos_backup = backup(positions_file)
    print(f"Backed up {positions_file} -> {pos_backup}")

    with open(positions_file, "w", encoding="utf-8", newline="") as f_pos:
        writer = csv.DictWriter(f_pos, fieldnames=REQUIRED_POS_HEADERS)
        writer.writeheader()
        for r in remaining:
            writer.writerow({k: r.get(k, "") for k in REQUIRED_POS_HEADERS})

    print(f"\nDone. Remaining open positions have been kept in {Path(positions_file).name}.")


def build_arg_parser():
    p = argparse.ArgumentParser(description="Interactive logger for closing option positions (scoped ledgers)")
    p.add_argument("--broker", choices=["robinhood", "alpaca"], help="Broker scope override")
    p.add_argument("--env", choices=["paper", "live"], help="Environment when broker=alpaca")
    p.add_argument("--positions-file", help="Explicit positions CSV path override")
    p.add_argument("--trade-log-file", help="Explicit trade history CSV path override")
    return p


if __name__ == "__main__":
    print("Option Position Closing Logger")
    print("================================")
    parser = build_arg_parser()
    args = parser.parse_args()
    try:
        positions_file, trade_log_file = resolve_paths(args)
        log_sales(positions_file, trade_log_file)
    except Exception as e:
        print(f"Error: {e}")
        raise
