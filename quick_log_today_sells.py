#!/usr/bin/env python3
"""
Quick append of today's SELLs and cleanup of scoped positions file.

- Appends SELL trades to the broker/env-scoped trade history CSV
- Uses entry price from the scoped positions file if available; otherwise falls back to provided defaults
- Removes the sold rows from the scoped positions file

Edit the SELLS list if needed before running.
"""
from __future__ import annotations
import csv
import os
import argparse
import logging
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

from utils.llm import load_config
from utils.scoped_files import get_scoped_paths, ensure_scoped_files
from utils.logging_utils import log_trade_decision

logger = logging.getLogger(__name__)

DATE_FMT = "%Y-%m-%dT%H:%M:%S"

# Provide defaults if a matching position row is not found
SELLS = [
    {
        "symbol": "IWM",
        "option_type": "CALL",
        "strike": "221.0",
        "expiry": "2025-08-08",
        "quantity": 1,
        "sell_price": 0.84,
        "fallback_entry_price": 0.88,
    },
    {
        "symbol": "IWM",
        "option_type": "CALL",
        "strike": "220.0",
        "expiry": "2025-08-08",
        "quantity": 1,
        "sell_price": 1.38,
        "fallback_entry_price": 0.71,
    },
]

TRADE_LOG_HEADERS = [  # Kept only for legacy backup readability
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


def ensure_dirs(path: str):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def backup(path: str) -> Optional[str]:
    if not os.path.exists(path):
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base, ext = os.path.splitext(path)
    backup_path = f"{base}_backup_{ts}{ext}"
    with open(path, "r", encoding="utf-8", newline="") as src, open(
        backup_path, "w", encoding="utf-8", newline=""
    ) as dst:
        dst.write(src.read())
    return backup_path


def load_positions(positions_file: str) -> List[Dict[str, str]]:
    if not os.path.exists(positions_file):
        return []
    with open(positions_file, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def write_positions(positions_file: str, rows: List[Dict[str, str]], headers: List[str]):
    with open(positions_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for r in rows:
            writer.writerow({h: r.get(h, "") for h in headers})


def ensure_trade_log_header(_trade_log_path: str):
    # No-op now; log_trade_decision will ensure header on first write
    ensure_dirs(_trade_log_path)


def find_and_consume_position(rows: List[Dict[str, str]], symbol: str, option_type: str, strike: str, expiry: str, qty: int) -> (Optional[float], List[Dict[str, str]]):
    """Find a row matching the position and remove it (or decrement contracts). Returns (entry_price, new_rows)."""
    new_rows: List[Dict[str, str]] = []
    entry_price: Optional[float] = None
    consumed = False

    for r in rows:
        if (
            r.get("symbol") == symbol
            and r.get("side", r.get("option_type", "")) == option_type
            and str(float(r.get("strike", "0"))) == str(float(strike))
            and r.get("expiry") == expiry
            and not consumed
        ):
            # Use this row
            try:
                row_qty = int(float(r.get("contracts", r.get("quantity", "1"))))
            except Exception:
                row_qty = 1
            try:
                entry_price = float(r.get("entry_premium", r.get("entry_price", "0")))
            except Exception:
                entry_price = None

            # Decrement or remove
            remaining_qty = max(0, row_qty - qty)
            if remaining_qty > 0:
                r["contracts"] = str(remaining_qty)
                new_rows.append(r)
            # else: fully consumed, drop row
            consumed = True
        else:
            new_rows.append(r)

    return entry_price, new_rows


def append_trade_log(trade_log_file: str, sell: Dict[str, any], entry_price: float):
    qty = int(sell["quantity"])
    sell_px = float(sell["sell_price"])
    gross = round(sell_px * qty * 100, 2)
    pnl_d = round((sell_px - entry_price) * qty * 100, 2)
    pnl_p = 0.0 if entry_price == 0 else round(((sell_px - entry_price) / entry_price) * 100.0, 2)

    # Map to scoped 15-field schema and append via shared utility
    decision = f"CLOSE_{sell['option_type'].upper()}"
    trade_data = {
        "timestamp": datetime.now().isoformat(),
        "symbol": sell["symbol"],
        "decision": decision,
        "confidence": 1.0,
        "current_price": "",
        "strike": float(sell["strike"]),
        "premium": float(entry_price),  # entry premium
        "quantity": qty,
        "total_cost": entry_price * qty * 100,
        "reason": "Manual SELL logging",
        "status": "CLOSED",
        "fill_price": sell_px,  # exit premium
        "pnl_pct": pnl_p,
        "pnl_amount": pnl_d,
        "exit_reason": "",
    }

    log_trade_decision(trade_log_file, trade_data)
    print(
        f"Appended SELL: {sell['symbol']} {sell['option_type']} ${sell['strike']} {sell['expiry']} x{qty} @ ${sell_px} | P&L ${pnl_d} ({pnl_p}%)"
    )


def resolve_paths(args) -> (str, str):
    """Resolve positions and trade log paths using CLI overrides or config scoped paths."""
    cfg = {}
    try:
        cfg = load_config("config.yaml")
    except Exception:
        cfg = {}

    # Determine broker/env
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
        # Ensure trade history header exists, positions handled by owning module
        try:
            ensure_scoped_files(paths)
        except Exception:
            pass

        positions_file = args.positions_file or cfg.get("POSITIONS_FILE", paths["positions"])
        trade_log_file = args.trade_log_file or cfg.get("TRADE_LOG_FILE", paths["trade_history"])

    return positions_file, trade_log_file


def build_arg_parser():
    p = argparse.ArgumentParser(description="Quickly log today's SELLs to scoped ledgers")
    p.add_argument("--broker", choices=["robinhood", "alpaca"], help="Broker scope override")
    p.add_argument("--env", choices=["paper", "live"], help="Environment when broker=alpaca")
    p.add_argument("--positions-file", help="Explicit positions CSV path override")
    p.add_argument("--trade-log-file", help="Explicit trade history CSV path override")
    return p


def main():
    args = build_arg_parser().parse_args()
    positions_file, trade_log_file = resolve_paths(args)

    ensure_dirs(trade_log_file)
    ensure_trade_log_header(trade_log_file)

    # Backups
    tl_bak = backup(trade_log_file)
    if tl_bak:
        print(f"Backed up {trade_log_file} -> {tl_bak}")
    pos_bak = backup(positions_file)
    if pos_bak:
        print(f"Backed up {positions_file} -> {pos_bak}")

    rows = load_positions(positions_file)
    headers = [
        "entry_time",
        "symbol",
        "expiry",
        "strike",
        "side",
        "contracts",
        "entry_premium",
    ]
    if rows:
        headers = list({h for r in rows for h in r.keys()} | set(headers))

    for sell in SELLS:
        entry_price, rows = find_and_consume_position(
            rows,
            symbol=sell["symbol"],
            option_type=sell["option_type"],
            strike=sell["strike"],
            expiry=sell["expiry"],
            qty=sell["quantity"],
        )
        if entry_price is None:
            entry_price = float(sell["fallback_entry_price"])
            print(
                f"No matching open position found for {sell['symbol']} ${sell['strike']} {sell['expiry']}; using fallback entry ${entry_price:.2f}"
            )
        append_trade_log(trade_log_file, sell, entry_price)

    # Write remaining positions
    write_positions(positions_file, rows, headers)
    print(f"Updated {Path(positions_file).name} and {Path(trade_log_file).name}")


if __name__ == "__main__":
    main()
