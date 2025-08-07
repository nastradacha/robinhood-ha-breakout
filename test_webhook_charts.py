#!/usr/bin/env python3
"""
Test Webhook Chart System - Enhanced Charts via Slack Webhook

Demonstrates the webhook-based chart delivery system that works with
your current Slack webhook configuration. Creates high-quality charts
and sends rich messages to Slack with chart information.
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from utils.webhook_chart_sender import WebhookChartSender


def create_sample_market_data(symbol: str = "SPY") -> pd.DataFrame:
    """Create realistic sample market data for testing."""
    # Generate 60 days of sample data
    dates = pd.date_range(
        start=datetime.now() - timedelta(days=60),
        end=datetime.now(),
        freq='D'
    )
    
    # Simulate realistic price movement
    np.random.seed(42)  # For reproducible results
    
    # Starting price
    base_price = 580.0
    prices = [base_price]
    
    # Generate realistic OHLCV data
    data = []
    
    for i, date in enumerate(dates):
        if i == 0:
            open_price = base_price
        else:
            # Small gap from previous close
            open_price = prices[-1] * (1 + np.random.normal(0, 0.002))
        
        # Daily volatility
        daily_range = open_price * 0.015  # 1.5% daily range
        
        # Generate OHLC
        high = open_price + np.random.uniform(0, daily_range)
        low = open_price - np.random.uniform(0, daily_range)
        close = low + np.random.uniform(0, high - low)
        
        # Volume (higher on big moves)
        price_change = abs(close - open_price) / open_price
        base_volume = 50000000
        volume = int(base_volume * (1 + price_change * 5) * np.random.uniform(0.5, 1.5))
        
        data.append({
            'Date': date,
            'Open': round(open_price, 2),
            'High': round(high, 2),
            'Low': round(low, 2),
            'Close': round(close, 2),
            'Volume': volume
        })
        
        prices.append(close)
    
    df = pd.DataFrame(data)
    df.set_index('Date', inplace=True)
    
    return df


def create_sample_analysis(market_data: pd.DataFrame) -> dict:
    """Create sample breakout analysis for testing."""
    current_price = market_data['Close'].iloc[-1]
    
    # Calculate some basic technical indicators
    sma_20 = market_data['Close'].rolling(20).mean().iloc[-1]
    price_change = (current_price - market_data['Close'].iloc[-2]) / market_data['Close'].iloc[-2]
    
    # Determine trend based on price vs SMA and recent change
    if current_price > sma_20 and price_change > 0.005:
        trend = "BULLISH"
        confidence = 75.5
    elif current_price < sma_20 and price_change < -0.005:
        trend = "BEARISH"
        confidence = 68.2
    else:
        trend = "NEUTRAL"
        confidence = 45.0
    
    # Support/resistance levels
    recent_high = market_data['High'].tail(20).max()
    recent_low = market_data['Low'].tail(20).min()
    
    analysis = {
        "current_price": current_price,
        "trend_direction": trend,
        "confidence": confidence,
        "breakout_strength": abs(price_change) * 100,
        "support_level": recent_low,
        "resistance_level": recent_high,
        "sma_20": sma_20,
        "volume_ratio": market_data['Volume'].iloc[-1] / market_data['Volume'].tail(10).mean(),
        "analysis_timestamp": datetime.now().isoformat()
    }
    
    return analysis


def test_webhook_chart_system():
    """Test the webhook chart system with sample data."""
    print("=" * 60)
    print("Webhook Chart System Test - Enhanced Charts")
    print("=" * 60)
    
    # Initialize chart sender
    chart_sender = WebhookChartSender()
    
    if not chart_sender.enabled:
        print("[ERROR] Slack webhook not configured!")
        print("Please set SLACK_WEBHOOK_URL in your .env file")
        return False
    
    print("[OK] Slack webhook configuration detected")
    print("[CHART] Generating enhanced charts with webhook delivery...")
    
    # Create sample data for multiple symbols
    symbols = ["SPY", "QQQ", "IWM"]
    
    for symbol in symbols:
        print(f"\n[{symbol}] Creating enhanced chart for {symbol}...")
        
        # Generate sample market data
        market_data = create_sample_market_data(symbol)
        
        # Create sample analysis
        analysis = create_sample_analysis(market_data)
        
        # Send enhanced chart alert
        success = chart_sender.send_enhanced_chart_alert(
            market_data=market_data,
            analysis=analysis,
            symbol=symbol
        )
        
        if success:
            print(f"[OK] {symbol} enhanced chart alert sent to Slack!")
        else:
            print(f"[ERROR] Failed to send {symbol} chart alert")
        
        # Small delay between charts
        import time
        time.sleep(3)
    
    print("\n" + "=" * 60)
    print("[DEMO] Webhook Chart Demo Complete!")
    print("Check your Slack channel to see the enhanced chart alerts.")
    print("\nKey Features Demonstrated:")
    print("• High-resolution chart generation (150 DPI)")
    print("• Professional dark theme with enhanced contrast")
    print("• Heikin-Ashi candles for smoother trend visualization")
    print("• Moving averages and technical indicators")
    print("• Rich Slack message blocks with analysis details")
    print("• Mobile-optimized formatting and annotations")
    print("\nNote: Charts are generated locally and referenced in messages.")
    print("To enable automatic image upload, add 'files:write' scope to your Slack bot.")
    
    return True


if __name__ == "__main__":
    try:
        success = test_webhook_chart_system()
        exit(0 if success else 1)
    except Exception as e:
        print(f"[ERROR] Test failed: {e}")
        exit(1)
