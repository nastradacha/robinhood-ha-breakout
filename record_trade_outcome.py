#!/usr/bin/env python3
"""
Utility script to record trade outcomes for LLM confidence calibration.

This script allows you to manually record whether a trade was a win or loss,
which feeds into the LLM's confidence calibration system.

Usage:
    python record_trade_outcome.py --win      # Record a winning trade
    python record_trade_outcome.py --loss     # Record a losing trade
    python record_trade_outcome.py --status   # Show current win/loss statistics
"""

import argparse
import sys
import yaml
from pathlib import Path

# Add the project root to the path so we can import our utilities
sys.path.append(str(Path(__file__).parent))

from utils.bankroll import BankrollManager


def load_config(config_file: str) -> dict:
    """Load configuration from YAML file."""
    with open(config_file, 'r') as f:
        return yaml.safe_load(f)


def main():
    """Main function to record trade outcomes."""
    parser = argparse.ArgumentParser(
        description='Record trade outcomes for LLM confidence calibration',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python record_trade_outcome.py --win     # Record a winning trade
  python record_trade_outcome.py --loss    # Record a losing trade  
  python record_trade_outcome.py --status  # Show current statistics
        """
    )
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--win', action='store_true', 
                      help='Record a winning trade')
    group.add_argument('--loss', action='store_true', 
                      help='Record a losing trade')
    group.add_argument('--status', action='store_true', 
                      help='Show current win/loss statistics')
    
    parser.add_argument('--config', default='config.yaml',
                       help='Configuration file path')
    
    args = parser.parse_args()
    
    try:
        # Load configuration
        config = load_config(args.config)
        
        # Initialize bankroll manager
        bankroll_manager = BankrollManager(
            config['BANKROLL_FILE'], 
            config['START_CAPITAL']
        )
        
        if args.status:
            # Show current statistics
            win_history = bankroll_manager.get_win_history()
            stats = bankroll_manager.get_win_rate_stats()
            
            print("\n" + "="*60)
            print("LLM CONFIDENCE CALIBRATION STATISTICS")
            print("="*60)
            
            if not stats['has_history']:
                print("No trade history available yet.")
                print("LLM will use default confidence cap of 50%.")
            else:
                print(f"Recent Trade History: {win_history}")
                print(f"Total Trades: {stats['total_trades']}")
                print(f"Wins: {stats['wins']}")
                print(f"Losses: {stats['losses']}")
                print(f"Win Rate: {stats['win_rate']:.2%}")
                print(f"LLM Confidence Base: {stats['confidence_base']:.2%}")
                
                # Show visual representation
                print(f"\nVisual History (last {len(win_history)} trades):")
                visual = "".join("W" if win else "L" for win in win_history)
                print(f"  {visual}")
                print("  (W=Win, L=Loss)")
            
            print("="*60)
        
        elif args.win:
            # Record a winning trade
            bankroll_manager.record_trade_outcome(True)
            stats = bankroll_manager.get_win_rate_stats()
            print(f"\n[WIN] Recorded WINNING trade!")
            print(f"   New win rate: {stats['win_rate']:.2%} ({stats['wins']}/{stats['total_trades']} trades)")
            print(f"   LLM confidence base: {stats['confidence_base']:.2%}")
        
        elif args.loss:
            # Record a losing trade
            bankroll_manager.record_trade_outcome(False)
            stats = bankroll_manager.get_win_rate_stats()
            print(f"\n[LOSS] Recorded LOSING trade.")
            print(f"   New win rate: {stats['win_rate']:.2%} ({stats['wins']}/{stats['total_trades']} trades)")
            print(f"   LLM confidence base: {stats['confidence_base']:.2%}")
    
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
