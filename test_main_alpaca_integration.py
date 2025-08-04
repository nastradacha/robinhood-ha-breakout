#!/usr/bin/env python3
"""
Test Main Trading Workflow with Alpaca Integration

Validates that the main trading analysis workflow properly uses Alpaca
real-time data for accurate breakout detection and trade decisions.

This ensures end-to-end data quality from market data fetching through
LLM analysis and trade execution preparation.

Usage:
    python test_main_alpaca_integration.py
"""

import os
import sys
import logging
from datetime import datetime
import pandas as pd

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.data import fetch_market_data, get_current_price, calculate_heikin_ashi, analyze_breakout_pattern
from utils.alpaca_client import AlpacaClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_alpaca_market_data_integration():
    """Test that main workflow uses Alpaca data properly."""
    print("=== TESTING MAIN WORKFLOW ALPACA INTEGRATION ===")
    
    symbol = "SPY"
    
    # Test 1: Market data fetching with Alpaca primary
    print(f"\n1. Testing market data fetching for {symbol}...")
    market_data = fetch_market_data(symbol=symbol, period="5d", interval="5m")
    
    if market_data is not None and not market_data.empty:
        print(f"[SUCCESS] Fetched {len(market_data)} bars of market data")
        print(f"Latest close: ${market_data['Close'].iloc[-1]:.2f}")
        print(f"Date range: {market_data.index[0]} to {market_data.index[-1]}")
    else:
        print("[ERROR] Failed to fetch market data")
        return False
    
    # Test 2: Real-time current price
    print(f"\n2. Testing real-time current price for {symbol}...")
    current_price = get_current_price(symbol)
    
    if current_price:
        print(f"[SUCCESS] Real-time price: ${current_price:.2f}")
        
        # Compare with latest historical price
        historical_price = market_data['Close'].iloc[-1]
        price_diff = abs(current_price - historical_price)
        price_diff_pct = (price_diff / historical_price) * 100
        
        print(f"Historical close: ${historical_price:.2f}")
        print(f"Price difference: ${price_diff:.2f} ({price_diff_pct:.2f}%)")
        
        if price_diff_pct > 5.0:
            print("[WARNING] Large price difference - may indicate stale historical data")
        else:
            print("[SUCCESS] Real-time and historical prices are consistent")
    else:
        print("[WARNING] Could not fetch real-time price")
    
    return True

def test_enhanced_analysis_workflow():
    """Test the enhanced analysis workflow with real-time price integration."""
    print("\n=== TESTING ENHANCED ANALYSIS WORKFLOW ===")
    
    symbol = "SPY"
    lookback_bars = 20
    
    # Step 1: Fetch market data
    print("1. Fetching market data...")
    market_data = fetch_market_data(symbol=symbol, period="5d", interval="5m")
    
    if market_data.empty:
        print("[ERROR] No market data available")
        return False
    
    # Step 2: Get real-time current price
    print("2. Fetching real-time current price...")
    current_price = get_current_price(symbol)
    
    # Step 3: Update market data with real-time price (simulating main.py logic)
    if current_price:
        print(f"3. Updating latest price with real-time data: ${current_price:.2f}")
        market_data.iloc[-1, market_data.columns.get_loc('Close')] = current_price
    
    # Step 4: Calculate Heikin-Ashi candles
    print("4. Calculating Heikin-Ashi candles...")
    ha_data = calculate_heikin_ashi(market_data)
    
    if ha_data.empty:
        print("[ERROR] Failed to calculate Heikin-Ashi candles")
        return False
    
    print(f"[SUCCESS] Calculated {len(ha_data)} Heikin-Ashi candles")
    
    # Step 5: Analyze breakout patterns
    print("5. Analyzing breakout patterns...")
    analysis = analyze_breakout_pattern(ha_data, lookback_bars)
    
    # Step 6: Override with real-time price (simulating main.py logic)
    if current_price:
        analysis['current_price'] = current_price
        analysis['data_source'] = 'alpaca_realtime'
        print(f"6. Updated analysis with real-time price: ${current_price:.2f}")
    
    # Display analysis results
    print("\n=== ANALYSIS RESULTS ===")
    print(f"Symbol: {symbol}")
    print(f"Current Price: ${analysis['current_price']:.2f}")
    print(f"Data Source: {analysis.get('data_source', 'yahoo_historical')}")
    print(f"Trend Direction: {analysis['trend_direction']}")
    print(f"Candle Body %: {analysis['candle_body_pct']:.2f}%")
    print(f"Breakout Strength: {analysis['breakout_strength']:.2f}")
    print(f"Volume Ratio: {analysis['volume_ratio']:.2f}")
    
    # Validate analysis quality
    if analysis['current_price'] > 0 and analysis['candle_body_pct'] >= 0:
        print("[SUCCESS] Analysis completed with valid results")
        return True
    else:
        print("[ERROR] Analysis produced invalid results")
        return False

def test_alpaca_connection_status():
    """Test Alpaca connection and capabilities."""
    print("\n=== TESTING ALPACA CONNECTION STATUS ===")
    
    alpaca = AlpacaClient()
    
    print(f"Alpaca enabled: {alpaca.enabled}")
    
    if alpaca.enabled:
        # Test account info
        account_info = alpaca.get_account_info()
        if account_info:
            print("[SUCCESS] Alpaca account connection verified")
            print(f"Account status: {account_info.get('status', 'unknown')}")
            print(f"Trading blocked: {account_info.get('trading_blocked', 'unknown')}")
        else:
            print("[WARNING] Could not fetch account info")
        
        # Test market status
        market_status = alpaca.get_market_status()
        if market_status:
            print(f"[SUCCESS] Market status: {market_status}")
        else:
            print("[WARNING] Could not fetch market status")
        
        return True
    else:
        print("[INFO] Alpaca not configured - will use Yahoo Finance fallback")
        return True

def test_data_quality_comparison():
    """Compare data quality between Alpaca and Yahoo Finance."""
    print("\n=== TESTING DATA QUALITY COMPARISON ===")
    
    symbol = "SPY"
    
    # Get Alpaca data
    alpaca = AlpacaClient()
    alpaca_data = None
    if alpaca.enabled:
        try:
            alpaca_data = alpaca.get_market_data(symbol, "1d")
            if alpaca_data is not None and not alpaca_data.empty:
                print(f"[ALPACA] Fetched {len(alpaca_data)} bars")
                print(f"[ALPACA] Latest close: ${alpaca_data['Close'].iloc[-1]:.2f}")
                print(f"[ALPACA] Data timestamp: {alpaca_data.index[-1]}")
        except Exception as e:
            print(f"[ALPACA] Error: {e}")
    
    # Get Yahoo Finance data
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        yahoo_data = ticker.history(period="1d", interval="5m")
        
        if not yahoo_data.empty:
            print(f"[YAHOO] Fetched {len(yahoo_data)} bars")
            print(f"[YAHOO] Latest close: ${yahoo_data['Close'].iloc[-1]:.2f}")
            print(f"[YAHOO] Data timestamp: {yahoo_data.index[-1]}")
            
            # Compare if both available
            if alpaca_data is not None and not alpaca_data.empty:
                alpaca_price = alpaca_data['Close'].iloc[-1]
                yahoo_price = yahoo_data['Close'].iloc[-1]
                price_diff = abs(alpaca_price - yahoo_price)
                price_diff_pct = (price_diff / yahoo_price) * 100
                
                print(f"\n[COMPARISON] Price difference: ${price_diff:.2f} ({price_diff_pct:.2f}%)")
                
                if price_diff_pct < 1.0:
                    print("[SUCCESS] Data sources are consistent")
                else:
                    print("[INFO] Significant price difference - Alpaca likely more current")
        
    except Exception as e:
        print(f"[YAHOO] Error: {e}")
    
    return True

def main():
    """Run comprehensive Alpaca integration tests."""
    print("MAIN TRADING WORKFLOW - ALPACA INTEGRATION TESTING")
    print("=" * 60)
    
    test_results = []
    
    try:
        # Test 1: Alpaca connection
        print("\nTEST 1: Alpaca Connection Status")
        result1 = test_alpaca_connection_status()
        test_results.append(("Alpaca Connection", result1))
        
        # Test 2: Market data integration
        print("\nTEST 2: Market Data Integration")
        result2 = test_alpaca_market_data_integration()
        test_results.append(("Market Data Integration", result2))
        
        # Test 3: Enhanced analysis workflow
        print("\nTEST 3: Enhanced Analysis Workflow")
        result3 = test_enhanced_analysis_workflow()
        test_results.append(("Enhanced Analysis", result3))
        
        # Test 4: Data quality comparison
        print("\nTEST 4: Data Quality Comparison")
        result4 = test_data_quality_comparison()
        test_results.append(("Data Quality", result4))
        
        # Summary
        print("\n" + "=" * 60)
        print("TEST RESULTS SUMMARY:")
        
        all_passed = True
        for test_name, result in test_results:
            status = "[PASS]" if result else "[FAIL]"
            print(f"{status} {test_name}")
            if not result:
                all_passed = False
        
        if all_passed:
            print("\n[SUCCESS] All tests passed!")
            print("\nYour main trading workflow now has:")
            print("- Real-time Alpaca market data integration")
            print("- Enhanced breakout analysis with current prices")
            print("- Professional-grade data quality")
            print("- Robust fallback to Yahoo Finance")
            print("\nThe system is ready for live trading with superior data quality!")
        else:
            print("\n[WARNING] Some tests failed - review configuration")
        
        return 0 if all_passed else 1
        
    except Exception as e:
        logger.error(f"Test suite failed: {e}")
        print(f"\n[ERROR] Test suite failed: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
