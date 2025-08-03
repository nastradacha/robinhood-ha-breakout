#!/usr/bin/env python3
"""
Test Trade Workflow - Force a Trade Signal for Demo

This script simulates a trade signal and tests the complete workflow:
1. Browser automation (login, navigate to options)
2. Trade confirmation system
3. Slack notifications
4. Portfolio/bankroll updates

Usage:
    python test_trade_workflow.py --call    # Test CALL trade
    python test_trade_workflow.py --put     # Test PUT trade
"""

import sys
import argparse
import logging
import yaml
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from utils.browser import RobinhoodBot
from utils.portfolio import PortfolioManager
from utils.bankroll import BankrollManager
from utils.slack_bot import SlackBot
from utils.trade_confirmation import TradeConfirmationManager

logger = logging.getLogger(__name__)


def load_config(config_file: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    try:
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.warning(f"Could not load config: {e}")
        return {}


def test_trade_workflow(direction: str, config: dict):
    """Test the complete trade workflow."""
    
    print(f"\n[TEST] TESTING {direction.upper()} TRADE WORKFLOW")
    print("="*50)
    
    # Initialize managers
    portfolio_manager = PortfolioManager(config.get('POSITIONS_FILE', 'positions.csv'))
    bankroll_manager = BankrollManager(
        config.get('BANKROLL_FILE', 'bankroll.json'),
        config.get('START_CAPITAL', 500.0)
    )
    slack_bot = SlackBot()
    
    # Initialize trade confirmation manager
    confirmation_manager = TradeConfirmationManager(
        portfolio_manager,
        bankroll_manager,
        slack_bot
    )
    
    # Show initial bankroll
    current_bankroll = bankroll_manager.get_current_bankroll()
    print(f"[BANKROLL] Current Bankroll: ${current_bankroll:.2f}")
    
    # Create fake trade details for testing
    trade_details = {
        'direction': direction.upper(),
        'strike': 635.0,
        'premium': 1.25,
        'quantity': 1,
        'symbol': 'SPY',
        'expiration': '2025-08-03'
    }
    
    print(f"\n[SIGNAL] SIMULATED TRADE SIGNAL:")
    print(f"   Direction: {trade_details['direction']}")
    print(f"   Strike: ${trade_details['strike']}")
    print(f"   Premium: ${trade_details['premium']:.2f}")
    print(f"   Quantity: {trade_details['quantity']}")
    
    # Send Slack alert
    if slack_bot.bot_enabled:
        print(f"\n[SLACK] Sending Slack alert...")
        alert_msg = f"""[TEST] **TEST TRADE SIGNAL**
Direction: {trade_details['direction']}
Strike: ${trade_details['strike']}
Expected Premium: ${trade_details['premium']:.2f}
Quantity: {trade_details['quantity']} contracts

**THIS IS A TEST** - Cancel when prompted!"""
        
        slack_bot.send_message(alert_msg)
        print("[SUCCESS] Slack alert sent")
    
    # Initialize browser bot
    print(f"\n[BROWSER] Initializing browser...")
    
    try:
        bot = RobinhoodBot(headless=False)
        print("[SUCCESS] Browser initialized")
        
        # Start browser and login
        print(f"\n[LOGIN] Starting browser and logging in...")
        bot.start_browser()
        print("[SUCCESS] Browser started and logged in")
        
        # Navigate to options page
        print(f"\n[OPTIONS] Navigating to SPY options...")
        bot.navigate_to_options('SPY')
        print("[SUCCESS] Navigated to options page")
        
        # Find and display ATM option
        print(f"\n[SEARCH] Finding ATM {direction.upper()} option...")
        current_price = 621.96  # Simulated current price
        option_data = bot.find_atm_option(current_price, direction.upper())
        
        if option_data:
            print(f"[SUCCESS] Found ATM option: Strike ${option_data['strike']}")
            
            # Store pending trade for confirmation
            confirmation_manager.store_pending_trade(trade_details)
            
            # This is where we would normally click the option and go to review
            print(f"\n[PAUSE] PAUSING BEFORE TRADE EXECUTION")
            print(f"   In real trading, we would now:")
            print(f"   1. Click the {direction.upper()} option at strike ${option_data['strike']}")
            print(f"   2. Set quantity to {trade_details['quantity']}")
            print(f"   3. Navigate to Review screen")
            print(f"   4. Show confirmation prompt")
            
            # Simulate the confirmation prompt
            print(f"\n[CONFIRM] SIMULATING TRADE CONFIRMATION PROMPT")
            print("="*60)
            
            # Call the interactive confirmation
            success = confirmation_manager.confirm_trade_interactive(trade_details)
            
            if success:
                print(f"\n[SUCCESS] Trade confirmation workflow completed successfully!")
            else:
                print(f"\n[CANCELLED] Trade confirmation was cancelled or failed")
                
        else:
            print(f"[ERROR] Could not find ATM {direction.upper()} option")
            
    except Exception as e:
        print(f"[ERROR] Browser test failed: {e}")
        logger.error(f"Browser test error: {e}", exc_info=True)
    
    finally:
        try:
            bot.close()
            print(f"\n[CLEANUP] Browser closed")
        except:
            pass
    
    # Show final bankroll
    final_bankroll = bankroll_manager.get_current_bankroll()
    print(f"\n[BANKROLL] Final Bankroll: ${final_bankroll:.2f}")
    
    print(f"\n[COMPLETE] WORKFLOW TEST COMPLETED")
    print("="*50)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Test Trade Workflow - Force Trade Signal for Demo'
    )
    
    parser.add_argument('--call', action='store_true',
                       help='Test CALL trade workflow')
    parser.add_argument('--put', action='store_true',
                       help='Test PUT trade workflow')
    parser.add_argument('--config', default='config.yaml',
                       help='Configuration file path')
    
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Load configuration
    config = load_config(args.config)
    
    if args.call:
        test_trade_workflow('CALL', config)
    elif args.put:
        test_trade_workflow('PUT', config)
    else:
        print("Test Trade Workflow - Use --call or --put to test")
        print("Example: python test_trade_workflow.py --call")


if __name__ == "__main__":
    main()
