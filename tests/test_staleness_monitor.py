"""
Test suite for Real-Time Data Staleness Detection (US-FA-008)

Tests enhanced staleness monitoring, exponential backoff retry logic,
data freshness metrics, and integration with the trading system.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path
from datetime import datetime, timedelta
import json
import tempfile
import time

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.staleness_monitor import (
    StalenessMonitor, StalenessLevel, StalenessMetrics, RetryConfig,
    check_symbol_staleness, get_staleness_summary, get_staleness_monitor
)
from utils.data_validation import DataPoint, ValidationResult, DataQuality


class TestStalenessLevel(unittest.TestCase):
    """Test StalenessLevel enumeration"""
    
    def test_staleness_levels(self):
        """Test all staleness levels are defined"""
        levels = [level.value for level in StalenessLevel]
        expected = ["fresh", "acceptable", "stale", "very_stale", "critical"]
        self.assertEqual(levels, expected)


class TestRetryConfig(unittest.TestCase):
    """Test RetryConfig dataclass"""
    
    def test_default_retry_config(self):
        """Test default retry configuration values"""
        config = RetryConfig()
        
        self.assertEqual(config.initial_delay, 1.0)
        self.assertEqual(config.max_delay, 300.0)
        self.assertEqual(config.backoff_factor, 2.0)
        self.assertEqual(config.max_retries, 10)
        self.assertTrue(config.jitter)
    
    def test_custom_retry_config(self):
        """Test custom retry configuration"""
        config = RetryConfig(
            initial_delay=2.0,
            max_delay=600.0,
            backoff_factor=1.5,
            max_retries=5,
            jitter=False
        )
        
        self.assertEqual(config.initial_delay, 2.0)
        self.assertEqual(config.max_delay, 600.0)
        self.assertEqual(config.backoff_factor, 1.5)
        self.assertEqual(config.max_retries, 5)
        self.assertFalse(config.jitter)


class TestStalenessMonitor(unittest.TestCase):
    """Test StalenessMonitor functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_config = {
            "STALENESS_MONITORING_ENABLED": True,
            "STALENESS_FRESH_SECONDS": 30,
            "STALENESS_ACCEPTABLE_SECONDS": 120,
            "STALENESS_STALE_SECONDS": 300,
            "STALENESS_VERY_STALE_SECONDS": 600,
            "STALENESS_BLOCK_TRADING": True,
            "STALENESS_ALERT_ENABLED": True,
            "STALENESS_METRICS_LOGGING": True,
            "STALENESS_RETRY_INITIAL_DELAY": 1.0,
            "STALENESS_RETRY_MAX_DELAY": 300.0,
            "STALENESS_RETRY_BACKOFF_FACTOR": 2.0,
            "STALENESS_RETRY_MAX_ATTEMPTS": 10,
            "STALENESS_RETRY_JITTER": True,
            "SLACK_ENABLED": False
        }
        
        # Use temporary directory for metrics file
        self.temp_dir = tempfile.mkdtemp()
        
    def test_monitor_initialization(self):
        """Test staleness monitor initialization"""
        monitor = StalenessMonitor(self.test_config)
        
        self.assertTrue(monitor.enabled)
        self.assertEqual(monitor.fresh_threshold, 30)
        self.assertEqual(monitor.acceptable_threshold, 120)
        self.assertEqual(monitor.stale_threshold, 300)
        self.assertEqual(monitor.very_stale_threshold, 600)
        self.assertTrue(monitor.block_on_stale)
        self.assertTrue(monitor.alert_on_stale)
    
    def test_staleness_classification(self):
        """Test staleness level classification"""
        monitor = StalenessMonitor(self.test_config)
        
        # Test all staleness levels
        self.assertEqual(monitor.classify_staleness(15), StalenessLevel.FRESH)
        self.assertEqual(monitor.classify_staleness(60), StalenessLevel.ACCEPTABLE)
        self.assertEqual(monitor.classify_staleness(240), StalenessLevel.STALE)
        self.assertEqual(monitor.classify_staleness(480), StalenessLevel.VERY_STALE)
        self.assertEqual(monitor.classify_staleness(720), StalenessLevel.CRITICAL)
        
        # Test boundary conditions
        self.assertEqual(monitor.classify_staleness(30), StalenessLevel.FRESH)
        self.assertEqual(monitor.classify_staleness(31), StalenessLevel.ACCEPTABLE)
        self.assertEqual(monitor.classify_staleness(120), StalenessLevel.ACCEPTABLE)
        self.assertEqual(monitor.classify_staleness(121), StalenessLevel.STALE)
    
    def test_retry_delay_calculation(self):
        """Test exponential backoff retry delay calculation"""
        monitor = StalenessMonitor(self.test_config)
        
        # Test exponential backoff progression
        delay1 = monitor.calculate_retry_delay(0)  # First retry
        delay2 = monitor.calculate_retry_delay(1)  # Second retry
        delay3 = monitor.calculate_retry_delay(2)  # Third retry
        
        # Should follow exponential pattern (with jitter)
        self.assertGreaterEqual(delay1, 1.0)
        self.assertLess(delay1, 2.0)  # 1.0 * 2^0 + jitter
        
        self.assertGreaterEqual(delay2, 2.0)
        self.assertLess(delay2, 3.0)  # 1.0 * 2^1 + jitter
        
        self.assertGreaterEqual(delay3, 4.0)
        self.assertLess(delay3, 5.0)  # 1.0 * 2^2 + jitter
        
        # Test max delay cap
        large_delay = monitor.calculate_retry_delay(20)
        self.assertLessEqual(large_delay, 330.0)  # Should cap at max_delay + jitter
    
    def test_retry_delay_without_jitter(self):
        """Test retry delay calculation without jitter"""
        config = self.test_config.copy()
        config["STALENESS_RETRY_JITTER"] = False
        monitor = StalenessMonitor(config)
        
        # Without jitter, delays should be exact
        self.assertEqual(monitor.calculate_retry_delay(0), 1.0)
        self.assertEqual(monitor.calculate_retry_delay(1), 2.0)
        self.assertEqual(monitor.calculate_retry_delay(2), 4.0)
        self.assertEqual(monitor.calculate_retry_delay(3), 8.0)
    
    def test_should_retry_logic(self):
        """Test retry decision logic"""
        monitor = StalenessMonitor(self.test_config)
        
        # Should retry for new symbol
        self.assertTrue(monitor.should_retry("SPY"))
        
        # Create metrics with retry count below limit
        now = datetime.now()
        monitor.metrics["SPY"] = StalenessMetrics(
            symbol="SPY",
            last_update=now,
            age_seconds=0.0,
            staleness_level=StalenessLevel.FRESH,
            retry_count=5,  # Below max of 10
            next_retry_time=now - timedelta(seconds=1),  # Past retry time
            consecutive_failures=0,
            total_failures=0,
            success_rate=1.0,
            timestamp=now
        )
        
        self.assertTrue(monitor.should_retry("SPY"))
        
        # Test max retries exceeded
        monitor.metrics["SPY"].retry_count = 10
        self.assertFalse(monitor.should_retry("SPY"))
        
        # Test retry time not reached
        monitor.metrics["SPY"].retry_count = 5
        monitor.metrics["SPY"].next_retry_time = now + timedelta(seconds=10)
        self.assertFalse(monitor.should_retry("SPY"))
    
    def test_metrics_update_success(self):
        """Test metrics update on successful data fetch"""
        monitor = StalenessMonitor(self.test_config)
        
        # Create fresh data point
        data_point = DataPoint(
            value=150.25,
            timestamp=datetime.now() - timedelta(seconds=45),
            source="alpaca",
            symbol="SPY",
            data_type="price"
        )
        
        monitor.update_metrics("SPY", data_point, success=True)
        
        metrics = monitor.metrics["SPY"]
        self.assertEqual(metrics.symbol, "SPY")
        self.assertEqual(metrics.staleness_level, StalenessLevel.ACCEPTABLE)
        self.assertEqual(metrics.retry_count, 0)
        self.assertIsNone(metrics.next_retry_time)
        self.assertEqual(metrics.consecutive_failures, 0)
    
    def test_metrics_update_failure(self):
        """Test metrics update on failed data fetch"""
        monitor = StalenessMonitor(self.test_config)
        
        # Simulate failed fetch with retry
        monitor.update_metrics("SPY", None, retry_attempted=True, success=False)
        
        metrics = monitor.metrics["SPY"]
        self.assertEqual(metrics.retry_count, 1)
        self.assertIsNotNone(metrics.next_retry_time)
        self.assertEqual(metrics.consecutive_failures, 1)
        self.assertEqual(metrics.total_failures, 1)
    
    @patch('utils.staleness_monitor.DataValidator')
    def test_check_symbol_staleness_success(self, mock_validator_class):
        """Test successful symbol staleness check"""
        # Mock data validator
        mock_validator = Mock()
        fresh_data = DataPoint(150.0, datetime.now(), "alpaca", "SPY", "price")
        mock_result = ValidationResult(
            symbol="SPY",
            primary_data=fresh_data,
            validation_data=None,
            quality=DataQuality.GOOD,
            discrepancy_pct=None,
            issues=[],
            recommendation="PROCEED_NORMAL",
            timestamp=datetime.now()
        )
        mock_validator.validate_symbol_data.return_value = mock_result
        mock_validator_class.return_value = mock_validator
        
        monitor = StalenessMonitor(self.test_config)
        monitor.data_validator = mock_validator
        
        is_fresh, reason, metrics = monitor.check_symbol_staleness("SPY")
        
        self.assertTrue(is_fresh)
        self.assertIn("acceptable", reason.lower())
        self.assertIsNotNone(metrics)
    
    @patch('utils.staleness_monitor.DataValidator')
    def test_check_symbol_staleness_stale_data(self, mock_validator_class):
        """Test staleness check with stale data"""
        # Mock data validator with stale data
        mock_validator = Mock()
        stale_data = DataPoint(150.0, datetime.now() - timedelta(seconds=400), "alpaca", "SPY", "price")
        mock_result = ValidationResult(
            symbol="SPY",
            primary_data=stale_data,
            validation_data=None,
            quality=DataQuality.ACCEPTABLE,
            discrepancy_pct=None,
            issues=[],
            recommendation="PROCEED_NORMAL",
            timestamp=datetime.now()
        )
        mock_validator.validate_symbol_data.return_value = mock_result
        mock_validator_class.return_value = mock_validator
        
        monitor = StalenessMonitor(self.test_config)
        monitor.data_validator = mock_validator
        
        is_fresh, reason, metrics = monitor.check_symbol_staleness("SPY")
        
        self.assertFalse(is_fresh)
        self.assertIn("stale", reason.lower())
        self.assertEqual(metrics.staleness_level, StalenessLevel.VERY_STALE)  # 400s is very_stale
    
    @patch('utils.staleness_monitor.DataValidator')
    def test_check_symbol_staleness_no_data_with_retry(self, mock_validator_class):
        """Test staleness check with no data and retry"""
        # Mock data validator returning no data first, then success
        mock_validator = Mock()
        
        # First call returns no data
        no_data_result = ValidationResult(
            symbol="SPY",
            primary_data=None,
            validation_data=None,
            quality=DataQuality.CRITICAL,
            discrepancy_pct=None,
            issues=["No data available"],
            recommendation="BLOCK_TRADING",
            timestamp=datetime.now()
        )
        
        # Second call (retry) returns fresh data
        fresh_data = DataPoint(150.0, datetime.now(), "alpaca", "SPY", "price")
        success_result = ValidationResult(
            symbol="SPY",
            primary_data=fresh_data,
            validation_data=None,
            quality=DataQuality.GOOD,
            discrepancy_pct=None,
            issues=[],
            recommendation="PROCEED_NORMAL",
            timestamp=datetime.now()
        )
        
        mock_validator.validate_symbol_data.side_effect = [no_data_result, success_result]
        mock_validator_class.return_value = mock_validator
        
        monitor = StalenessMonitor(self.test_config)
        monitor.data_validator = mock_validator
        
        # Mock time.sleep to avoid actual delays in tests
        with patch('time.sleep'):
            is_fresh, reason, metrics = monitor.check_symbol_staleness("SPY", with_retry=True)
        
        self.assertTrue(is_fresh)
        self.assertIn("acceptable", reason.lower())
    
    def test_check_multiple_symbols(self):
        """Test checking staleness for multiple symbols"""
        monitor = StalenessMonitor(self.test_config)
        
        # Mock the single symbol check method
        def mock_check(symbol, with_retry=True):
            if symbol == "SPY":
                return True, "Fresh data", None
            elif symbol == "QQQ":
                return False, "Stale data", None
            else:
                return True, "Acceptable data", None
        
        monitor.check_symbol_staleness = mock_check
        
        results = monitor.check_multiple_symbols(["SPY", "QQQ", "IWM"])
        
        self.assertEqual(len(results), 3)
        self.assertTrue(results["SPY"][0])
        self.assertFalse(results["QQQ"][0])
        self.assertTrue(results["IWM"][0])
    
    def test_staleness_summary_generation(self):
        """Test staleness summary generation"""
        monitor = StalenessMonitor(self.test_config)
        
        # Add test metrics
        now = datetime.now()
        monitor.metrics["SPY"] = StalenessMetrics(
            symbol="SPY",
            last_update=now,
            age_seconds=45.0,
            staleness_level=StalenessLevel.ACCEPTABLE,
            retry_count=0,
            next_retry_time=None,
            consecutive_failures=0,
            total_failures=0,
            success_rate=1.0,
            timestamp=now
        )
        
        monitor.metrics["QQQ"] = StalenessMetrics(
            symbol="QQQ",
            last_update=now - timedelta(seconds=400),
            age_seconds=400.0,
            staleness_level=StalenessLevel.STALE,
            retry_count=2,
            next_retry_time=None,
            consecutive_failures=1,
            total_failures=3,
            success_rate=0.7,
            timestamp=now
        )
        
        summary = monitor.get_staleness_summary(["SPY", "QQQ"])
        
        self.assertEqual(summary["total_symbols"], 2)
        self.assertEqual(summary["staleness_distribution"]["acceptable"], 1)
        self.assertEqual(summary["staleness_distribution"]["stale"], 1)
        self.assertEqual(len(summary["symbols_with_issues"]), 1)
        self.assertEqual(summary["symbols_with_issues"][0]["symbol"], "QQQ")
        self.assertEqual(summary["overall_health"], "degraded")  # 1 stale out of 2 = 50% > 30%
    
    def test_monitoring_disabled(self):
        """Test behavior when staleness monitoring is disabled"""
        config = self.test_config.copy()
        config["STALENESS_MONITORING_ENABLED"] = False
        monitor = StalenessMonitor(config)
        
        is_fresh, reason, metrics = monitor.check_symbol_staleness("SPY")
        
        self.assertTrue(is_fresh)
        self.assertEqual(reason, "Staleness monitoring disabled")
        self.assertIsNone(metrics)


class TestConvenienceFunctions(unittest.TestCase):
    """Test convenience functions"""
    
    @patch('utils.staleness_monitor.StalenessMonitor')
    def test_check_symbol_staleness_function(self, mock_monitor_class):
        """Test convenience function for symbol staleness check"""
        mock_monitor = Mock()
        mock_monitor.check_symbol_staleness.return_value = (True, "Fresh data", None)
        mock_monitor_class.return_value = mock_monitor
        
        is_fresh, reason = check_symbol_staleness("SPY", with_retry=True)
        
        self.assertTrue(is_fresh)
        self.assertEqual(reason, "Fresh data")
        mock_monitor.check_symbol_staleness.assert_called_once_with("SPY", True)
    
    @patch('utils.staleness_monitor.StalenessMonitor')
    def test_get_staleness_summary_function(self, mock_monitor_class):
        """Test convenience function for staleness summary"""
        mock_monitor = Mock()
        mock_summary = {"total_symbols": 3, "overall_health": "healthy"}
        mock_monitor.get_staleness_summary.return_value = mock_summary
        mock_monitor_class.return_value = mock_monitor
        
        summary = get_staleness_summary()
        
        self.assertEqual(summary, mock_summary)
        mock_monitor.get_staleness_summary.assert_called_once()
    
    def test_get_staleness_monitor_singleton(self):
        """Test singleton behavior of staleness monitor"""
        # Clear any existing instance
        if hasattr(get_staleness_monitor, '_staleness_monitor_instance'):
            get_staleness_monitor._staleness_monitor_instance = None
        
        monitor1 = get_staleness_monitor()
        monitor2 = get_staleness_monitor()
        
        self.assertIs(monitor1, monitor2)


class TestSlackIntegration(unittest.TestCase):
    """Test Slack alert integration"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_config = {
            "STALENESS_MONITORING_ENABLED": True,
            "STALENESS_ALERT_ENABLED": True,
            "SLACK_ENABLED": True,
            "STALENESS_STALE_SECONDS": 300,
            "STALENESS_BLOCK_TRADING": True
        }
    
    @patch('utils.staleness_monitor.EnhancedSlackIntegration')
    def test_slack_alert_for_staleness(self, mock_slack_class):
        """Test Slack alert for staleness issues"""
        mock_slack = Mock()
        mock_slack.enabled = True
        mock_slack_class.return_value = mock_slack
        
        monitor = StalenessMonitor(self.test_config)
        monitor.slack = mock_slack
        
        # Send staleness alert
        monitor._send_staleness_alert("SPY", StalenessLevel.STALE, 400.0)
        
        # Verify Slack alert was sent
        mock_slack.send_alert.assert_called_once()
        call_args = mock_slack.send_alert.call_args[0][0]
        self.assertIn("DATA STALENESS ALERT", call_args)
        self.assertIn("SPY", call_args)
        self.assertIn("STALE", call_args)
        self.assertIn("400.0", call_args)


class TestMetricsLogging(unittest.TestCase):
    """Test metrics logging functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_config = {
            "STALENESS_MONITORING_ENABLED": True,
            "STALENESS_METRICS_LOGGING": True
        }
    
    def test_metrics_file_creation(self):
        """Test metrics file is created and written to"""
        monitor = StalenessMonitor(self.test_config)
        
        # Override metrics file path to use temp directory
        monitor.metrics_file = Path(self.temp_dir) / "test_staleness_metrics.json"
        
        # Create test metrics
        now = datetime.now()
        metrics = StalenessMetrics(
            symbol="SPY",
            last_update=now,
            age_seconds=45.0,
            staleness_level=StalenessLevel.ACCEPTABLE,
            retry_count=0,
            next_retry_time=None,
            consecutive_failures=0,
            total_failures=0,
            success_rate=1.0,
            timestamp=now
        )
        
        # Log metrics
        monitor._log_metrics(metrics)
        
        # Verify file was created and contains data
        self.assertTrue(monitor.metrics_file.exists())
        
        with open(monitor.metrics_file, 'r') as f:
            logged_data = json.load(f)
        
        self.assertEqual(len(logged_data), 1)
        self.assertEqual(logged_data[0]["symbol"], "SPY")
        self.assertEqual(logged_data[0]["staleness_level"], "acceptable")


if __name__ == "__main__":
    # Run specific test groups
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "quick":
        # Quick test suite - core functionality only
        suite = unittest.TestSuite()
        suite.addTest(TestStalenessMonitor('test_monitor_initialization'))
        suite.addTest(TestStalenessMonitor('test_staleness_classification'))
        suite.addTest(TestStalenessMonitor('test_retry_delay_calculation'))
        suite.addTest(TestConvenienceFunctions('test_check_symbol_staleness_function'))
        
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        
        print(f"\nQuick Test Results: {result.testsRun} tests, {len(result.failures)} failures, {len(result.errors)} errors")
    else:
        # Full test suite
        unittest.main(verbosity=2)
