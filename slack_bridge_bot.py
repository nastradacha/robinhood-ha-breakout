#!/usr/bin/env python3
"""
Slack Bot Bridge for Real-Time Trade Confirmation

This script uses your Slack Bot Token to listen for trade confirmation messages
and automatically record them in your trading system.

Usage:
    python slack_bridge_bot.py --listen    # Listen for confirmations
    python slack_bridge_bot.py --test      # Test bot connection
    python slack_bridge_bot.py --status    # Show pending trades

Slack Commands (send in your channel):
    - "filled 1.28" → Confirms trade at $1.28 premium
    - "cancelled" → Confirms trade was cancelled
    - "status" → Shows pending trade status
"""

import time
import logging
import argparse
import sys
import yaml
import os
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from utils.slack_bot import SlackBot
from utils.trade_confirmation import TradeConfirmationManager
from utils.portfolio import PortfolioManager
from utils.bankroll import BankrollManager

logger = logging.getLogger(__name__)


class SlackBridgeBot:
    """Real-time Slack bridge using Bot Token for trade confirmations."""
    
    def __init__(self, config: dict):
        self.config = config
        
        # Initialize Slack bot
        self.slack_bot = SlackBot()
        if not self.slack_bot.bot_enabled:
            raise ValueError("Slack Bot Token and Channel ID required. Check your .env file.")
        
        # Initialize managers
        self.portfolio_manager = PortfolioManager(config.get('POSITIONS_FILE', 'positions.csv'))
        self.bankroll_manager = BankrollManager(
            config.get('BANKROLL_FILE', 'bankroll.json'),
            config.get('START_CAPITAL', 500.0)
        )
        
        # Initialize trade confirmation manager
        self.confirmation_manager = TradeConfirmationManager(
            self.portfolio_manager,
            self.bankroll_manager,
            self.slack_bot
        )
        
        logger.info("Slack Bridge Bot initialized successfully")
    
    def test_connection(self) -> bool:
        """Test Slack bot connection."""
        logger.info("Testing Slack bot connection...")
        
        success = self.slack_bot.send_message("🧪 Slack Bridge Bot test - connection successful!")
        
        if success:
            logger.info("✅ Slack bot connection working")
            return True
        else:
            logger.error("❌ Slack bot connection failed")
            return False
    
    def show_pending_status(self):
        """Show status of pending trades."""
        if self.confirmation_manager.pending_trade:
            trade = self.confirmation_manager.pending_trade
            
            # Send status to Slack
            status_msg = f"""📋 **PENDING TRADE STATUS**
Direction: {trade.get('direction', 'N/A')}
Strike: ${trade.get('strike', 'N/A')}
Expected Premium: ${trade.get('premium', 'N/A'):.2f}
Quantity: {trade.get('quantity', 1)} contracts

💬 Send confirmation:
• `filled 1.28` (if submitted at $1.28)
• `cancelled` (if cancelled)"""
            
            self.slack_bot.send_message(status_msg)
            
            # Also print to console
            print("\n📋 PENDING TRADE:")
            print(f"  Direction: {trade.get('direction', 'N/A')}")
            print(f"  Strike: ${trade.get('strike', 'N/A')}")
            print(f"  Expected Premium: ${trade.get('premium', 'N/A'):.2f}")
            print(f"  Quantity: {trade.get('quantity', 1)} contracts")
        else:
            msg = "✅ No pending trades to confirm"
            self.slack_bot.send_message(msg)
            print(f"\n{msg}")
    
    def listen_for_confirmations(self, check_interval: int = 10):
        """Listen for trade confirmation messages in Slack."""
        logger.info(f"🎧 Listening for trade confirmations (checking every {check_interval}s)")
        logger.info("Send 'filled 1.28' or 'cancelled' in Slack to confirm trades")
        
        # Send startup message
        self.slack_bot.send_message("🎧 Slack Bridge Bot is now listening for trade confirmations!")
        
        last_check = datetime.now()
        
        try:
            while True:
                # Check for new messages since last check
                confirmations = self.slack_bot.check_for_trade_confirmations(
                    minutes_back=max(1, check_interval // 60 + 1)
                )
                
                for confirmation in confirmations:
                    logger.info(f"📱 Received confirmation: {confirmation}")
                    
                    # Process the confirmation
                    success = self.confirmation_manager.process_slack_message(confirmation)
                    
                    if success:
                        logger.info("✅ Trade confirmation processed successfully")
                    else:
                        logger.warning("⚠️ Could not process confirmation")
                
                # Update last check time
                last_check = datetime.now()
                
                # Wait before next check
                time.sleep(check_interval)
                
        except KeyboardInterrupt:
            logger.info("🛑 Stopping Slack bridge...")
            self.slack_bot.send_message("🛑 Slack Bridge Bot stopped")
    
    def process_single_command(self, command: str) -> bool:
        """Process a single command for testing."""
        logger.info(f"Processing command: {command}")
        return self.confirmation_manager.process_slack_message(command)


def load_config(config_file: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    try:
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.warning(f"Could not load config: {e}")
        return {}


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Slack Bot Bridge for Real-Time Trade Confirmation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python slack_bridge_bot.py --test       # Test bot connection
  python slack_bridge_bot.py --listen     # Listen for confirmations
  python slack_bridge_bot.py --status     # Show pending trades
  python slack_bridge_bot.py --confirm "filled 1.28"  # Process single command
        """
    )
    
    parser.add_argument('--test', action='store_true',
                       help='Test Slack bot connection')
    parser.add_argument('--listen', action='store_true',
                       help='Listen for trade confirmations')
    parser.add_argument('--status', action='store_true',
                       help='Show pending trade status')
    parser.add_argument('--confirm', type=str,
                       help='Process a single confirmation command')
    parser.add_argument('--interval', type=int, default=10,
                       help='Check interval in seconds (default: 10)')
    parser.add_argument('--config', default='config.yaml',
                       help='Configuration file path')
    
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        # Load configuration
        config = load_config(args.config)
        
        # Initialize bridge
        bridge = SlackBridgeBot(config)
        
        if args.test:
            success = bridge.test_connection()
            sys.exit(0 if success else 1)
            
        elif args.listen:
            bridge.listen_for_confirmations(args.interval)
            
        elif args.status:
            bridge.show_pending_status()
            
        elif args.confirm:
            success = bridge.process_single_command(args.confirm)
            if success:
                print("✅ Trade confirmation processed")
            else:
                print("❌ Trade confirmation failed")
                
        else:
            print("Slack Bot Bridge - Use --help for options")
            bridge.show_pending_status()
            
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        print(f"\n[ERROR] {e}")
        print("\nMake sure your .env file contains:")
        print("SLACK_BOT_TOKEN=xoxb-your-bot-token")
        print("SLACK_CHANNEL_ID=C1234567890")
        sys.exit(1)
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
