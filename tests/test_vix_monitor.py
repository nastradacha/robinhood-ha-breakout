"""
Test suite for VIX Spike Detection (US-FA-001)
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import yaml

from utils.vix_monitor import VIXMonitor, VIXData, check_vix_spike, get_vix_monitor


class TestVIXData:
    """Test VIXData dataclass functionality."""
    
    def test_vix_data_creation(self):
        """Test VIXData creation and properties."""
        timestamp = datetime.now()
        vix_data = VIXData(value=25.5, timestamp=timestamp)
        
        assert vix_data.value == 25.5
        assert vix_data.timestamp == timestamp
        assert vix_data.source == "yahoo_finance"
        assert vix_data.age_minutes < 0.1  # Should be very recent
    
    def test_vix_data_age_calculation(self):
        """Test VIX data age calculation."""
        old_timestamp = datetime.now() - timedelta(minutes=10)
        vix_data = VIXData(value=20.0, timestamp=old_timestamp)
        
        assert 9.5 < vix_data.age_minutes < 10.5  # Should be around 10 minutes


class TestVIXMonitor:
    """Test VIX Monitor functionality."""
    
    def setup_method(self):
        """Setup test environment."""
        # Create temporary config
        self.temp_config = {
            'VIX_SPIKE_THRESHOLD': 25.0,
            'VIX_CACHE_MINUTES': 3,
            'VIX_ENABLED': True
        }
    
    def test_vix_monitor_initialization(self):
        """Test VIX monitor initialization with config."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(self.temp_config, f)
            config_path = f.name
        
        try:
            monitor = VIXMonitor(config_path)
            assert monitor.vix_threshold == 25.0
            assert monitor.cache_minutes == 3
            assert monitor.enabled is True
            assert monitor._cached_vix is None
            assert monitor._last_spike_state is False
        finally:
            os.unlink(config_path)
    
    def test_vix_monitor_disabled(self):
        """Test VIX monitor when disabled."""
        config = {'VIX_ENABLED': False}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            config_path = f.name
        
        try:
            monitor = VIXMonitor(config_path)
            is_spike, vix_value, reason = monitor.is_vix_spike_active()
            
            assert is_spike is False
            assert vix_value is None
            assert "disabled" in reason.lower()
        finally:
            os.unlink(config_path)
    
    @patch('utils.vix_monitor.yf.Ticker')
    def test_vix_fetch_success(self, mock_ticker):
        """Test successful VIX data fetching."""
        # Mock yfinance response
        mock_history = Mock()
        mock_history.empty = False
        mock_history.__getitem__ = Mock(return_value=Mock(iloc=Mock(__getitem__=Mock(return_value=22.5))))
        
        mock_ticker_instance = Mock()
        mock_ticker_instance.history.return_value = mock_history
        mock_ticker.return_value = mock_ticker_instance
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(self.temp_config, f)
            config_path = f.name
        
        try:
            monitor = VIXMonitor(config_path)
            vix_data = monitor.get_current_vix()
            
            assert vix_data is not None
            assert vix_data.value == 22.5
            assert vix_data.source == "yahoo_finance"
            assert vix_data.age_minutes < 0.1
        finally:
            os.unlink(config_path)
    
    @patch('utils.vix_monitor.yf.Ticker')
    def test_vix_spike_detection(self, mock_ticker):
        """Test VIX spike detection logic."""
        # Mock high VIX value
        mock_history = Mock()
        mock_history.empty = False
        mock_history.__getitem__ = Mock(return_value=Mock(iloc=Mock(__getitem__=Mock(return_value=35.0))))
        
        mock_ticker_instance = Mock()
        mock_ticker_instance.history.return_value = mock_history
        mock_ticker.return_value = mock_ticker_instance
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(self.temp_config, f)
            config_path = f.name
        
        try:
            monitor = VIXMonitor(config_path)
            is_spike, vix_value, reason = monitor.is_vix_spike_active(send_alerts=False)
            
            assert is_spike is True
            assert vix_value == 35.0
            assert "spike detected" in reason.lower()
            assert "35.00 > 25.0" in reason
        finally:
            os.unlink(config_path)
    
    @patch('utils.vix_monitor.yf.Ticker')
    def test_vix_normal_conditions(self, mock_ticker):
        """Test VIX normal conditions."""
        # Mock normal VIX value
        mock_history = Mock()
        mock_history.empty = False
        mock_history.__getitem__ = Mock(return_value=Mock(iloc=Mock(__getitem__=Mock(return_value=18.5))))
        
        mock_ticker_instance = Mock()
        mock_ticker_instance.history.return_value = mock_history
        mock_ticker.return_value = mock_ticker_instance
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(self.temp_config, f)
            config_path = f.name
        
        try:
            monitor = VIXMonitor(config_path)
            is_spike, vix_value, reason = monitor.is_vix_spike_active(send_alerts=False)
            
            assert is_spike is False
            assert vix_value == 18.5
            assert "normal" in reason.lower()
            assert "18.50 <= 25.0" in reason
        finally:
            os.unlink(config_path)
    
    def test_vix_caching(self):
        """Test VIX data caching mechanism."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(self.temp_config, f)
            config_path = f.name
        
        try:
            monitor = VIXMonitor(config_path)
            
            # Set cached data
            cached_vix = VIXData(value=20.0, timestamp=datetime.now())
            monitor._cached_vix = cached_vix
            
            # Should return cached data without API call
            with patch('utils.vix_monitor.yf.Ticker') as mock_ticker:
                vix_data = monitor.get_current_vix()
                
                assert vix_data.value == 20.0
                mock_ticker.assert_not_called()  # Should use cache
        finally:
            os.unlink(config_path)
    
    @patch('utils.vix_monitor.yf.Ticker')
    def test_vix_fetch_failure_fallback(self, mock_ticker):
        """Test VIX fetch failure with cached fallback."""
        # Mock yfinance failure
        mock_ticker.side_effect = Exception("API Error")
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(self.temp_config, f)
            config_path = f.name
        
        try:
            monitor = VIXMonitor(config_path)
            
            # Set stale cached data
            stale_vix = VIXData(value=22.0, timestamp=datetime.now() - timedelta(minutes=10))
            monitor._cached_vix = stale_vix
            
            vix_data = monitor.get_current_vix()
            
            # Should return stale cache on failure
            assert vix_data.value == 22.0
            assert vix_data.age_minutes > 9
        finally:
            os.unlink(config_path)
    
    def test_vix_status_summary(self):
        """Test VIX status summary for dashboard."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(self.temp_config, f)
            config_path = f.name
        
        try:
            monitor = VIXMonitor(config_path)
            
            # Test with cached data
            cached_vix = VIXData(value=28.0, timestamp=datetime.now())
            monitor._cached_vix = cached_vix
            
            status = monitor.get_vix_status_summary()
            
            assert status["enabled"] is True
            assert status["status"] == "spike"  # 28.0 > 25.0 threshold
            assert status["vix_value"] == 28.0
            assert status["threshold"] == 25.0
            assert status["blocking_trades"] is True
            assert "message" in status
        finally:
            os.unlink(config_path)


class TestVIXGlobalFunctions:
    """Test global VIX utility functions."""
    
    @patch('utils.vix_monitor.VIXMonitor')
    def test_check_vix_spike_function(self, mock_monitor_class):
        """Test check_vix_spike convenience function."""
        mock_monitor = Mock()
        mock_monitor.is_vix_spike_active.return_value = (True, 32.0, "VIX spike")
        mock_monitor_class.return_value = mock_monitor
        
        is_spike, vix_value, reason = check_vix_spike()
        
        assert is_spike is True
        assert vix_value == 32.0
        assert reason == "VIX spike"
    
    @patch('utils.vix_monitor.VIXMonitor')
    def test_get_vix_monitor_singleton(self, mock_monitor_class):
        """Test VIX monitor singleton pattern."""
        mock_monitor = Mock()
        mock_monitor_class.return_value = mock_monitor
        
        # Clear singleton
        import utils.vix_monitor
        utils.vix_monitor._vix_monitor_instance = None
        
        monitor1 = get_vix_monitor()
        monitor2 = get_vix_monitor()
        
        assert monitor1 is monitor2  # Should be same instance
        mock_monitor_class.assert_called_once()  # Should only create once


class TestVIXIntegration:
    """Test VIX integration with trading system."""
    
    @patch('utils.vix_monitor.check_vix_spike')
    def test_vix_integration_with_pre_llm_gate(self, mock_check_vix):
        """Test VIX integration with trading decision gate."""
        from utils.multi_symbol_scanner import MultiSymbolScanner
        
        # Mock VIX spike
        mock_check_vix.return_value = (True, 35.0, "VIX spike detected: 35.0 > 30.0")
        
        config = {"SYMBOLS": ["SPY"], "multi_symbol": {"enabled": False}}
        scanner = MultiSymbolScanner(config, None, None)
        
        market_data = {"symbol": "SPY", "current_price": 500.0}
        proceed, reason = scanner._pre_llm_hard_gate(market_data, config)
        
        assert proceed is False
        assert "VIX spike blocking trades" in reason
        assert "35.0 > 30.0" in reason
    
    @patch('utils.vix_monitor.check_vix_spike')
    def test_vix_normal_allows_trading(self, mock_check_vix):
        """Test that normal VIX allows trading to proceed."""
        from utils.multi_symbol_scanner import MultiSymbolScanner
        
        # Mock normal VIX
        mock_check_vix.return_value = (False, 18.5, "VIX normal: 18.5 <= 30.0")
        
        config = {
            "SYMBOLS": ["SPY"], 
            "multi_symbol": {"enabled": False},
            "MIN_TR_RANGE_PCT": 0.1,
            "MIN_TR_RANGE_PCT_BY_SYMBOL": {"SPY": 0.1}
        }
        scanner = MultiSymbolScanner(config, None, None)
        
        # Mock market data with sufficient TR
        market_data = {
            "symbol": "SPY", 
            "current_price": 500.0,
            "today_true_range_pct": 0.15  # Above 0.1% threshold
        }
        
        with patch('utils.multi_symbol_scanner.datetime') as mock_dt:
            # Mock market hours (11 AM ET)
            mock_now = Mock()
            mock_now.weekday.return_value = 1  # Tuesday
            mock_now.time.return_value = Mock()
            mock_now.time.return_value.__ge__ = Mock(return_value=False)  # Before 15:15
            mock_now.time.return_value.__lt__ = Mock(return_value=False)  # After 09:30
            
            mock_dt.now.return_value = mock_now
            
            proceed, reason = scanner._pre_llm_hard_gate(market_data, config)
            
            # Should proceed since VIX is normal and other conditions met
            assert proceed is True or "VIX" not in reason  # VIX should not block


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
