"""
Comprehensive test suite for Weekly Drawdown Protection (US-FA-005)

Tests the WeeklyPnLTracker and integrated circuit breaker functionality
to ensure robust capital preservation during extended losing periods.
"""

import pytest
import json
import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

# Import the modules under test
from utils.weekly_pnl_tracker import WeeklyPnLTracker
from utils.drawdown_circuit_breaker import DrawdownCircuitBreaker
from utils.llm import load_config


class TestWeeklyPnLTracker:
    """Test suite for WeeklyPnLTracker functionality"""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files"""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
    @pytest.fixture
    def mock_config(self):
        """Mock configuration for testing"""
        return {
            'BROKER': 'alpaca',
            'ALPACA_ENV': 'paper',
            'WEEKLY_DRAWDOWN_PERFORMANCE_WINDOW': 7,
            'WEEKLY_DRAWDOWN_MIN_TRADING_DAYS': 3
        }
    
    @pytest.fixture
    def sample_trade_data(self):
        """Sample trade data for testing"""
        base_time = datetime.now()
        return [
            {
                'timestamp': (base_time - timedelta(days=6)).isoformat(),
                'symbol': 'SPY',
                'pnl': 100.0,
                'broker_env': 'alpaca:paper'
            },
            {
                'timestamp': (base_time - timedelta(days=5)).isoformat(),
                'symbol': 'QQQ',
                'pnl': -50.0,
                'broker_env': 'alpaca:paper'
            },
            {
                'timestamp': (base_time - timedelta(days=4)).isoformat(),
                'symbol': 'IWM',
                'pnl': -200.0,
                'broker_env': 'alpaca:paper'
            },
            {
                'timestamp': (base_time - timedelta(days=3)).isoformat(),
                'symbol': 'SPY',
                'pnl': 75.0,
                'broker_env': 'alpaca:paper'
            },
            {
                'timestamp': (base_time - timedelta(days=2)).isoformat(),
                'symbol': 'QQQ',
                'pnl': -150.0,
                'broker_env': 'alpaca:paper'
            },
            {
                'timestamp': (base_time - timedelta(days=1)).isoformat(),
                'symbol': 'IWM',
                'pnl': -300.0,
                'broker_env': 'alpaca:paper'
            },
            {
                'timestamp': base_time.isoformat(),
                'symbol': 'SPY',
                'pnl': 25.0,
                'broker_env': 'alpaca:paper'
            }
        ]
    
    def test_weekly_tracker_initialization(self, mock_config, temp_dir):
        """Test WeeklyPnLTracker initialization"""
        with patch('utils.weekly_pnl_tracker.load_config', return_value=mock_config):
            with patch('utils.weekly_pnl_tracker.Path.cwd', return_value=temp_dir):
                tracker = WeeklyPnLTracker()
                
                assert tracker.performance_window == 7
                assert tracker.min_trading_days == 3
                assert tracker.broker == 'alpaca'
                assert tracker.env == 'paper'
    
    def test_weekly_performance_calculation(self, mock_config, temp_dir, sample_trade_data):
        """Test weekly performance calculation with sample data"""
        # Create mock trade history file
        trade_file = temp_dir / "trade_history_alpaca_paper.csv"
        trade_file.write_text("timestamp,symbol,pnl,broker_env\n")
        
        with patch('utils.weekly_pnl_tracker.load_config', return_value=mock_config):
            with patch('utils.weekly_pnl_tracker.Path.cwd', return_value=temp_dir):
                with patch.object(WeeklyPnLTracker, '_load_trade_history', return_value=sample_trade_data):
                    tracker = WeeklyPnLTracker()
                    performance = tracker.get_weekly_performance()
                    
                    # Expected: 100 - 50 - 200 + 75 - 150 - 300 + 25 = -500
                    assert performance['total_pnl'] == -500.0
                    assert performance['trading_days'] == 7
                    assert performance['winning_days'] == 3
                    assert performance['losing_days'] == 4
                    assert performance['worst_day_pnl'] == -300.0
                    assert performance['best_day_pnl'] == 100.0
    
    def test_weekly_pnl_percentage_calculation(self, mock_config, temp_dir):
        """Test weekly P&L percentage calculation"""
        sample_data = [
            {
                'timestamp': datetime.now().isoformat(),
                'symbol': 'SPY',
                'pnl': -150.0,  # 15% loss on $1000 balance
                'broker_env': 'alpaca:paper'
            }
        ]
        
        with patch('utils.weekly_pnl_tracker.load_config', return_value=mock_config):
            with patch('utils.weekly_pnl_tracker.Path.cwd', return_value=temp_dir):
                with patch.object(WeeklyPnLTracker, '_load_trade_history', return_value=sample_data):
                    with patch.object(WeeklyPnLTracker, '_get_start_balance', return_value=1000.0):
                        tracker = WeeklyPnLTracker()
                        performance = tracker.get_weekly_performance()
                        
                        assert performance['weekly_pnl_percent'] == -15.0
    
    def test_insufficient_trading_days(self, mock_config, temp_dir):
        """Test behavior with insufficient trading days"""
        sample_data = [
            {
                'timestamp': datetime.now().isoformat(),
                'symbol': 'SPY',
                'pnl': -100.0,
                'broker_env': 'alpaca:paper'
            }
        ]
        
        with patch('utils.weekly_pnl_tracker.load_config', return_value=mock_config):
            with patch('utils.weekly_pnl_tracker.Path.cwd', return_value=temp_dir):
                with patch.object(WeeklyPnLTracker, '_load_trade_history', return_value=sample_data):
                    tracker = WeeklyPnLTracker()
                    performance = tracker.get_weekly_performance()
                    
                    assert performance['trading_days'] == 1
                    assert performance['trading_days'] < tracker.min_trading_days


class TestWeeklyCircuitBreakerIntegration:
    """Test suite for weekly circuit breaker integration"""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files"""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
    @pytest.fixture
    def weekly_config(self):
        """Configuration with weekly protection enabled"""
        return {
            'DAILY_DRAWDOWN_ENABLED': True,
            'DAILY_DRAWDOWN_THRESHOLD_PERCENT': 5.0,
            'WEEKLY_DRAWDOWN_ENABLED': True,
            'WEEKLY_DRAWDOWN_THRESHOLD_PERCENT': 15.0,
            'WEEKLY_DRAWDOWN_REQUIRE_MANUAL_RESET': True,
            'WEEKLY_DRAWDOWN_ALERT_LEVELS': [10.0, 12.5, 15.0],
            'WEEKLY_DRAWDOWN_PERFORMANCE_WINDOW': 7,
            'WEEKLY_DRAWDOWN_MIN_TRADING_DAYS': 3,
            'BROKER': 'alpaca',
            'ALPACA_ENV': 'paper'
        }
    
    def test_weekly_protection_initialization(self, weekly_config, temp_dir):
        """Test circuit breaker initialization with weekly protection"""
        with patch('utils.drawdown_circuit_breaker.load_config', return_value=weekly_config):
            with patch('utils.drawdown_circuit_breaker.Path.cwd', return_value=temp_dir):
                breaker = DrawdownCircuitBreaker()
                
                assert breaker.weekly_enabled == True
                assert breaker.weekly_threshold_percent == 15.0
                assert breaker.weekly_min_trading_days == 3
                assert breaker.weekly_tracker is not None
    
    def test_weekly_protection_precedence(self, weekly_config, temp_dir):
        """Test that weekly protection takes precedence over daily"""
        with patch('utils.drawdown_circuit_breaker.load_config', return_value=weekly_config):
            with patch('utils.drawdown_circuit_breaker.Path.cwd', return_value=temp_dir):
                breaker = DrawdownCircuitBreaker()
                
                # Mock weekly protection triggered
                mock_weekly_performance = {
                    'weekly_pnl_percent': -16.0,  # Exceeds 15% threshold
                    'trading_days': 5,
                    'total_pnl': -800.0
                }
                
                with patch.object(breaker.weekly_tracker, 'get_weekly_performance', return_value=mock_weekly_performance):
                    with patch.object(breaker, '_save_state'):
                        allowed, reason = breaker.check_trading_allowed(current_pnl_percent=-3.0)  # Daily within limits
                        
                        assert not allowed
                        assert "Weekly protection triggered" in reason
                        assert breaker.state.get('weekly_disabled') == True
    
    def test_weekly_protection_with_insufficient_days(self, weekly_config, temp_dir):
        """Test weekly protection with insufficient trading days"""
        with patch('utils.drawdown_circuit_breaker.load_config', return_value=weekly_config):
            with patch('utils.drawdown_circuit_breaker.Path.cwd', return_value=temp_dir):
                breaker = DrawdownCircuitBreaker()
                
                # Mock insufficient trading days
                mock_weekly_performance = {
                    'weekly_pnl_percent': -20.0,  # Would exceed threshold
                    'trading_days': 2,  # Below minimum of 3
                    'total_pnl': -400.0
                }
                
                with patch.object(breaker.weekly_tracker, 'get_weekly_performance', return_value=mock_weekly_performance):
                    allowed, reason = breaker.check_trading_allowed(current_pnl_percent=-3.0)
                    
                    assert allowed
                    assert "Weekly protection inactive" in reason
    
    def test_weekly_protection_manual_reset(self, weekly_config, temp_dir):
        """Test manual reset of weekly protection"""
        with patch('utils.drawdown_circuit_breaker.load_config', return_value=weekly_config):
            with patch('utils.drawdown_circuit_breaker.Path.cwd', return_value=temp_dir):
                breaker = DrawdownCircuitBreaker()
                
                # Set weekly disabled state
                breaker.state.update({
                    'weekly_disabled': True,
                    'weekly_disable_reason': 'Test disable',
                    'weekly_disable_date': datetime.now().isoformat()
                })
                
                with patch.object(breaker, '_save_state'):
                    with patch.object(breaker.slack, 'send_weekly_system_reenable_alert'):
                        success, message = breaker.reset_weekly_protection("Manual test reset")
                        
                        assert success
                        assert "Weekly protection reset" in message
                        assert not breaker.state.get('weekly_disabled', False)
    
    def test_weekly_alert_levels(self, weekly_config, temp_dir):
        """Test weekly alert level notifications"""
        with patch('utils.drawdown_circuit_breaker.load_config', return_value=weekly_config):
            with patch('utils.drawdown_circuit_breaker.Path.cwd', return_value=temp_dir):
                breaker = DrawdownCircuitBreaker()
                
                # Mock weekly performance at alert level
                mock_weekly_performance = {
                    'weekly_pnl_percent': -12.5,  # At alert level
                    'trading_days': 5,
                    'total_pnl': -625.0
                }
                
                with patch.object(breaker.weekly_tracker, 'get_weekly_performance', return_value=mock_weekly_performance):
                    with patch.object(breaker, '_save_state'):
                        with patch.object(breaker.slack, 'send_heartbeat') as mock_slack:
                            allowed, reason = breaker.check_trading_allowed()
                            
                            assert allowed  # Still within threshold
                            assert "Weekly protection OK" in reason
                            mock_slack.assert_called_once()  # Alert sent


class TestWeeklyProtectionErrorHandling:
    """Test error handling in weekly protection system"""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files"""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
    @pytest.fixture
    def weekly_config(self):
        """Configuration with weekly protection enabled"""
        return {
            'WEEKLY_DRAWDOWN_ENABLED': True,
            'WEEKLY_DRAWDOWN_THRESHOLD_PERCENT': 15.0,
            'BROKER': 'alpaca',
            'ALPACA_ENV': 'paper'
        }
    
    def test_weekly_tracker_error_handling(self, weekly_config, temp_dir):
        """Test error handling when weekly tracker fails"""
        with patch('utils.drawdown_circuit_breaker.load_config', return_value=weekly_config):
            with patch('utils.drawdown_circuit_breaker.Path.cwd', return_value=temp_dir):
                breaker = DrawdownCircuitBreaker()
                
                # Mock weekly tracker to raise exception
                with patch.object(breaker.weekly_tracker, 'get_weekly_performance', side_effect=Exception("Test error")):
                    allowed, reason = breaker.check_trading_allowed()
                    
                    assert allowed  # Should allow trading on error
                    assert "Weekly protection check failed" in reason
    
    def test_slack_alert_error_handling(self, weekly_config, temp_dir):
        """Test error handling when Slack alerts fail"""
        with patch('utils.drawdown_circuit_breaker.load_config', return_value=weekly_config):
            with patch('utils.drawdown_circuit_breaker.Path.cwd', return_value=temp_dir):
                breaker = DrawdownCircuitBreaker()
                
                # Mock weekly performance that triggers protection
                mock_weekly_performance = {
                    'weekly_pnl_percent': -16.0,
                    'trading_days': 5,
                    'total_pnl': -800.0
                }
                
                with patch.object(breaker.weekly_tracker, 'get_weekly_performance', return_value=mock_weekly_performance):
                    with patch.object(breaker, '_save_state'):
                        with patch.object(breaker.slack, 'send_weekly_system_disable_alert', side_effect=Exception("Slack error")):
                            allowed, reason = breaker.check_trading_allowed()
                            
                            assert not allowed  # Should still disable trading
                            assert breaker.state.get('weekly_disabled') == True


class TestWeeklyProtectionConfiguration:
    """Test configuration loading and validation for weekly protection"""
    
    def test_default_configuration_values(self):
        """Test default configuration values are properly set"""
        default_config = {
            'WEEKLY_DRAWDOWN_ENABLED': True,
            'WEEKLY_DRAWDOWN_THRESHOLD_PERCENT': 15.0,
            'WEEKLY_DRAWDOWN_REQUIRE_MANUAL_RESET': True,
            'WEEKLY_DRAWDOWN_ALERT_LEVELS': [10.0, 12.5, 15.0],
            'WEEKLY_DRAWDOWN_PERFORMANCE_WINDOW': 7,
            'WEEKLY_DRAWDOWN_MIN_TRADING_DAYS': 3
        }
        
        with patch('utils.drawdown_circuit_breaker.load_config', return_value=default_config):
            with tempfile.TemporaryDirectory() as temp_dir:
                with patch('utils.drawdown_circuit_breaker.Path.cwd', return_value=Path(temp_dir)):
                    breaker = DrawdownCircuitBreaker()
                    
                    assert breaker.weekly_enabled == True
                    assert breaker.weekly_threshold_percent == 15.0
                    assert breaker.weekly_require_manual_reset == True
                    assert breaker.weekly_alert_levels == [10.0, 12.5, 15.0]
                    assert breaker.weekly_performance_window == 7
                    assert breaker.weekly_min_trading_days == 3
    
    def test_disabled_weekly_protection(self):
        """Test behavior when weekly protection is disabled"""
        disabled_config = {
            'WEEKLY_DRAWDOWN_ENABLED': False,
            'DAILY_DRAWDOWN_ENABLED': True,
            'DAILY_DRAWDOWN_THRESHOLD_PERCENT': 5.0
        }
        
        with patch('utils.drawdown_circuit_breaker.load_config', return_value=disabled_config):
            with tempfile.TemporaryDirectory() as temp_dir:
                with patch('utils.drawdown_circuit_breaker.Path.cwd', return_value=Path(temp_dir)):
                    breaker = DrawdownCircuitBreaker()
                    
                    assert breaker.weekly_enabled == False
                    assert breaker.weekly_tracker is None
                    
                    # Should only check daily protection
                    allowed, reason = breaker.check_trading_allowed(current_pnl_percent=-3.0)
                    assert allowed
                    assert "daily loss within" in reason.lower()


if __name__ == "__main__":
    # Run tests if executed directly
    pytest.main([__file__, "-v"])
