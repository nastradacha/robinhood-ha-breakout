#!/usr/bin/env python3
"""
Test loop timing functionality for continuous scan mode.

Tests that sleep_secs respects --interval even when run_once() takes variable time.
Uses monkeypatch on time.sleep to verify timing calculations.
"""

import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from zoneinfo import ZoneInfo

# Import the functions we need to test
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from main import main_loop, run_once, parse_end_time


class TestLoopTiming:
    """Test suite for loop timing functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.tz = ZoneInfo("America/New_York")
        self.mock_config = {
            'SYMBOL': 'SPY',
            'TRADE_LOG_FILE': 'test_trade_log.csv',
            'HEADLESS': True,
            'IMPLICIT_WAIT': 5,
            'PAGE_LOAD_TIMEOUT': 15
        }
        self.mock_args = Mock()
        self.mock_args.interval = 5  # 5 minute intervals
        self.mock_args.dry_run = True
        
        self.mock_env_vars = {
            'RH_USER': 'test@example.com',
            'RH_PASS': 'testpass'
        }
        
        # Mock all the manager objects
        self.mock_bankroll_manager = Mock()
        self.mock_portfolio_manager = Mock()
        self.mock_llm_client = Mock()
        self.mock_slack_notifier = Mock()
    
    def test_parse_end_time_valid_format(self):
        """Test parsing valid end time formats."""
        # Test normal time
        end_time = parse_end_time("12:30")
        assert end_time is not None
        assert end_time.hour == 12
        assert end_time.minute == 30
        
        # Test edge cases
        end_time = parse_end_time("00:00")
        assert end_time.hour == 0
        assert end_time.minute == 0
        
        end_time = parse_end_time("23:59")
        assert end_time.hour == 23
        assert end_time.minute == 59
    
    def test_parse_end_time_invalid_format(self):
        """Test parsing invalid end time formats."""
        with pytest.raises(ValueError):
            parse_end_time("25:00")  # Invalid hour
        
        with pytest.raises(ValueError):
            parse_end_time("12:60")  # Invalid minute
        
        with pytest.raises(ValueError):
            parse_end_time("12")     # Missing minute
        
        with pytest.raises(ValueError):
            parse_end_time("12:30:45")  # Too many parts
        
        with pytest.raises(ValueError):
            parse_end_time("abc:def")   # Non-numeric
    
    def test_parse_end_time_none_input(self):
        """Test parsing None input."""
        result = parse_end_time(None)
        assert result is None
        
        result = parse_end_time("")
        assert result is None
    
    @patch('time.sleep')
    @patch('main.datetime')
    def test_loop_timing_fast_cycle(self, mock_datetime, mock_sleep):
        """Test timing when run_once completes quickly."""
        # Mock datetime to control time progression
        start_time = datetime(2024, 1, 1, 9, 30, 0, tzinfo=self.tz)
        end_time = datetime(2024, 1, 1, 9, 30, 10, tzinfo=self.tz)  # 10 seconds later
        
        mock_datetime.now.side_effect = [start_time, end_time]
        
        # Mock run_once to return NO_TRADE decision
        mock_decision = Mock()
        mock_decision.decision = "NO_TRADE"
        mock_decision.confidence = 0.3
        mock_decision.reason = "No clear pattern"
        mock_decision.tokens_used = 100
        
        with patch('main.run_once') as mock_run_once:
            mock_run_once.return_value = {
                'analysis': {'current_price': 635.0, 'candle_body_pct': 0.1},
                'decision': mock_decision,
                'current_bankroll': 1000.0,
                'position_size': 0
            }
            
            # Mock the loop to exit after one iteration
            with patch('main.datetime') as mock_dt:
                mock_dt.now.side_effect = [
                    start_time,  # cycle_start
                    end_time,    # cycle_end
                    start_time + timedelta(minutes=6)  # next iteration (should exit)
                ]
                
                # Set end time to exit after first cycle
                loop_end_time = start_time + timedelta(minutes=1)
                
                try:
                    main_loop(
                        self.mock_config, self.mock_args, self.mock_env_vars,
                        self.mock_bankroll_manager, self.mock_portfolio_manager,
                        self.mock_llm_client, self.mock_slack_notifier, loop_end_time
                    )
                except SystemExit:
                    pass  # Expected when loop exits
        
        # Verify sleep was called with correct duration
        # Cycle took 10 seconds, interval is 5 minutes (300 seconds)
        # So sleep should be 300 - 10 = 290 seconds
        expected_sleep = 300 - 10  # 290 seconds
        mock_sleep.assert_called_with(expected_sleep)
    
    @patch('time.sleep')
    @patch('main.datetime')
    def test_loop_timing_slow_cycle(self, mock_datetime, mock_sleep):
        """Test timing when run_once takes longer than interval."""
        # Mock datetime to control time progression
        start_time = datetime(2024, 1, 1, 9, 30, 0, tzinfo=self.tz)
        end_time = datetime(2024, 1, 1, 9, 36, 0, tzinfo=self.tz)  # 6 minutes later
        
        # Mock run_once to return NO_TRADE decision
        mock_decision = Mock()
        mock_decision.decision = "NO_TRADE"
        mock_decision.confidence = 0.3
        mock_decision.reason = "No clear pattern"
        mock_decision.tokens_used = 100
        
        with patch('main.run_once') as mock_run_once:
            mock_run_once.return_value = {
                'analysis': {'current_price': 635.0, 'candle_body_pct': 0.1},
                'decision': mock_decision,
                'current_bankroll': 1000.0,
                'position_size': 0
            }
            
            # Mock the loop to exit after one iteration
            with patch('main.datetime') as mock_dt:
                mock_dt.now.side_effect = [
                    start_time,  # cycle_start
                    end_time,    # cycle_end
                    start_time + timedelta(minutes=7)  # next iteration (should exit)
                ]
                
                # Set end time to exit after first cycle
                loop_end_time = start_time + timedelta(minutes=1)
                
                try:
                    main_loop(
                        self.mock_config, self.mock_args, self.mock_env_vars,
                        self.mock_bankroll_manager, self.mock_portfolio_manager,
                        self.mock_llm_client, self.mock_slack_notifier, loop_end_time
                    )
                except SystemExit:
                    pass  # Expected when loop exits
        
        # Verify sleep was called with 0 (cycle took longer than interval)
        # Cycle took 6 minutes (360 seconds), interval is 5 minutes (300 seconds)
        # So sleep should be max(0, 300 - 360) = 0
        mock_sleep.assert_called_with(0)
    
    @patch('time.sleep')
    def test_loop_timing_variable_intervals(self, mock_sleep):
        """Test different interval settings."""
        test_cases = [
            (1, 60),    # 1 minute interval
            (3, 180),   # 3 minute interval
            (10, 600),  # 10 minute interval
            (15, 900),  # 15 minute interval
        ]
        
        for interval_minutes, expected_seconds in test_cases:
            with patch('main.datetime') as mock_dt:
                start_time = datetime(2024, 1, 1, 9, 30, 0, tzinfo=self.tz)
                end_time = start_time + timedelta(seconds=5)  # Fast 5-second cycle
                
                mock_dt.now.side_effect = [
                    start_time,  # cycle_start
                    end_time,    # cycle_end
                    start_time + timedelta(minutes=interval_minutes + 1)  # exit
                ]
                
                # Update args for this test
                self.mock_args.interval = interval_minutes
                
                # Mock run_once
                mock_decision = Mock()
                mock_decision.decision = "NO_TRADE"
                mock_decision.confidence = 0.3
                mock_decision.reason = "No clear pattern"
                mock_decision.tokens_used = 100
                
                with patch('main.run_once') as mock_run_once:
                    mock_run_once.return_value = {
                        'analysis': {'current_price': 635.0, 'candle_body_pct': 0.1},
                        'decision': mock_decision,
                        'current_bankroll': 1000.0,
                        'position_size': 0
                    }
                    
                    # Set end time to exit after first cycle
                    loop_end_time = start_time + timedelta(seconds=1)
                    
                    try:
                        main_loop(
                            self.mock_config, self.mock_args, self.mock_env_vars,
                            self.mock_bankroll_manager, self.mock_portfolio_manager,
                            self.mock_llm_client, self.mock_slack_notifier, loop_end_time
                        )
                    except SystemExit:
                        pass  # Expected when loop exits
                
                # Verify sleep was called with correct duration
                expected_sleep = expected_seconds - 5  # Subtract 5-second cycle time
                mock_sleep.assert_called_with(expected_sleep)
    
    def test_end_time_logic(self):
        """Test that loop exits correctly when end time is reached."""
        with patch('main.datetime') as mock_dt:
            start_time = datetime(2024, 1, 1, 9, 30, 0, tzinfo=self.tz)
            end_time = datetime(2024, 1, 1, 9, 31, 0, tzinfo=self.tz)  # 1 minute later
            
            # First call returns start time, second call returns end time (should exit)
            mock_dt.now.side_effect = [start_time, end_time]
            
            # Mock run_once (shouldn't be called since we exit immediately)
            with patch('main.run_once') as mock_run_once:
                try:
                    main_loop(
                        self.mock_config, self.mock_args, self.mock_env_vars,
                        self.mock_bankroll_manager, self.mock_portfolio_manager,
                        self.mock_llm_client, self.mock_slack_notifier, end_time
                    )
                except SystemExit:
                    pass  # Expected when loop exits
                
                # run_once should not be called since we exit immediately
                mock_run_once.assert_not_called()
    
    @patch('main.time.sleep')
    def test_heartbeat_timing_accuracy(self, mock_sleep):
        """Test that heartbeat messages are sent at correct intervals."""
        with patch('main.datetime') as mock_dt:
            # Simulate multiple cycles
            times = [
                datetime(2024, 1, 1, 9, 30, 0, tzinfo=self.tz),  # cycle 1 start
                datetime(2024, 1, 1, 9, 30, 2, tzinfo=self.tz),  # cycle 1 end
                datetime(2024, 1, 1, 9, 35, 0, tzinfo=self.tz),  # cycle 2 start
                datetime(2024, 1, 1, 9, 35, 3, tzinfo=self.tz),  # cycle 2 end
                datetime(2024, 1, 1, 9, 40, 1, tzinfo=self.tz),  # exit time
            ]
            mock_dt.now.side_effect = times
            
            # Mock run_once to return NO_TRADE decisions
            mock_decision = Mock()
            mock_decision.decision = "NO_TRADE"
            mock_decision.confidence = 0.3
            mock_decision.reason = "No clear pattern"
            mock_decision.tokens_used = 100
            
            with patch('main.run_once') as mock_run_once:
                mock_run_once.return_value = {
                    'analysis': {'current_price': 635.0, 'candle_body_pct': 0.1},
                    'decision': mock_decision,
                    'current_bankroll': 1000.0,
                    'position_size': 0
                }
                
                # Set end time to allow 2 cycles
                loop_end_time = datetime(2024, 1, 1, 9, 40, 0, tzinfo=self.tz)
                
                try:
                    main_loop(
                        self.mock_config, self.mock_args, self.mock_env_vars,
                        self.mock_bankroll_manager, self.mock_portfolio_manager,
                        self.mock_llm_client, self.mock_slack_notifier, loop_end_time
                    )
                except SystemExit:
                    pass  # Expected when loop exits
            
            # Verify sleep was called twice with correct durations
            expected_calls = [
                ((300 - 2,),),  # First cycle: 5min - 2sec = 298sec
                ((300 - 3,),),  # Second cycle: 5min - 3sec = 297sec
            ]
            assert mock_sleep.call_count == 2
            assert mock_sleep.call_args_list == expected_calls
    
    def test_slack_heartbeat_integration(self):
        """Test that Slack heartbeat messages are sent correctly."""
        mock_decision = Mock()
        mock_decision.decision = "NO_TRADE"
        mock_decision.confidence = 0.3
        mock_decision.reason = "No clear pattern"
        mock_decision.tokens_used = 100
        
        with patch('main.run_once') as mock_run_once:
            mock_run_once.return_value = {
                'analysis': {'current_price': 635.0, 'candle_body_pct': 0.15},
                'decision': mock_decision,
                'current_bankroll': 1000.0,
                'position_size': 0
            }
            
            with patch('main.datetime') as mock_dt:
                start_time = datetime(2024, 1, 1, 9, 30, 0, tzinfo=self.tz)
                end_time = datetime(2024, 1, 1, 9, 30, 5, tzinfo=self.tz)
                
                mock_dt.now.side_effect = [
                    start_time,  # cycle_start
                    end_time,    # cycle_end
                    start_time + timedelta(minutes=6)  # exit
                ]
                
                # Set end time to exit after first cycle
                loop_end_time = start_time + timedelta(seconds=1)
                
                with patch('time.sleep'):  # Mock sleep to speed up test
                    try:
                        main_loop(
                            self.mock_config, self.mock_args, self.mock_env_vars,
                            self.mock_bankroll_manager, self.mock_portfolio_manager,
                            self.mock_llm_client, self.mock_slack_notifier, loop_end_time
                        )
                    except SystemExit:
                        pass  # Expected when loop exits
        
        # Verify heartbeat was sent
        self.mock_slack_notifier.send_heartbeat.assert_called_once()
        call_args = self.mock_slack_notifier.send_heartbeat.call_args[0][0]
        assert "09:30" in call_args  # Time should be in message
        assert "No breakout" in call_args  # Status should be in message
        assert "0.15%" in call_args  # Body percentage should be in message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
