#!/usr/bin/env python3
"""
Scoped File Path Management for Broker/Environment Separation (v0.9.0)

Provides utilities for managing broker and environment-specific file paths
to ensure complete separation between paper/live trading and different brokers.

Key Features:
- Scoped bankroll ledgers: bankroll_{broker}_{env}.json
- Scoped trade history: trade_history_{broker}_{env}.csv
- Scoped positions: positions_{broker}_{env}.csv
- Automatic file creation with proper headers
- Backward compatibility with existing files

Usage:
    from utils.scoped_files import get_scoped_paths, ensure_scoped_files
    
    paths = get_scoped_paths("alpaca", "paper")
    ensure_scoped_files(paths)
"""

import os
import csv
from pathlib import Path
from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)


def get_scoped_paths(broker: str, env: str) -> Dict[str, str]:
    """Get scoped file paths for a broker/environment combination.
    
    Args:
        broker: Broker name ("alpaca" or "robinhood")
        env: Environment ("paper" or "live")
        
    Returns:
        Dict with scoped file paths for bankroll, trade_history, and positions
    """
    return {
        "bankroll": f"bankroll_{broker}_{env}.json",
        "trade_history": f"logs/trade_history_{broker}_{env}.csv", 
        "positions": f"positions_{broker}_{env}.csv"
    }


def ensure_scoped_files(paths: Dict[str, str]) -> None:
    """Ensure scoped files exist with proper headers.
    
    Args:
        paths: Dict of file paths from get_scoped_paths()
    """
    # Ensure logs directory exists
    Path("logs").mkdir(exist_ok=True)
    
    # Create trade history CSV if it doesn't exist
    trade_history_path = Path(paths["trade_history"])
    if not trade_history_path.exists():
        with open(trade_history_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp', 'symbol', 'decision', 'confidence', 'current_price',
                'strike', 'premium', 'quantity', 'total_cost', 'reason', 'status',
                'fill_price', 'pnl_pct', 'pnl_amount', 'exit_reason'
            ])
        logger.info(f"Created scoped trade history: {trade_history_path}")
    
    # Create positions CSV if it doesn't exist with the expected schema
    # Header expected by tests and downstream components
    positions_path = Path(paths["positions"])
    if not positions_path.exists():
        with open(positions_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'symbol', 'strike', 'option_type', 'expiry', 'quantity', 'contracts',
                'entry_price', 'current_price', 'pnl_pct', 'pnl_amount', 'timestamp'
            ])
        logger.info(f"Created scoped positions file: {positions_path}")


def migrate_legacy_files(broker: str = "robinhood", env: str = "live") -> None:
    """Migrate existing legacy files to scoped format.
    
    Args:
        broker: Target broker for migration (default: "robinhood")
        env: Target environment for migration (default: "live")
    """
    legacy_files = {
        "bankroll.json": f"bankroll_{broker}_{env}.json",
        "logs/trade_log.csv": f"logs/trade_history_{broker}_{env}.csv",
        "positions.csv": f"positions_{broker}_{env}.csv"
    }
    
    for legacy_path, scoped_path in legacy_files.items():
        legacy_file = Path(legacy_path)
        scoped_file = Path(scoped_path)
        
        if legacy_file.exists() and not scoped_file.exists():
            # Copy legacy file to scoped location
            import shutil
            shutil.copy2(legacy_file, scoped_file)
            logger.info(f"Migrated {legacy_path} -> {scoped_path}")


def get_ledger_summary() -> Dict[str, Dict]:
    """Get summary of all existing ledger files.
    
    Returns:
        Dict mapping ledger_id to file info for all discovered ledgers
    """
    summary = {}
    
    # Find all bankroll files
    for bankroll_file in Path(".").glob("bankroll_*_*.json"):
        parts = bankroll_file.stem.split("_")
        if len(parts) >= 3:
            broker = parts[1]
            env = "_".join(parts[2:])  # Handle multi-part environments
            ledger_id = f"{broker}:{env}"
            
            paths = get_scoped_paths(broker, env)
            summary[ledger_id] = {
                "broker": broker,
                "env": env,
                "bankroll_file": str(bankroll_file),
                "trade_history_file": paths["trade_history"],
                "positions_file": paths["positions"],
                "bankroll_exists": bankroll_file.exists(),
                "trade_history_exists": Path(paths["trade_history"]).exists(),
                "positions_exists": Path(paths["positions"]).exists()
            }
    
    return summary
