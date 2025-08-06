#!/usr/bin/env python3
"""
Trading Data Backup Utility

Creates timestamped backups of all trading data to prevent accidental loss.
Run this regularly to maintain backups of your valuable trading data.

Usage:
    python backup_trading_data.py
"""

import os
import shutil
import json
from datetime import datetime
from pathlib import Path


def backup_trading_data():
    """Create timestamped backup of all trading data."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path(f"backups/trading_data_{timestamp}")
    backup_dir.mkdir(parents=True, exist_ok=True)

    files_backed_up = []

    # Files to backup
    backup_files = [
        "logs/trade_log.csv",
        "bankroll.json",
        "positions.csv",
        "logs/monitor_alpaca.log",
        "logs/app.log",
    ]

    for file_path in backup_files:
        if os.path.exists(file_path):
            backup_path = backup_dir / Path(file_path).name
            shutil.copy2(file_path, backup_path)
            files_backed_up.append(file_path)
            print(f"Backed up: {file_path}")

    if files_backed_up:
        print(f"\nBackup created: {backup_dir}")
        print(f"Files backed up: {len(files_backed_up)}")

        # Create backup manifest
        manifest = {
            "timestamp": timestamp,
            "backup_date": datetime.now().isoformat(),
            "files": files_backed_up,
            "backup_directory": str(backup_dir),
        }

        with open(backup_dir / "backup_manifest.json", "w") as f:
            json.dump(manifest, f, indent=2)

        print("Backup completed successfully!")
    else:
        print("No trading data files found to backup")

    return str(backup_dir)


def restore_from_backup(backup_dir: str):
    """Restore trading data from a backup directory."""
    backup_path = Path(backup_dir)

    if not backup_path.exists():
        print(f"Backup directory not found: {backup_dir}")
        return False

    manifest_path = backup_path / "backup_manifest.json"
    if manifest_path.exists():
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
        print(f"Restoring from backup: {manifest['backup_date']}")

    restored_files = []

    for backup_file in backup_path.glob("*"):
        if backup_file.name == "backup_manifest.json":
            continue

        # Determine original location
        if backup_file.name == "trade_log.csv":
            original_path = "logs/trade_log.csv"
        elif backup_file.name.endswith(".log"):
            original_path = f"logs/{backup_file.name}"
        else:
            original_path = backup_file.name

        # Ensure directory exists
        Path(original_path).parent.mkdir(parents=True, exist_ok=True)

        # Restore file
        shutil.copy2(backup_file, original_path)
        restored_files.append(original_path)
        print(f"Restored: {original_path}")

    print(f"\nRestoration completed! Restored {len(restored_files)} files")
    return True


def list_backups():
    """List all available backups."""
    backups_dir = Path("backups")

    if not backups_dir.exists():
        print("No backups directory found")
        return []

    backups = []
    for backup_dir in backups_dir.glob("trading_data_*"):
        manifest_path = backup_dir / "backup_manifest.json"
        if manifest_path.exists():
            with open(manifest_path, "r") as f:
                manifest = json.load(f)
            backups.append(
                {
                    "directory": str(backup_dir),
                    "date": manifest["backup_date"],
                    "files": len(manifest["files"]),
                }
            )

    if backups:
        print("Available backups:")
        for i, backup in enumerate(
            sorted(backups, key=lambda x: x["date"], reverse=True), 1
        ):
            print(
                f"  {i}. {backup['date']} - {backup['files']} files - {backup['directory']}"
            )
    else:
        print("No backups found")

    return backups


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Trading Data Backup Utility")
    parser.add_argument("--backup", action="store_true", help="Create backup")
    parser.add_argument("--restore", type=str, help="Restore from backup directory")
    parser.add_argument("--list", action="store_true", help="List available backups")

    args = parser.parse_args()

    if args.backup:
        backup_trading_data()
    elif args.restore:
        restore_from_backup(args.restore)
    elif args.list:
        list_backups()
    else:
        print("Creating automatic backup...")
        backup_trading_data()
