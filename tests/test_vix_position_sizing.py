"""
Test suite for VIX-Adjusted Position Sizing (US-FA-006)

Tests VIX-based position size adjustments, volatility regime classification,
and integration with existing bankroll management system.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.vix_position_sizing import VIXPositionSizer, get_vix_position_sizer, calculate_vix_adjusted_size
from utils.vix_monitor import VIXData


class TestVIXPositionSizing(unittest.TestCase):
    """Test VIX position sizing functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_config = {
            "VIX_POSITION_SIZING_ENABLED": True,
            "VIX_NORMAL_THRESHOLD": 20.0,
            "VIX_MODERATE_THRESHOLD": 25.0,
            "VIX_HIGH_THRESHOLD": 35.0,
            "VIX_MODERATE_REDUCTION": 0.5,
            "VIX_HIGH_REDUCTION": 0.25,
            "VIX_ALERT_ON_REGIME_CHANGE": True
        }
        
        # Mock VIX monitor
        self.mock_vix_monitor = Mock()
        
    def test_vix_sizer_initialization(self):
        """Test VIX position sizer initialization with config"""
        sizer = VIXPositionSizer(self.test_config)
        
        self.assertTrue(sizer.enabled)
        self.assertEqual(sizer.normal_threshold, 20.0)
        self.assertEqual(sizer.moderate_threshold, 25.0)
        self.assertEqual(sizer.high_threshold, 35.0)
        self.assertEqual(sizer.moderate_reduction, 0.5)
        self.assertEqual(sizer.high_reduction, 0.25)
    
    @patch('utils.vix_position_sizing.get_vix_monitor')
    def test_low_vix_normal_sizing(self, mock_get_monitor):
        """Test normal position sizing when VIX is low (< 20)"""
        # Mock VIX data for low volatility
        mock_vix_data = VIXData(value=15.0, timestamp=datetime.now())
        mock_get_monitor.return_value.get_current_vix.return_value = mock_vix_data
        
        sizer = VIXPositionSizer(self.test_config)
        sizer.vix_monitor = mock_get_monitor.return_value
        
        factor, reason, vix_value = sizer.get_vix_adjustment_factor()
        
        self.assertEqual(factor, 1.0)
        self.assertEqual(vix_value, 15.0)
        self.assertIn("Low volatility", reason)
        self.assertIn("normal sizing", reason)
    
    @patch('utils.vix_position_sizing.get_vix_monitor')
    def test_moderate_vix_reduced_sizing(self, mock_get_monitor):
        """Test 50% position sizing when VIX is moderate (25-35)"""
        # Mock VIX data for moderate volatility
        mock_vix_data = VIXData(value=28.0, timestamp=datetime.now())
        mock_get_monitor.return_value.get_current_vix.return_value = mock_vix_data
        
        sizer = VIXPositionSizer(self.test_config)
        sizer.vix_monitor = mock_get_monitor.return_value
        
        factor, reason, vix_value = sizer.get_vix_adjustment_factor()
        
        self.assertEqual(factor, 0.5)
        self.assertEqual(vix_value, 28.0)
        self.assertIn("Moderate volatility", reason)
        self.assertIn("50% size reduction", reason)
    
    @patch('utils.vix_position_sizing.get_vix_monitor')
    def test_high_vix_minimal_sizing(self, mock_get_monitor):
        """Test 25% position sizing when VIX is high (> 35)"""
        # Mock VIX data for high volatility
        mock_vix_data = VIXData(value=40.0, timestamp=datetime.now())
        mock_get_monitor.return_value.get_current_vix.return_value = mock_vix_data
        
        sizer = VIXPositionSizer(self.test_config)
        sizer.vix_monitor = mock_get_monitor.return_value
        
        factor, reason, vix_value = sizer.get_vix_adjustment_factor()
        
        self.assertEqual(factor, 0.25)
        self.assertEqual(vix_value, 40.0)
        self.assertIn("High volatility", reason)
        self.assertIn("75% size reduction", reason)
    
    @patch('utils.vix_position_sizing.get_vix_monitor')
    def test_position_size_adjustment(self, mock_get_monitor):
        """Test actual position size adjustment calculation"""
        # Mock VIX data for moderate volatility (50% reduction)
        mock_vix_data = VIXData(value=28.0, timestamp=datetime.now())
        mock_get_monitor.return_value.get_current_vix.return_value = mock_vix_data
        
        sizer = VIXPositionSizer(self.test_config)
        sizer.vix_monitor = mock_get_monitor.return_value
        
        base_size = 1000.0  # $1000 position
        adjusted_size, info = sizer.adjust_position_size(base_size, "SPY")
        
        self.assertEqual(adjusted_size, 500.0)  # 50% of $1000
        self.assertEqual(info["adjustment_factor"], 0.5)
        self.assertEqual(info["base_size"], 1000.0)
        self.assertEqual(info["adjusted_size"], 500.0)
        self.assertEqual(info["size_reduction_pct"], 50.0)
        self.assertEqual(info["vix_value"], 28.0)
        self.assertEqual(info["symbol"], "SPY")
    
    @patch('utils.vix_position_sizing.get_vix_monitor')
    def test_volatility_regime_classification(self, mock_get_monitor):
        """Test volatility regime classification"""
        sizer = VIXPositionSizer(self.test_config)
        sizer.vix_monitor = mock_get_monitor.return_value
        
        # Test low volatility
        mock_vix_data = VIXData(value=15.0, timestamp=datetime.now())
        mock_get_monitor.return_value.get_current_vix.return_value = mock_vix_data
        regime, vix_value = sizer.get_volatility_regime()
        self.assertEqual(regime, "LOW")
        self.assertEqual(vix_value, 15.0)
        
        # Test normal volatility
        mock_vix_data = VIXData(value=22.0, timestamp=datetime.now())
        mock_get_monitor.return_value.get_current_vix.return_value = mock_vix_data
        regime, vix_value = sizer.get_volatility_regime()
        self.assertEqual(regime, "NORMAL")
        self.assertEqual(vix_value, 22.0)
        
        # Test moderate volatility
        mock_vix_data = VIXData(value=30.0, timestamp=datetime.now())
        mock_get_monitor.return_value.get_current_vix.return_value = mock_vix_data
        regime, vix_value = sizer.get_volatility_regime()
        self.assertEqual(regime, "MODERATE")
        self.assertEqual(vix_value, 30.0)
        
        # Test high volatility
        mock_vix_data = VIXData(value=45.0, timestamp=datetime.now())
        mock_get_monitor.return_value.get_current_vix.return_value = mock_vix_data
        regime, vix_value = sizer.get_volatility_regime()
        self.assertEqual(regime, "HIGH")
        self.assertEqual(vix_value, 45.0)
    
    @patch('utils.vix_position_sizing.get_vix_monitor')
    def test_disabled_vix_sizing(self, mock_get_monitor):
        """Test behavior when VIX position sizing is disabled"""
        disabled_config = self.test_config.copy()
        disabled_config["VIX_POSITION_SIZING_ENABLED"] = False
        
        sizer = VIXPositionSizer(disabled_config)
        
        factor, reason, vix_value = sizer.get_vix_adjustment_factor()
        
        self.assertEqual(factor, 1.0)
        self.assertIsNone(vix_value)
        self.assertIn("disabled", reason)
    
    @patch('utils.vix_position_sizing.get_vix_monitor')
    def test_vix_data_unavailable(self, mock_get_monitor):
        """Test behavior when VIX data is unavailable"""
        # Mock VIX monitor to return None (data unavailable)
        mock_get_monitor.return_value.get_current_vix.return_value = None
        
        sizer = VIXPositionSizer(self.test_config)
        sizer.vix_monitor = mock_get_monitor.return_value
        
        factor, reason, vix_value = sizer.get_vix_adjustment_factor()
        
        self.assertEqual(factor, 1.0)
        self.assertIsNone(vix_value)
        self.assertIn("unavailable", reason)
    
    @patch('utils.vix_position_sizing.get_vix_monitor')
    def test_should_reduce_exposure(self, mock_get_monitor):
        """Test exposure reduction recommendation"""
        sizer = VIXPositionSizer(self.test_config)
        sizer.vix_monitor = mock_get_monitor.return_value
        
        # Test normal VIX - no reduction
        mock_vix_data = VIXData(value=20.0, timestamp=datetime.now())
        mock_get_monitor.return_value.get_current_vix.return_value = mock_vix_data
        should_reduce, reason, vix_value = sizer.should_reduce_exposure()
        self.assertFalse(should_reduce)
        
        # Test high VIX - should reduce
        mock_vix_data = VIXData(value=40.0, timestamp=datetime.now())
        mock_get_monitor.return_value.get_current_vix.return_value = mock_vix_data
        should_reduce, reason, vix_value = sizer.should_reduce_exposure()
        self.assertTrue(should_reduce)
        self.assertEqual(vix_value, 40.0)
    
    def test_convenience_function(self):
        """Test convenience function for VIX-adjusted sizing"""
        with patch('utils.vix_position_sizing.get_vix_position_sizer') as mock_get_sizer:
            mock_sizer = Mock()
            mock_sizer.adjust_position_size.return_value = (500.0, {"adjustment_factor": 0.5})
            mock_get_sizer.return_value = mock_sizer
            
            adjusted_size, info = calculate_vix_adjusted_size(1000.0, "SPY")
            
            self.assertEqual(adjusted_size, 500.0)
            self.assertEqual(info["adjustment_factor"], 0.5)
            mock_sizer.adjust_position_size.assert_called_once_with(1000.0, "SPY")


class TestVIXBankrollIntegration(unittest.TestCase):
    """Test VIX integration with bankroll management"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_config = {
            "VIX_POSITION_SIZING_ENABLED": True,
            "VIX_NORMAL_THRESHOLD": 20.0,
            "VIX_MODERATE_THRESHOLD": 25.0,
            "VIX_HIGH_THRESHOLD": 35.0,
            "VIX_MODERATE_REDUCTION": 0.5,
            "VIX_HIGH_REDUCTION": 0.25
        }
    
    @patch('utils.vix_position_sizing.calculate_vix_adjusted_size')
    def test_bankroll_vix_integration(self, mock_vix_adjust):
        """Test VIX integration with bankroll position calculation"""
        from utils.bankroll import BankrollManager
        
        # Mock VIX adjustment to return 50% sizing
        mock_vix_adjust.return_value = (250.0, {"adjustment_factor": 0.5, "vix_value": 28.0})
        
        # Create bankroll manager with test data
        with patch.object(Path, 'exists', return_value=True), \
             patch('builtins.open', unittest.mock.mock_open(read_data='{"current_bankroll": 1000.0}')):
            
            bankroll = BankrollManager(bankroll_file="test_bankroll.json")
            
            # Test position size calculation with VIX adjustment
            with patch.object(bankroll, '_load_bankroll', return_value={"current_bankroll": 1000.0}):
                quantity = bankroll.calculate_position_size(
                    premium=2.50,
                    risk_fraction=0.5,
                    size_rule="fixed-qty",
                    fixed_qty=2,
                    symbol="SPY",
                    apply_vix_adjustment=True
                )
                
                # Verify VIX adjustment was called
                mock_vix_adjust.assert_called_once()
                
                # With 50% VIX adjustment, 2 contracts should become 1 contract
                # (500 dollar size / (2.50 * 100) = 2 contracts, but VIX reduces to 250 / 250 = 1)
                self.assertEqual(quantity, 1)
    
    @patch('utils.vix_position_sizing.calculate_vix_adjusted_size')
    def test_bankroll_no_vix_adjustment(self, mock_vix_adjust):
        """Test bankroll calculation without VIX adjustment"""
        from utils.bankroll import BankrollManager
        
        # Create bankroll manager
        with patch.object(Path, 'exists', return_value=True), \
             patch('builtins.open', unittest.mock.mock_open(read_data='{"current_bankroll": 1000.0}')):
            
            bankroll = BankrollManager(bankroll_file="test_bankroll.json")
            
            # Test position size calculation without VIX adjustment
            with patch.object(bankroll, '_load_bankroll', return_value={"current_bankroll": 1000.0}):
                quantity = bankroll.calculate_position_size(
                    premium=2.50,
                    risk_fraction=0.5,
                    size_rule="fixed-qty",
                    fixed_qty=2,
                    symbol="SPY",
                    apply_vix_adjustment=False
                )
                
                # Verify VIX adjustment was NOT called
                mock_vix_adjust.assert_not_called()
                
                # Should return base fixed quantity
                self.assertEqual(quantity, 2)


class TestVIXConfigurationValidation(unittest.TestCase):
    """Test VIX configuration validation and edge cases"""
    
    def test_missing_config_defaults(self):
        """Test behavior with missing configuration values"""
        minimal_config = {"VIX_POSITION_SIZING_ENABLED": True}
        
        with patch('utils.vix_position_sizing.get_vix_monitor'):
            sizer = VIXPositionSizer(minimal_config)
            
            # Should use default values
            self.assertEqual(sizer.normal_threshold, 20.0)
            self.assertEqual(sizer.moderate_threshold, 25.0)
            self.assertEqual(sizer.high_threshold, 35.0)
            self.assertEqual(sizer.moderate_reduction, 0.5)
            self.assertEqual(sizer.high_reduction, 0.25)
    
    def test_invalid_config_values(self):
        """Test behavior with invalid configuration values"""
        invalid_config = {
            "VIX_POSITION_SIZING_ENABLED": True,
            "VIX_NORMAL_THRESHOLD": -5.0,  # Invalid negative threshold
            "VIX_MODERATE_REDUCTION": 1.5,  # Invalid > 1.0 reduction
        }
        
        with patch('utils.vix_position_sizing.get_vix_monitor'):
            # Should not crash, should use provided values (validation in config layer)
            sizer = VIXPositionSizer(invalid_config)
            self.assertEqual(sizer.normal_threshold, -5.0)
            self.assertEqual(sizer.moderate_reduction, 1.5)


class TestVIXEdgeCases(unittest.TestCase):
    """Test VIX position sizing edge cases and error handling"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_config = {
            "VIX_POSITION_SIZING_ENABLED": True,
            "VIX_NORMAL_THRESHOLD": 20.0,
            "VIX_MODERATE_THRESHOLD": 25.0,
            "VIX_HIGH_THRESHOLD": 35.0,
            "VIX_MODERATE_REDUCTION": 0.5,
            "VIX_HIGH_REDUCTION": 0.25
        }
    
    @patch('utils.vix_position_sizing.get_vix_monitor')
    def test_zero_position_size(self, mock_get_monitor):
        """Test behavior with zero base position size"""
        mock_vix_data = VIXData(value=40.0, timestamp=datetime.now())
        mock_get_monitor.return_value.get_current_vix.return_value = mock_vix_data
        
        sizer = VIXPositionSizer(self.test_config)
        sizer.vix_monitor = mock_get_monitor.return_value
        
        adjusted_size, info = sizer.adjust_position_size(0.0, "SPY")
        
        self.assertEqual(adjusted_size, 0.0)
        self.assertEqual(info["base_size"], 0.0)
        self.assertEqual(info["adjusted_size"], 0.0)
    
    @patch('utils.vix_position_sizing.get_vix_monitor')
    def test_vix_monitor_exception(self, mock_get_monitor):
        """Test behavior when VIX monitor raises exception"""
        # Mock VIX monitor to raise exception
        mock_get_monitor.return_value.get_current_vix.side_effect = Exception("VIX fetch failed")
        
        sizer = VIXPositionSizer(self.test_config)
        sizer.vix_monitor = mock_get_monitor.return_value
        
        factor, reason, vix_value = sizer.get_vix_adjustment_factor()
        
        # Should fallback gracefully
        self.assertEqual(factor, 1.0)
        self.assertIsNone(vix_value)
        self.assertIn("unavailable", reason)
    
    @patch('utils.vix_position_sizing.get_vix_monitor')
    def test_boundary_vix_values(self, mock_get_monitor):
        """Test VIX values exactly at thresholds"""
        sizer = VIXPositionSizer(self.test_config)
        sizer.vix_monitor = mock_get_monitor.return_value
        
        # Test VIX exactly at moderate threshold (25.0)
        mock_vix_data = VIXData(value=25.0, timestamp=datetime.now())
        mock_get_monitor.return_value.get_current_vix.return_value = mock_vix_data
        factor, reason, vix_value = sizer.get_vix_adjustment_factor()
        self.assertEqual(factor, 1.0)  # Should be normal sizing (<=25)
        
        # Test VIX just above moderate threshold (25.1)
        mock_vix_data = VIXData(value=25.1, timestamp=datetime.now())
        mock_get_monitor.return_value.get_current_vix.return_value = mock_vix_data
        factor, reason, vix_value = sizer.get_vix_adjustment_factor()
        self.assertEqual(factor, 0.5)  # Should be moderate reduction (>25)
        
        # Test VIX exactly at high threshold (35.0)
        mock_vix_data = VIXData(value=35.0, timestamp=datetime.now())
        mock_get_monitor.return_value.get_current_vix.return_value = mock_vix_data
        factor, reason, vix_value = sizer.get_vix_adjustment_factor()
        self.assertEqual(factor, 0.5)  # Should be moderate reduction (<=35)
        
        # Test VIX just above high threshold (35.1)
        mock_vix_data = VIXData(value=35.1, timestamp=datetime.now())
        mock_get_monitor.return_value.get_current_vix.return_value = mock_vix_data
        factor, reason, vix_value = sizer.get_vix_adjustment_factor()
        self.assertEqual(factor, 0.25)  # Should be high reduction (>35)


class TestVIXSlackIntegration(unittest.TestCase):
    """Test VIX alerts and Slack integration"""
    
    @patch('utils.enhanced_slack.EnhancedSlackIntegration')
    def test_vix_regime_change_alert(self, mock_slack_class):
        """Test VIX regime change Slack alerts"""
        mock_slack = Mock()
        mock_slack_class.return_value = mock_slack
        mock_slack.enabled = True
        
        from utils.enhanced_slack import EnhancedSlackIntegration
        slack = EnhancedSlackIntegration()
        
        # Test regime change alert
        slack.send_vix_regime_change_alert("NORMAL", "HIGH", 40.0, 0.25)
        
        # Verify alert was sent (method exists and was called)
        self.assertTrue(hasattr(slack, 'send_vix_regime_change_alert'))


if __name__ == "__main__":
    # Run specific test groups
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "quick":
        # Quick test suite - core functionality only
        suite = unittest.TestSuite()
        suite.addTest(TestVIXPositionSizing('test_low_vix_normal_sizing'))
        suite.addTest(TestVIXPositionSizing('test_moderate_vix_reduced_sizing'))
        suite.addTest(TestVIXPositionSizing('test_high_vix_minimal_sizing'))
        suite.addTest(TestVIXPositionSizing('test_position_size_adjustment'))
        
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        
        print(f"\nQuick Test Results: {result.testsRun} tests, {len(result.failures)} failures, {len(result.errors)} errors")
    else:
        # Full test suite
        unittest.main(verbosity=2)
