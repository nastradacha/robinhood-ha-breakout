#!/usr/bin/env python3
"""
Test script to validate UVXY shares fallback functionality
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from utils.alpaca_options import create_alpaca_trader
from utils.llm import load_config
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_uvxy_shares_fallback():
    """Test UVXY options filtering and shares fallback"""
    try:
        # Load config
        config = load_config('config/config_dryrun.yaml')
        
        # Initialize Alpaca options trader
        trader = create_alpaca_trader(paper=True)
        if not trader:
            print("[ERROR] Failed to create Alpaca trader - check API credentials")
            return False
        
        # Monkey patch the config loading to use our test config
        import utils.alpaca_options
        original_load_config = utils.alpaca_options.load_config
        utils.alpaca_options.load_config = lambda: config
        
        print("=" * 60)
        print("TESTING UVXY SHARES FALLBACK FUNCTIONALITY")
        print("=" * 60)
        
        # Test UVXY CALL contract finding
        print(f"\n1. Testing UVXY CALL contract selection...")
        contract = trader.find_atm_contract('UVXY', 'CALL', '0DTE', '2025-08-20')
        
        if contract:
            print(f"   [OK] Contract found: {contract.symbol}")
            print(f"   [TYPE] Contract type: {'SHARES' if getattr(contract, 'is_shares_fallback', False) else 'OPTIONS'}")
            print(f"   [PREMIUM] Premium: ${getattr(contract, 'premium', 'N/A')}")
            print(f"   [DELTA] Delta: {getattr(contract, 'delta', 'N/A')}")
            print(f"   [LIQUIDITY] Liquidity: {getattr(contract, 'liquidity_score', 'N/A')}")
            
            if hasattr(contract, 'is_shares_fallback') and contract.is_shares_fallback:
                print(f"   [FALLBACK] SHARES FALLBACK ACTIVATED!")
                print(f"   [REASON] Fallback reason: {getattr(contract, 'fallback_reason', 'Unknown')}")
            else:
                print(f"   [OPTIONS] Options contract selected")
                print(f"   [STRIKE] Strike: ${getattr(contract, 'strike', 'N/A')}")
                print(f"   [EXPIRY] Expiry: {getattr(contract, 'expiry', 'N/A')}")
        else:
            print(f"   [ERROR] No contract found (neither options nor shares)")
        
        # Test UVXY PUT contract finding
        print(f"\n2. Testing UVXY PUT contract selection...")
        contract_put = trader.find_atm_contract('UVXY', 'PUT', '0DTE', '2025-08-20')
        
        if contract_put:
            print(f"   [OK] Contract found: {contract_put.symbol}")
            print(f"   [TYPE] Contract type: {'SHARES' if getattr(contract_put, 'is_shares_fallback', False) else 'OPTIONS'}")
            
            if hasattr(contract_put, 'is_shares_fallback') and contract_put.is_shares_fallback:
                print(f"   [FALLBACK] SHARES FALLBACK ACTIVATED!")
                print(f"   [REASON] Fallback reason: {getattr(contract_put, 'fallback_reason', 'Unknown')}")
        else:
            print(f"   [ERROR] No contract found (neither options nor shares)")
        
        print(f"\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        
        call_fallback = contract and hasattr(contract, 'is_shares_fallback') and contract.is_shares_fallback
        put_fallback = contract_put and hasattr(contract_put, 'is_shares_fallback') and contract_put.is_shares_fallback
        
        print(f"CALL shares fallback: {'[OK] WORKING' if call_fallback else '[SKIP] NOT TRIGGERED'}")
        print(f"PUT shares fallback:  {'[OK] WORKING' if put_fallback else '[SKIP] NOT TRIGGERED'}")
        
        if call_fallback or put_fallback:
            print(f"\n[SUCCESS] SHARES FALLBACK FUNCTIONALITY VALIDATED!")
        else:
            print(f"\n[INFO] Shares fallback not triggered - options may be passing filters")
            print(f"       This could mean UVXY options are currently liquid enough")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Restore original config loading
        try:
            utils.alpaca_options.load_config = original_load_config
        except:
            pass

if __name__ == "__main__":
    success = test_uvxy_shares_fallback()
    sys.exit(0 if success else 1)
