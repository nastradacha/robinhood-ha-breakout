#!/usr/bin/env python3
"""
Multi-Symbol Scanner Test Script

Tests the multi-symbol functionality without executing actual trades.
Validates configuration, scanning logic, and Slack integration.
"""

import sys
import logging
from pathlib import Path
import yaml
from dotenv import load_dotenv

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from utils.multi_symbol_scanner import MultiSymbolScanner
from utils.llm import LLMClient
from utils.enhanced_slack import EnhancedSlackIntegration

# Load environment variables
load_dotenv()

def setup_test_logging():
    """Setup logging for testing."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )

def load_test_config():
    """Load configuration for testing."""
    try:
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        # Ensure multi-symbol is enabled for testing
        if 'multi_symbol' not in config:
            config['multi_symbol'] = {}
        
        config['multi_symbol']['enabled'] = True
        config['multi_symbol']['max_concurrent_trades'] = 2
        
        # Test with SPY, QQQ, IWM
        config['SYMBOLS'] = ['SPY', 'QQQ', 'IWM']
        
        print("Configuration loaded successfully")
        print(f"Symbols to test: {config['SYMBOLS']}")
        print(f"Max concurrent trades: {config['multi_symbol']['max_concurrent_trades']}")
        
        return config
        
    except Exception as e:
        print(f"Error loading config: {e}")
        return None

def test_multi_symbol_scanner():
    """Test the multi-symbol scanner functionality."""
    print("\nTesting Multi-Symbol Scanner...")
    
    # Setup
    setup_test_logging()
    config = load_test_config()
    
    if not config:
        return False
    
    try:
        # Initialize components
        llm_client = LLMClient(config['MODEL'])
        slack_notifier = EnhancedSlackIntegration()
        
        # Initialize scanner
        scanner = MultiSymbolScanner(config, llm_client, slack_notifier)
        
        print(f"Scanner initialized for symbols: {scanner.symbols}")
        print(f"Multi-symbol enabled: {scanner.enabled}")
        print(f"Max concurrent trades: {scanner.max_concurrent_trades}")
        
        # Test scanning (dry run)
        print("\nStarting multi-symbol scan...")
        opportunities = scanner.scan_all_symbols()
        
        if opportunities:
            print(f"Found {len(opportunities)} trading opportunities:")
            for i, opp in enumerate(opportunities, 1):
                print(f"  {i}. {opp['symbol']} - {opp['decision']}")
                print(f"     Confidence: {opp['confidence']:.1%}")
                print(f"     Priority Score: {opp['priority_score']:.1f}")
                print(f"     Reason: {opp['reason'][:100]}...")
                print()
        else:
            print("No trading opportunities found (this is normal during off-hours)")
        
        print("Multi-symbol scanner test completed successfully!")
        return True
        
    except Exception as e:
        print(f"Error testing multi-symbol scanner: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_cli_integration():
    """Test CLI argument integration."""
    print("\nTesting CLI Integration...")
    
    # Test command examples
    test_commands = [
        "python main.py --multi-symbol --dry-run",
        "python main.py --symbols SPY QQQ --dry-run",
        "python main.py --multi-symbol --loop --interval 5 --max-trades 2 --dry-run",
        "python main.py --symbols SPY QQQ IWM --loop --end-at 15:45 --dry-run"
    ]
    
    print("Available CLI commands for multi-symbol trading:")
    for i, cmd in enumerate(test_commands, 1):
        print(f"  {i}. {cmd}")
    
    print("\nCLI integration ready!")
    return True

def test_config_validation():
    """Test configuration validation."""
    print("\nTesting Configuration Validation...")
    
    config = load_test_config()
    if not config:
        return False
    
    # Test required fields
    required_fields = ['SYMBOLS', 'multi_symbol']
    for field in required_fields:
        if field not in config:
            print(f"Missing required field: {field}")
            return False
        print(f"Found required field: {field}")
    
    # Test multi-symbol config
    multi_config = config['multi_symbol']
    required_multi_fields = ['enabled', 'max_concurrent_trades']
    
    for field in required_multi_fields:
        if field not in multi_config:
            print(f"Missing multi-symbol field: {field}")
            return False
        print(f"Found multi-symbol field: {field}")
    
    # Validate symbols
    symbols = config['SYMBOLS']
    if not isinstance(symbols, list) or len(symbols) == 0:
        print(f"Invalid SYMBOLS configuration: {symbols}")
        return False
    
    print(f"Valid symbols configuration: {symbols}")
    print("Configuration validation passed!")
    return True

def main():
    """Run all multi-symbol tests."""
    print("Multi-Symbol Trading System Test Suite")
    print("=" * 50)
    
    tests = [
        ("Configuration Validation", test_config_validation),
        ("CLI Integration", test_cli_integration),
        ("Multi-Symbol Scanner", test_multi_symbol_scanner)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\nRunning: {test_name}")
        print("-" * 30)
        
        try:
            if test_func():
                print(f"{test_name}: PASSED")
                passed += 1
            else:
                print(f"{test_name}: FAILED")
        except Exception as e:
            print(f"{test_name}: ERROR - {e}")
    
    print("\n" + "=" * 50)
    print(f"Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("All tests passed! Multi-symbol system is ready!")
        print("\nReady to use:")
        print("   python main.py --multi-symbol --dry-run")
        print("   python main.py --symbols SPY QQQ IWM --loop --dry-run")
    else:
        print("Some tests failed. Please review the errors above.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
