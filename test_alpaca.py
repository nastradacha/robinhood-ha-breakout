#!/usr/bin/env python3
"""
Test Alpaca API connection and data quality
"""

import os
from dotenv import load_dotenv
from utils.alpaca_client import AlpacaClient
import yfinance as yf

def test_alpaca_setup():
    """Test Alpaca API setup and compare data quality with Yahoo Finance."""
    
    print("=== ALPACA API SETUP TEST ===")
    print()
    
    # Load environment variables
    load_dotenv()
    
    # Check environment variables
    api_key = os.getenv('ALPACA_API_KEY')
    secret_key = os.getenv('ALPACA_SECRET_KEY')
    base_url = os.getenv('ALPACA_BASE_URL')
    
    print("ENVIRONMENT VARIABLES:")
    print(f"ALPACA_API_KEY: {'[OK] Set' if api_key else '[X] Missing'}")
    print(f"ALPACA_SECRET_KEY: {'[OK] Set' if secret_key else '[X] Missing'}")
    print(f"ALPACA_BASE_URL: {base_url or 'Using default'}")
    print()
    
    if not api_key or not secret_key:
        print("[X] SETUP REQUIRED:")
        print("Add these lines to your .env file:")
        print("ALPACA_API_KEY=your_api_key_here")
        print("ALPACA_SECRET_KEY=your_secret_key_here")
        print("ALPACA_BASE_URL=https://paper-api.alpaca.markets")
        return
    
    # Test Alpaca connection
    print("TESTING ALPACA CONNECTION:")
    alpaca = AlpacaClient()
    
    if not alpaca.enabled:
        print("❌ Alpaca client failed to initialize")
        return
    
    # Test connection
    if alpaca.test_connection():
        print("[OK] Alpaca connection successful!")
    else:
        print("[X] Alpaca connection failed")
        return
    
    # Get account info
    account_info = alpaca.get_account_info()
    if account_info:
        print(f"[OK] Account: {account_info['account_number']}")
        print(f"[OK] Paper Trading: {account_info['paper_trading']}")
        print(f"[OK] Buying Power: ${account_info['buying_power']:,.2f}")
    
    print()
    
    # Test data quality comparison
    print("DATA QUALITY COMPARISON:")
    print("Testing SPY price accuracy...")
    print()
    
    # Get Alpaca data
    alpaca_price = alpaca.get_current_price('SPY')
    
    # Get Yahoo Finance data
    try:
        spy_ticker = yf.Ticker('SPY')
        yahoo_data = spy_ticker.history(period="1d")
        yahoo_price = yahoo_data['Close'].iloc[-1] if not yahoo_data.empty else None
    except Exception as e:
        yahoo_price = None
        print(f"Yahoo Finance error: {e}")
    
    print("PRICE COMPARISON:")
    print(f"Alpaca (Real-time): ${alpaca_price:.2f}" if alpaca_price else "Alpaca: [X] Failed")
    print(f"Yahoo Finance (Delayed): ${yahoo_price:.2f}" if yahoo_price else "Yahoo: [X] Failed")
    
    if alpaca_price and yahoo_price:
        price_diff = abs(alpaca_price - yahoo_price)
        price_diff_pct = (price_diff / yahoo_price) * 100
        print(f"Difference: ${price_diff:.2f} ({price_diff_pct:.2f}%)")
        
        if price_diff_pct > 0.1:
            print("[OK] Significant difference detected - Alpaca provides more current data!")
        else:
            print("[INFO] Prices similar - both sources current")
    
    print()
    
    # Test option estimation
    print("OPTION ESTIMATION TEST:")
    if alpaca_price:
        # Test ATM call option estimation
        strike = round(alpaca_price)  # ATM strike
        option_estimate = alpaca.get_option_estimate('SPY', strike, 'CALL', '2025-08-04', alpaca_price)
        
        print(f"SPY ${strike} CALL (0DTE) estimate: ${option_estimate:.2f}" if option_estimate else "Option estimation failed")
        
        # Compare intrinsic value
        intrinsic = max(0, alpaca_price - strike)
        time_value = option_estimate - intrinsic if option_estimate else 0
        
        print(f"Intrinsic Value: ${intrinsic:.2f}")
        print(f"Time Value: ${time_value:.2f}")
    
    print()
    
    # Market status
    is_open = alpaca.is_market_open()
    print(f"Market Status: {'[OPEN]' if is_open else '[CLOSED]'}")
    
    print()
    print("=== SETUP COMPLETE ===")
    
    if alpaca.enabled and alpaca_price:
        print("[OK] Alpaca integration ready!")
        print("[OK] Real-time data available")
        print("[OK] Better option price estimation")
        print()
        print("NEXT STEPS:")
        print("1. Update position monitoring to use Alpaca data")
        print("2. Test improved profit/loss alerts")
        print("3. Compare performance with Yahoo Finance fallback")
    else:
        print("[X] Setup incomplete - check API keys and permissions")

if __name__ == "__main__":
    test_alpaca_setup()
