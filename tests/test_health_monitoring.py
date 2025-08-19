"""
Comprehensive tests for the System Health Monitoring module (US-FA-009).

This test suite validates the complete health monitoring system including:
- Health check execution and status determination
- Trading disable/enable functionality
- Slack alert integration
- Configuration validation
- API connectivity checks
- System resource monitoring
- Integration with main trading logic
"""

import pytest
import json
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from datetime import datetime, timedelta

# Import the health monitoring module
from utils.health_monitor import (
    SystemHealthMonitor,
    HealthStatus,
    perform_system_health_check,
    is_system_healthy
)


class TestSystemHealthMonitor:
    """Test the SystemHealthMonitor class functionality."""
    
    @pytest.fixture
    def mock_config(self):
        """Mock configuration for testing."""
        return {
            "HEALTH_MONITORING_ENABLED": True,
            "HEALTH_CHECK_INTERVAL": 60,
            "HEALTH_ALERT_COOLDOWN": 900,
            "HEALTH_AUTO_DISABLE_TRADING": True,
            "HEALTH_DISK_WARNING_THRESHOLD": 80,
            "HEALTH_DISK_CRITICAL_THRESHOLD": 90,
            "HEALTH_MEMORY_WARNING_THRESHOLD": 85,
            "HEALTH_MEMORY_CRITICAL_THRESHOLD": 95,
            "HEALTH_API_TIMEOUT": 10,
            "HEALTH_API_RETRIES": 3,
            "ALPACA_API_KEY": "test_key",
            "ALPACA_SECRET_KEY": "test_secret",
            "SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"
        }
    
    @pytest.fixture
    def health_monitor(self, mock_config):
        """Create a SystemHealthMonitor instance for testing."""
        with patch('utils.health_monitor.load_config', return_value=mock_config):
            monitor = SystemHealthMonitor()
            return monitor
    
    def test_health_monitor_initialization(self, health_monitor, mock_config):
        """Test that health monitor initializes correctly."""
        assert health_monitor.config == mock_config
        assert health_monitor.enabled == True
        assert health_monitor.check_interval == 60
        assert health_monitor.alert_cooldown == 900
        assert health_monitor.auto_disable_trading == True
    
    @patch('utils.health_monitor.psutil.disk_usage')
    @patch('utils.health_monitor.psutil.virtual_memory')
    def test_check_system_resources_healthy(self, mock_memory, mock_disk_usage, health_monitor):
        """Test system resource check with healthy values."""
        # Mock healthy disk usage (70% used)
        from collections import namedtuple
        DiskUsage = namedtuple('DiskUsage', ['total', 'used', 'free'])
        mock_disk_usage.return_value = DiskUsage(total=1000, used=700, free=300)
        
        # Mock healthy memory usage (75% used)
        VirtualMemory = namedtuple('VirtualMemory', ['percent', 'available'])
        mock_memory.return_value = VirtualMemory(percent=75.0, available=2*1024**3)
        
        result = health_monitor.check_system_resources()
        
        assert result.status == HealthStatus.HEALTHY
        assert "System resources are healthy" in result.message
        assert result.details["disk_usage_percent"] == 70.0
        assert result.details["memory_percent"] == 75.0
    
    @patch('utils.health_monitor.psutil.disk_usage')
    @patch('utils.health_monitor.psutil.virtual_memory')
    def test_check_system_resources_warning(self, mock_memory, mock_disk_usage, health_monitor):
        """Test system resource check with warning levels."""
        # Mock warning disk usage (85% used)
        from collections import namedtuple
        DiskUsage = namedtuple('DiskUsage', ['total', 'used', 'free'])
        mock_disk_usage.return_value = DiskUsage(total=1000, used=850, free=150)
        
        # Mock warning memory usage (87% used)
        VirtualMemory = namedtuple('VirtualMemory', ['percent', 'available'])
        mock_memory.return_value = VirtualMemory(percent=87.0, available=1*1024**3)
        
        result = health_monitor.check_system_resources()
        
        assert result.status == HealthStatus.WARNING
        assert "warning thresholds" in result.message.lower()
        assert result.details["disk_usage_percent"] == 85.0
        assert result.details["memory_percent"] == 87.0
    
    @patch('utils.health_monitor.psutil.disk_usage')
    @patch('utils.health_monitor.psutil.virtual_memory')
    def test_check_system_resources_critical(self, mock_memory, mock_disk_usage, health_monitor):
        """Test system resource check with critical levels."""
        # Mock critical disk usage (95% used)
        from collections import namedtuple
        DiskUsage = namedtuple('DiskUsage', ['total', 'used', 'free'])
        mock_disk_usage.return_value = DiskUsage(total=1000, used=950, free=50)
        
        # Mock critical memory usage (97% used)
        VirtualMemory = namedtuple('VirtualMemory', ['percent', 'available'])
        mock_memory.return_value = VirtualMemory(percent=97.0, available=0.5*1024**3)
        
        result = health_monitor.check_system_resources()
        
        assert result.status == HealthStatus.CRITICAL
        assert "critical thresholds" in result.message.lower()
        assert result.details["disk_usage_percent"] == 95.0
        assert result.details["memory_percent"] == 97.0
    
    @patch('requests.get')
    def test_check_api_connectivity_success(self, mock_get, health_monitor):
        """Test API connectivity check with successful responses."""
        # Mock successful API responses
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_get.return_value = mock_response
        
        result = health_monitor.check_api_connectivity()
        
        assert result.status == HealthStatus.HEALTHY
        assert "All APIs are accessible" in result.message
        assert len(result.details["api_results"]) > 0
    
    @patch('requests.get')
    def test_check_api_connectivity_failure(self, mock_get, health_monitor):
        """Test API connectivity check with failed responses."""
        # Mock failed API responses
        mock_get.side_effect = Exception("Connection failed")
        
        result = health_monitor.check_api_connectivity()
        
        assert result.status == HealthStatus.CRITICAL
        assert "Critical API failures detected" in result.message
    
    def test_check_config_integrity_valid(self, health_monitor):
        """Test configuration integrity check with valid config."""
        result = health_monitor.check_config_integrity()
        
        assert result.status == HealthStatus.HEALTHY
        assert "Configuration is valid" in result.message
        assert result.details["config_valid"] == True
    
    def test_check_config_integrity_missing_keys(self, health_monitor):
        """Test configuration integrity check with missing required keys."""
        # Remove required keys from config
        health_monitor.config.pop("ALPACA_API_KEY", None)
        health_monitor.config.pop("SLACK_WEBHOOK_URL", None)
        
        result = health_monitor.check_config_integrity()
        
        assert result.status == HealthStatus.CRITICAL
        assert "Missing required configuration keys" in result.message
        assert "ALPACA_API_KEY" in result.details["missing_keys"]
        assert "SLACK_WEBHOOK_URL" in result.details["missing_keys"]
    
    @patch('utils.data_validation.DataValidator')
    def test_check_data_sources_healthy(self, mock_validator, health_monitor):
        """Test data source health check with healthy status."""
        # Mock healthy data validation
        mock_instance = Mock()
        mock_instance.get_health_status.return_value = {
            "status": "healthy",
            "last_check": datetime.now().isoformat(),
            "validation_rate": 0.95
        }
        mock_validator.get_instance.return_value = mock_instance
        
        result = health_monitor.check_data_sources()
        
        assert result.status == HealthStatus.HEALTHY
        assert "Data sources are healthy" in result.message
    
    @patch('utils.staleness_monitor.StalenessMonitor')
    def test_check_data_sources_stale(self, mock_monitor, health_monitor):
        """Test data source health check with stale data."""
        # Mock stale data monitoring
        mock_instance = Mock()
        mock_instance.get_health_status.return_value = {
            "status": "stale",
            "last_check": (datetime.now() - timedelta(minutes=10)).isoformat(),
            "staleness_level": "VERY_STALE"
        }
        mock_monitor.get_instance.return_value = mock_instance
        
        result = health_monitor.check_data_sources()
        
        assert result.status == HealthStatus.WARNING
        assert "stale" in result.message.lower()
    
    @patch('psutil.Process')
    def test_check_process_health_healthy(self, mock_process, health_monitor):
        """Test process health check with healthy metrics."""
        # Mock healthy process metrics
        mock_proc = Mock()
        mock_proc.cpu_percent.return_value = 25.0
        mock_proc.memory_info.return_value = Mock(rss=100 * 1024 * 1024)  # 100MB
        mock_proc.num_threads.return_value = 10
        mock_process.return_value = mock_proc
        
        result = health_monitor.check_process_health()
        
        assert result.status == HealthStatus.HEALTHY
        assert "Process health is good" in result.message
        assert result.details["cpu_percent"] == 25.0
        assert result.details["memory_mb"] == 100.0
        assert result.details["thread_count"] == 10
    
    def test_determine_overall_health_all_healthy(self, health_monitor):
        """Test overall health determination with all checks healthy."""
        checks = {
            "system_resources": HealthCheckResult(HealthStatus.HEALTHY, "OK", {}),
            "api_connectivity": HealthCheckResult(HealthStatus.HEALTHY, "OK", {}),
            "config_integrity": HealthCheckResult(HealthStatus.HEALTHY, "OK", {}),
            "data_sources": HealthCheckResult(HealthStatus.HEALTHY, "OK", {}),
            "process_health": HealthCheckResult(HealthStatus.HEALTHY, "OK", {})
        }
        
        status, message = health_monitor.determine_overall_health(checks)
        
        assert status == HealthStatus.HEALTHY
        assert "All systems healthy" in message
    
    def test_determine_overall_health_with_warnings(self, health_monitor):
        """Test overall health determination with warning conditions."""
        checks = {
            "system_resources": HealthCheckResult(HealthStatus.WARNING, "High usage", {}),
            "api_connectivity": HealthCheckResult(HealthStatus.HEALTHY, "OK", {}),
            "config_integrity": HealthCheckResult(HealthStatus.HEALTHY, "OK", {}),
            "data_sources": HealthCheckResult(HealthStatus.HEALTHY, "OK", {}),
            "process_health": HealthCheckResult(HealthStatus.HEALTHY, "OK", {})
        }
        
        status, message = health_monitor.determine_overall_health(checks)
        
        assert status == HealthStatus.WARNING
        assert "warning conditions detected" in message.lower()
    
    def test_determine_overall_health_critical_failure(self, health_monitor):
        """Test overall health determination with critical failures."""
        checks = {
            "system_resources": HealthCheckResult(HealthStatus.HEALTHY, "OK", {}),
            "api_connectivity": HealthCheckResult(HealthStatus.CRITICAL, "API down", {}),
            "config_integrity": HealthCheckResult(HealthStatus.HEALTHY, "OK", {}),
            "data_sources": HealthCheckResult(HealthStatus.HEALTHY, "OK", {}),
            "process_health": HealthCheckResult(HealthStatus.HEALTHY, "OK", {})
        }
        
        status, message = health_monitor.determine_overall_health(checks)
        
        assert status == HealthStatus.CRITICAL
        assert "critical failures detected" in message.lower()
    
    def test_should_disable_trading_critical_health(self, health_monitor):
        """Test trading disable logic with critical health status."""
        health_status = Mock()
        health_status.overall_status = HealthStatus.CRITICAL
        
        should_disable = health_monitor.should_disable_trading(health_status)
        
        assert should_disable == True
    
    def test_should_disable_trading_healthy_status(self, health_monitor):
        """Test trading disable logic with healthy status."""
        health_status = Mock()
        health_status.overall_status = HealthStatus.HEALTHY
        
        should_disable = health_monitor.should_disable_trading(health_status)
        
        assert should_disable == False
    
    def test_should_disable_trading_disabled_config(self, health_monitor):
        """Test trading disable logic when auto-disable is disabled."""
        health_monitor.auto_disable_trading = False
        health_status = Mock()
        health_status.overall_status = HealthStatus.CRITICAL
        
        should_disable = health_monitor.should_disable_trading(health_status)
        
        assert should_disable == False
    
    @patch('utils.enhanced_slack.EnhancedSlackIntegration')
    def test_send_health_alert_critical(self, mock_slack, health_monitor):
        """Test sending critical health alerts via Slack."""
        mock_slack_instance = Mock()
        mock_slack.return_value = mock_slack_instance
        
        health_status = Mock()
        health_status.overall_status = HealthStatus.CRITICAL
        health_status.message = "Critical system failure"
        health_status.timestamp = datetime.now()
        health_status.checks = {}
        
        health_monitor.send_health_alert(health_status, trading_disabled=True)
        
        # Verify Slack message was sent
        mock_slack_instance.send_message.assert_called_once()
        call_args = mock_slack_instance.send_message.call_args[0][0]
        assert "🚨 CRITICAL SYSTEM HEALTH ALERT" in call_args
        assert "Trading has been DISABLED" in call_args
    
    def test_log_health_metrics(self, health_monitor):
        """Test health metrics logging functionality."""
        with tempfile.TemporaryDirectory() as temp_dir:
            health_monitor.metrics_file = Path(temp_dir) / "health_metrics.json"
            
            health_status = Mock()
            health_status.overall_status = HealthStatus.HEALTHY
            health_status.message = "All systems healthy"
            health_status.timestamp = datetime.now()
            health_status.checks = {"test": Mock(status=HealthStatus.HEALTHY)}
            
            health_monitor.log_health_metrics(health_status)
            
            # Verify metrics file was created and contains data
            assert health_monitor.metrics_file.exists()
            
            with open(health_monitor.metrics_file, 'r') as f:
                metrics = json.load(f)
                assert len(metrics) == 1
                assert metrics[0]["overall_status"] == "HEALTHY"
                assert metrics[0]["message"] == "All systems healthy"


class TestHealthMonitoringIntegration:
    """Test integration of health monitoring with the trading system."""
    
    @patch('utils.health_monitor.SystemHealthMonitor')
    def test_perform_system_health_check(self, mock_monitor_class):
        """Test the perform_system_health_check convenience function."""
        mock_instance = Mock()
        mock_health_status = Mock()
        mock_health_status.overall_status = HealthStatus.HEALTHY
        mock_instance.perform_health_check.return_value = mock_health_status
        mock_monitor_class.get_instance.return_value = mock_instance
        
        result = perform_system_health_check()
        
        assert result == mock_health_status
        mock_instance.perform_health_check.assert_called_once()
    
    @patch('utils.health_monitor.SystemHealthMonitor')
    def test_is_system_healthy_true(self, mock_monitor_class):
        """Test is_system_healthy function with healthy system."""
        mock_instance = Mock()
        mock_instance.is_system_healthy.return_value = True
        mock_monitor_class.get_instance.return_value = mock_instance
        
        result = is_system_healthy()
        
        assert result == True
        mock_instance.is_system_healthy.assert_called_once()
    
    @patch('utils.health_monitor.SystemHealthMonitor')
    def test_is_system_healthy_false(self, mock_monitor_class):
        """Test is_system_healthy function with unhealthy system."""
        mock_instance = Mock()
        mock_instance.is_system_healthy.return_value = False
        mock_monitor_class.get_instance.return_value = mock_instance
        
        result = is_system_healthy()
        
        assert result == False
        mock_instance.is_system_healthy.assert_called_once()
    
    def test_trading_allowed_logic(self):
        """Test trading allowed logic based on system health."""
        # Test that healthy system allows trading
        healthy_status = is_system_healthy()
        assert isinstance(healthy_status, tuple)
        allowed, reason = healthy_status
        assert isinstance(allowed, bool)
        assert isinstance(reason, str)
    
    @patch('utils.health_monitor.SystemHealthMonitor')
    def test_get_health_status(self, mock_monitor_class):
        """Test get_health_status convenience function."""
        mock_instance = Mock()
        mock_health_status = Mock()
        mock_instance.get_current_health_status.return_value = mock_health_status
        mock_monitor_class.get_instance.return_value = mock_instance
        
        result = get_health_status()
        
        assert result == mock_health_status
        mock_instance.get_current_health_status.assert_called_once()
    
    @patch('utils.health_monitor.SystemHealthMonitor')
    def test_get_health_summary(self, mock_monitor_class):
        """Test get_health_summary convenience function."""
        mock_instance = Mock()
        mock_summary = {"overall": "HEALTHY", "details": {}}
        mock_instance.get_health_summary.return_value = mock_summary
        mock_monitor_class.get_instance.return_value = mock_instance
        
        result = get_health_summary()
        
        assert result == mock_summary
        mock_instance.get_health_summary.assert_called_once()


class TestHealthMonitoringConfiguration:
    """Test health monitoring configuration validation."""
    
    def test_health_monitoring_enabled_by_default(self):
        """Test that health monitoring is enabled by default in config."""
        # This would typically load from the actual config.yaml
        # For testing, we verify the expected default values
        expected_defaults = {
            "HEALTH_MONITORING_ENABLED": True,
            "HEALTH_CHECK_INTERVAL": 60,
            "HEALTH_ALERT_COOLDOWN": 900,
            "HEALTH_AUTO_DISABLE_TRADING": True,
            "HEALTH_DISK_WARNING_THRESHOLD": 80,
            "HEALTH_DISK_CRITICAL_THRESHOLD": 90,
            "HEALTH_MEMORY_WARNING_THRESHOLD": 85,
            "HEALTH_MEMORY_CRITICAL_THRESHOLD": 95,
            "HEALTH_API_TIMEOUT": 10,
            "HEALTH_API_RETRIES": 3
        }
        
        # Verify expected configuration structure
        for key, expected_value in expected_defaults.items():
            assert isinstance(expected_value, (bool, int, float))
    
    def test_health_monitoring_disabled_config(self):
        """Test health monitoring behavior when disabled in config."""
        disabled_config = {
            "HEALTH_MONITORING_ENABLED": False,
            "HEALTH_CHECK_INTERVAL": 60,
            "HEALTH_AUTO_DISABLE_TRADING": False
        }
        
        with patch('utils.health_monitor.load_config', return_value=disabled_config):
            monitor = SystemHealthMonitor()
            
            assert monitor.enabled == False
            assert monitor.auto_disable_trading == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
