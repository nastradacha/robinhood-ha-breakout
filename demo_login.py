#!/usr/bin/env python3
"""
Explicit Login Demo - Shows Login Process Step by Step

This script demonstrates the complete login process by clearing
existing cookies first, so you can see the actual login steps.

Usage:
    python demo_login.py
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


def demo_explicit_login():
    """Demo explicit login process by clearing cookies first."""
    
    print("\n[DEMO] EXPLICIT LOGIN PROCESS")
    print("="*60)
    print("This demo will clear existing cookies and show the login process.")
    print("Watch the browser window for each step.")
    print("="*60)
    
    # Clear existing cookies to force fresh login
    cookie_path = Path("robin_cookies_selenium.json")
    if cookie_path.exists():
        print(f"\n[SETUP] Removing existing cookies to force fresh login...")
        cookie_path.unlink()
        print("[SUCCESS] Existing cookies cleared")
    else:
        print(f"\n[SETUP] No existing cookies found - will do fresh login")
    
    try:
        # Initialize browser
        print("\n[STEP 1] Initializing browser (non-headless mode)...")
        bot = RobinhoodBot(headless=False)
        print("[SUCCESS] Browser initialized")
        
        # Start browser (this will now do fresh login)
        print("\n[STEP 2] Starting browser...")
        print("         Browser window should open now")
        bot.start_browser()
        print("[SUCCESS] Browser started")
        
        # Pause to show initial state
        print("\n[PAUSE] Pausing 3 seconds - browser should be open")
        time.sleep(3)
        
        # Now do the login process explicitly
        print("\n[STEP 3] Navigating to Robinhood login page...")
        bot.driver.get("https://robinhood.com/login")
        print("[SUCCESS] Navigated to login page")
        
        # Pause to show login page
        print("\n[PAUSE] Pausing 5 seconds - you should see Robinhood login page")
        time.sleep(5)
        
        # Check if we have credentials
        rh_user = os.getenv('RH_USER')
        rh_pass = os.getenv('RH_PASS')
        
        if rh_user and rh_pass:
            print(f"\n[STEP 4] Attempting to fill login credentials...")
            print(f"         Username: {rh_user[:3]}***@{rh_user.split('@')[1] if '@' in rh_user else 'hidden'}")
            
            try:
                # Find and fill username
                username_field = bot.driver.find_element("name", "username")
                username_field.clear()
                username_field.send_keys(rh_user)
                print("[SUCCESS] Username filled")
                
                # Find and fill password
                password_field = bot.driver.find_element("name", "password")
                password_field.clear()
                password_field.send_keys(rh_pass)
                print("[SUCCESS] Password filled")
                
                # Pause to show filled form
                print("\n[PAUSE] Pausing 5 seconds - credentials should be filled")
                time.sleep(5)
                
                # Find and click login button
                login_button = bot.driver.find_element("xpath", "//button[contains(text(), 'Sign In') or contains(text(), 'Log In')]")
                login_button.click()
                print("[SUCCESS] Login button clicked")
                
                # Wait for login to complete
                print("\n[STEP 5] Waiting for login to complete...")
                print("         This may take 10-30 seconds depending on 2FA")
                time.sleep(10)
                
                # Check if we're logged in by looking for dashboard elements
                current_url = bot.driver.current_url
                if "login" not in current_url.lower():
                    print(f"[SUCCESS] Login completed - now at: {current_url}")
                else:
                    print(f"[WARNING] Still on login page - may need 2FA or manual intervention")
                    print(f"          Current URL: {current_url}")
                
            except Exception as e:
                print(f"[ERROR] Login automation failed: {e}")
                print("        This is normal if Robinhood has anti-automation measures")
                print("        You may need to complete login manually")
        
        else:
            print(f"\n[WARNING] No credentials found in .env file")
            print(f"          RH_USER: {'Found' if rh_user else 'Missing'}")
            print(f"          RH_PASS: {'Found' if rh_pass else 'Missing'}")
            print(f"          You'll need to login manually")
        
        # Pause to show final state
        print(f"\n[PAUSE] Pausing 15 seconds - observe final login state")
        print(f"        If login succeeded, you should see Robinhood dashboard")
        print(f"        If login failed, you may need to complete it manually")
        time.sleep(15)
        
        # Test navigation to options
        print(f"\n[STEP 6] Testing navigation to SPY options...")
        try:
            bot.navigate_to_options('SPY')
            print("[SUCCESS] Navigated to SPY options")
            
            # Pause to show options page
            print(f"\n[PAUSE] Pausing 10 seconds - you should see SPY options page")
            time.sleep(10)
            
        except Exception as e:
            print(f"[ERROR] Navigation to options failed: {e}")
            print("        This may be due to incomplete login or weekend limitations")
        
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
    
    print(f"\n[COMPLETE] Login demo completed")
    print("="*60)


def main():
    """Main function."""
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("Explicit Login Process Demo")
    print("This will clear cookies and show the complete login process.")
    print("Starting demo automatically...")
    
    # Run demo automatically
    demo_explicit_login()


if __name__ == "__main__":
    main()
