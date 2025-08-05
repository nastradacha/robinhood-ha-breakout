#!/usr/bin/env python3
"""
Test script for Performance Analytics Dashboard

Creates sample trading data and validates all analytics functionality
including metrics calculation, report generation, and chart creation.
"""

import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from analytics_dashboard import TradingAnalytics

def create_sample_trade_data():
    """Create realistic sample trading data for testing."""
    print("Creating sample trading data...")
    
    # Ensure logs directory exists
    os.makedirs('logs', exist_ok=True)
    
    # Generate 50 sample trades over 30 days
    np.random.seed(42)  # For reproducible results
    
    trades = []
    start_date = datetime.now() - timedelta(days=30)
    
    for i in range(50):
        # Random trade timing
        trade_date = start_date + timedelta(days=np.random.randint(0, 30))
        
        # Simulate realistic option trading
        option_type = np.random.choice(['CALL', 'PUT'], p=[0.6, 0.4])  # Slightly more calls
        strike = np.random.choice([630, 635, 640, 645, 650])  # ATM strikes around SPY
        
        # Simulate win/loss with 55% win rate (good but realistic)
        is_winner = np.random.random() < 0.55
        
        if is_winner:
            # Winning trades: 5% to 25% profit
            pnl = np.random.uniform(5, 25)
        else:
            # Losing trades: -5% to -25% loss
            pnl = np.random.uniform(-25, -5)
        
        # Convert percentage to dollar amount (assuming $100 average position)
        pnl_dollars = pnl
        
        trades.append({
            'timestamp': trade_date.strftime('%Y-%m-%d %H:%M:%S'),
            'symbol': 'SPY',
            'option_type': option_type,
            'strike': strike,
            'action': 'CLOSE',
            'quantity': 1,
            'entry_price': 100.0,  # Simplified
            'exit_price': 100.0 + pnl_dollars,
            'pnl': pnl_dollars,
            'pnl_pct': pnl,
            'reason': 'Manual close' if is_winner else 'Stop loss'
        })
    
    # Create trade log CSV
    df = pd.DataFrame(trades)
    df.to_csv('logs/trade_log.csv', index=False)
    print(f"Created sample trade log with {len(trades)} trades")
    
    return df

def create_sample_bankroll_data():
    """Create sample bankroll data for testing."""
    print("Creating sample bankroll data...")
    
    bankroll_data = {
        'starting_bankroll': 500.0,
        'current_bankroll': 650.0,  # 30% gain
        'peak_bankroll': 700.0,
        'total_trades': 50,
        'total_pnl': 150.0,
        'last_updated': datetime.now().isoformat()
    }
    
    with open('bankroll.json', 'w') as f:
        json.dump(bankroll_data, f, indent=2)
    
    print("Created sample bankroll data")
    return bankroll_data

def test_analytics_functionality():
    """Test all analytics dashboard functionality."""
    print("\n" + "="*60)
    print("TESTING ANALYTICS DASHBOARD FUNCTIONALITY")
    print("="*60)
    
    # Initialize analytics
    analytics = TradingAnalytics()
    
    # Test 1: Load data
    print("\n1. Testing data loading...")
    success = analytics.load_data()
    print(f"   Data loading: {'SUCCESS' if success else 'FAILED'}")
    
    if not analytics.trades_df.empty:
        print(f"   Loaded {len(analytics.trades_df)} trades")
    
    # Test 2: Calculate metrics
    print("\n2. Testing metrics calculation...")
    metrics = analytics.calculate_performance_metrics()
    print(f"   Metrics calculation: {'SUCCESS' if metrics else 'FAILED'}")
    
    if metrics:
        print(f"   Win rate: {metrics.get('win_rate', 0):.1f}%")
        print(f"   Total P&L: ${metrics.get('total_pnl', 0):.2f}")
        print(f"   Risk-reward ratio: {metrics.get('risk_reward_ratio', 0):.2f}:1")
    
    # Test 3: Generate report
    print("\n3. Testing report generation...")
    try:
        report = analytics.generate_performance_report('cli')
        print("   Report generation: SUCCESS")
        print(f"   Report length: {len(report)} characters")
    except Exception as e:
        print(f"   Report generation: FAILED - {e}")
    
    # Test 4: Performance grading
    print("\n4. Testing performance grading...")
    try:
        grade = analytics._calculate_performance_grade(metrics)
        print("   Performance grading: SUCCESS")
        print(f"   Grade: {grade['letter']} ({grade['score']:.1f}/100)")
        print(f"   Assessment: {grade['assessment']}")
    except Exception as e:
        print(f"   Performance grading: FAILED - {e}")
    
    # Test 5: Recommendations
    print("\n5. Testing recommendations...")
    try:
        recommendations = analytics._generate_recommendations(metrics)
        print("   Recommendations: SUCCESS")
        print(f"   Generated {len(recommendations)} recommendations")
        for i, rec in enumerate(recommendations[:3], 1):  # Show first 3
            print(f"   {i}. {rec}")
    except Exception as e:
        print(f"   Recommendations: FAILED - {e}")
    
    # Test 6: Chart generation
    print("\n6. Testing chart generation...")
    try:
        chart_files = analytics.create_performance_charts()
        print("   Chart generation: SUCCESS")
        print(f"   Generated {len(chart_files)} chart files")
        for chart in chart_files:
            print(f"   - {chart}")
    except Exception as e:
        print(f"   Chart generation: FAILED - {e}")
    
    # Test 7: Slack integration (dry run)
    print("\n7. Testing Slack integration...")
    try:
        # This will test the logic but won't actually send (no webhook configured)
        success = analytics.send_slack_summary()
        print(f"   Slack integration: {'SUCCESS' if success else 'SKIPPED (no config)'}")
    except Exception as e:
        print(f"   Slack integration: FAILED - {e}")
    
    print("\n" + "="*60)
    print("ANALYTICS TESTING COMPLETE")
    print("="*60)
    
    return analytics

def display_sample_report(analytics):
    """Display the full sample report."""
    print("\n" + "="*60)
    print("SAMPLE PERFORMANCE REPORT")
    print("="*60)
    
    report = analytics.generate_performance_report('cli')
    print(report)

def main():
    """Main test execution."""
    print("TESTING ROBINHOOD HA BREAKOUT ANALYTICS DASHBOARD")
    print("="*60)
    
    # Create sample data
    trades_df = create_sample_trade_data()
    bankroll_data = create_sample_bankroll_data()
    
    # Test analytics functionality
    analytics = test_analytics_functionality()
    
    # Display sample report
    display_sample_report(analytics)
    
    print("\nANALYTICS DASHBOARD TESTING COMPLETE!")
    print("\nYou can now run the analytics dashboard with:")
    print("  python analytics_dashboard.py --mode cli")
    print("  python analytics_dashboard.py --charts")
    print("  python analytics_dashboard.py --slack-summary")

if __name__ == "__main__":
    main()
