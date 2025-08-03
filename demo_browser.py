#!/usr/bin/env python3
"""
Detailed Browser Demo - Shows Each Step Clearly

This script demonstrates the browser automation with clear pauses
so you can see each step of the navigation process.

Usage:
    python demo_browser.py
"""

import time
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from utils.browser import RobinhoodBot

logger = logging.getLogger(__name__)


def demo_browser_navigation():
    """Demo browser navigation with clear steps and pauses."""
    
    print("\n[DEMO] DETAILED BROWSER NAVIGATION TEST")
    print("="*60)
    print("This demo will show each step of browser automation.")
    print("Watch the browser window for navigation steps.")
    print("="*60)
    
    try:
        # Initialize browser
        print("\n[STEP 1] Initializing browser (non-headless mode)...")
        bot = RobinhoodBot(headless=False)
        print("[SUCCESS] Browser initialized")
        
        # Start browser and login
        print("\n[STEP 2] Starting browser and logging into Robinhood...")
        print("         Watch the browser window - login should happen automatically")
        bot.start_browser()
        print("[SUCCESS] Browser started and login completed")
        
        # Pause to let you see the logged-in state
        print("\n[PAUSE] Pausing 5 seconds - you should see Robinhood dashboard")
        time.sleep(5)
        
        # Navigate to SPY options
        print("\n[STEP 3] Navigating to SPY options page...")
        print("         Watch browser navigate to options chain")
        bot.navigate_to_options('SPY')
        print("[SUCCESS] Navigated to SPY options page")
        
        # Pause to let you see the options page
        print("\n[PAUSE] Pausing 10 seconds - you should see SPY options chain")
        print("        (May be empty/limited on weekends)")
        time.sleep(10)
        
        # Try to find ATM option
        print("\n[STEP 4] Searching for ATM CALL option...")
        current_price = 621.96  # Simulated current price
        option_data = bot.find_atm_option(current_price, 'CALL')
        
        if option_data:
            print(f"[SUCCESS] Found ATM option: Strike ${option_data['strike']}")
            
            # Pause to show the found option
            print("\n[PAUSE] Pausing 5 seconds - option should be highlighted")
            time.sleep(5)
            
        else:
            print("[INFO] No ATM options found (expected on weekends)")
            print("       During market hours, this would show available options")
        
        # Test browser session recovery
        print("\n[STEP 5] Testing session recovery...")
        print("         This ensures browser stays logged in")
        bot.ensure_open()
        print("[SUCCESS] Session recovery test completed")
        
        # Final pause before closing
        print("\n[PAUSE] Demo complete - pausing 10 seconds before closing browser")
        print("        You can see the final state of the browser")
        time.sleep(10)
        
    except Exception as e:
        print(f"[ERROR] Demo failed: {e}")
        logger.error(f"Demo error: {e}", exc_info=True)
    
    finally:
        try:
            print("\n[CLEANUP] Closing browser...")
            bot.close()
            print("[SUCCESS] Browser closed")
        except:
            print("[WARNING] Browser may have already closed")
    
    print("\n[COMPLETE] Browser demo completed")
    print("="*60)


def main():
    """Main function."""
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("Detailed Browser Navigation Demo")
    print("This will show you exactly what the browser automation does.")
    print("Starting demo automatically...")
    
    # Run demo automatically
    demo_browser_navigation()


if __name__ == "__main__":
    main()
