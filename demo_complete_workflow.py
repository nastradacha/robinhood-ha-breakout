#!/usr/bin/env python3
"""
Complete Trading Workflow Demo

This script demonstrates the complete end-to-end trading workflow:
1. Login to Robinhood
2. Navigate to SPY options
3. Find and select ATM option
4. Set quantity and navigate to review
5. Wait for your manual review and decision
6. Record the outcome with confirmation system

Usage:
    python demo_complete_workflow.py --call    # Demo CALL trade
    python demo_complete_workflow.py --put     # Demo PUT trade
"""

import time
import sys
import os
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


def demo_complete_workflow(direction: str, config: dict):
    """Demo the complete trading workflow from login to trade confirmation."""
    
    print(f"\n[DEMO] COMPLETE {direction.upper()} TRADING WORKFLOW")
    print("="*70)
    print("This demo shows the complete end-to-end trading process:")
    print("1. Login to Robinhood")
    print("2. Navigate to SPY options")
    print("3. Find and select ATM option")
    print("4. Set quantity and go to review")
    print("5. Wait for your manual decision")
    print("6. Record the outcome")
    print("="*70)
    
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
    print(f"\n[BANKROLL] Current Bankroll: ${current_bankroll:.2f}")
    
    # Check credentials
    rh_user = os.getenv('RH_USER')
    rh_pass = os.getenv('RH_PASS')
    
    if not rh_user or not rh_pass:
        print(f"\n[ERROR] Missing credentials in .env file")
        return
    
    # Clear existing cookies to force fresh login
    cookie_path = Path("robin_cookies_selenium.json")
    if cookie_path.exists():
        print(f"\n[SETUP] Clearing existing cookies to show complete login process...")
        cookie_path.unlink()
        print("[SUCCESS] Cookies cleared - will perform fresh login")
    
    try:
        # Initialize browser
        print(f"\n[STEP 1] Initializing browser...")
        bot = RobinhoodBot(headless=False)
        print("[SUCCESS] Browser initialized")
        
        # Start browser and login
        print(f"\n[STEP 2] Starting browser and performing fresh login...")
        bot.start_browser()
        
        # Always do fresh login since we cleared cookies
        print("         Performing fresh login with credentials...")
        print("         Watch the browser for login process")
        login_success = bot.login(rh_user, rh_pass)
        
        if not login_success:
            print("[ERROR] Login failed - cannot continue")
            return
        
        print("[SUCCESS] Fresh login completed successfully")
        
        # Navigate to SPY options
        print(f"\n[STEP 3] Navigating to SPY options...")
        bot.navigate_to_options('SPY')
        print("[SUCCESS] Navigated to SPY options page")
        
        # Pause to show options page
        print(f"\n[PAUSE] Pausing 5 seconds - observe SPY options chain")
        time.sleep(5)
        
        # Find ATM option
        print(f"\n[STEP 4] Finding ATM {direction.upper()} option...")
        current_price = 621.96  # Simulated current SPY price
        option_data = bot.find_atm_option(current_price, direction.upper())
        
        if not option_data:
            print(f"[ERROR] Could not find ATM {direction.upper()} option")
            print("        This may be due to weekend/after-hours limitations")
            print("        During market hours, options would be available")
            
            # Show what we would do
            print(f"\n[SIMULATION] In live trading, we would:")
            print(f"             1. Find ATM {direction.upper()} option near ${current_price}")
            print(f"             2. Click the option to select it")
            print(f"             3. Set quantity to 1 contract")
            print(f"             4. Navigate to review screen")
            print(f"             5. Wait for your manual decision")
            
            # Simulate the trade details
            trade_details = {
                'direction': direction.upper(),
                'strike': round(current_price),  # Round to nearest dollar
                'premium': 1.25,  # Estimated premium
                'quantity': 1,
                'symbol': 'SPY',
                'expiration': '2025-08-03'
            }
            
            # Send Slack alert
            if slack_bot.bot_enabled:
                print(f"\n[SLACK] Sending trade alert...")
                alert_msg = f"""🚨 **DEMO TRADE SIGNAL**
📊 Direction: {trade_details['direction']}
💰 Strike: ${trade_details['strike']}
💵 Expected Premium: ${trade_details['premium']:.2f}
📈 Quantity: {trade_details['quantity']} contracts

⚠️ **THIS IS A DEMO** - Practice the confirmation workflow!"""
                
                slack_bot.send_message(alert_msg)
                print("[SUCCESS] Slack alert sent")
            
            # Store pending trade and show confirmation
            confirmation_manager.store_pending_trade(trade_details)
            
            print(f"\n[STEP 5] SIMULATED TRADE CONFIRMATION")
            print("="*60)
            print("In live trading, you would now:")
            print("1. Review the trade details on Robinhood")
            print("2. Decide to SUBMIT or CANCEL")
            print("3. Complete the confirmation process below")
            print("="*60)
            
            # Call the interactive confirmation
            success = confirmation_manager.confirm_trade_interactive(trade_details)
            
            if success:
                print(f"\n[SUCCESS] Demo workflow completed successfully!")
                print("          Your decision was recorded properly")
            else:
                print(f"\n[CANCELLED] Demo workflow cancelled")
            
            return
        
        # If we found an actual option (during market hours)
        print(f"[SUCCESS] Found ATM option: Strike ${option_data['strike']}")
        
        # Create trade details
        trade_details = {
            'direction': direction.upper(),
            'strike': option_data['strike'],
            'premium': 1.25,  # Will be updated with actual premium
            'quantity': 1,
            'symbol': 'SPY',
            'expiration': '2025-08-03'  # Will be updated with actual expiration
        }
        
        # Send Slack alert
        if slack_bot.bot_enabled:
            print(f"\n[SLACK] Sending trade alert...")
            alert_msg = f"""🚨 **LIVE DEMO TRADE SIGNAL**
📊 Direction: {trade_details['direction']}
💰 Strike: ${trade_details['strike']}
💵 Expected Premium: ${trade_details['premium']:.2f}
📈 Quantity: {trade_details['quantity']} contracts

⚠️ **THIS IS A DEMO** - You can practice the real workflow!"""
            
            slack_bot.send_message(alert_msg)
            print("[SUCCESS] Slack alert sent")
        
        # Store pending trade
        confirmation_manager.store_pending_trade(trade_details)
        
        print(f"\n[STEP 5] Clicking option and setting up trade...")
        print("         Watch the browser as it:")
        print("         1. Clicks the ATM option")
        print("         2. Sets quantity to 1")
        print("         3. Navigates to review screen")
        
        # Click the option and set up the trade
        success = bot.click_option_and_buy(option_data, quantity=1)
        
        if success:
            print("[SUCCESS] Trade setup completed - you should see review screen")
            
            # Pause to let user review
            print(f"\n[REVIEW] MANUAL REVIEW TIME")
            print("="*60)
            print("🎯 The browser should now show the Robinhood review screen")
            print("📋 Please review the trade details carefully")
            print("⏸️  Take your time to decide: SUBMIT or CANCEL")
            print("💡 This is exactly what happens in live trading")
            print("="*60)
            
            # Wait for user to complete their review
            print(f"\n[WAITING] Waiting 30 seconds for your manual review...")
            print("          Use this time to examine the trade details")
            print("          Decide if you want to SUBMIT or CANCEL")
            time.sleep(30)
            
            # Now show the confirmation prompt
            print(f"\n[STEP 6] TRADE CONFIRMATION")
            print("="*60)
            
            # Call the interactive confirmation
            success = confirmation_manager.confirm_trade_interactive(trade_details)
            
            if success:
                print(f"\n[SUCCESS] Complete workflow finished successfully!")
                print("          Your trade decision was recorded properly")
            else:
                print(f"\n[CANCELLED] Workflow completed - trade was cancelled")
        
        else:
            print("[ERROR] Could not set up trade - may be market hours issue")
            
    except Exception as e:
        print(f"[ERROR] Demo failed: {e}")
        logger.error(f"Demo error: {e}", exc_info=True)
    
    finally:
        try:
            print(f"\n[CLEANUP] Keeping browser open for 10 more seconds...")
            print("          You can continue exploring if needed")
            time.sleep(10)
            bot.close()
            print("[SUCCESS] Browser closed")
        except:
            print("[WARNING] Browser may have already closed")
    
    # Show final bankroll
    final_bankroll = bankroll_manager.get_current_bankroll()
    print(f"\n[BANKROLL] Final Bankroll: ${final_bankroll:.2f}")
    
    print(f"\n[COMPLETE] COMPLETE WORKFLOW DEMO FINISHED")
    print("="*70)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Complete Trading Workflow Demo'
    )
    
    parser.add_argument('--call', action='store_true',
                       help='Demo CALL trade workflow')
    parser.add_argument('--put', action='store_true',
                       help='Demo PUT trade workflow')
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
        demo_complete_workflow('CALL', config)
    elif args.put:
        demo_complete_workflow('PUT', config)
    else:
        print("Complete Trading Workflow Demo")
        print("Usage:")
        print("  python demo_complete_workflow.py --call    # Demo CALL trade")
        print("  python demo_complete_workflow.py --put     # Demo PUT trade")


if __name__ == "__main__":
    main()
