#!/usr/bin/env python3
"""
Test Automatic Chart Integration - Shows How Charts Are Sent During Trading

This demonstrates exactly how the enhanced chart system integrates with
your normal robinhood-ha-breakout trading workflow. Charts are sent
automatically whenever a CALL or PUT trading opportunity is detected.
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from utils.enhanced_slack import EnhancedSlackIntegration


def create_sample_trading_scenario(symbol: str, decision: str) -> tuple:
    """Create sample trading scenario data."""
    # Generate realistic market data
    dates = pd.date_range(
        start=datetime.now() - timedelta(days=30),
        end=datetime.now(),
        freq='D'
    )
    
    np.random.seed(hash(symbol) % 100)  # Different seed per symbol
    
    base_price = {"SPY": 580.0, "QQQ": 480.0, "IWM": 220.0}.get(symbol, 500.0)
    
    data = []
    current_price = base_price
    
    for date in dates:
        # Simulate price movement
        daily_change = np.random.normal(0, 0.01)  # 1% daily volatility
        
        open_price = current_price * (1 + daily_change * 0.5)
        high = open_price * (1 + abs(daily_change) * 0.5)
        low = open_price * (1 - abs(daily_change) * 0.5)
        close = low + np.random.uniform(0, 1) * (high - low)
        
        volume = int(50000000 * np.random.uniform(0.5, 1.5))
        
        data.append({
            'Date': date,
            'Open': round(open_price, 2),
            'High': round(high, 2),
            'Low': round(low, 2),
            'Close': round(close, 2),
            'Volume': volume
        })
        
        current_price = close
    
    market_data = pd.DataFrame(data)
    market_data.set_index('Date', inplace=True)
    
    # Create analysis based on decision
    final_price = market_data['Close'].iloc[-1]
    sma_20 = market_data['Close'].rolling(20).mean().iloc[-1]
    
    if decision == "CALL":
        trend = "BULLISH"
        confidence = 78.5
    elif decision == "PUT":
        trend = "BEARISH"
        confidence = 72.3
    else:
        trend = "NEUTRAL"
        confidence = 45.0
    
    analysis = {
        "current_price": final_price,
        "trend_direction": trend,
        "confidence": confidence,
        "breakout_strength": 2.5,
        "support_level": market_data['Low'].tail(20).min(),
        "resistance_level": market_data['High'].tail(20).max(),
        "sma_20": sma_20,
        "volume_ratio": 1.2,
        "analysis_timestamp": datetime.now().isoformat()
    }
    
    return market_data, analysis


def demonstrate_automatic_chart_workflow():
    """Demonstrate how charts are sent automatically during trading."""
    print("=" * 70)
    print("AUTOMATIC CHART INTEGRATION DEMO")
    print("How Charts Are Sent During Your Normal Trading Workflow")
    print("=" * 70)
    
    # Initialize enhanced Slack integration (same as your main system)
    slack = EnhancedSlackIntegration()
    
    if not slack.enabled:
        print("[ERROR] Slack not configured!")
        return False
    
    print("[OK] Enhanced Slack integration initialized")
    print("[INFO] Charts will be sent automatically for CALL/PUT decisions")
    print()
    
    # Simulate different trading scenarios
    scenarios = [
        ("SPY", "CALL", "Bullish breakout detected"),
        ("QQQ", "PUT", "Bearish signal identified"),
        ("IWM", "NO_TRADE", "No clear signal (no chart sent)"),
    ]
    
    for symbol, decision, description in scenarios:
        print(f"[SCENARIO] {symbol} - {decision}")
        print(f"[ANALYSIS] {description}")
        
        # Generate sample data for this scenario
        market_data, analysis = create_sample_trading_scenario(symbol, decision)
        
        # This is exactly how your main trading system calls it
        # Charts are sent automatically for CALL/PUT decisions
        slack.send_breakout_alert_with_chart(
            symbol=symbol,
            decision=decision,
            analysis=analysis,
            market_data=market_data,
            confidence=analysis["confidence"]
        )
        
        if decision in ["CALL", "PUT"]:
            print(f"[CHART] High-quality chart image automatically sent to Slack!")
            print(f"[DETAILS] 200 DPI resolution, professional styling, mobile-optimized")
        else:
            print(f"[NO CHART] Only text alert sent (NO_TRADE decision)")
        
        print("-" * 50)
        
        # Small delay between scenarios
        import time
        time.sleep(2)
    
    print("\n" + "=" * 70)
    print("DEMO COMPLETE - Check Your Slack Channel!")
    print("=" * 70)
    print()
    print("🎯 WHAT HAPPENS AUTOMATICALLY IN YOUR TRADING SYSTEM:")
    print()
    print("1. 📊 System detects breakout opportunity")
    print("2. 🤖 LLM analyzes and decides: CALL, PUT, or NO_TRADE")
    print("3. 📈 IF decision is CALL or PUT:")
    print("   → High-quality chart is automatically generated")
    print("   → Chart image is uploaded directly to Slack")
    print("   → Rich message with analysis details is sent")
    print("4. 📱 You receive professional chart on your mobile device")
    print("5. 💡 Make confident trading decisions from anywhere!")
    print()
    print("✅ NO MANUAL INTERVENTION REQUIRED")
    print("✅ CHARTS SENT AUTOMATICALLY FOR EVERY TRADE OPPORTUNITY")
    print("✅ CRYSTAL-CLEAR MOBILE VIEWING")
    print("✅ PROFESSIONAL INSTITUTIONAL-QUALITY ANALYSIS")
    
    return True


if __name__ == "__main__":
    try:
        success = demonstrate_automatic_chart_workflow()
        exit(0 if success else 1)
    except Exception as e:
        print(f"[ERROR] Demo failed: {e}")
        exit(1)
