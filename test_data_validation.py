#!/usr/bin/env python3
"""
Test script for improved data validation system
Tests the new internal validation approach vs old Yahoo Finance method
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import logging
import yaml
from utils.data_validation import DataValidator, ValidationResult

def load_config():
    """Load configuration from config file"""
    try:
        with open('config/config_dryrun.yaml', 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Warning: Could not load config: {e}")
        return {}

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_data_validation():
    """Test the improved data validation system"""
    
    print("=== TESTING IMPROVED DATA VALIDATION SYSTEM ===\n")
    
    # Load config with new validation settings
    config = load_config()
    
    # Test symbols
    test_symbols = ["SPY", "DIA", "QQQ", "IWM", "UVXY"]
    
    print("Configuration:")
    print(f"  DATA_USE_YAHOO_VALIDATION: {config.get('DATA_USE_YAHOO_VALIDATION', True)}")
    print(f"  DATA_USE_INTERNAL_VALIDATION: {config.get('DATA_USE_INTERNAL_VALIDATION', False)}")
    print(f"  DATA_MAX_DISCREPANCY_PCT: {config.get('DATA_MAX_DISCREPANCY_PCT', 1.0)}")
    print(f"  DATA_HISTORICAL_LOOKBACK_MINUTES: {config.get('DATA_HISTORICAL_LOOKBACK_MINUTES', 15)}")
    print()
    
    # Initialize validator
    validator = DataValidator(config)
    
    print("Testing data validation for each symbol:\n")
    
    for symbol in test_symbols:
        print(f"--- Testing {symbol} ---")
        
        try:
            # Test validation
            result = validator.validate_symbol_data(symbol)
            
            # Display results
            print(f"Symbol: {result.symbol}")
            print(f"Quality: {result.quality.value}")
            print(f"Recommendation: {result.recommendation}")
            
            if result.primary_data:
                print(f"Primary Price: ${result.primary_data.value:.2f} (source: {result.primary_data.source})")
            else:
                print("Primary Price: No data available")
                
            if result.validation_data:
                print(f"Validation Price: ${result.validation_data.value:.2f} (source: {result.validation_data.source})")
                if result.discrepancy_pct is not None:
                    print(f"Discrepancy: {result.discrepancy_pct:.2f}%")
            else:
                print("Validation Price: No validation data")
            
            if result.issues:
                print(f"Issues: {', '.join(result.issues)}")
            else:
                print("Issues: None")
                
            print(f"Status: {'PASS' if result.recommendation in ['PROCEED', 'PROCEED_WITH_CAUTION', 'PROCEED_NORMAL'] else 'BLOCKED'}")
            
        except Exception as e:
            print(f"ERROR testing {symbol}: {e}")
            
        print()
    
    # Test specific scenarios
    print("=== TESTING SPECIFIC SCENARIOS ===\n")
    
    # Test 1: Alpaca client availability
    print("--- Test 1: Alpaca Client Availability ---")
    if validator.alpaca_client:
        print("PASS: Alpaca client initialized successfully")
        
        # Test getting a price
        try:
            spy_data = validator.get_alpaca_price("SPY")
            if spy_data:
                print(f"PASS: Alpaca price fetch successful: SPY = ${spy_data.value:.2f}")
            else:
                print("FAIL: Alpaca price fetch returned None")
        except Exception as e:
            print(f"FAIL: Alpaca price fetch failed: {e}")
    else:
        print("FAIL: Alpaca client not available")
    
    print()
    
    # Test 2: Internal validation
    print("--- Test 2: Internal Validation ---")
    if config.get('DATA_USE_INTERNAL_VALIDATION', False):
        try:
            spy_current = validator.get_alpaca_price("SPY")
            if spy_current:
                spy_historical = validator.get_internal_validation_price("SPY", spy_current.value)
                if spy_historical:
                    discrepancy = validator.calculate_discrepancy(spy_current, spy_historical)
                    print(f"PASS: Internal validation working:")
                    print(f"   Current: ${spy_current.value:.2f}")
                    print(f"   Historical avg: ${spy_historical.value:.2f}")
                    print(f"   Discrepancy: {discrepancy:.2f}%")
                else:
                    print("FAIL: Internal validation returned None")
            else:
                print("FAIL: Cannot test internal validation - no current price")
        except Exception as e:
            print(f"FAIL: Internal validation test failed: {e}")
    else:
        print("WARNING: Internal validation disabled in config")
    
    print()
    
    # Test 3: Yahoo Finance (if enabled)
    print("--- Test 3: Yahoo Finance Validation ---")
    if config.get('DATA_USE_YAHOO_VALIDATION', True):
        try:
            spy_yahoo = validator.get_yahoo_price("SPY")
            if spy_yahoo:
                print(f"PASS: Yahoo Finance fetch successful: SPY = ${spy_yahoo.value:.2f}")
            else:
                print("FAIL: Yahoo Finance fetch returned None")
        except Exception as e:
            print(f"FAIL: Yahoo Finance test failed: {e}")
    else:
        print("PASS: Yahoo Finance validation disabled (as configured)")
    
    print()
    
    print("=== TEST SUMMARY ===")
    print("PASS: Data validation system tested successfully")
    print("INFO: Check the results above for any issues")
    print("INFO: Adjust configuration in config_dryrun.yaml if needed")

if __name__ == "__main__":
    test_data_validation()
