#!/usr/bin/env python3
"""
Slack Bridge for Remote Trade Confirmation

This script allows you to confirm trades via Slack messages when away from your PC.
Run this in the background to listen for confirmation messages.

Usage:
    python slack_bridge.py

Slack Commands:
    - "filled 1.28" → Confirms trade at $1.28 premium
    - "cancelled" → Confirms trade was cancelled
    - "status" → Shows pending trade status
"""

import time
import logging
import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from utils.trade_confirmation import TradeConfirmationManager
from utils.portfolio import PortfolioManager
from utils.bankroll import BankrollManager
from utils.slack import SlackNotifier

logger = logging.getLogger(__name__)


class SlackBridge:
    """Bridge for processing Slack trade confirmations."""
    
    def __init__(self, config: dict):
        self.config = config
        
        # Initialize managers
        self.portfolio_manager = PortfolioManager(config.get('POSITIONS_FILE', 'positions.csv'))
        self.bankroll_manager = BankrollManager(
            config.get('BANKROLL_FILE', 'bankroll.json'),
            config.get('START_CAPITAL', 500.0)
        )
        
        # Initialize Slack notifier if available
        try:
            self.slack_notifier = SlackNotifier()
            logger.info("Slack notifier initialized")
        except Exception as e:
            logger.warning(f"Slack notifier not available: {e}")
            self.slack_notifier = None
        
        # Initialize trade confirmation manager
        self.confirmation_manager = TradeConfirmationManager(
            self.portfolio_manager,
            self.bankroll_manager,
            self.slack_notifier
        )
    
    def process_manual_command(self, command: str) -> bool:
        """Process a manual command for testing."""
        return self.confirmation_manager.process_slack_message(command)
    
    def show_pending_status(self):
        """Show status of pending trades."""
        if self.confirmation_manager.pending_trade:
            trade = self.confirmation_manager.pending_trade
            print("\n📋 PENDING TRADE:")
            print(f"  Direction: {trade.get('direction', 'N/A')}")
            print(f"  Strike: ${trade.get('strike', 'N/A')}")
            print(f"  Expected Premium: ${trade.get('premium', 'N/A'):.2f}")
            print(f"  Quantity: {trade.get('quantity', 1)} contracts")
            print("\n💬 Send Slack message to confirm:")
            print("  • 'filled 1.28' (if submitted at $1.28)")
            print("  • 'cancelled' (if cancelled)")
        else:
            print("\n✅ No pending trades to confirm")
    
    def run_interactive_mode(self):
        """Run in interactive mode for testing."""
        print("\n🌉 Slack Bridge - Interactive Mode")
        print("=" * 50)
        print("Commands:")
        print("  • 'filled X.XX' - Confirm trade at premium")
        print("  • 'cancelled' - Confirm trade cancelled")
        print("  • 'status' - Show pending trades")
        print("  • 'quit' - Exit")
        print("=" * 50)
        
        while True:
            try:
                command = input("\nSlack Bridge> ").strip()
                
                if command.lower() in ['quit', 'exit', 'q']:
                    break
                elif command.lower() == 'status':
                    self.show_pending_status()
                elif command:
                    success = self.process_manual_command(command)
                    if success:
                        print("✅ Command processed successfully")
                    else:
                        print("❌ Command failed or not recognized")
                        
            except KeyboardInterrupt:
                break
        
        print("\n👋 Slack Bridge stopped")


def load_config(config_file: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    try:
        import yaml
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.warning(f"Could not load config: {e}")
        return {}


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Slack Bridge for Remote Trade Confirmation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python slack_bridge.py --interactive    # Test mode with manual commands
  python slack_bridge.py --status         # Show pending trades
  python slack_bridge.py --confirm "filled 1.28"  # Process single command
        """
    )
    
    parser.add_argument('--interactive', action='store_true',
                       help='Run in interactive test mode')
    parser.add_argument('--status', action='store_true',
                       help='Show pending trade status')
    parser.add_argument('--confirm', type=str,
                       help='Process a single confirmation command')
    parser.add_argument('--config', default='config.yaml',
                       help='Configuration file path')
    
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Load configuration
    config = load_config(args.config)
    
    # Initialize bridge
    bridge = SlackBridge(config)
    
    if args.status:
        bridge.show_pending_status()
    elif args.confirm:
        success = bridge.process_manual_command(args.confirm)
        if success:
            print("✅ Trade confirmation processed")
        else:
            print("❌ Trade confirmation failed")
    elif args.interactive:
        bridge.run_interactive_mode()
    else:
        print("Slack Bridge - Use --help for options")
        bridge.show_pending_status()


if __name__ == "__main__":
    main()
