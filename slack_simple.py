#!/usr/bin/env python3
"""
Simplified Slack Integration for Trade Notifications

This version works with basic bot permissions and focuses on:
1. Sending trade alerts to Slack
2. Interactive confirmation prompts (primary method)
3. Manual confirmation script (backup method)

Usage:
    python slack_simple.py --test           # Test connection
    python slack_simple.py --alert "test"   # Send test alert
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from utils.slack_bot import SlackBot

logger = logging.getLogger(__name__)


class SimpleSlackNotifier:
    """Simplified Slack notifier for trade alerts."""
    
    def __init__(self):
        self.slack_bot = SlackBot()
        
        if not self.slack_bot.bot_enabled:
            raise ValueError("Slack Bot Token and Channel ID required. Check your .env file.")
        
        logger.info("Simple Slack notifier initialized")
    
    def test_connection(self) -> bool:
        """Test Slack connection."""
        logger.info("Testing Slack connection...")
        
        message = """🧪 **SLACK CONNECTION TEST**
✅ Bot Token: Working
✅ Channel Access: Working
✅ Message Delivery: Success

Your trading bot can now send notifications to this channel!"""
        
        success = self.slack_bot.send_message(message)
        
        if success:
            logger.info("[SUCCESS] Slack connection successful")
            return True
        else:
            logger.error("[ERROR] Slack connection failed")
            return False
    
    def send_trade_alert(self, trade_details: dict) -> bool:
        """Send trade alert to Slack."""
        direction = trade_details.get('direction', 'N/A')
        strike = trade_details.get('strike', 'N/A')
        premium = trade_details.get('premium', 0)
        quantity = trade_details.get('quantity', 1)
        
        message = f"""🚨 **TRADE SIGNAL DETECTED**
📊 Direction: {direction}
💰 Strike: ${strike}
💵 Expected Premium: ${premium:.2f}
📈 Quantity: {quantity} contracts

⏰ **ACTION REQUIRED**
Check your trading terminal for confirmation prompt!

💡 **Backup Options:**
• Use interactive prompt (recommended)
• Run: `python confirm_trade.py --help`"""
        
        return self.slack_bot.send_message(message)
    
    def send_heartbeat(self, message: str = None) -> bool:
        """Send heartbeat message."""
        if not message:
            message = "💓 Trading bot is running - no signals detected"
        
        return self.slack_bot.send_message(message)
    
    def send_custom_alert(self, message: str) -> bool:
        """Send custom alert message."""
        return self.slack_bot.send_message(message)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Simplified Slack Integration for Trade Notifications'
    )
    
    parser.add_argument('--test', action='store_true',
                       help='Test Slack connection')
    parser.add_argument('--alert', type=str,
                       help='Send custom alert message')
    parser.add_argument('--heartbeat', action='store_true',
                       help='Send heartbeat message')
    
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    try:
        notifier = SimpleSlackNotifier()
        
        if args.test:
            success = notifier.test_connection()
            sys.exit(0 if success else 1)
            
        elif args.alert:
            success = notifier.send_custom_alert(args.alert)
            if success:
                print("[SUCCESS] Alert sent successfully")
            else:
                print("[ERROR] Failed to send alert")
                
        elif args.heartbeat:
            success = notifier.send_heartbeat()
            if success:
                print("[SUCCESS] Heartbeat sent successfully")
            else:
                print("[ERROR] Failed to send heartbeat")
                
        else:
            print("Simple Slack Notifier - Use --help for options")
            
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        print(f"\n[ERROR] {e}")
        sys.exit(1)
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
