#!/usr/bin/env python3
"""
Proper Login Demo - Uses the Real Login Method

This script demonstrates the actual login process using the
robust login method from the RobinhoodBot class.

Usage:
    python demo_proper_login.py
"""

import time
import sys
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from utils.browser import RobinhoodBot

logger = logging.getLogger(__name__)


def demo_proper_login():
    """Demo the proper login process using the real RobinhoodBot login method."""
    
    print("\n[DEMO] PROPER LOGIN PROCESS")
    print("="*60)
    print("This demo uses the actual RobinhoodBot login method.")
    print("It includes MFA handling and login verification.")
    print("="*60)
    
    # Clear existing cookies to force fresh login
    cookie_path = Path("robin_cookies_selenium.json")
    if cookie_path.exists():
        print(f"\n[SETUP] Removing existing cookies to force fresh login...")
        cookie_path.unlink()
        print("[SUCCESS] Existing cookies cleared")
    
    # Check credentials
    rh_user = os.getenv('RH_USER')
    rh_pass = os.getenv('RH_PASS')
    
    if not rh_user or not rh_pass:
        print(f"\n[ERROR] Missing credentials in .env file:")
        print(f"         RH_USER: {'Found' if rh_user else 'MISSING'}")
        print(f"         RH_PASS: {'Found' if rh_pass else 'MISSING'}")
        print(f"         Please add your Robinhood credentials to .env file")
        return
    
    print(f"\n[CREDENTIALS] Found credentials for: {rh_user[:3]}***@{rh_user.split('@')[1] if '@' in rh_user else 'hidden'}")
    
    try:
        # Initialize browser
        print("\n[STEP 1] Initializing browser...")
        bot = RobinhoodBot(headless=False)
        print("[SUCCESS] Browser initialized")
        
        # Start browser (without cookies, so no auto-login)
        print("\n[STEP 2] Starting browser...")
        bot.start_browser()
        print("[SUCCESS] Browser started")
        
        # Pause to show browser
        print("\n[PAUSE] Pausing 3 seconds - browser should be open")
        time.sleep(3)
        
        # Use the proper login method
        print("\n[STEP 3] Starting proper login process...")
        print("         This uses the robust RobinhoodBot.login() method")
        print("         Watch for:")
        print("         - Navigation to login page")
        print("         - Human-like typing of credentials")
        print("         - Login button click")
        print("         - MFA prompt (if enabled)")
        print("         - Login verification")
        
        # Call the real login method
        login_success = bot.login(rh_user, rh_pass)
        
        if login_success:
            print("\n[SUCCESS] Login completed successfully!")
            print("          - Credentials were accepted")
            print("          - MFA was completed (if required)")
            print("          - Login was verified")
            print("          - Session cookies were saved")
            
            # Test navigation to options
            print("\n[STEP 4] Testing navigation to SPY options...")
            try:
                bot.navigate_to_options('SPY')
                print("[SUCCESS] Navigated to SPY options page")
                
                # Check if we're actually on the options page
                current_url = bot.driver.current_url
                if "options" in current_url.lower() or "spy" in current_url.lower():
                    print(f"[VERIFIED] On options page: {current_url}")
                else:
                    print(f"[WARNING] Unexpected page: {current_url}")
                
                # Pause to show options page
                print("\n[PAUSE] Pausing 10 seconds - observe the options page")
                time.sleep(10)
                
            except Exception as e:
                print(f"[ERROR] Navigation failed: {e}")
                print("        This may be due to weekend limitations")
        
        else:
            print("\n[FAILED] Login was not successful!")
            print("         Possible reasons:")
            print("         - Incorrect credentials")
            print("         - MFA timeout (120 seconds)")
            print("         - Robinhood anti-automation measures")
            print("         - Network issues")
            
            # Show current page
            current_url = bot.driver.current_url
            print(f"         Current page: {current_url}")
            
            # Pause to show failed state
            print("\n[PAUSE] Pausing 10 seconds - observe the failed login state")
            time.sleep(10)
        
    except Exception as e:
        print(f"[ERROR] Demo failed: {e}")
        logger.error(f"Demo error: {e}", exc_info=True)
    
    finally:
        try:
            print(f"\n[CLEANUP] Closing browser in 5 seconds...")
            time.sleep(5)
            bot.close()
            print("[SUCCESS] Browser closed")
        except:
            print("[WARNING] Browser may have already closed")
    
    print(f"\n[COMPLETE] Proper login demo completed")
    print("="*60)


def main():
    """Main function."""
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("Proper Login Process Demo")
    print("This uses the actual RobinhoodBot login method with MFA support.")
    print("Starting demo automatically...")
    
    # Run demo automatically
    demo_proper_login()


if __name__ == "__main__":
    main()
