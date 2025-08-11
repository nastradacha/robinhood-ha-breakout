"""
Shared logging utilities for trade decisions, analytics, and centralized setup.
"""

import csv
import os
import logging
import sys
from pathlib import Path
from typing import Dict


def setup_logging(log_level: str = "INFO", log_file: str = "logs/app.log") -> None:
    """
    Setup comprehensive logging configuration for the system.

    Creates both file and console logging handlers with detailed formatting.
    Automatically creates the logs directory if it doesn't exist.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to the log file (default: "logs/app.log")

    Note:
        Mirrors the setup used in main.py to ensure consistency across scripts.
    """
    # Ensure log directory exists
    Path(log_file).parent.mkdir(exist_ok=True)

    # Configure root logger (no-op if already configured)
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Fix Windows console encoding issues
    if sys.platform == "win32":
        try:
            os.system("chcp 65001 > nul 2>&1")
        except Exception:
            pass


def log_trade_decision(log_file: str, trade_data: Dict):
    """
    Log trade decision to CSV file using the scoped ledger 15-field schema.

    Args:
        log_file: Path to the trade log CSV file
        trade_data: Dictionary containing trade decision data
    """
    # Ensure directory exists
    try:
        os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
    except Exception:
        pass

    header = [
        "timestamp",
        "symbol",
        "decision",
        "confidence",
        "current_price",
        "strike",
        "premium",
        "quantity",
        "total_cost",
        "reason",
        "status",
        "fill_price",
        "pnl_pct",
        "pnl_amount",
        "exit_reason",
    ]

    file_exists = os.path.exists(log_file)
    with open(log_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(header)

        # Map incoming trade_data to the 15-field scoped schema
        row = [
            trade_data.get("timestamp", ""),
            trade_data.get("symbol", ""),
            trade_data.get("decision", ""),
            trade_data.get("confidence", ""),
            trade_data.get("current_price", ""),
            trade_data.get("strike", ""),
            trade_data.get("premium", ""),
            trade_data.get("quantity", ""),
            trade_data.get("total_cost", ""),
            trade_data.get("reason", ""),
            trade_data.get("status", ""),
            trade_data.get("fill_price", ""),
            trade_data.get("pnl_pct", ""),
            trade_data.get("pnl_amount", trade_data.get("realized_pnl", "")),
            trade_data.get("exit_reason", ""),
        ]

        writer.writerow(row)
