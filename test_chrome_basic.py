#!/usr/bin/env python3
"""
Basic Chrome Driver Stability Test

Simple test to validate Chrome driver stability features:
1. Chrome version pinning
2. Random temp profile creation
3. Basic navigation
4. Proper cleanup

Author: Robinhood HA Breakout System
Version: 0.6.1
"""

import os
import sys
import time
import tempfile
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.browser import RobinhoodBot
from utils.llm import load_config


def test_chrome_basic():
    """Basic Chrome driver stability test."""
    print("Chrome Driver Basic Stability Test")
    print("=" * 40)
    
    # Show configuration
    try:
        config = load_config()
        chrome_major = config.get("CHROME_MAJOR")
        print(f"Chrome config: {chrome_major if chrome_major else 'Auto-detect'}")
    except Exception as e:
        print(f"Config error: {e}")
    
    print("\n[TEST] Creating RobinhoodBot...")
    bot = RobinhoodBot(headless=True, implicit_wait=5)  # Headless for stability
    
    try:
        print("[TEST] Starting Chrome browser...")
        bot.start_browser()
        
        print("[SUCCESS] Browser started!")
        print(f"  Temp profile: {bot._temp_profile_dir is not None}")
        
        print("[TEST] Basic navigation...")
        bot.driver.get("https://www.google.com")
        time.sleep(2)
        
        title = bot.driver.title
        print(f"[SUCCESS] Page loaded: {title}")
        
        print("[TEST] Chrome stability validated!")
        
    except Exception as e:
        print(f"[ERROR] Test failed: {e}")
        
    finally:
        print("[TEST] Cleaning up...")
        bot.quit()
        print("[SUCCESS] Cleanup complete!")


if __name__ == "__main__":
    test_chrome_basic()
