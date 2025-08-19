"""
Unit tests for the Stress Testing Framework (US-FA-013)

Tests the comprehensive stress testing capabilities including VIX spikes,
circuit breaker validation, emergency stop mechanisms, data source failures,
and system health monitoring under adverse conditions.
"""

import pytest
import json
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from pathlib import Path

# Import the stress testing framework
from utils.stress_testing import StressTestFramework, StressTestResult


class TestStressTestResult:
    """Test the StressTestResult class."""
    
    def test_result_initialization(self):
        """Test stress test result initialization."""
        result = StressTestResult("Test Name", "Test Category")
        
        assert result.test_name == "Test Name"
        assert result.category == "Test Category"
        assert result.start_time is not None
        assert result.end_time is None
        assert result.passed is False
        assert result.error_message is None
        assert result.metrics == {}
        assert result.logs == []
    
    def test_result_completion(self):
        """Test marking result as complete."""
        result = StressTestResult("Test", "Category")
        metrics = {"key": "value"}
        
        result.complete(True, "Success", metrics)
        
        assert result.passed is True
        assert result.error_message == "Success"
        assert result.metrics == metrics
        assert result.end_time is not None
        assert result.duration is not None
    
    def test_add_log(self):
        """Test adding log entries."""
        result = StressTestResult("Test", "Category")
        
        result.add_log("Test message", "INFO")
        
        assert len(result.logs) == 1
        assert result.logs[0]["message"] == "Test message"
        assert result.logs[0]["level"] == "INFO"
        assert "timestamp" in result.logs[0]
    
    def test_to_dict(self):
        """Test converting result to dictionary."""
        result = StressTestResult("Test", "Category")
        result.complete(True, metrics={"test": 123})
        result.add_log("Test log")
        
        result_dict = result.to_dict()
        
        assert result_dict["test_name"] == "Test"
        assert result_dict["category"] == "Category"
        assert result_dict["passed"] is True
        assert result_dict["metrics"]["test"] == 123
        assert len(result_dict["logs"]) == 1


class TestStressTestFramework:
    """Test the StressTestFramework class."""
    
    @pytest.fixture
    def mock_config(self):
        """Mock configuration for testing."""
        return {
            "DAILY_DRAWDOWN_ENABLED": True,
            "DAILY_DRAWDOWN_THRESHOLD_PERCENT": 5.0,
            "WEEKLY_DRAWDOWN_ENABLED": True,
            "WEEKLY_DRAWDOWN_THRESHOLD_PERCENT": 15.0,
            "VIX_POSITION_SIZING_ENABLED": True,
            "HEALTH_MONITORING_ENABLED": True
        }
    
    @pytest.fixture
    def framework(self, mock_config):
        """Create stress test framework for testing."""
        with patch('utils.stress_testing.load_config', return_value=mock_config):
            with patch('utils.stress_testing.EnhancedSlackIntegration'):
                with patch('utils.stress_testing.SystemHealthMonitor.get_instance'):
                    return StressTestFramework(mock_config)
    
    def test_framework_initialization(self, framework):
        """Test framework initialization."""
        assert framework.config is not None
        assert framework.results == []
        assert framework.test_data_dir.exists()
    
    @patch('utils.stress_testing.VIXMonitor')
    def test_vix_stress_tests(self, mock_vix_monitor, framework):
        """Test VIX stress testing scenarios."""
        # Mock VIX monitor
        mock_monitor_instance = Mock()
        mock_vix_monitor.return_value = mock_monitor_instance
        
        # Test extreme VIX spike
        mock_monitor_instance.get_position_size_adjustment.return_value = 0.05  # Heavily reduced
        
        framework.run_vix_stress_tests()
        
        # Should have created VIX stress test results
        vix_results = [r for r in framework.results if r.category == "VIX Stress"]
        assert len(vix_results) >= 1
        
        # Check that extreme VIX test passed
        extreme_vix_test = next((r for r in vix_results if "Extreme" in r.test_name), None)
        assert extreme_vix_test is not None
        assert extreme_vix_test.passed is True
    
    @patch('utils.stress_testing.DrawdownCircuitBreaker')
    @patch('utils.bankroll.BankrollManager.get_current_bankroll')
    def test_circuit_breaker_tests(self, mock_bankroll, mock_circuit_breaker, framework):
        """Test circuit breaker stress scenarios."""
        # Mock circuit breaker
        mock_breaker_instance = Mock()
        mock_circuit_breaker.return_value = mock_breaker_instance
        
        # Mock daily drawdown trigger
        mock_breaker_instance.should_block_trading.return_value = (True, "Daily drawdown exceeded 5%")
        mock_bankroll.return_value = 940.0  # 6% loss
        
        framework.run_circuit_breaker_tests()
        
        # Should have created circuit breaker test results
        cb_results = [r for r in framework.results if r.category == "Circuit Breaker"]
        assert len(cb_results) >= 1
        
        # Check that daily drawdown test exists
        daily_test = next((r for r in cb_results if "Daily" in r.test_name), None)
        assert daily_test is not None
    
    @patch('utils.stress_testing.KillSwitch')
    def test_emergency_stop_tests(self, mock_kill_switch, framework):
        """Test emergency stop mechanisms."""
        # Mock kill switch
        mock_switch_instance = Mock()
        mock_kill_switch.return_value = mock_switch_instance
        
        # Test file-based activation
        mock_switch_instance.is_active.side_effect = [False, True]  # Initially inactive, then active
        mock_switch_instance.should_block_trading.return_value = (True, "Emergency stop active")
        
        framework.run_emergency_stop_tests()
        
        # Should have created emergency stop test results
        es_results = [r for r in framework.results if r.category == "Emergency Stop"]
        assert len(es_results) >= 1
        
        # Check that file-based test exists
        file_test = next((r for r in es_results if "File-based" in r.test_name), None)
        assert file_test is not None
    
    @patch('utils.stress_testing.DataValidator')
    @patch('utils.stress_testing.StalenessMonitor')
    def test_data_failure_tests(self, mock_staleness, mock_validator, framework):
        """Test data source failure scenarios."""
        # Mock data validator for API failure
        mock_validator_instance = Mock()
        mock_validator.return_value = mock_validator_instance
        mock_validator_instance.validate_symbol_data.return_value = Mock(
            quality="Poor",
            recommendation="BLOCK_TRADING"
        )
        
        # Mock staleness monitor
        mock_staleness_instance = Mock()
        mock_staleness.return_value = mock_staleness_instance
        mock_staleness_instance.check_data_staleness.return_value = {
            "SPY": {"classification": "Stale", "staleness_seconds": 300}
        }
        
        framework.run_data_failure_tests()
        
        # Should have created data failure test results
        df_results = [r for r in framework.results if r.category == "Data Failure"]
        assert len(df_results) >= 1
        
        # Check that API failure test exists
        api_test = next((r for r in df_results if "API Failure" in r.test_name), None)
        assert api_test is not None
    
    @patch('shutil.disk_usage')
    @patch('psutil.virtual_memory')
    def test_system_health_tests(self, mock_memory, mock_disk, framework):
        """Test system health monitoring under stress."""
        # Mock low disk space
        mock_disk.return_value = (100 * 1024**3, 10 * 1024**3, 90 * 1024**3)
        
        # Mock high memory usage
        mock_memory.return_value = Mock(percent=95.0, available=1024**3)
        
        # Mock health monitor to return unhealthy status
        framework.health_monitor.perform_health_check = Mock(return_value=Mock(
            overall_status="Critical",
            trading_allowed=False,
            checks=[Mock(component="Disk Space", status="Critical")]
        ))
        
        framework.run_system_health_tests()
        
        # Should have created system health test results
        sh_results = [r for r in framework.results if r.category == "System Health"]
        assert len(sh_results) >= 1
        
        # Check that disk space test exists
        disk_test = next((r for r in sh_results if "Disk Space" in r.test_name), None)
        assert disk_test is not None
    
    def test_generate_report(self, framework):
        """Test report generation."""
        # Add some mock results
        result1 = StressTestResult("Test 1", "Category A")
        result1.complete(True, metrics={"test": 1})
        
        result2 = StressTestResult("Test 2", "Category A")
        result2.complete(False, "Test failed")
        
        result3 = StressTestResult("Test 3", "Category B")
        result3.complete(True)
        
        framework.results = [result1, result2, result3]
        
        report = framework.generate_report()
        
        # Check report structure
        assert "timestamp" in report
        assert "summary" in report
        assert "categories" in report
        assert "recommendations" in report
        
        # Check summary
        assert report["summary"]["total_tests"] == 3
        assert report["summary"]["passed_tests"] == 2
        assert report["summary"]["failed_tests"] == 1
        assert report["summary"]["success_rate"] == pytest.approx(66.67, rel=1e-2)
        
        # Check categories
        assert "Category A" in report["categories"]
        assert "Category B" in report["categories"]
        assert report["categories"]["Category A"]["passed"] == 1
        assert report["categories"]["Category A"]["failed"] == 1
        assert report["categories"]["Category B"]["passed"] == 1
        assert report["categories"]["Category B"]["failed"] == 0
    
    def test_recommendations_generation(self, framework):
        """Test recommendation generation based on results."""
        # Add failed tests from different categories
        vix_fail = StressTestResult("VIX Test", "VIX Stress")
        vix_fail.complete(False, "VIX test failed")
        
        cb_fail = StressTestResult("Circuit Breaker Test", "Circuit Breaker")
        cb_fail.complete(False, "Circuit breaker failed")
        
        framework.results = [vix_fail, cb_fail]
        
        recommendations = framework._generate_recommendations()
        
        assert len(recommendations) > 0
        assert any("failed test" in rec.lower() for rec in recommendations)
        assert any("vix" in rec.lower() for rec in recommendations)
        assert any("circuit breaker" in rec.lower() for rec in recommendations)
    
    def test_all_tests_passed_recommendations(self, framework):
        """Test recommendations when all tests pass."""
        # Add passing tests
        result1 = StressTestResult("Test 1", "Category A")
        result1.complete(True)
        
        result2 = StressTestResult("Test 2", "Category B")
        result2.complete(True)
        
        framework.results = [result1, result2]
        
        recommendations = framework._generate_recommendations()
        
        assert any("all stress tests passed" in rec.lower() for rec in recommendations)
        assert any("system appears robust" in rec.lower() for rec in recommendations)


class TestStressTestIntegration:
    """Integration tests for the stress testing framework."""
    
    @pytest.fixture
    def temp_config_file(self):
        """Create temporary config file for testing."""
        config_data = {
            "DAILY_DRAWDOWN_ENABLED": True,
            "DAILY_DRAWDOWN_THRESHOLD_PERCENT": 5.0,
            "WEEKLY_DRAWDOWN_ENABLED": True,
            "WEEKLY_DRAWDOWN_THRESHOLD_PERCENT": 15.0,
            "VIX_POSITION_SIZING_ENABLED": True,
            "HEALTH_MONITORING_ENABLED": True
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            import yaml
            yaml.dump(config_data, f)
            temp_file = f.name
        
        yield temp_file
        
        # Cleanup
        os.unlink(temp_file)
    
    @patch('utils.stress_testing.EnhancedSlackIntegration')
    @patch('utils.stress_testing.SystemHealthMonitor.get_instance')
    def test_framework_with_real_config(self, mock_health, mock_slack, temp_config_file):
        """Test framework initialization with real config file."""
        with patch('utils.stress_testing.load_config') as mock_load:
            mock_load.return_value = {
                "DAILY_DRAWDOWN_ENABLED": True,
                "VIX_POSITION_SIZING_ENABLED": True
            }
            
            framework = StressTestFramework()
            
            assert framework.config is not None
            assert framework.test_data_dir.exists()
    
    def test_stress_test_data_directory_creation(self):
        """Test that stress test data directory is created."""
        with patch('utils.stress_testing.load_config', return_value={}):
            with patch('utils.stress_testing.EnhancedSlackIntegration'):
                with patch('utils.stress_testing.SystemHealthMonitor.get_instance'):
                    framework = StressTestFramework()
                    
                    assert framework.test_data_dir.exists()
                    assert framework.test_data_dir.is_dir()
    
    def test_report_file_creation(self):
        """Test that report files are created correctly."""
        mock_config = {
            "DAILY_DRAWDOWN_ENABLED": True,
            "VIX_POSITION_SIZING_ENABLED": True
        }
        
        with patch('utils.stress_testing.load_config', return_value=mock_config):
            with patch('utils.stress_testing.EnhancedSlackIntegration'):
                with patch('utils.stress_testing.SystemHealthMonitor.get_instance'):
                    framework = StressTestFramework(mock_config)
                    
                    # Add a test result
                    result = StressTestResult("Test", "Category")
                    result.complete(True)
                    framework.results = [result]
                    
                    report = framework.generate_report()
                    
                    # Check that report file was created
                    report_files = list(framework.test_data_dir.glob("stress_test_report_*.json"))
                    assert len(report_files) >= 1
                    
                    # Verify report file content
                    with open(report_files[-1], 'r') as f:
                        saved_report = json.load(f)
                    
                    assert saved_report["summary"]["total_tests"] == 1
                    assert saved_report["summary"]["passed_tests"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
