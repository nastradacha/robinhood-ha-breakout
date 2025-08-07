#!/usr/bin/env python3
"""
Test Enhanced Slack Chart System - High-Quality Chart Images

Demonstrates the enhanced Slack chart functionality with:
- High-resolution chart generation (200 DPI)
- Professional styling and clear visual elements
- Direct image upload to Slack channels
- Mobile-optimized chart formatting

This test creates sample market data and sends a professional
breakout analysis chart to your Slack channel.
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from utils.enhanced_slack_charts import EnhancedSlackChartSender


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


def test_enhanced_chart_system():
    """Test the enhanced Slack chart system with sample data."""
    print("=" * 60)
    print("Enhanced Slack Chart System Test")
    print("=" * 60)
    
    # Initialize chart sender
    chart_sender = EnhancedSlackChartSender()
    
    if not chart_sender.enabled:
        print("[ERROR] Slack not configured!")
        print("Please set SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN in your .env file")
        return False
    
    print("[OK] Slack configuration detected")
    print("[CHART] Generating high-quality sample chart...")
    
    # Create sample data for multiple symbols
    symbols = ["SPY", "QQQ", "IWM"]
    
    for symbol in symbols:
        print(f"\n[{symbol}] Creating chart for {symbol}...")
        
        # Generate sample market data
        market_data = create_sample_market_data(symbol)
        
        # Create sample analysis
        analysis = create_sample_analysis(market_data)
        
        # Create custom message
        trend_emoji = "📈" if analysis["trend_direction"] == "BULLISH" else "📉" if analysis["trend_direction"] == "BEARISH" else "📊"
        
        message = f"""{trend_emoji} **ENHANCED CHART DEMO - {symbol}**

**🎯 High-Quality Chart Features:**
• 200 DPI resolution for crystal-clear mobile viewing
• Professional dark theme with enhanced contrast
• Large fonts and thick lines for readability
• Heikin-Ashi candles for smoother trend visualization
• Support/resistance levels and moving averages
• Volume analysis with moving average overlay

**📊 Current Analysis:**
• **Price:** ${analysis['current_price']:.2f}
• **Trend:** {analysis['trend_direction']}
• **Confidence:** {analysis['confidence']:.1f}%
• **Breakout Strength:** {analysis['breakout_strength']:.2f}

**📱 Mobile-Optimized:** This chart is designed for clear viewing on mobile devices with enhanced visual clarity and professional presentation.

⬆️ **Professional chart image attached above**"""
        
        # Send chart to Slack
        success = chart_sender.send_breakout_chart_to_slack(
            market_data=market_data,
            analysis=analysis,
            symbol=symbol,
            message_text=message
        )
        
        if success:
            print(f"[OK] {symbol} chart sent successfully to Slack!")
        else:
            print(f"[ERROR] Failed to send {symbol} chart to Slack")
        
        # Small delay between charts
        import time
        time.sleep(3)
    
    print("\n" + "=" * 60)
    print("[DEMO] Enhanced Chart Demo Complete!")
    print("Check your Slack channel to see the high-quality charts.")
    print("\nKey Improvements:")
    print("• 200 DPI resolution (vs 100 DPI before)")
    print("• Larger fonts and thicker lines for mobile clarity")
    print("• Professional GitHub dark theme")
    print("• Enhanced visual elements and annotations")
    print("• Direct image upload to Slack channels")
    print("• Optimized file sizes for fast mobile loading")
    
    return True


if __name__ == "__main__":
    try:
        success = test_enhanced_chart_system()
        exit(0 if success else 1)
    except Exception as e:
        print(f"[ERROR] Test failed: {e}")
        exit(1)
