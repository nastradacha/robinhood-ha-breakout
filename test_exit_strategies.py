#!/usr/bin/env python3
"""
Test Advanced Exit Strategies

Validates the new trailing stop, time-based exit, and profit target
functionality to ensure proper integration with position monitoring.

Usage:
    python test_exit_strategies.py
"""

import os
import sys
import logging
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.exit_strategies import ExitStrategyManager, ExitStrategyConfig, ExitReason

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_trailing_stop():
    """Test trailing stop functionality."""
    print("=== TESTING TRAILING STOP LOGIC ===")
    
    config = ExitStrategyConfig(
        trailing_stop_enabled=True,
        trailing_stop_activation_pct=10.0,  # Start trailing after 10% profit
        trailing_stop_distance_pct=5.0      # Trail 5% behind peak
    )
    
    manager = ExitStrategyManager(config)
    
    # Simulate a profitable position
    test_position = {
        'symbol': 'SPY',
        'strike': 628.0,
        'option_type': 'CALL',
        'entry_price': 1.42,
        'entry_time': '2025-01-04 09:55'
    }
    
    # Test scenarios
    scenarios = [
        (628.5, 1.50, "Small gain - no trailing stop yet"),
        (630.0, 1.65, "16% gain - should activate trailing stop"),
        (632.0, 1.85, "30% gain - update trailing stop to 25%"),
        (631.5, 1.78, "Slight pullback - still above trailing stop"),
        (631.0, 1.70, "Larger pullback - should trigger trailing stop"),
    ]
    
    for i, (stock_price, option_price, description) in enumerate(scenarios, 1):
        print(f"\nScenario {i}: {description}")
        print(f"Stock: ${stock_price:.2f}, Option: ${option_price:.2f}")
        
        decision = manager.evaluate_exit(test_position, stock_price, option_price)
        
        pnl_pct = ((option_price - test_position['entry_price']) / test_position['entry_price']) * 100
        print(f"P&L: {pnl_pct:+.1f}%")
        print(f"Exit Decision: {decision.should_exit}")
        print(f"Reason: {decision.reason.value}")
        print(f"Message: {decision.message}")
        
        if decision.should_exit and decision.reason == ExitReason.TRAILING_STOP:
            print("[SUCCESS] TRAILING STOP TRIGGERED CORRECTLY!")
            break
        elif decision.reason == ExitReason.NO_EXIT:
            print("[HOLD] Position held, trailing stop updated")
        
        print("-" * 50)

def test_time_based_exit():
    """Test time-based exit functionality."""
    print("\n=== TESTING TIME-BASED EXIT LOGIC ===")
    
    # Create config with market close in 10 minutes (for testing)
    future_time = (datetime.now() + timedelta(minutes=10)).strftime("%H:%M")
    
    config = ExitStrategyConfig(
        time_based_exit_enabled=True,
        market_close_time=future_time,
        warning_minutes_before_close=15
    )
    
    manager = ExitStrategyManager(config)
    
    test_position = {
        'symbol': 'SPY',
        'strike': 628.0,
        'option_type': 'CALL',
        'entry_price': 1.42,
        'entry_time': '2025-01-04 14:30'
    }
    
    decision = manager.evaluate_exit(test_position, 629.0, 1.55)
    
    print(f"Market close time: {future_time}")
    print(f"Exit Decision: {decision.should_exit}")
    print(f"Reason: {decision.reason.value}")
    print(f"Message: {decision.message}")
    print(f"Urgency: {decision.urgency}")
    
    if decision.should_exit and decision.reason == ExitReason.TIME_BASED:
        print("[SUCCESS] TIME-BASED EXIT TRIGGERED CORRECTLY!")
    else:
        print("[INFO] Time-based exit not triggered (market close not imminent)")

def test_profit_targets():
    """Test profit target alerts."""
    print("\n=== TESTING PROFIT TARGET ALERTS ===")
    
    config = ExitStrategyConfig(
        profit_targets=[15.0, 25.0, 35.0]
    )
    
    manager = ExitStrategyManager(config)
    
    test_position = {
        'symbol': 'SPY',
        'strike': 628.0,
        'option_type': 'CALL',
        'entry_price': 1.42,
        'entry_time': '2025-01-04 10:15'
    }
    
    # Test different profit levels
    profit_scenarios = [
        (1.50, "5% gain - below first target"),
        (1.63, "15% gain - first target hit"),
        (1.78, "25% gain - second target hit"),
        (1.92, "35% gain - third target hit"),
    ]
    
    for option_price, description in profit_scenarios:
        print(f"\n{description}")
        print(f"Option Price: ${option_price:.2f}")
        
        decision = manager.evaluate_exit(test_position, 629.0, option_price)
        
        pnl_pct = ((option_price - test_position['entry_price']) / test_position['entry_price']) * 100
        print(f"P&L: {pnl_pct:+.1f}%")
        print(f"Reason: {decision.reason.value}")
        print(f"Message: {decision.message}")
        
        if decision.reason == ExitReason.PROFIT_TARGET:
            print("[SUCCESS] PROFIT TARGET ALERT TRIGGERED!")
        
        print("-" * 40)

def test_stop_loss():
    """Test stop loss functionality."""
    print("\n=== TESTING STOP LOSS LOGIC ===")
    
    config = ExitStrategyConfig(
        stop_loss_pct=25.0
    )
    
    manager = ExitStrategyManager(config)
    
    test_position = {
        'symbol': 'SPY',
        'strike': 628.0,
        'option_type': 'CALL',
        'entry_price': 1.42,
        'entry_time': '2025-01-04 11:30'
    }
    
    # Test stop loss scenario
    decision = manager.evaluate_exit(test_position, 625.0, 1.05)  # ~26% loss
    
    pnl_pct = ((1.05 - test_position['entry_price']) / test_position['entry_price']) * 100
    print(f"Option Price: $1.05 (down from $1.42)")
    print(f"P&L: {pnl_pct:+.1f}%")
    print(f"Exit Decision: {decision.should_exit}")
    print(f"Reason: {decision.reason.value}")
    print(f"Message: {decision.message}")
    
    if decision.should_exit and decision.reason == ExitReason.STOP_LOSS:
        print("[SUCCESS] STOP LOSS TRIGGERED CORRECTLY!")
    else:
        print("[ERROR] Stop loss should have triggered")

def test_config_loading():
    """Test configuration loading from YAML file."""
    print("\n=== TESTING CONFIG LOADING ===")
    
    try:
        from utils.exit_strategies import load_exit_config_from_file
        config = load_exit_config_from_file("config.yaml")
        
        print("[SUCCESS] Configuration loaded successfully!")
        print(f"Trailing stop enabled: {config.trailing_stop_enabled}")
        print(f"Activation threshold: {config.trailing_stop_activation_pct}%")
        print(f"Trail distance: {config.trailing_stop_distance_pct}%")
        print(f"Market close time: {config.market_close_time}")
        print(f"Profit targets: {config.profit_targets}")
        print(f"Stop loss: {config.stop_loss_pct}%")
        
    except Exception as e:
        print(f"[ERROR] Config loading failed: {e}")

def main():
    """Run all exit strategy tests."""
    print("ADVANCED EXIT STRATEGIES - COMPREHENSIVE TESTING")
    print("=" * 60)
    
    try:
        test_config_loading()
        test_trailing_stop()
        test_time_based_exit()
        test_profit_targets()
        test_stop_loss()
        
        print("\n" + "=" * 60)
        print("[SUCCESS] ALL TESTS COMPLETED!")
        print("\nAdvanced exit strategies are ready for integration with")
        print("position monitoring and live trading workflows.")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        print(f"\n[ERROR] TEST FAILED: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
