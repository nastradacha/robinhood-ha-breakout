"""
Shared logging utilities for trade decisions, analytics, and centralized setup.
"""

import csv
import os
import logging
import sys
import re
from pathlib import Path
from typing import Dict


def mask_secrets(message: str) -> str:
    """
    Mask sensitive information in log messages.
    
    Args:
        message: Log message that may contain secrets
        
    Returns:
        Message with secrets masked
    """
    # Patterns for common secrets
    patterns = [
        (r'(API_KEY["\s]*[:=]["\s]*)([^"\s]{8,})', r'\1***MASKED***'),
        (r'(SECRET["\s]*[:=]["\s]*)([^"\s]{8,})', r'\1***MASKED***'),
        (r'(TOKEN["\s]*[:=]["\s]*)([^"\s]{8,})', r'\1***MASKED***'),
        (r'(PASSWORD["\s]*[:=]["\s]*)([^"\s]{8,})', r'\1***MASKED***'),
        (r'(WEBHOOK["\s]*[:=]["\s]*)([^"\s]{20,})', r'\1***MASKED***'),
        # Alpaca API keys (format: PK/SK + base64-like string)
        (r'(PK[A-Z0-9]{20,})', r'PK***MASKED***'),
        (r'(SK[A-Z0-9]{20,})', r'SK***MASKED***'),
        # Generic long alphanumeric strings that look like secrets
        (r'([A-Za-z0-9]{32,})', lambda m: m.group(1)[:4] + '***MASKED***' if len(m.group(1)) > 20 else m.group(1)),
    ]
    
    masked_message = message
    for pattern, replacement in patterns:
        if callable(replacement):
            masked_message = re.sub(pattern, replacement, masked_message)
        else:
            masked_message = re.sub(pattern, replacement, masked_message)
    
    return masked_message


class SecureMaskingFormatter(logging.Formatter):
    """Custom logging formatter that masks sensitive information."""
    
    def format(self, record):
        # Get the original formatted message
        original_message = super().format(record)
        # Mask any secrets in the message
        return mask_secrets(original_message)


def setup_logging(log_level: str = "INFO", log_file: str = "logs/app.log") -> None:
    """
    Setup comprehensive logging configuration for the system with secret masking.

    Creates both file and console logging handlers with detailed formatting.
    Automatically creates the logs directory if it doesn't exist.
    Masks sensitive information like API keys and tokens.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to the log file (default: "logs/app.log")

    Note:
        Mirrors the setup used in main.py to ensure consistency across scripts.
    """
    # Ensure log directory exists
    Path(log_file).parent.mkdir(exist_ok=True)

    # Create secure formatter that masks secrets
    secure_formatter = SecureMaskingFormatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Configure root logger (no-op if already configured)
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # Clear existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    # Add file handler with secret masking
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(secure_formatter)
    root_logger.addHandler(file_handler)
    
    # Add console handler with secret masking
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(secure_formatter)
    root_logger.addHandler(console_handler)

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
        "vix_level",
        "vix_adjustment_factor",
        "vix_regime",
    ]

    file_exists = os.path.exists(log_file)
    with open(log_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(header)

        # Map incoming trade_data to the 18-field scoped schema with VIX data
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
            trade_data.get("vix_level", ""),
            trade_data.get("vix_adjustment_factor", ""),
            trade_data.get("vix_regime", ""),
        ]

        writer.writerow(row)
