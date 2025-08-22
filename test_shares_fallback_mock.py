#!/usr/bin/env python3
"""
Test script to validate UVXY shares fallback functionality using mocks
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from unittest.mock import Mock, patch
from utils.alpaca_options import AlpacaOptionsTrader, ContractInfo
from utils.llm import load_config
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_uvxy_shares_fallback_mock():
    """Test UVXY options filtering and shares fallback using mocks"""
    try:
        # Load config
        config = load_config('config/config_dryrun.yaml')
        
        print("=" * 60)
        print("TESTING UVXY SHARES FALLBACK FUNCTIONALITY (MOCK)")
        print("=" * 60)
        
        # Mock the Alpaca client to avoid API calls
        with patch('utils.alpaca_options.TradingClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            
            # Create trader with mock credentials
            trader = AlpacaOptionsTrader("test_key", "test_secret", paper=True)
            trader.client = mock_client
            
            # Mock market open check
            mock_client.get_clock.return_value = Mock(is_open=True)
            
            # Test scenario 1: Options available and pass filters
            print(f"\n1. Testing UVXY CALL - Options available scenario...")
            
            # Mock options chain response with good liquidity
            mock_options = [
                Mock(
                    symbol="UVXY250820C00014000",
                    strike_price=14.0,
                    expiration_date="2025-08-20",
                    open_interest=1000,
                    implied_volatility=0.5,
                    delta=0.45
                ),
                Mock(
                    symbol="UVXY250820C00015000", 
                    strike_price=15.0,
                    expiration_date="2025-08-20",
                    open_interest=800,
                    implied_volatility=0.52,
                    delta=0.35
                )
            ]
            mock_client.get_options_chain.return_value = Mock(options=mock_options)
            
            # Mock quote with tight spread (should pass filters)
            mock_client.get_latest_quote.return_value = Mock(
                bid=0.45,
                ask=0.50,
                bid_size=100,
                ask_size=150
            )
            
            contract = trader.find_atm_contract('UVXY', 'CALL')
            
            if contract:
                print(f"   [OK] Contract found: {contract.symbol}")
                is_shares = getattr(contract, 'is_shares_fallback', False)
                print(f"   [TYPE] Contract type: {'SHARES' if is_shares else 'OPTIONS'}")
                
                if is_shares:
                    print(f"   [UNEXPECTED] Shares fallback triggered when options should pass")
                else:
                    print(f"   [EXPECTED] Options contract selected (good liquidity)")
            else:
                print(f"   [ERROR] No contract found")
            
            # Test scenario 2: Options fail filters, trigger shares fallback
            print(f"\n2. Testing UVXY CALL - Options fail filters scenario...")
            
            # Mock options with poor liquidity (wide spreads, low OI)
            mock_bad_options = [
                Mock(
                    symbol="UVXY250820C00014000",
                    strike_price=14.0,
                    expiration_date="2025-08-20",
                    open_interest=50,  # Below UVXY min_oi=150
                    implied_volatility=0.8,
                    delta=0.45
                )
            ]
            mock_client.get_options_chain.return_value = Mock(options=mock_bad_options)
            
            # Mock quote with wide spread (should fail filters)
            mock_client.get_latest_quote.return_value = Mock(
                bid=0.20,
                ask=0.40,  # 50% spread - way above 25% threshold
                bid_size=10,
                ask_size=5
            )
            
            # Mock current stock price for shares fallback
            mock_client.get_latest_trade.return_value = Mock(price=14.0)
            
            contract_fallback = trader.find_atm_contract('UVXY', 'CALL')
            
            if contract_fallback:
                print(f"   [OK] Contract found: {contract_fallback.symbol}")
                is_shares = getattr(contract_fallback, 'is_shares_fallback', False)
                print(f"   [TYPE] Contract type: {'SHARES' if is_shares else 'OPTIONS'}")
                
                if is_shares:
                    print(f"   [SUCCESS] SHARES FALLBACK ACTIVATED!")
                    print(f"   [REASON] Fallback reason: {getattr(contract_fallback, 'fallback_reason', 'Unknown')}")
                else:
                    print(f"   [UNEXPECTED] Options selected despite poor liquidity")
            else:
                print(f"   [ERROR] No contract found (shares fallback may have failed)")
            
            # Test scenario 3: PUT with shares fallback
            print(f"\n3. Testing UVXY PUT - Shares fallback scenario...")
            
            contract_put = trader.find_atm_contract('UVXY', 'PUT')
            
            if contract_put:
                print(f"   [OK] Contract found: {contract_put.symbol}")
                is_shares = getattr(contract_put, 'is_shares_fallback', False)
                print(f"   [TYPE] Contract type: {'SHARES' if is_shares else 'OPTIONS'}")
                
                if is_shares:
                    print(f"   [SUCCESS] PUT shares fallback activated!")
            else:
                print(f"   [ERROR] No PUT contract found")
        
        print(f"\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        
        # Check if shares fallback was triggered in scenario 2
        fallback_triggered = (contract_fallback and 
                            hasattr(contract_fallback, 'is_shares_fallback') and 
                            contract_fallback.is_shares_fallback)
        
        print(f"Shares fallback test: {'[SUCCESS] WORKING' if fallback_triggered else '[FAIL] NOT TRIGGERED'}")
        
        if fallback_triggered:
            print(f"\n[SUCCESS] SHARES FALLBACK FUNCTIONALITY VALIDATED!")
            print(f"          System correctly falls back to shares when options fail liquidity filters")
        else:
            print(f"\n[FAIL] Shares fallback not working as expected")
            print(f"       Check implementation in utils/alpaca_options.py")
        
        return fallback_triggered
        
    except Exception as e:
        print(f"[ERROR] Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_uvxy_shares_fallback_mock()
    sys.exit(0 if success else 1)
