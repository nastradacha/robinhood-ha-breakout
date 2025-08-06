"""
Shared logging utilities for trade decisions and analytics.
"""

import csv
from typing import Dict


def log_trade_decision(log_file: str, trade_data: Dict):
    """
    Log trade decision to CSV file with correct 12-field format.

    Args:
        log_file: Path to the trade log CSV file
        trade_data: Dictionary containing trade decision data
    """
    with open(log_file, "a", newline="") as f:
        writer = csv.writer(f)
        # Write 12 fields to match CSV header: timestamp,symbol,option_type,strike,expiry,action,quantity,price,total_cost,reason,pnl,pnl_pct
        writer.writerow(
            [
                trade_data.get("timestamp", ""),
                trade_data.get("symbol", ""),
                trade_data.get(
                    "option_type", trade_data.get("decision", "")
                ),  # Map decision to option_type
                trade_data.get("strike", ""),
                trade_data.get("expiry", ""),
                trade_data.get(
                    "action", trade_data.get("direction", "")
                ),  # Map direction to action
                trade_data.get("quantity", ""),
                trade_data.get(
                    "price", trade_data.get("premium", "")
                ),  # Map premium to price
                trade_data.get("total_cost", ""),
                trade_data.get("reason", ""),
                trade_data.get(
                    "pnl", trade_data.get("realized_pnl", "")
                ),  # Map realized_pnl to pnl
                trade_data.get("pnl_pct", ""),  # pnl_pct field
            ]
        )
