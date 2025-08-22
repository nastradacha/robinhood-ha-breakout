#!/usr/bin/env python3
"""
Alpaca Synchronization Command-Line Tool

Standalone script for synchronizing local system state with Alpaca account data.
Handles manual trades, balance updates, and position reconciliation.

Usage:
    python sync_alpaca.py --env paper --sync-type all
    python sync_alpaca.py --env live --sync-type bankroll
    python sync_alpaca.py --env paper --check-only
"""

import argparse
import logging
import sys
from utils.alpaca_sync import AlpacaSync
from utils.logging_utils import setup_logging


def main():
    """Main synchronization command."""
    parser = argparse.ArgumentParser(description="Alpaca Data Synchronization Tool")
    parser.add_argument("--env", choices=["paper", "live"], default="paper", 
                       help="Alpaca environment (default: paper)")
    parser.add_argument("--sync-type", choices=["all", "bankroll", "positions", "transactions"], 
                       default="all", help="Type of synchronization (default: all)")
    parser.add_argument("--check-only", action="store_true", 
                       help="Check if sync needed without performing sync")
    parser.add_argument("--verbose", "-v", action="store_true", 
                       help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(log_level, "logs/sync_alpaca.log")
    logger = logging.getLogger(__name__)
    
    logger.info(f"Starting Alpaca sync for {args.env} environment")
    
    try:
        # Create sync instance
        sync = AlpacaSync(env=args.env)
        
        if args.check_only:
            # Check sync status only
            logger.info("Checking sync status...")
            sync_needed = sync.check_sync_needed()
            needs_bankroll_sync = sync_needed['bankroll']
            needs_position_sync = sync_needed['positions']
            needs_transaction_sync = sync_needed['transactions']
            # Display status
            print(f"\n=== Alpaca Sync Status ({args.env.upper()}) ===")
            print(f"Bankroll sync needed: {'YES' if needs_bankroll_sync else 'NO'}")
            print(f"Position sync needed: {'YES' if needs_position_sync else 'NO'}")
            print(f"Transaction sync needed: {'YES' if needs_transaction_sync else 'NO'}")
            
            if any([needs_bankroll_sync, needs_position_sync, needs_transaction_sync]):
                print(f"\nRecommendation: Run sync with --sync-type all")
                sys.exit(1)
            else:
                print(f"\nAll data is synchronized ")
                sys.exit(0)
        
        else:
            # Perform synchronization
            logger.info(f"Performing {args.sync_type} synchronization...")
            
            if args.sync_type == "all":
                results = sync.sync_all()
            elif args.sync_type == "bankroll":
                results = {"bankroll": sync.sync_bankroll()}
            elif args.sync_type == "positions":
                results = {"positions": sync.sync_positions()}
            elif args.sync_type == "transactions":
                results = {"transactions": sync.sync_transactions()}
            
            # Display results
            print(f"\n=== Alpaca Sync Results ({args.env.upper()}) ===")
            for component, success in results.items():
                status = "SUCCESS" if success else "FAILED"
                print(f"{component.capitalize()}: {status}")
            
            # Exit with appropriate code
            if all(results.values()):
                print(f"\nSynchronization completed successfully")
                sys.exit(0)
            else:
                print(f"\nSome synchronization operations failed")
                sys.exit(1)
    
    except KeyboardInterrupt:
        logger.info("Synchronization cancelled by user")
        sys.exit(130)
    
    except Exception as e:
        logger.error(f"Synchronization failed: {e}")
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
