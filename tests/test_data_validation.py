"""
Test suite for Cross-Source Data Validation (US-FA-007)

Tests data quality validation, cross-source comparison, staleness detection,
and integration with the trading system.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.data_validation import (
    DataValidator, DataPoint, DataQuality, ValidationResult,
    validate_symbol_data_quality, check_trading_allowed, get_data_validator
)


class TestDataPoint(unittest.TestCase):
    """Test DataPoint functionality"""
    
    def test_data_point_creation(self):
        """Test DataPoint creation and properties"""
        timestamp = datetime.now()
        data_point = DataPoint(
            value=100.50,
            timestamp=timestamp,
            source="alpaca",
            symbol="SPY",
            data_type="price"
        )
        
        self.assertEqual(data_point.value, 100.50)
        self.assertEqual(data_point.timestamp, timestamp)
        self.assertEqual(data_point.source, "alpaca")
        self.assertEqual(data_point.symbol, "SPY")
        self.assertEqual(data_point.data_type, "price")
    
    def test_data_point_age_calculation(self):
        """Test age calculation for data points"""
        old_timestamp = datetime.now() - timedelta(seconds=300)  # 5 minutes ago
        data_point = DataPoint(
            value=100.50,
            timestamp=old_timestamp,
            source="alpaca",
            symbol="SPY",
            data_type="price"
        )
        
        # Should be approximately 300 seconds old
        self.assertGreater(data_point.age_seconds, 290)
        self.assertLess(data_point.age_seconds, 310)
    
    def test_data_point_staleness(self):
        """Test staleness detection"""
        # Fresh data
        fresh_data = DataPoint(
            value=100.50,
            timestamp=datetime.now(),
            source="alpaca",
            symbol="SPY",
            data_type="price"
        )
        self.assertFalse(fresh_data.is_stale(120))
        
        # Stale data (5 minutes old)
        stale_data = DataPoint(
            value=100.50,
            timestamp=datetime.now() - timedelta(seconds=300),
            source="yahoo",
            symbol="SPY",
            data_type="price"
        )
        self.assertTrue(stale_data.is_stale(120))


class TestDataValidator(unittest.TestCase):
    """Test DataValidator functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_config = {
            "DATA_VALIDATION_ENABLED": True,
            "DATA_MAX_DISCREPANCY_PCT": 1.0,
            "DATA_MAX_STALENESS_SECONDS": 120,
            "DATA_REQUIRE_VALIDATION": False,
            "DATA_PRIORITIZE_ALPACA": True,
            "DATA_ALERT_ON_DISCREPANCY": True
        }
        
    def test_validator_initialization(self):
        """Test validator initialization with config"""
        validator = DataValidator(self.test_config)
        
        self.assertTrue(validator.validation_enabled)
        self.assertEqual(validator.max_discrepancy_pct, 1.0)
        self.assertEqual(validator.max_staleness_seconds, 120)
        self.assertFalse(validator.require_validation)
    
    def test_validator_default_config(self):
        """Test validator with default configuration"""
        validator = DataValidator()
        
        self.assertTrue(validator.validation_enabled)
        self.assertEqual(validator.max_discrepancy_pct, 1.0)
        self.assertEqual(validator.max_staleness_seconds, 120)
        self.assertFalse(validator.require_validation)
    
    @patch('utils.data_validation.AlpacaClient')
    def test_get_alpaca_price_success(self, mock_alpaca_class):
        """Test successful Alpaca price retrieval"""
        mock_alpaca = Mock()
        mock_alpaca.get_current_price.return_value = 150.25
        mock_alpaca_class.return_value = mock_alpaca
        
        validator = DataValidator(self.test_config)
        validator.alpaca_client = mock_alpaca
        
        data_point = validator.get_alpaca_price("SPY")
        
        self.assertIsNotNone(data_point)
        self.assertEqual(data_point.value, 150.25)
        self.assertEqual(data_point.source, "alpaca")
        self.assertEqual(data_point.symbol, "SPY")
        self.assertEqual(data_point.data_type, "price")
    
    @patch('utils.data_validation.AlpacaClient')
    def test_get_alpaca_price_failure(self, mock_alpaca_class):
        """Test Alpaca price retrieval failure"""
        mock_alpaca = Mock()
        mock_alpaca.get_current_price.side_effect = Exception("API Error")
        mock_alpaca_class.return_value = mock_alpaca
        
        validator = DataValidator(self.test_config)
        validator.alpaca_client = mock_alpaca
        
        data_point = validator.get_alpaca_price("SPY")
        
        self.assertIsNone(data_point)
    
    @patch('utils.data_validation.yf')
    def test_get_yahoo_price_success(self, mock_yf):
        """Test successful Yahoo Finance price retrieval"""
        mock_ticker = Mock()
        mock_data = Mock()
        mock_data.empty = False
        mock_data.iloc = [Mock()]
        mock_data.iloc[-1] = 149.75
        mock_data.index = [Mock()]
        mock_data.index[-1].to_pydatetime.return_value = datetime.now()
        mock_data.__getitem__ = Mock(return_value=mock_data)
        
        mock_ticker.history.return_value = mock_data
        mock_yf.Ticker.return_value = mock_ticker
        
        validator = DataValidator(self.test_config)
        data_point = validator.get_yahoo_price("SPY")
        
        self.assertIsNotNone(data_point)
        self.assertEqual(data_point.value, 149.75)
        self.assertEqual(data_point.source, "yahoo")
        self.assertEqual(data_point.symbol, "SPY")
    
    @patch('utils.data_validation.yf')
    def test_get_yahoo_price_failure(self, mock_yf):
        """Test Yahoo Finance price retrieval failure"""
        mock_ticker = Mock()
        mock_ticker.history.side_effect = Exception("Network Error")
        mock_yf.Ticker.return_value = mock_ticker
        
        validator = DataValidator(self.test_config)
        data_point = validator.get_yahoo_price("SPY")
        
        self.assertIsNone(data_point)
    
    def test_calculate_discrepancy(self):
        """Test discrepancy calculation between data points"""
        validator = DataValidator(self.test_config)
        
        primary = DataPoint(100.0, datetime.now(), "alpaca", "SPY", "price")
        validation = DataPoint(101.0, datetime.now(), "yahoo", "SPY", "price")
        
        discrepancy = validator.calculate_discrepancy(primary, validation)
        self.assertEqual(discrepancy, 1.0)  # 1% difference
        
        # Test zero primary value
        zero_primary = DataPoint(0.0, datetime.now(), "alpaca", "SPY", "price")
        discrepancy = validator.calculate_discrepancy(zero_primary, validation)
        self.assertEqual(discrepancy, float('inf'))
    
    def test_assess_quality_excellent(self):
        """Test excellent quality assessment"""
        validator = DataValidator(self.test_config)
        
        primary = DataPoint(100.0, datetime.now(), "alpaca", "SPY", "price")
        validation = DataPoint(100.5, datetime.now(), "yahoo", "SPY", "price")
        discrepancy = 0.5  # Within threshold
        issues = []
        
        quality, recommendation = validator._assess_quality(primary, validation, discrepancy, issues)
        
        self.assertEqual(quality, DataQuality.EXCELLENT)
        self.assertEqual(recommendation, "PROCEED_NORMAL")
    
    def test_assess_quality_poor_stale_data(self):
        """Test poor quality assessment for stale data"""
        validator = DataValidator(self.test_config)
        
        stale_time = datetime.now() - timedelta(seconds=300)  # 5 minutes ago
        primary = DataPoint(100.0, stale_time, "alpaca", "SPY", "price")
        issues = ["Primary data is stale (300s old)"]
        
        quality, recommendation = validator._assess_quality(primary, None, None, issues)
        
        self.assertEqual(quality, DataQuality.POOR)
        self.assertEqual(recommendation, "PROCEED_WITH_CAUTION")
    
    def test_assess_quality_high_discrepancy(self):
        """Test quality assessment with high discrepancy"""
        validator = DataValidator(self.test_config)
        
        primary = DataPoint(100.0, datetime.now(), "alpaca", "SPY", "price")
        validation = DataPoint(105.0, datetime.now(), "yahoo", "SPY", "price")
        discrepancy = 5.0  # Above threshold
        issues = ["Price discrepancy 5.00% exceeds threshold 1.0%"]
        
        quality, recommendation = validator._assess_quality(primary, validation, discrepancy, issues)
        
        self.assertEqual(quality, DataQuality.ACCEPTABLE)
        self.assertEqual(recommendation, "PROCEED_WITH_CAUTION")


class TestDataValidationIntegration(unittest.TestCase):
    """Test integration with trading system"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_config = {
            "DATA_VALIDATION_ENABLED": True,
            "DATA_MAX_DISCREPANCY_PCT": 1.0,
            "DATA_MAX_STALENESS_SECONDS": 120,
            "DATA_REQUIRE_VALIDATION": False
        }
    
    @patch('utils.data_validation.DataValidator.get_alpaca_price')
    @patch('utils.data_validation.DataValidator.get_yahoo_price')
    def test_validate_symbol_data_excellent_quality(self, mock_yahoo, mock_alpaca):
        """Test symbol validation with excellent data quality"""
        # Mock both sources returning similar prices
        alpaca_data = DataPoint(150.0, datetime.now(), "alpaca", "SPY", "price")
        yahoo_data = DataPoint(150.2, datetime.now(), "yahoo", "SPY", "price")
        
        mock_alpaca.return_value = alpaca_data
        mock_yahoo.return_value = yahoo_data
        
        validator = DataValidator(self.test_config)
        result = validator.validate_symbol_data("SPY")
        
        self.assertEqual(result.symbol, "SPY")
        self.assertEqual(result.quality, DataQuality.EXCELLENT)
        self.assertEqual(result.recommendation, "PROCEED_NORMAL")
        self.assertLess(result.discrepancy_pct, 1.0)
    
    @patch('utils.data_validation.DataValidator.get_alpaca_price')
    @patch('utils.data_validation.DataValidator.get_yahoo_price')
    def test_validate_symbol_data_no_data(self, mock_yahoo, mock_alpaca):
        """Test symbol validation with no data available"""
        mock_alpaca.return_value = None
        mock_yahoo.return_value = None
        
        validator = DataValidator(self.test_config)
        result = validator.validate_symbol_data("SPY")
        
        self.assertEqual(result.quality, DataQuality.CRITICAL)
        self.assertEqual(result.recommendation, "BLOCK_TRADING")
        self.assertIn("No data available", result.issues[0])
    
    @patch('utils.data_validation.DataValidator.get_alpaca_price')
    @patch('utils.data_validation.DataValidator.get_yahoo_price')
    def test_validate_symbol_data_high_discrepancy(self, mock_yahoo, mock_alpaca):
        """Test symbol validation with high price discrepancy"""
        # Mock sources with high discrepancy
        alpaca_data = DataPoint(150.0, datetime.now(), "alpaca", "SPY", "price")
        yahoo_data = DataPoint(155.0, datetime.now(), "yahoo", "SPY", "price")
        
        mock_alpaca.return_value = alpaca_data
        mock_yahoo.return_value = yahoo_data
        
        validator = DataValidator(self.test_config)
        result = validator.validate_symbol_data("SPY")
        
        self.assertEqual(result.quality, DataQuality.ACCEPTABLE)
        self.assertEqual(result.recommendation, "PROCEED_WITH_CAUTION")
        self.assertGreater(result.discrepancy_pct, 1.0)
    
    def test_should_allow_trading_validation_disabled(self):
        """Test trading allowance when validation is disabled"""
        config = {"DATA_VALIDATION_ENABLED": False}
        validator = DataValidator(config)
        
        allowed, reason = validator.should_allow_trading("SPY")
        
        self.assertTrue(allowed)
        self.assertEqual(reason, "Data validation disabled")
    
    @patch('utils.data_validation.DataValidator.validate_symbol_data')
    def test_should_allow_trading_good_quality(self, mock_validate):
        """Test trading allowance with good data quality"""
        mock_result = ValidationResult(
            symbol="SPY",
            primary_data=Mock(),
            validation_data=Mock(),
            quality=DataQuality.GOOD,
            discrepancy_pct=0.5,
            issues=[],
            recommendation="PROCEED_NORMAL",
            timestamp=datetime.now()
        )
        mock_validate.return_value = mock_result
        
        validator = DataValidator(self.test_config)
        allowed, reason = validator.should_allow_trading("SPY")
        
        self.assertTrue(allowed)
        self.assertIn("Data quality acceptable", reason)
    
    @patch('utils.data_validation.DataValidator.validate_symbol_data')
    def test_should_allow_trading_blocked(self, mock_validate):
        """Test trading blocked due to poor data quality"""
        mock_result = ValidationResult(
            symbol="SPY",
            primary_data=None,
            validation_data=None,
            quality=DataQuality.CRITICAL,
            discrepancy_pct=None,
            issues=["No data available"],
            recommendation="BLOCK_TRADING",
            timestamp=datetime.now()
        )
        mock_validate.return_value = mock_result
        
        validator = DataValidator(self.test_config)
        allowed, reason = validator.should_allow_trading("SPY")
        
        self.assertFalse(allowed)
        self.assertIn("Data quality too poor", reason)


class TestConvenienceFunctions(unittest.TestCase):
    """Test convenience functions"""
    
    @patch('utils.data_validation.DataValidator')
    def test_validate_symbol_data_quality(self, mock_validator_class):
        """Test convenience function for symbol validation"""
        mock_validator = Mock()
        mock_result = Mock()
        mock_validator.validate_symbol_data.return_value = mock_result
        mock_validator_class.return_value = mock_validator
        
        result = validate_symbol_data_quality("SPY")
        
        self.assertEqual(result, mock_result)
        mock_validator.validate_symbol_data.assert_called_once_with("SPY")
    
    @patch('utils.data_validation.DataValidator')
    def test_check_trading_allowed(self, mock_validator_class):
        """Test convenience function for trading allowance"""
        mock_validator = Mock()
        mock_validator.should_allow_trading.return_value = (True, "Good quality")
        mock_validator_class.return_value = mock_validator
        
        allowed, reason = check_trading_allowed("SPY")
        
        self.assertTrue(allowed)
        self.assertEqual(reason, "Good quality")
        mock_validator.should_allow_trading.assert_called_once_with("SPY")
    
    def test_get_data_validator_singleton(self):
        """Test singleton behavior of data validator"""
        # Clear any existing instance
        if hasattr(get_data_validator, '_instance'):
            delattr(get_data_validator, '_instance')
        
        validator1 = get_data_validator()
        validator2 = get_data_validator()
        
        self.assertIs(validator1, validator2)


class TestSlackIntegration(unittest.TestCase):
    """Test Slack alert integration"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_config = {
            "DATA_VALIDATION_ENABLED": True,
            "DATA_ALERT_ON_DISCREPANCY": True
        }
    
    @patch('utils.data_validation.EnhancedSlackIntegration')
    def test_slack_alert_integration(self, mock_slack_class):
        """Test Slack alert for data quality issues"""
        mock_slack = Mock()
        mock_slack.enabled = True
        mock_slack_class.return_value = mock_slack
        
        validator = DataValidator(self.test_config)
        validator.slack = mock_slack
        
        # Create a poor quality result
        result = ValidationResult(
            symbol="SPY",
            primary_data=DataPoint(100.0, datetime.now(), "alpaca", "SPY", "price"),
            validation_data=DataPoint(105.0, datetime.now(), "yahoo", "SPY", "price"),
            quality=DataQuality.POOR,
            discrepancy_pct=5.0,
            issues=["High discrepancy"],
            recommendation="BLOCK_TRADING",
            timestamp=datetime.now()
        )
        
        validator._send_data_quality_alert(result)
        
        # Verify Slack alert was sent
        mock_slack.send_alert.assert_called_once()
        call_args = mock_slack.send_alert.call_args[0][0]
        self.assertIn("DATA QUALITY ISSUE", call_args)
        self.assertIn("SPY", call_args)


if __name__ == "__main__":
    # Run specific test groups
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "quick":
        # Quick test suite - core functionality only
        suite = unittest.TestSuite()
        suite.addTest(TestDataPoint('test_data_point_creation'))
        suite.addTest(TestDataValidator('test_validator_initialization'))
        suite.addTest(TestDataValidationIntegration('test_validate_symbol_data_excellent_quality'))
        suite.addTest(TestConvenienceFunctions('test_check_trading_allowed'))
        
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        
        print(f"\nQuick Test Results: {result.testsRun} tests, {len(result.failures)} failures, {len(result.errors)} errors")
    else:
        # Full test suite
        unittest.main(verbosity=2)
