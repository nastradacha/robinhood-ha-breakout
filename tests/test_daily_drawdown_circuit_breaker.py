"""
Comprehensive test suite for US-FA-004 Daily Drawdown Circuit Breaker

Tests cover:
- Daily P&L tracking across multiple brokers
- Circuit breaker activation and state management
- Manual reset mechanisms
- Slack alert integration
- Pre-LLM gate integration
- Multi-broker environment support
- Edge cases and error handling
"""

import pytest
import json
import tempfile
import shutil
from datetime import datetime, time, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytz

# Import modules under test
from utils.daily_pnl_tracker import DailyPnLTracker, get_daily_pnl_tracker
from utils.drawdown_circuit_breaker import DrawdownCircuitBreaker, get_drawdown_circuit_breaker, check_circuit_breaker
from utils.circuit_breaker_reset import CircuitBreakerResetManager, get_reset_manager, check_and_process_file_reset
from utils.multi_symbol_scanner import MultiSymbolScanner

# Test fixtures
@pytest.fixture
def temp_dir():
    """Create temporary directory for test files"""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)

@pytest.fixture
def test_config():
    """Standard test configuration"""
    return {
        "DAILY_DRAWDOWN_ENABLED": True,
        "DAILY_DRAWDOWN_THRESHOLD_PERCENT": 5.0,
        "DAILY_DRAWDOWN_POST_THRESHOLD_PERCENT": 0.0,
        "DAILY_DRAWDOWN_REQUIRE_MANUAL_RESET": True,
        "DAILY_DRAWDOWN_RESET_TIME": "09:30",
        "DAILY_DRAWDOWN_ALERT_LEVELS": [2.5, 4.0, 5.0],
        "BANKROLL_ALPACA_PAPER": 1000.0,
        "BANKROLL_ALPACA_LIVE": 5000.0,
        "BANKROLL_ROBINHOOD_LIVE": 2000.0
    }

@pytest.fixture
def mock_bankroll_data():
    """Mock bankroll data for different broker/environment combinations"""
    return {
        "alpaca_paper": {"current": 950.0, "starting": 1000.0},  # -5% loss
        "alpaca_live": {"current": 4800.0, "starting": 5000.0},  # -4% loss
        "robinhood_live": {"current": 1900.0, "starting": 2000.0}  # -5% loss
    }

class TestDailyPnLTracker:
    """Test Daily P&L Tracker functionality"""
    
    def test_daily_pnl_tracker_initialization(self, test_config, temp_dir):
        """Test tracker initialization and state creation"""
        with patch('utils.daily_pnl_tracker.Path.cwd', return_value=temp_dir):
            tracker = DailyPnLTracker(test_config)
            
            assert tracker.config == test_config
            assert tracker.state_file.name == "daily_pnl_tracker.json"
            assert isinstance(tracker._state, dict)
            assert "tracking_date" in tracker._state
            assert "broker_starting_balances" in tracker._state
    
    def test_daily_pnl_calculation_single_broker(self, test_config, temp_dir):
        """Test P&L calculation for single broker"""
        with patch('utils.daily_pnl_tracker.Path.cwd', return_value=temp_dir):
            tracker = DailyPnLTracker(test_config)
            
            # Mock bankroll manager
            mock_bankroll_manager = Mock()
            mock_bankroll_manager.get_current_bankroll.return_value = 950.0  # -5% from 1000 starting
            
            with patch('utils.daily_pnl_tracker.BankrollManager', return_value=mock_bankroll_manager):
                # Set starting balance
                tracker._state["broker_starting_balances"] = {"alpaca_paper": 1000.0}
                
                daily_pnl, daily_pnl_percent, breakdown = tracker.calculate_current_daily_pnl()
                
                assert daily_pnl == -50.0
                assert daily_pnl_percent == -5.0
                assert "alpaca_paper" in breakdown
                assert breakdown["alpaca_paper"]["pnl"] == -50.0
                assert breakdown["alpaca_paper"]["pnl_percent"] == -5.0
    
    def test_daily_pnl_calculation_multi_broker(self, test_config, temp_dir, mock_bankroll_data):
        """Test P&L calculation across multiple brokers"""
        with patch('utils.daily_pnl_tracker.Path.cwd', return_value=temp_dir):
            tracker = DailyPnLTracker(test_config)
            
            # Mock bankroll manager for multiple brokers
            def mock_bankroll_manager_factory(broker, env):
                mock_manager = Mock()
                key = f"{broker}_{env}"
                mock_manager.get_current_bankroll.return_value = mock_bankroll_data[key]["current"]
                return mock_manager
            
            with patch('utils.daily_pnl_tracker.BankrollManager', side_effect=mock_bankroll_manager_factory):
                # Set starting balances
                tracker._state["broker_starting_balances"] = {
                    "alpaca_paper": 1000.0,
                    "alpaca_live": 5000.0,
                    "robinhood_live": 2000.0
                }
                
                daily_pnl, daily_pnl_percent, breakdown = tracker.calculate_current_daily_pnl()
                
                # Total: -50 + -200 + -100 = -350 loss on 8000 starting = -4.375%
                expected_total_pnl = -350.0
                expected_total_percent = -4.375
                
                assert abs(daily_pnl - expected_total_pnl) < 0.01
                assert abs(daily_pnl_percent - expected_total_percent) < 0.01
                assert len(breakdown) == 3
    
    def test_daily_reset_logic(self, test_config, temp_dir):
        """Test daily reset functionality"""
        with patch('utils.daily_pnl_tracker.Path.cwd', return_value=temp_dir):
            tracker = DailyPnLTracker(test_config)
            
            # Set yesterday's date
            yesterday = datetime.now(pytz.timezone('US/Eastern')) - timedelta(days=1)
            tracker._state["tracking_date"] = yesterday.strftime("%Y-%m-%d")
            
            # Should trigger reset for new day
            assert tracker._should_reset_for_new_day()
            
            # Mock bankroll manager
            mock_bankroll_manager = Mock()
            mock_bankroll_manager.get_current_bankroll.return_value = 1000.0
            
            # Reset and verify
            with patch('utils.daily_pnl_tracker.BankrollManager', return_value=mock_bankroll_manager):
                tracker.reset_daily_tracking()
                
                today = datetime.now(pytz.timezone('US/Eastern'))
                assert tracker._state["tracking_date"] == today.strftime("%Y-%m-%d")

class TestDrawdownCircuitBreaker:
    """Test Drawdown Circuit Breaker functionality"""
    
    def test_circuit_breaker_initialization(self, test_config, temp_dir):
        """Test circuit breaker initialization"""
        with patch('utils.drawdown_circuit_breaker.Path.cwd', return_value=temp_dir):
            cb = DrawdownCircuitBreaker(test_config)
            
            assert cb.threshold_percent == 5.0
            assert cb.enabled == True
            assert cb.require_manual_reset == True
            assert not cb.is_circuit_breaker_active()
    
    def test_circuit_breaker_activation(self, test_config, temp_dir):
        """Test circuit breaker activation when threshold exceeded"""
        with patch('utils.drawdown_circuit_breaker.Path.cwd', return_value=temp_dir):
            cb = DrawdownCircuitBreaker(test_config)
            
            # Mock P&L tracker to return loss exceeding threshold
            mock_tracker = Mock()
            mock_tracker.calculate_current_daily_pnl.return_value = (
                -500.0,  # $500 loss
                -6.25,   # 6.25% loss (exceeds 5% threshold)
                {"alpaca_paper": {"pnl": -500.0, "pnl_percent": -6.25}}
            )
            
            with patch('utils.drawdown_circuit_breaker.get_daily_pnl_tracker', return_value=mock_tracker):
                with patch.object(cb, '_activate_circuit_breaker') as mock_activate:
                    should_block, reason = cb.check_daily_drawdown_limit()
                    
                    assert should_block
                    assert "Daily drawdown limit exceeded" in reason
                    assert "6.25%" in reason
                    mock_activate.assert_called_once()
    
    def test_circuit_breaker_within_limits(self, test_config, temp_dir):
        """Test circuit breaker when P&L is within limits"""
        with patch('utils.drawdown_circuit_breaker.Path.cwd', return_value=temp_dir):
            cb = DrawdownCircuitBreaker(test_config)
            
            # Mock P&L tracker to return loss within threshold
            mock_tracker = Mock()
            mock_tracker.calculate_current_daily_pnl.return_value = (
                -300.0,  # $300 loss
                -3.75,   # 3.75% loss (within 5% threshold)
                {"alpaca_paper": {"pnl": -300.0, "pnl_percent": -3.75}}
            )
            
            with patch('utils.drawdown_circuit_breaker.get_daily_pnl_tracker', return_value=mock_tracker):
                should_block, reason = cb.check_daily_drawdown_limit()
                
                assert not should_block
                assert "Daily P&L within limits" in reason
                assert "3.75%" in reason
    
    def test_circuit_breaker_disabled(self, test_config, temp_dir):
        """Test circuit breaker when disabled in config"""
        test_config["DAILY_DRAWDOWN_ENABLED"] = False
        
        with patch('utils.drawdown_circuit_breaker.Path.cwd', return_value=temp_dir):
            cb = DrawdownCircuitBreaker(test_config)
            
            should_block, reason = cb.check_daily_drawdown_limit()
            
            assert not should_block
            assert "disabled" in reason.lower()
    
    def test_manual_reset_functionality(self, test_config, temp_dir):
        """Test manual reset of active circuit breaker"""
        with patch('utils.drawdown_circuit_breaker.Path.cwd', return_value=temp_dir):
            cb = DrawdownCircuitBreaker(test_config)
            
            # Activate circuit breaker first
            cb.force_activate_circuit_breaker("Test activation")
            assert cb.is_circuit_breaker_active()
            
            # Test manual reset
            with patch('utils.drawdown_circuit_breaker.EnhancedSlackIntegration'):
                success = cb.manual_reset_circuit_breaker("Test reset")
                
                assert success
                assert not cb.is_circuit_breaker_active()
                assert cb._state["reset_count"] == 1
    
    def test_circuit_breaker_state_persistence(self, test_config, temp_dir):
        """Test circuit breaker state persistence across restarts"""
        state_file = temp_dir / "circuit_breaker_state.json"
        
        with patch('utils.drawdown_circuit_breaker.Path.cwd', return_value=temp_dir):
            # First instance - activate circuit breaker
            cb1 = DrawdownCircuitBreaker(test_config)
            cb1.force_activate_circuit_breaker("Test persistence")
            
            # Second instance - should load active state
            cb2 = DrawdownCircuitBreaker(test_config)
            assert cb2.is_circuit_breaker_active()
            assert "Test persistence" in cb2._state["activation_reason"]

class TestCircuitBreakerResetManager:
    """Test Circuit Breaker Reset Manager functionality"""
    
    def test_file_based_reset_trigger(self, test_config, temp_dir):
        """Test file-based reset trigger mechanism"""
        with patch('utils.circuit_breaker_reset.Path.cwd', return_value=temp_dir):
            reset_manager = CircuitBreakerResetManager(test_config)
            
            # Create reset trigger file
            reset_manager.create_reset_trigger_file("Emergency reset")
            
            # Check for reset trigger
            reset_triggered, reason = reset_manager.check_file_based_reset()
            
            assert reset_triggered
            assert "Emergency reset" in reason
            assert not reset_manager.reset_trigger_file.exists()  # File should be removed
    
    def test_slack_reset_command_processing(self, test_config, temp_dir):
        """Test Slack reset command processing"""
        with patch('utils.circuit_breaker_reset.Path.cwd', return_value=temp_dir):
            reset_manager = CircuitBreakerResetManager(test_config)
            
            # Test valid reset command
            with patch.object(reset_manager, 'execute_manual_reset', return_value=(True, "Reset successful")):
                success, response = reset_manager.process_slack_reset_command(
                    "reset circuit breaker reason: Market conditions improved", 
                    "user123"
                )
                
                assert success
                assert "✅" in response
                assert "Trading has been resumed" in response
    
    def test_reset_history_logging(self, test_config, temp_dir):
        """Test reset history logging and retrieval"""
        with patch('utils.circuit_breaker_reset.Path.cwd', return_value=temp_dir):
            reset_manager = CircuitBreakerResetManager(test_config)
            
            # Mock circuit breaker status
            mock_status = {
                "is_active": True,
                "activation_date": "2024-01-15",
                "activation_time": "10:30:00",
                "activation_pnl_percent": -6.5,
                "activation_reason": "Test activation"
            }
            
            # Log a reset
            reset_manager._log_reset("Test reset", "manual", mock_status)
            
            # Retrieve history
            history = reset_manager.get_reset_history(5)
            
            assert len(history) == 1
            assert history[0]["reset_reason"] == "Test reset"
            assert history[0]["reset_source"] == "manual"
            assert history[0]["status_before_reset"]["was_active"] == True

class TestIntegration:
    """Test integration with existing system components"""
    
    def test_pre_llm_gate_integration(self, test_config):
        """Test circuit breaker integration with pre-LLM gates"""
        market_data = {
            "symbol": "SPY",
            "current_price": 450.0,
            "today_true_range_pct": 2.0
        }
        
        # Mock circuit breaker to block trading
        with patch('utils.drawdown_circuit_breaker.check_circuit_breaker', return_value=(True, "Circuit breaker active: -6% daily loss")):
            with patch('utils.multi_symbol_scanner.datetime') as mock_datetime:
                # Mock current time to be during market hours
                mock_et_time = datetime(2024, 1, 15, 14, 30, 0, tzinfo=pytz.timezone('US/Eastern'))
                mock_datetime.now.return_value = mock_et_time
                
                with patch('utils.multi_symbol_scanner.validate_market_hours', return_value=(True, "Market open")):
                    with patch('utils.multi_symbol_scanner.validate_earnings_blocking', return_value=(True, "No earnings")):
                        # Create scanner instance and test gate
                        scanner = MultiSymbolScanner(test_config)
                        can_trade, reason = scanner._pre_llm_hard_gate(market_data, test_config)
                        
                        assert not can_trade
                        assert "Circuit breaker" in reason
                        assert "-6% daily loss" in reason
    
    def test_slack_alert_integration(self, test_config, temp_dir):
        """Test Slack alert integration with circuit breaker"""
        with patch('utils.drawdown_circuit_breaker.Path.cwd', return_value=temp_dir):
            cb = DrawdownCircuitBreaker(test_config)
            
            # Mock Slack integration
            mock_slack = Mock()
            
            with patch('utils.drawdown_circuit_breaker.EnhancedSlackIntegration', return_value=mock_slack):
                # Trigger circuit breaker activation
                cb._activate_circuit_breaker(
                    -6.5, 
                    -650.0, 
                    {"alpaca_paper": {"pnl": -650.0, "pnl_percent": -6.5}}
                )
                
                # Verify Slack alert was sent
                mock_slack.send_circuit_breaker_activation_alert.assert_called_once()
                
                # Verify alert content
                alert_info = mock_slack.send_circuit_breaker_activation_alert.call_args[0][0]
                assert alert_info["activation_pnl_percent"] == -6.5
                assert alert_info["threshold_percent"] == 5.0
    
    def test_multi_broker_environment_support(self, test_config, temp_dir, mock_bankroll_data):
        """Test support for multiple broker environments"""
        # Extended config with multiple brokers
        extended_config = {
            **test_config,
            "BROKER_ENVIRONMENTS": {
                "alpaca": ["paper", "live"],
                "robinhood": ["live"]
            }
        }
        
        with patch('utils.daily_pnl_tracker.Path.cwd', return_value=temp_dir):
            tracker = DailyPnLTracker(extended_config)
            
            # Mock bankroll manager for multiple environments
            bankroll_responses = {
                ("alpaca", "paper"): 950.0,
                ("alpaca", "live"): 4750.0,
                ("robinhood", "live"): 1900.0
            }
            
            def mock_bankroll_manager_factory(broker, env):
                mock_manager = Mock()
                key = (broker, env)
                mock_manager.get_current_bankroll.return_value = bankroll_responses.get(key, 0.0)
                return mock_manager
            
            with patch('utils.daily_pnl_tracker.BankrollManager', side_effect=mock_bankroll_manager_factory):
                # Set starting balances
                tracker._state["broker_starting_balances"] = {
                    "alpaca_paper": 1000.0,
                    "alpaca_live": 5000.0,
                    "robinhood_live": 2000.0
                }
                
                daily_pnl, daily_pnl_percent, breakdown = tracker.calculate_current_daily_pnl()
                
                # Verify all broker environments are included
                assert "alpaca_paper" in breakdown
                assert "alpaca_live" in breakdown
                assert "robinhood_live" in breakdown
                
                # Verify aggregated P&L calculation
                total_starting = 8000.0
                total_current = 950.0 + 4750.0 + 1900.0  # 7600.0
                expected_pnl = total_current - total_starting  # -400.0
                expected_percent = (expected_pnl / total_starting) * 100  # -5.0%
                
                assert abs(daily_pnl - expected_pnl) < 0.01
                assert abs(daily_pnl_percent - expected_percent) < 0.01

class TestErrorHandling:
    """Test error handling and edge cases"""
    
    def test_missing_bankroll_data_handling(self, test_config, temp_dir):
        """Test handling of missing bankroll data"""
        with patch('utils.daily_pnl_tracker.Path.cwd', return_value=temp_dir):
            tracker = DailyPnLTracker(test_config)
            
            # Mock bankroll manager to raise exception
            mock_bankroll_manager = Mock()
            mock_bankroll_manager.get_current_bankroll.side_effect = Exception("Bankroll unavailable")
            
            with patch('utils.daily_pnl_tracker.BankrollManager', return_value=mock_bankroll_manager):
                daily_pnl, daily_pnl_percent, breakdown = tracker.calculate_current_daily_pnl()
                
                # Should return zero values when bankroll unavailable
                assert daily_pnl == 0.0
                assert daily_pnl_percent == 0.0
                assert len(breakdown) == 0
    
    def test_corrupted_state_file_handling(self, test_config, temp_dir):
        """Test handling of corrupted state files"""
        # Create corrupted state file
        state_file = temp_dir / "circuit_breaker_state.json"
        state_file.write_text("invalid json content")
        
        with patch('utils.drawdown_circuit_breaker.Path.cwd', return_value=temp_dir):
            # Should handle corrupted file gracefully
            cb = DrawdownCircuitBreaker(test_config)
            
            assert not cb.is_circuit_breaker_active()
            assert isinstance(cb._state, dict)
    
    def test_circuit_breaker_fail_safe_behavior(self, test_config):
        """Test fail-safe behavior when circuit breaker check fails"""
        # Mock circuit breaker to raise exception
        with patch('utils.drawdown_circuit_breaker.get_drawdown_circuit_breaker', side_effect=Exception("System error")):
            should_block, reason = check_circuit_breaker(test_config)
            
            # Should fail-safe to allow trading
            assert not should_block
            assert "allowing trading" in reason.lower()
            assert "System error" in reason

class TestPublicAPI:
    """Test public API functions"""
    
    def test_get_daily_pnl_tracker_factory(self, test_config):
        """Test factory function for daily P&L tracker"""
        with patch('utils.daily_pnl_tracker.DailyPnLTracker') as mock_tracker_class:
            mock_instance = Mock()
            mock_tracker_class.return_value = mock_instance
            
            tracker = get_daily_pnl_tracker(test_config)
            
            assert tracker == mock_instance
            mock_tracker_class.assert_called_once_with(test_config)
    
    def test_get_drawdown_circuit_breaker_factory(self, test_config):
        """Test factory function for circuit breaker"""
        with patch('utils.drawdown_circuit_breaker.DrawdownCircuitBreaker') as mock_cb_class:
            mock_instance = Mock()
            mock_cb_class.return_value = mock_instance
            
            cb = get_drawdown_circuit_breaker(test_config)
            
            assert cb == mock_instance
            mock_cb_class.assert_called_once_with(test_config)
    
    def test_check_circuit_breaker_api(self, test_config):
        """Test public API for circuit breaker checking"""
        with patch('utils.drawdown_circuit_breaker.get_drawdown_circuit_breaker') as mock_get_cb:
            mock_cb = Mock()
            mock_cb.check_daily_drawdown_limit.return_value = (True, "Test block reason")
            mock_get_cb.return_value = mock_cb
            
            should_block, reason = check_circuit_breaker(test_config)
            
            assert should_block
            assert reason == "Test block reason"
            mock_cb.check_daily_drawdown_limit.assert_called_once()

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
