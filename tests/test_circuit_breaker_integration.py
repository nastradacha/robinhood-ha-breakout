#!/usr/bin/env python3
"""
End-to-End Integration Tests for Daily Drawdown Circuit Breaker

Tests complete trading scenarios with real-world workflows including:
- Multi-broker P&L tracking and circuit breaker activation
- File-based and Slack reset workflows
- Integration with position monitoring and main trading loop
- Performance impact assessment
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta
import time

from utils.drawdown_circuit_breaker import DrawdownCircuitBreaker, validate_circuit_breaker_config
from utils.daily_pnl_tracker import DailyPnLTracker
from utils.circuit_breaker_reset import check_and_process_file_reset, process_slack_reset_command


@pytest.fixture
def integration_config():
    """Configuration for integration tests."""
    return {
        "DAILY_DRAWDOWN_ENABLED": True,
        "DAILY_DRAWDOWN_THRESHOLD_PERCENT": 5.0,
        "DAILY_DRAWDOWN_REQUIRE_MANUAL_RESET": True,
        "DAILY_DRAWDOWN_RESET_TIME": "09:30",
        "DAILY_DRAWDOWN_ALERT_LEVELS": [2.5, 4.0],
        "SLACK_WEBHOOK_URL": "https://hooks.slack.com/test",
        "BROKER": "alpaca",
        "ALPACA_ENV": "paper"
    }


class TestEndToEndTradingScenarios:
    """Test complete trading scenarios that trigger circuit breaker."""
    
    def test_progressive_loss_scenario_with_alerts(self, integration_config):
        """Test trading day with progressive losses triggering warnings then activation."""
        with patch('utils.bankroll.BankrollManager.get_current_bankroll') as mock_get_bankroll:
            # Day starts with $1000 bankroll
            mock_get_bankroll.return_value = 1000.0
            
            # Initialize circuit breaker and track daily start
            cb = DrawdownCircuitBreaker(integration_config)
            cb.pnl_tracker.track_daily_start_balance()
            
            # Simulate first loss: -2% (should not trigger circuit breaker but may warn)
            mock_get_bankroll.return_value = 980.0
            should_block, reason = cb.check_daily_drawdown_limit()
            assert not should_block
            assert "within acceptable range" in reason.lower() or "warning" in reason.lower()
            
            # Simulate second loss: -4.5% (approaching threshold)
            mock_get_bankroll.return_value = 955.0
            should_block, reason = cb.check_daily_drawdown_limit()
            assert not should_block
            
            # Simulate final loss: -6% (should activate circuit breaker)
            mock_get_bankroll.return_value = 940.0
            should_block, reason = cb.check_daily_drawdown_limit()
            assert should_block
            assert "circuit breaker activated" in reason.lower()
            
            # Verify circuit breaker state
            status = cb.get_circuit_breaker_status()
            assert status["is_active"]
            assert abs(status["activation_pnl_percent"] - (-6.0)) < 0.1
    
    def test_multi_broker_aggregation_scenario(self, integration_config):
        """Test circuit breaker with losses across multiple broker environments."""
        with patch('utils.bankroll.BankrollManager.get_current_bankroll') as mock_get_bankroll:
            # Mock different balances for different brokers
            balance_map = {
                ("alpaca", "paper"): 500.0,
                ("alpaca", "live"): 300.0, 
                ("robinhood", "live"): 200.0
            }
            
            def mock_balance_side_effect(broker, env):
                return balance_map.get((broker, env), 0.0)
            
            mock_get_bankroll.side_effect = mock_balance_side_effect
            
            # Initialize circuit breaker
            cb = DrawdownCircuitBreaker(integration_config)
            cb.pnl_tracker.track_daily_start_balance()
            
            # Simulate losses across all brokers (total: $1000 -> $940 = -6%)
            balance_map[("alpaca", "paper")] = 470.0  # -30
            balance_map[("alpaca", "live")] = 280.0   # -20
            balance_map[("robinhood", "live")] = 190.0 # -10
            
            should_block, reason = cb.check_daily_drawdown_limit()
            assert should_block
            assert "circuit breaker activated" in reason.lower()
    
    def test_intraday_recovery_scenario(self, integration_config):
        """Test scenario where losses recover before hitting threshold."""
        with patch('utils.bankroll.BankrollManager.get_current_bankroll') as mock_get_bankroll:
            mock_get_bankroll.return_value = 1000.0
            
            cb = DrawdownCircuitBreaker(integration_config)
            cb.pnl_tracker.track_daily_start_balance()
            
            # Simulate loss approaching threshold
            mock_get_bankroll.return_value = 955.0  # -4.5%
            should_block, reason = cb.check_daily_drawdown_limit()
            assert not should_block
            
            # Simulate recovery
            mock_get_bankroll.return_value = 980.0  # -2%
            should_block, reason = cb.check_daily_drawdown_limit()
            assert not should_block
            
            # Verify circuit breaker remains inactive
            status = cb.get_circuit_breaker_status()
            assert not status["is_active"]


class TestResetWorkflows:
    """Test complete reset workflows."""
    
    def test_file_based_reset_workflow(self, integration_config):
        """Test complete file-based reset workflow."""
        with patch('utils.bankroll.BankrollManager.get_current_bankroll') as mock_get_bankroll:
            mock_get_bankroll.return_value = 940.0  # -6% loss
            
            # Activate circuit breaker
            cb = DrawdownCircuitBreaker(integration_config)
            cb.pnl_tracker.track_daily_start_balance()
            
            should_block, reason = cb.check_daily_drawdown_limit()
            assert should_block
            
            # Test file-based reset
            reset_file = Path("circuit_breaker_reset.trigger")
            reset_file.write_text("integration test reset")
            
            try:
                reset_executed, reset_message = check_and_process_file_reset(integration_config)
                assert reset_executed
                assert "successfully reset" in reset_message.lower()
                
                # Verify circuit breaker is now inactive
                should_block, reason = cb.check_daily_drawdown_limit()
                assert not should_block
                
            finally:
                if reset_file.exists():
                    reset_file.unlink()
    
    def test_slack_reset_workflow(self, integration_config):
        """Test Slack-based reset workflow."""
        with patch('utils.bankroll.BankrollManager.get_current_bankroll') as mock_get_bankroll:
            mock_get_bankroll.return_value = 940.0
            
            # Activate circuit breaker
            cb = DrawdownCircuitBreaker(integration_config)
            cb.pnl_tracker.track_daily_start_balance()
            
            should_block, reason = cb.check_daily_drawdown_limit()
            assert should_block
            
            # Test Slack reset command
            reset_executed, reset_message = process_slack_reset_command(
                "reset circuit breaker", integration_config
            )
            assert reset_executed
            assert "successfully reset" in reset_message.lower()
            
            # Verify circuit breaker is now inactive
            should_block, reason = cb.check_daily_drawdown_limit()
            assert not should_block


class TestSystemIntegration:
    """Test integration with main system components."""
    
    def test_integration_with_position_monitoring(self, integration_config):
        """Test circuit breaker integration with position monitoring system."""
        with patch('utils.bankroll.BankrollManager.get_current_bankroll') as mock_get_bankroll:
            mock_get_bankroll.return_value = 940.0
            
            # Activate circuit breaker
            cb = DrawdownCircuitBreaker(integration_config)
            cb.pnl_tracker.track_daily_start_balance()
            
            should_block, reason = cb.check_daily_drawdown_limit()
            assert should_block
            
            # Test file reset detection (simulating monitor_alpaca.py behavior)
            reset_file = Path("circuit_breaker_reset.trigger")
            reset_file.write_text("monitor reset test")
            
            try:
                # Simulate monitoring cycle checking for reset
                reset_executed, reset_message = check_and_process_file_reset(integration_config)
                assert reset_executed
                
                # Verify monitoring can detect reset
                should_block, reason = cb.check_daily_drawdown_limit()
                assert not should_block
                
            finally:
                if reset_file.exists():
                    reset_file.unlink()
    
    def test_integration_with_main_trading_loop(self, integration_config):
        """Test circuit breaker integration with main trading loop."""
        with patch('utils.bankroll.BankrollManager.get_current_bankroll') as mock_get_bankroll:
            mock_get_bankroll.return_value = 940.0
            
            # Activate circuit breaker
            cb = DrawdownCircuitBreaker(integration_config)
            cb.pnl_tracker.track_daily_start_balance()
            
            should_block, reason = cb.check_daily_drawdown_limit()
            assert should_block
            
            # Test main loop file reset detection
            reset_file = Path("circuit_breaker_reset.trigger")
            reset_file.write_text("main loop reset test")
            
            try:
                # Simulate main loop checking for reset
                reset_executed, reset_message = check_and_process_file_reset(integration_config)
                assert reset_executed
                
                # Verify main loop can detect reset
                should_block, reason = cb.check_daily_drawdown_limit()
                assert not should_block
                
            finally:
                if reset_file.exists():
                    reset_file.unlink()


class TestSlackIntegration:
    """Test Slack integration workflows."""
    
    def test_slack_activation_alert_workflow(self, integration_config):
        """Test complete Slack activation alert workflow."""
        with patch('utils.enhanced_slack.EnhancedSlackIntegration') as mock_slack:
            with patch('utils.bankroll.BankrollManager.get_current_bankroll') as mock_get_bankroll:
                mock_slack_instance = MagicMock()
                mock_slack.return_value = mock_slack_instance
                
                mock_get_bankroll.return_value = 1000.0
                
                # Initialize and activate circuit breaker
                cb = DrawdownCircuitBreaker(integration_config)
                cb.pnl_tracker.track_daily_start_balance()
                
                # Trigger activation
                mock_get_bankroll.return_value = 940.0
                should_block, reason = cb.check_daily_drawdown_limit()
                
                # Verify Slack activation alert was sent
                mock_slack_instance.send_circuit_breaker_activation_alert.assert_called_once()
                
                # Verify alert contains correct information
                call_args = mock_slack_instance.send_circuit_breaker_activation_alert.call_args[0][0]
                assert call_args["activation_pnl_percent"] == -6.0
    
    def test_slack_reset_command_workflow(self, integration_config):
        """Test complete Slack reset command workflow."""
        with patch('utils.enhanced_slack.EnhancedSlackIntegration') as mock_slack:
            with patch('utils.bankroll.BankrollManager.get_current_bankroll') as mock_get_bankroll:
                mock_slack_instance = MagicMock()
                mock_slack.return_value = mock_slack_instance
                
                mock_get_bankroll.return_value = 940.0
                
                # Activate circuit breaker
                cb = DrawdownCircuitBreaker(integration_config)
                cb.pnl_tracker.track_daily_start_balance()
                
                should_block, reason = cb.check_daily_drawdown_limit()
                assert should_block
                
                # Test Slack reset command
                reset_executed, reset_message = process_slack_reset_command(
                    "reset circuit breaker", integration_config
                )
                assert reset_executed
                
                # Verify Slack reset alert was sent
                mock_slack_instance.send_circuit_breaker_reset_alert.assert_called_once()


class TestConfigurationValidation:
    """Test configuration validation scenarios."""
    
    def test_valid_configuration(self, integration_config):
        """Test validation with valid configuration."""
        is_valid, errors = validate_circuit_breaker_config(integration_config)
        assert is_valid
        assert len(errors) == 0
    
    def test_invalid_threshold_configuration(self):
        """Test validation with invalid threshold."""
        config = {
            "DAILY_DRAWDOWN_ENABLED": True,
            "DAILY_DRAWDOWN_THRESHOLD_PERCENT": -5.0,  # Invalid: negative
            "DAILY_DRAWDOWN_REQUIRE_MANUAL_RESET": True,
            "DAILY_DRAWDOWN_RESET_TIME": "09:30",
            "DAILY_DRAWDOWN_ALERT_LEVELS": [2.5, 4.0],
            "SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"
        }
        
        is_valid, errors = validate_circuit_breaker_config(config)
        assert not is_valid
        assert any("must be between 0 and 50" in error for error in errors)
    
    def test_invalid_alert_levels_configuration(self):
        """Test validation with invalid alert levels."""
        config = {
            "DAILY_DRAWDOWN_ENABLED": True,
            "DAILY_DRAWDOWN_THRESHOLD_PERCENT": 5.0,
            "DAILY_DRAWDOWN_REQUIRE_MANUAL_RESET": True,
            "DAILY_DRAWDOWN_RESET_TIME": "09:30",
            "DAILY_DRAWDOWN_ALERT_LEVELS": [2.5, 6.0],  # Invalid: 6.0 > threshold
            "SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"
        }
        
        is_valid, errors = validate_circuit_breaker_config(config)
        assert not is_valid
        assert any("must be between 0 and 5.0" in error for error in errors)


class TestPerformanceImpact:
    """Test performance impact of circuit breaker on trading operations."""
    
    def test_circuit_breaker_check_performance(self, integration_config):
        """Test performance impact of circuit breaker checks."""
        with patch('utils.bankroll.BankrollManager.get_current_bankroll') as mock_get_bankroll:
            mock_get_bankroll.return_value = 1000.0
            
            cb = DrawdownCircuitBreaker(integration_config)
            cb.pnl_tracker.track_daily_start_balance()
            
            # Measure performance of circuit breaker check
            start_time = time.time()
            
            # Perform multiple checks to measure average performance
            for _ in range(100):
                should_block, reason = cb.check_daily_drawdown_limit()
            
            end_time = time.time()
            avg_time_per_check = (end_time - start_time) / 100
            
            # Circuit breaker check should be very fast (< 10ms per check)
            assert avg_time_per_check < 0.01, f"Circuit breaker check too slow: {avg_time_per_check:.4f}s"
    
    def test_file_reset_check_performance(self, integration_config):
        """Test performance impact of file reset checks."""
        # Measure performance of file reset check
        start_time = time.time()
        
        # Perform multiple checks to measure average performance
        for _ in range(100):
            reset_executed, reset_message = check_and_process_file_reset(integration_config)
        
        end_time = time.time()
        avg_time_per_check = (end_time - start_time) / 100
        
        # File reset check should be very fast (< 5ms per check)
        assert avg_time_per_check < 0.005, f"File reset check too slow: {avg_time_per_check:.4f}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
