#!/usr/bin/env python3
"""
Cleanup Obsolete Files - Robinhood HA Breakout v1.0.0

This script safely removes obsolete test files, demos, and temporary files
that are no longer needed after the Alpaca Options Trading Integration completion.

Run with --dry-run to see what would be deleted without actually deleting.
"""

import os
import sys
import shutil
from pathlib import Path

# Files and patterns to delete
OBSOLETE_FILES = [
    # Test files (development complete)
    "test_alpaca_options_e2e.py",
    "test_automatic_charts.py", 
    "test_browser_e2e_demo.py",
    "test_browser_version_pin.py",
    "test_chrome_basic.py",
    "test_chrome_fixed.py",
    "test_e2e_simple.py",
    "test_e2e_workflow.py",
    "test_enhanced_chart_clarity.py",
    "test_enhanced_slack_charts.py",
    "test_full_e2e_with_browser.py",
    "test_full_trading_workflow.py",
    "test_llm_feature_rules.py",
    "test_paper_trade.py",
    "test_production_simulation.py",
    "test_slack_simple.py",
    "test_slack_ux_demo.py",
    "test_webhook_charts.py",
    
    # Demo files (no longer needed)
    "demo_chrome_stability.py",
    "demo_llm_payload_comparison.py",
    
    # Test data files
    "test_trade_log.csv",
    
    # Old backup files
    "bankroll_backup_20250807_124352.json",
    "positions_backup_20250808_112739.csv",
    "positions_backup_20250808_122729.csv",
    "trade_log_backup_20250808_104005.csv",
]

OBSOLETE_LOG_FILES = [
    "logs/test_atm_options.png",
    "logs/test_auto_options_page.png", 
    "logs/test_auto_review_screen.png",
    "logs/test_chrome_fixed.log",
    "logs/test_e2e_simple.log",
    "logs/test_e2e_workflow.log",
    "logs/test_enhanced_chart_clarity.log",
    "logs/test_full_trading_workflow.log",
    "logs/test_options_navigation.png",
    "logs/trade_log.csv.repaired",
    "logs/trade_log_backup_20250808_112739.csv",
]

# Cache files to clean
CACHE_PATTERNS = [
    "__pycache__/test_*.cpython-*.pyc",
]

def cleanup_files(dry_run=False):
    """Clean up obsolete files."""
    project_root = Path(__file__).parent
    deleted_count = 0
    total_size = 0
    
    print("ROBINHOOD HA BREAKOUT - OBSOLETE FILE CLEANUP")
    print("=" * 50)
    
    if dry_run:
        print("DRY RUN MODE - No files will be deleted")
        print()
    
    # Clean up main directory files
    print("Cleaning main directory...")
    for file_name in OBSOLETE_FILES:
        file_path = project_root / file_name
        if file_path.exists():
            size = file_path.stat().st_size
            total_size += size
            print(f"  {'[DRY RUN] ' if dry_run else ''}DELETE: {file_name} ({size:,} bytes)")
            if not dry_run:
                file_path.unlink()
                deleted_count += 1
        else:
            print(f"  SKIP: {file_name} (not found)")
    
    # Clean up log files
    print("\nCleaning log files...")
    for file_name in OBSOLETE_LOG_FILES:
        file_path = project_root / file_name
        if file_path.exists():
            size = file_path.stat().st_size
            total_size += size
            print(f"  {'[DRY RUN] ' if dry_run else ''}DELETE: {file_name} ({size:,} bytes)")
            if not dry_run:
                file_path.unlink()
                deleted_count += 1
        else:
            print(f"  SKIP: {file_name} (not found)")
    
    # Clean up cache files
    print("\nCleaning cache files...")
    cache_dir = project_root / "__pycache__"
    if cache_dir.exists():
        for cache_file in cache_dir.glob("test_*.cpython-*.pyc"):
            size = cache_file.stat().st_size
            total_size += size
            print(f"  {'[DRY RUN] ' if dry_run else ''}DELETE: {cache_file.name} ({size:,} bytes)")
            if not dry_run:
                cache_file.unlink()
                deleted_count += 1
    
    print("\n" + "=" * 50)
    if dry_run:
        print(f"SUMMARY: Would delete {len(OBSOLETE_FILES + OBSOLETE_LOG_FILES)} files")
        print(f"STORAGE: Would free up {total_size:,} bytes ({total_size/1024/1024:.1f} MB)")
    else:
        print(f"SUCCESS: Deleted {deleted_count} obsolete files")
        print(f"STORAGE: Freed up {total_size:,} bytes ({total_size/1024/1024:.1f} MB)")
    
    print("\nCleanup complete! Repository is now production-ready.")

def main():
    """Main entry point."""
    dry_run = "--dry-run" in sys.argv
    
    if dry_run:
        print("Running in DRY RUN mode...")
    else:
        response = input("⚠️  This will permanently delete obsolete files. Continue? (y/N): ")
        if response.lower() != 'y':
            print("❌ Cleanup cancelled.")
            return
    
    cleanup_files(dry_run=dry_run)

if __name__ == "__main__":
    main()
