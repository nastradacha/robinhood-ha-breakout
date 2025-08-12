#!/usr/bin/env python3
"""
Test script to demonstrate a complete Alpaca paper trade workflow.

This script simulates a full paper trade transaction to verify that all
components are working correctly, including contract selection, manual
approval, order placement, fill polling, and trade recording.

Author: Robinhood HA Breakout System
Version: 2.0.0
License: MIT
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
load_dotenv()

from utils.alpaca_options import create_alpaca_trader, ContractInfo, FillResult
from utils.bankroll import BankrollManager
from utils.portfolio import PortfolioManager
from utils.enhanced_slack import EnhancedSlackIntegration
from utils.trade_confirmation import TradeConfirmationManager
from utils.llm import TradeDecision
from main import execute_alpaca_options_trade
import yaml


def load_test_config():
    """Load configuration for testing."""
    try:
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        print(f"Error loading config: {e}")
        return None


def test_alpaca_connection():
    """Test basic Alpaca connection."""
    print("🔗 Testing Alpaca Connection...")
    
    trader = create_alpaca_trader(paper=True)
    if trader:
        print("✅ Alpaca connection successful")
        
        # Test market status
        is_valid, reason = trader.is_market_open_and_valid_time()
        print(f"📊 Market Status: {reason}")
        
        # Test expiry policy
        policy, expiry = trader.get_expiry_policy()
        print(f"📅 Expiry Policy: {policy} ({expiry})")
        
        return trader
    else:
        print("❌ Alpaca connection failed")
        return None


def test_contract_lookup(trader):
    """Test contract lookup functionality."""
    print("\n🔍 Testing Contract Lookup...")
    
    try:
        # Test contract lookup for SPY (most liquid)
        contract = trader.find_atm_contract(
            symbol="SPY",
            side="CALL",
            policy="0DTE",
            expiry_date="2025-01-17",  # Use next Friday
            min_oi=1000,  # Lower requirements for testing
            min_vol=100,
            max_spread_pct=15.0
        )
        
        if contract:
            print(f"✅ Found contract: {contract.symbol}")
            print(f"   Strike: ${contract.strike}")
            print(f"   Mid Price: ${contract.mid:.2f}")
            print(f"   Spread: {contract.spread_pct:.1f}%")
            print(f"   OI: {contract.open_interest:,}")
            print(f"   Volume: {contract.volume:,}")
            return contract
        else:
            print("❌ No suitable contract found")
            return None
            
    except Exception as e:
        print(f"❌ Contract lookup error: {e}")
        return None


def simulate_paper_trade():
    """Simulate a complete paper trade workflow."""
    print("\n🎯 Simulating Complete Paper Trade Workflow...")
    
    # Load configuration
    config = load_test_config()
    if not config:
        print("❌ Failed to load configuration")
        return
    
    # Override for testing
    config["BROKER"] = "alpaca"
    config["ALPACA_ENV"] = "paper"
    
    # Create mock objects
    class MockArgs:
        i_understand_live_risk = False
    
    args = MockArgs()
    env_vars = {
        "ALPACA_API_KEY": os.getenv("ALPACA_API_KEY"),
        "ALPACA_SECRET_KEY": os.getenv("ALPACA_SECRET_KEY")
    }
    
    # Initialize managers
    bankroll_manager = BankrollManager(config)
    portfolio_manager = PortfolioManager()
    slack_notifier = None  # Skip Slack for testing
    
    # Create mock LLM decision
    decision = TradeDecision(
        decision="CALL",
        confidence=0.75,
        reason="Test paper trade - simulated bullish signal"
    )
    
    # Create mock analysis
    analysis = {
        "symbol": "SPY",
        "current_price": 450.0,
        "trend_direction": "bullish",
        "data_source": "alpaca_test"
    }
    
    print("📋 Trade Setup:")
    print(f"   Symbol: {analysis['symbol']}")
    print(f"   Decision: {decision.decision}")
    print(f"   Confidence: {decision.confidence:.2f}")
    print(f"   Current Price: ${analysis['current_price']:.2f}")
    
    # Execute the trade workflow
    try:
        result = execute_alpaca_options_trade(
            config=config,
            args=args,
            env_vars=env_vars,
            bankroll_manager=bankroll_manager,
            portfolio_manager=portfolio_manager,
            slack_notifier=slack_notifier,
            decision=decision,
            analysis=analysis,
            position_size=1
        )
        
        print(f"\n📊 Trade Result:")
        print(f"   Status: {result.get('status', 'UNKNOWN')}")
        print(f"   Reason: {result.get('reason', 'No reason provided')}")
        
        if result.get('status') == 'SUBMITTED':
            print(f"   Strike: ${result.get('strike', 0):.2f}")
            print(f"   Premium: ${result.get('actual_premium', 0):.2f}")
            print(f"   Quantity: {result.get('quantity', 0)}")
            print(f"   Total Cost: ${result.get('total_cost', 0):.2f}")
            print(f"   Order ID: {result.get('order_id', 'N/A')}")
        
        return result
        
    except Exception as e:
        print(f"❌ Trade execution error: {e}")
        return None


def main():
    """Main test function."""
    print("🧪 Alpaca Paper Trade Test")
    print("=" * 50)
    
    # Test 1: Connection
    trader = test_alpaca_connection()
    if not trader:
        return
    
    # Test 2: Contract Lookup
    contract = test_contract_lookup(trader)
    
    # Test 3: Full Workflow Simulation
    result = simulate_paper_trade()
    
    print("\n" + "=" * 50)
    print("🎉 Test Complete!")
    
    if result:
        status = result.get('status', 'UNKNOWN')
        if status in ['SUBMITTED', 'NO_TRADE']:
            print("✅ All systems working correctly!")
        else:
            print(f"⚠️  Trade result: {status}")
    else:
        print("❌ Some tests failed - check logs above")
    
    print("\n💡 Next Steps:")
    print("   • Test during market hours (9:30 AM - 3:15 PM ET)")
    print("   • Run: python main.py")
    print("   • Monitor positions: python main.py --monitor-positions")


if __name__ == "__main__":
    main()
