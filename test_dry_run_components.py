"""
Test script for US-FA-014 dry run components
Tests all safety hooks, configuration, and monitoring without requiring env vars
"""

import os
import sys
import yaml
import tempfile
import json
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

def test_config_loading():
    """Test dry run configuration loading."""
    print("Testing configuration loading...")
    
    config_path = "config/config_dryrun.yaml"
    if not os.path.exists(config_path):
        print(f"Config file missing: {config_path}")
        return False
    
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Check required sections
        required_sections = ['app', 'broker', 'validation', 'risk', 'logging', 'notifiers', 'monitoring']
        for section in required_sections:
            if section not in config:
                print(f"Missing config section: {section}")
                return False
        
        # Check critical values
        if config['broker']['env'] != 'paper':
            print(f"Broker env should be 'paper', got: {config['broker']['env']}")
            return False
        
        if config['broker']['position_sizing_pct'] != 0.5:
            print(f"Position sizing should be 0.5, got: {config['broker']['position_sizing_pct']}")
            return False
        
        print("Configuration loading successful")
        return True
        
    except Exception as e:
        print(f"Config loading failed: {e}")
        return False

def test_safety_hooks():
    """Test safety hook functions."""
    print("Testing safety hooks...")
    
    try:
        from utils.safety_hooks import (
            parse_hhmm, parse_duration, session_phase, 
            ValidationPauseManager, HealthSnapshotManager,
            validate_dry_run_config
        )
        
        # Test time parsing
        time_obj = parse_hhmm("15:30")
        if time_obj.hour != 15 or time_obj.minute != 30:
            print("Time parsing failed")
            return False
        
        # Test duration parsing
        duration = parse_duration("30m")
        if duration != timedelta(minutes=30):
            print("Duration parsing failed")
            return False
        
        # Test session phase
        phase = session_phase()
        if phase not in ["Weekend", "Pre-market", "Regular session", "After-hours"]:
            print(f"Invalid session phase: {phase}")
            return False
        
        # Test config validation
        test_config = {
            'broker': {'env': 'paper', 'position_sizing_pct': 0.5},
            'validation': {'strict': True},
            'logging': {'json_metrics_file': 'test.jsonl'}
        }
        
        if not validate_dry_run_config(test_config):
            print("Config validation failed")
            return False
        
        print("Safety hooks working correctly")
        return True
        
    except Exception as e:
        print(f"Safety hooks test failed: {e}")
        return False

def test_logging_setup():
    """Test enhanced logging system."""
    print("Testing logging setup...")
    
    try:
        from utils.logging_setup import setup_logging, MetricsLogger
        
        # Create test config
        test_config = {
            'logging': {
                'file_prefix': 'logs/test_dryrun',
                'rotate_mb': 1,
                'backups': 2,
                'level': 'INFO',
                'json_metrics_file': 'logs/test_metrics.jsonl'
            }
        }
        
        # Test metrics logger
        metrics_logger = MetricsLogger('logs/test_metrics.jsonl')
        
        # Test writing metrics
        metrics_logger.write(test_type="unit_test", value=123)
        
        # Test system snapshot
        metrics_logger.snapshot_system(extra={"test": True})
        
        # Test incident logging
        metrics_logger.log_incident(
            event_type="test_incident",
            severity="info",
            symbol="TEST",
            context="Unit test",
            action="none",
            notes="Test incident"
        )
        
        # Verify files were created
        if not os.path.exists('logs/test_metrics.jsonl'):
            print("Metrics file not created")
            return False
        
        if not os.path.exists('monitoring/incident_log.csv'):
            print("Incident log not created")
            return False
        
        print("Logging setup working correctly")
        return True
        
    except Exception as e:
        print(f"Logging setup test failed: {e}")
        return False

def test_vix_monitor_config():
    """Test VIX monitor config handling."""
    print("Testing VIX monitor config...")
    
    try:
        from utils.vix_monitor import VIXMonitor
        
        # Test with dict config
        test_config = {
            'risk': {
                'vix_halt_threshold': 25.0,
                'vix_cache_minutes': 3,
                'vix_enabled': True
            }
        }
        
        # This should not raise an exception
        vix_monitor = VIXMonitor(test_config)
        
        if vix_monitor.vix_threshold != 25.0:
            print(f"VIX threshold incorrect: {vix_monitor.vix_threshold}")
            return False
        
        print("VIX monitor config handling working")
        return True
        
    except Exception as e:
        print(f"VIX monitor test failed: {e}")
        return False

def test_dry_run_checklist():
    """Test dry run validation checklist."""
    print("Testing dry run checklist...")
    
    try:
        from utils.dry_run_checklist import DryRunValidator
        
        # Create test config
        test_config = {
            'logging': {
                'json_metrics_file': 'logs/test_metrics.jsonl'
            }
        }
        
        validator = DryRunValidator(test_config)
        
        # Test basic functionality (won't have real data)
        performance = validator._check_system_performance()
        if 'cpu_percent' not in performance:
            print("Performance check missing CPU data")
            return False
        
        print("Dry run checklist working")
        return True
        
    except Exception as e:
        print(f"Dry run checklist test failed: {e}")
        return False

def test_file_structure():
    """Test that all required files and directories exist."""
    print("Testing file structure...")
    
    required_files = [
        'config/config_dryrun.yaml',
        'monitoring/incident_log.csv',
        'utils/logging_setup.py',
        'utils/safety_hooks.py',
        'utils/dry_run_launcher.py',
        'utils/dry_run_checklist.py'
    ]
    
    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
    
    if missing_files:
        print(f"Missing files: {missing_files}")
        return False
    
    # Check directories exist
    required_dirs = ['config', 'monitoring', 'logs', 'utils']
    for dir_path in required_dirs:
        if not os.path.exists(dir_path):
            print(f"Missing directory: {dir_path}")
            return False
    
    print("File structure complete")
    return True

def test_main_py_integration():
    """Test integration with main.py CLI arguments."""
    print("Testing main.py integration...")
    
    try:
        # Test that main.py can parse the dry run arguments
        import subprocess
        result = subprocess.run([
            'python', 'main.py', '--help'
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode != 0:
            print(f"main.py help failed: {result.stderr}")
            return False
        
        # Check for required CLI arguments
        help_text = result.stdout
        required_args = ['--broker', '--alpaca-env', '--multi-symbol', '--config', '--strict-validation', '--end-at']
        
        missing_args = []
        for arg in required_args:
            if arg not in help_text:
                missing_args.append(arg)
        
        if missing_args:
            print(f"Missing CLI arguments: {missing_args}")
            return False
        
        print("main.py integration working")
        return True
        
    except Exception as e:
        print(f"main.py integration test failed: {e}")
        return False

def run_all_tests():
    """Run all component tests."""
    print("=" * 60)
    print("US-FA-014 DRY RUN COMPONENT TESTS")
    print("=" * 60)
    
    tests = [
        ("File Structure", test_file_structure),
        ("Configuration Loading", test_config_loading),
        ("Safety Hooks", test_safety_hooks),
        ("Logging Setup", test_logging_setup),
        ("VIX Monitor Config", test_vix_monitor_config),
        ("Dry Run Checklist", test_dry_run_checklist),
        ("Main.py Integration", test_main_py_integration)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n[{test_name}]")
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"{test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for test_name, success in results:
        status = "PASS" if success else "FAIL"
        print(f"{test_name:.<40} {status}")
        if success:
            passed += 1
        else:
            failed += 1
    
    print(f"\nTotal: {len(results)} tests, {passed} passed, {failed} failed")
    
    if failed == 0:
        print("\nALL TESTS PASSED - US-FA-014 ready for deployment!")
        return True
    else:
        print(f"\n{failed} TESTS FAILED - Fix issues before deployment")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
