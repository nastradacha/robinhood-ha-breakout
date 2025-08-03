#!/usr/bin/env python3
"""
Minimal Forced Login Test

This script forces a fresh login by:
1. Clearing ALL cookies and session data
2. Starting with a completely clean browser
3. Manually navigating to login page
4. Forcing the login process

Usage:
    python test_forced_login.py
"""

import time
import sys
import os
import shutil
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from utils.browser import RobinhoodBot

logger = logging.getLogger(__name__)


def clear_all_session_data():
    """Clear all possible session data."""
    files_to_clear = [
        "robin_cookies_selenium.json",
        "robin_cookies.json",
        "cookies.json"
    ]
    
    dirs_to_clear = [
        "temp_chrome_profile",
        "__pycache__"
    ]
    
    print("[CLEANUP] Clearing all session data...")
    
    for file_name in files_to_clear:
        file_path = Path(file_name)
        if file_path.exists():
            file_path.unlink()
            print(f"[DELETED] {file_name}")
    
    for dir_name in dirs_to_clear:
        dir_path = Path(dir_name)
        if dir_path.exists():
            shutil.rmtree(dir_path, ignore_errors=True)
            print(f"[DELETED] {dir_name}/")
    
    print("[SUCCESS] All session data cleared")


def test_forced_login():
    """Test forced fresh login with completely clean state."""
    
    print("\n[TEST] FORCED LOGIN TEST")
    print("="*50)
    print("This test will force a completely fresh login")
    print("by clearing all session data first.")
    print("="*50)
    
    # Check credentials
    rh_user = os.getenv('RH_USER')
    rh_pass = os.getenv('RH_PASS')
    
    if not rh_user or not rh_pass:
        print(f"\n[ERROR] Missing credentials in .env file")
        print(f"         RH_USER: {'Found' if rh_user else 'MISSING'}")
        print(f"         RH_PASS: {'Found' if rh_pass else 'MISSING'}")
        return
    
    print(f"\n[CREDENTIALS] Using: {rh_user[:3]}***@{rh_user.split('@')[1] if '@' in rh_user else 'hidden'}")
    
    # Clear all session data
    clear_all_session_data()
    
    try:
        # Initialize browser with clean state
        print(f"\n[STEP 1] Initializing completely clean browser...")
        bot = RobinhoodBot(headless=False)
        print("[SUCCESS] Browser initialized")
        
        # Start browser (no cookies will be loaded)
        print(f"\n[STEP 2] Starting clean browser...")
        bot.start_browser()
        print("[SUCCESS] Clean browser started")
        
        # Pause to show clean browser
        print(f"\n[PAUSE] Pausing 3 seconds - browser should be clean")
        time.sleep(3)
        
        # Manually navigate to login page
        print(f"\n[STEP 3] Manually navigating to login page...")
        bot.driver.get("https://robinhood.com/login")
        print("[SUCCESS] Navigated to login page")
        
        # Pause to show login page
        print(f"\n[PAUSE] Pausing 5 seconds - you should see login form")
        time.sleep(5)
        
        # Check current URL
        current_url = bot.driver.current_url
        print(f"[INFO] Current URL: {current_url}")
        
        # Now call the login method
        print(f"\n[STEP 4] Calling RobinhoodBot.login() method...")
        print("         This should show the complete login process:")
        print("         - Fill username")
        print("         - Fill password") 
        print("         - Click login button")
        print("         - Handle MFA if needed")
        print("         - Verify login success")
        
        login_success = bot.login(rh_user, rh_pass)
        
        if login_success:
            print(f"\n[SUCCESS] Login completed successfully!")
            
            # Verify we're logged in
            final_url = bot.driver.current_url
            print(f"[VERIFY] Final URL: {final_url}")
            
            if "login" not in final_url.lower():
                print("[VERIFIED] Successfully logged in - not on login page")
            else:
                print("[WARNING] Still on login page - login may have failed")
            
            # Test navigation
            print(f"\n[STEP 5] Testing navigation to verify login...")
            try:
                bot.driver.get("https://robinhood.com/account")
                time.sleep(3)
                account_url = bot.driver.current_url
                print(f"[TEST] Account page URL: {account_url}")
                
                if "login" in account_url.lower():
                    print("[ERROR] Redirected to login - session not established")
                else:
                    print("[SUCCESS] Can access account page - login verified")
                    
            except Exception as e:
                print(f"[ERROR] Navigation test failed: {e}")
        
        else:
            print(f"\n[FAILED] Login was not successful")
            
            # Show current state
            failed_url = bot.driver.current_url
            print(f"[DEBUG] Current URL after failed login: {failed_url}")
            
        # Keep browser open for inspection
        print(f"\n[PAUSE] Keeping browser open for 15 seconds for inspection...")
        time.sleep(15)
        
    except Exception as e:
        print(f"[ERROR] Test failed: {e}")
        logger.error(f"Test error: {e}", exc_info=True)
    
    finally:
        try:
            bot.close()
            print(f"\n[CLEANUP] Browser closed")
        except:
            print(f"[WARNING] Browser may have already closed")
    
    print(f"\n[COMPLETE] Forced login test completed")
    print("="*50)


def main():
    """Main function."""
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("Minimal Forced Login Test")
    print("This will clear all session data and force a fresh login.")
    
    test_forced_login()


if __name__ == "__main__":
    main()
