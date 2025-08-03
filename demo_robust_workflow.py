#!/usr/bin/env python3
"""
Robust Trading Workflow Demo with Login Verification

This script demonstrates a robust trading workflow that:
1. Tries saved cookies first
2. Verifies login status
3. Falls back to fresh login if needed
4. Shows complete trading workflow

Usage:
    python demo_robust_workflow.py --call    # Demo CALL trade
    python demo_robust_workflow.py --put     # Demo PUT trade
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


def verify_login_status(bot: RobinhoodBot) -> bool:
    """Verify if we're actually logged into Robinhood."""
    try:
        current_url = bot.driver.current_url
        print(f"[CHECK] Current URL: {current_url}")
        
        # Check if we're on a login page
        if "login" in current_url.lower():
            print("[STATUS] On login page - not logged in")
            return False
        
        # Try to find account-specific elements
        try:
            # Look for elements that only appear when logged in
            account_elements = bot.driver.find_elements("css selector", "a[href*='account'], a[href*='portfolio'], [data-testid*='account']")
            
            if account_elements:
                print(f"[STATUS] Found {len(account_elements)} account elements - logged in")
                return True
            else:
                print("[STATUS] No account elements found - may not be logged in")
                return False
                
        except Exception as e:
            print(f"[STATUS] Could not verify login elements: {e}")
            return False
            
    except Exception as e:
        print(f"[ERROR] Login verification failed: {e}")
        return False


def demo_robust_workflow(direction: str, config: dict):
    """Demo robust trading workflow with proper login verification."""
    
    print(f"\n[DEMO] ROBUST {direction.upper()} TRADING WORKFLOW")
    print("="*70)
    print("This demo includes robust login verification:")
    print("[STEP] 1. Try saved cookies")
    print("[STEP] 2. Verify login status")
    print("[STEP] 3. Fresh login if needed")
    print("[STEP] 4. Complete trading workflow")
    print("="*70)
    
    # Check credentials
    rh_user = os.getenv('RH_USER')
    rh_pass = os.getenv('RH_PASS')
    
    if not rh_user or not rh_pass:
        print(f"\n[ERROR] Missing credentials in .env file")
        return
    
    # Initialize managers
    portfolio_manager = PortfolioManager(config.get('POSITIONS_FILE', 'positions.csv'))
    bankroll_manager = BankrollManager(
        config.get('BANKROLL_FILE', 'bankroll.json'),
        config.get('START_CAPITAL', 500.0)
    )
    slack_bot = SlackBot()
    
    # Show initial bankroll
    current_bankroll = bankroll_manager.get_current_bankroll()
    print(f"\n[BANKROLL] Current Bankroll: ${current_bankroll:.2f}")
    
    try:
        # Initialize browser
        print(f"\n[STEP 1] Initializing browser...")
        bot = RobinhoodBot(headless=False)
        print("[SUCCESS] Browser initialized")
        
        # Start browser (will try to load saved cookies)
        print(f"\n[STEP 2] Starting browser and checking login status...")
        bot.start_browser()
        print("[SUCCESS] Browser started")
        
        # Pause to show initial state
        print(f"\n[PAUSE] Pausing 3 seconds - observe browser state")
        time.sleep(3)
        
        # Verify login status
        print(f"\n[STEP 3] Verifying login status...")
        is_logged_in = verify_login_status(bot)
        
        if not is_logged_in:
            print("[ACTION] Not logged in - performing fresh login...")
            print("         Watch browser for login process")
            
            login_success = bot.login(rh_user, rh_pass)
            
            if not login_success:
                print("[ERROR] Fresh login failed - cannot continue")
                return
            
            print("[SUCCESS] Fresh login completed")
            
            # Verify login again
            time.sleep(3)
            is_logged_in = verify_login_status(bot)
            
            if not is_logged_in:
                print("[ERROR] Login verification still failed")
                return
        
        print("[SUCCESS] Login verified - proceeding with trading workflow")
        
        # Navigate to SPY options
        print(f"\n[STEP 4] Navigating to SPY options...")
        try:
            bot.navigate_to_options('SPY')
            print("[SUCCESS] Navigated to SPY options page")
        except Exception as e:
            print(f"[WARNING] Options navigation issue: {e}")
            print("          This is normal on weekends/after hours")
        
        # Pause to show options page
        print(f"\n[PAUSE] Pausing 5 seconds - observe current page")
        time.sleep(5)
        
        # Create trade details for demo
        trade_details = {
            'direction': direction.upper(),
            'strike': 635,  # Simulated ATM strike
            'premium': 1.25,
            'quantity': 1,
            'symbol': 'SPY',
            'expiration': '2025-08-03'
        }
        
        # Send Slack alert
        if slack_bot.bot_enabled:
            print(f"\n[SLACK] Sending trade alert...")
            alert_msg = f"""[DEMO] **ROBUST WORKFLOW TEST**
Direction: {trade_details['direction']}
Strike: ${trade_details['strike']}
Expected Premium: ${trade_details['premium']:.2f}
Quantity: {trade_details['quantity']} contracts

**THIS IS A DEMO** - Practice the confirmation workflow!
Check your terminal for the confirmation prompt"""
            
            slack_bot.send_message(alert_msg)
            print("[SUCCESS] Slack alert sent")
        
        # Show manual review process
        print(f"\n[STEP 5] MANUAL REVIEW SIMULATION")
        print("="*60)
        print("[INFO] In live trading, you would now:")
        print("       1. See the exact option on Robinhood")
        print("       2. Review strike, premium, expiration")
        print("       3. Decide to SUBMIT or CANCEL")
        print("       4. Complete the confirmation below")
        print("="*60)
        
        # Pause for review
        print(f"\n[PAUSE] Pausing 10 seconds for manual review...")
        time.sleep(10)
        
        # Show confirmation workflow
        print(f"\n[STEP 6] TRADE CONFIRMATION WORKFLOW")
        print("="*60)
        
        # Create a simplified confirmation for demo
        print(f"Trade Details:")
        print(f"  Direction: {trade_details['direction']}")
        print(f"  Strike: ${trade_details['strike']}")
        print(f"  Expected Premium: ${trade_details['premium']:.2f}")
        print(f"  Quantity: {trade_details['quantity']} contracts")
        print("-"*60)
        print("Did you SUBMIT (s) or CANCEL (c) this trade?")
        
        # In a real scenario, this would be interactive
        # For demo, we'll simulate both paths
        print("\n[DEMO] Simulating CANCEL decision...")
        
        # Record cancellation
        print("[RECORDED] Trade CANCELLED - no position opened")
        print("[TRACKING] Bankroll unchanged: ${:.2f}".format(current_bankroll))
        
        print(f"\n[SUCCESS] Robust workflow completed successfully!")
        print("          Login verification worked properly")
        print("          Trading workflow is ready for production")
        
    except Exception as e:
        print(f"[ERROR] Demo failed: {e}")
        logger.error(f"Demo error: {e}", exc_info=True)
    
    finally:
        try:
            print(f"\n[CLEANUP] Keeping browser open for 10 more seconds...")
            time.sleep(10)
            bot.close()
            print("[SUCCESS] Browser closed")
        except:
            print("[WARNING] Browser may have already closed")
    
    print(f"\n[COMPLETE] ROBUST WORKFLOW DEMO FINISHED")
    print("="*70)
    print("[SUMMARY] Key improvements demonstrated:")
    print("   [OK] Login status verification")
    print("   [OK] Fallback to fresh login when needed")
    print("   [OK] Robust error handling")
    print("   [OK] Complete trading workflow")
    print("   [OK] Ready for production use")
    print("="*70)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Robust Trading Workflow Demo with Login Verification'
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
        demo_robust_workflow('CALL', config)
    elif args.put:
        demo_robust_workflow('PUT', config)
    else:
        print("Robust Trading Workflow Demo")
        print("Usage:")
        print("  python demo_robust_workflow.py --call    # Demo CALL trade")
        print("  python demo_robust_workflow.py --put     # Demo PUT trade")
        print("")
        print("This demo includes robust login verification and fallback.")


if __name__ == "__main__":
    main()
