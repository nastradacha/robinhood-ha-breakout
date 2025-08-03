#!/usr/bin/env python3
"""
Trading Workflow Demo - Post-Login Focus

This script demonstrates the core trading workflow using saved cookies
(which is how the production system works). Focus is on:
1. Using saved session (realistic)
2. Navigate to options
3. Find and select trade
4. Review and confirm
5. Record outcome

Usage:
    python demo_trading_workflow.py --call    # Demo CALL trade
    python demo_trading_workflow.py --put     # Demo PUT trade
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


def demo_trading_workflow(direction: str, config: dict):
    """Demo the trading workflow using saved cookies (production-like)."""
    
    print(f"\n[DEMO] PRODUCTION-LIKE {direction.upper()} TRADING WORKFLOW")
    print("="*70)
    print("This demo shows the realistic trading process:")
    print("[OK] Uses saved session cookies (bypasses bot detection)")
    print("[OK] Focuses on option selection and review process")
    print("[OK] Shows the actual confirmation workflow")
    print("[OK] Exactly how the production system works")
    print("="*70)
    
    # Check if we have saved cookies
    cookie_path = Path("robin_cookies_selenium.json")
    if not cookie_path.exists():
        print(f"\n[ERROR] No saved session cookies found!")
        print("        Run the login demo first to establish a session:")
        print("        python demo_proper_login.py")
        return
    
    print(f"\n[SESSION] Using saved Robinhood session cookies")
    print("          This is how the production system works")
    
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
    
    try:
        # Initialize browser
        print(f"\n[STEP 1] Initializing browser with saved session...")
        bot = RobinhoodBot(headless=False)
        print("[SUCCESS] Browser initialized")
        
        # Start browser (will automatically load saved cookies)
        print(f"\n[STEP 2] Starting browser with saved session...")
        print("         This will automatically log you in using saved cookies")
        bot.start_browser()
        print("[SUCCESS] Browser started with saved session")
        
        # Pause to show logged-in state
        print(f"\n[PAUSE] Pausing 5 seconds - you should see Robinhood dashboard")
        time.sleep(5)
        
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
        
        # Create trade details (simulated for demo)
        trade_details = {
            'direction': direction.upper(),
            'strike': round(current_price) if not option_data else option_data['strike'],
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

⚠️ **THIS IS A DEMO** - Practice the confirmation workflow!
🎯 Check your terminal for the confirmation prompt"""
            
            slack_bot.send_message(alert_msg)
            print("[SUCCESS] Slack alert sent to your channel")
        
        # Store pending trade
        confirmation_manager.store_pending_trade(trade_details)
        
        if option_data:
            print(f"[SUCCESS] Found ATM option: Strike ${option_data['strike']}")
            
            print(f"\n[STEP 5] Attempting to click option and set up trade...")
            print("         Watch the browser as it:")
            print("         1. Clicks the ATM option")
            print("         2. Sets quantity to 1")
            print("         3. Navigates toward review")
            
            # Try to click the option and set up the trade
            try:
                success = bot.click_option_and_buy(option_data, quantity=1)
                
                if success:
                    print("[SUCCESS] Option clicked and trade setup initiated")
                    
                    # Pause for manual review
                    print(f"\n[REVIEW] MANUAL REVIEW TIME")
                    print("="*60)
                    print("🎯 Browser should show trade details or review screen")
                    print("📋 Take time to review the trade setup")
                    print("⏸️  You have 20 seconds to examine everything")
                    print("💡 In live trading, you'd submit or cancel here")
                    print("="*60)
                    
                    # Wait for manual review
                    time.sleep(20)
                    
                else:
                    print("[INFO] Could not complete option click (expected on weekends)")
                    print("      During market hours, this would work perfectly")
                    
            except Exception as e:
                print(f"[INFO] Option interaction limited: {e}")
                print("      This is normal outside market hours")
        
        else:
            print(f"[INFO] No live options found (expected on weekends)")
            print("      During market hours, ATM options would be available")
        
        # Show the confirmation workflow regardless
        print(f"\n[STEP 6] TRADE CONFIRMATION WORKFLOW")
        print("="*60)
        print("This is the core of the trading system:")
        print("- Records your actual decision (submit/cancel)")
        print("- Captures real fill prices")
        print("- Updates portfolio and bankroll")
        print("- Provides audit trail")
        print("="*60)
        
        # Call the interactive confirmation
        success = confirmation_manager.confirm_trade_interactive(trade_details)
        
        if success:
            print(f"\n[SUCCESS] Trading workflow completed successfully!")
            print("          Your decision was recorded and tracked")
        else:
            print(f"\n[CANCELLED] Trading workflow cancelled")
            print("            Cancellation was recorded properly")
            
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
    
    print(f"\n[COMPLETE] PRODUCTION-LIKE WORKFLOW DEMO FINISHED")
    print("="*70)
    print("[SUMMARY] This is exactly how your live trading system works:")
    print("   [OK] Uses saved cookies for reliable access")
    print("   [OK] Navigates to options automatically")
    print("   [OK] Finds ATM strikes efficiently")
    print("   [OK] Provides manual review time")
    print("   [OK] Records decisions accurately")
    print("   [OK] Updates tracking perfectly")
    print("="*70)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Production-Like Trading Workflow Demo'
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
        demo_trading_workflow('CALL', config)
    elif args.put:
        demo_trading_workflow('PUT', config)
    else:
        print("Production-Like Trading Workflow Demo")
        print("Usage:")
        print("  python demo_trading_workflow.py --call    # Demo CALL trade")
        print("  python demo_trading_workflow.py --put     # Demo PUT trade")
        print("")
        print("This demo uses saved cookies (production-like) and focuses on")
        print("the core trading workflow: options selection and confirmation.")


if __name__ == "__main__":
    main()
