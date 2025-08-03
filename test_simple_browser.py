#!/usr/bin/env python3
"""
Simple Browser Test - No Hanging Version

This script tests a simplified browser automation flow that won't hang.
"""

import sys
import time
from pathlib import Path
from dotenv import load_dotenv
import os

# Add utils to path
sys.path.append(str(Path(__file__).parent / 'utils'))

# Load environment variables
load_dotenv()

def test_simple_flow():
    """Test simplified browser flow that won't hang."""
    print("[TEST] Testing SIMPLIFIED Browser Flow...")
    print("=" * 60)
    
    try:
        from browser import RobinhoodBot
        
        with RobinhoodBot(headless=False) as bot:
            print("[OK] Browser started successfully")
            
            # Test login
            print("\n[LOGIN] Testing login...")
            if not bot.login(os.getenv('RH_USER'), os.getenv('RH_PASS')):
                print("[ERROR] Login failed!")
                return False
                
            print("[OK] Login successful!")
            
            # Navigate to SPY options
            print("\n[NAV] Navigating to SPY options...")
            if not bot.navigate_to_options("SPY"):
                print("[ERROR] Navigation to options failed!")
                return False
                
            print("[OK] Navigation successful!")
            
            # Take screenshot
            screenshot = bot.take_screenshot("test_simple_options.png")
            print(f"[SCREENSHOT] Options page: {screenshot}")
            
            # Find ATM option (this should work with our stale element fix)
            print("\n[FIND] Finding ATM CALL option...")
            current_price = 635.0  # Adjust based on current SPY price
            atm_option = bot.find_atm_option(current_price, "CALL")
            
            if not atm_option:
                print("[ERROR] Could not find ATM option!")
                return False
            
            print(f"[OK] Found ATM CALL: Strike ${atm_option['strike']}")
            
            # Test simplified order flow (should not hang)
            print("\n[ORDER] Testing SIMPLIFIED order flow...")
            print("[INFO] Using simplified click_option_and_buy method...")
            
            try:
                if bot.click_option_and_buy(atm_option, 1):
                    print("[SUCCESS] Simplified flow successful - reached Review screen!")
                    
                    # Take screenshot at review
                    screenshot = bot.take_screenshot("test_simple_review.png")
                    print(f"[SCREENSHOT] Review screen: {screenshot}")
                    
                    print("\n[STOP] STOPPED AT REVIEW - Order NOT submitted")
                    print("[SUCCESS] Simplified browser automation completed!")
                    
                    time.sleep(5)  # Brief pause for review
                    return True
                else:
                    print("[ERROR] Simplified order flow failed!")
                    return False
                    
            except Exception as e:
                print(f"[ERROR] Order flow exception: {e}")
                return False
        
        return True
        
    except Exception as e:
        print(f"[CRASH] Test failed with error: {e}")
        return False

def main():
    """Main test runner."""
    # Validate environment
    if not os.getenv('RH_USER') or not os.getenv('RH_PASS'):
        print("[ERROR] RH_USER and RH_PASS must be set in .env file")
        sys.exit(1)
    
    print("[START] Starting simplified browser test...")
    print("=" * 60)
    print("[INFO] This test uses simplified methods to prevent hanging")
    print("[INFO] Manual MFA completion may be required during login")
    print("=" * 60)
    
    try:
        success = test_simple_flow()
        
        if success:
            print("\n" + "=" * 60)
            print("[SUCCESS] Simplified browser test completed successfully!")
            print("=" * 60)
            sys.exit(0)
        else:
            print("\n" + "=" * 60)
            print("[FAILED] Simplified browser test failed!")
            print("=" * 60)
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[CRASH] Test crashed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
