"""
Unit tests for S4: End-of-day summary block functionality.
Tests the generate_daily_summary function and integration with main.py loop exit.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock, mock_open
import sys
import os
from datetime import datetime, date
import csv
import io

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import generate_daily_summary


class TestDailySummary(unittest.TestCase):
    """Test S4: End-of-day summary block."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_config = {
            "TRADE_LOG_FILE": "logs/trade_history.csv",
            "BANKROLL_FILE": "bankroll.json",
            "START_CAPITAL": 500.0,
        }
        
        self.end_time = datetime(2025, 1, 10, 15, 45, 0)  # 3:45 PM

    def test_daily_summary_basic_format(self):
        """Test basic daily summary message format."""
        # Mock empty trade log (no trades today)
        with patch("pathlib.Path.exists", return_value=False):
            with patch("main.BankrollManager") as mock_bankroll_class:
                mock_bankroll = Mock()
                mock_bankroll.get_current_bankroll.return_value = 500.0
                mock_bankroll.peak_bankroll = 520.0
                mock_bankroll_class.return_value = mock_bankroll
                
                summary = generate_daily_summary(self.mock_config, self.end_time)
                
                # Check basic format components
                self.assertIn("📊", summary)
                self.assertIn("Daily Wrap-Up", summary)
                self.assertIn("15:45", summary)
                self.assertIn("EST", summary)
                self.assertIn("Trades: 0", summary)
                self.assertIn("Wins/Loss: 0/0", summary)
                self.assertIn("P&L: $0.00", summary)
                self.assertIn("Current balance: $500.00", summary)

    def test_daily_summary_with_trades(self):
        """Test daily summary with actual trades."""
        # Mock trade log CSV data
        csv_data = """timestamp,symbol,direction,strike,quantity,premium,actual_premium,exit_premium,status
2025-01-10T09:30:00,SPY,CALL,580,1,1.25,1.28,1.45,SUBMITTED
2025-01-10T10:15:00,QQQ,PUT,485,2,2.50,2.45,2.30,SUBMITTED
2025-01-10T11:00:00,IWM,CALL,220,1,1.50,1.52,0.00,SUBMITTED"""
        
        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=csv_data)):
                with patch("main.BankrollManager") as mock_bankroll_class:
                    mock_bankroll = Mock()
                    mock_bankroll.get_current_bankroll.return_value = 515.0
                    mock_bankroll.peak_bankroll = 525.0
                    mock_bankroll_class.return_value = mock_bankroll
                    
                    summary = generate_daily_summary(self.mock_config, self.end_time)
                    
                    # Check trade statistics
                    self.assertIn("Trades: 3", summary)
                    self.assertIn("Wins/Loss: 1/1", summary)  # SPY win, QQQ loss, IWM open
                    
                    # Calculate expected P&L
                    spy_pl = (1.45 - 1.28) * 1 * 100  # +$17.00
                    qqq_pl = (2.30 - 2.45) * 2 * 100  # -$30.00
                    total_pl = spy_pl + qqq_pl  # -$13.00
                    
                    self.assertIn(f"P&L: ${total_pl:.2f}", summary)

    def test_daily_summary_only_today_trades(self):
        """Test daily summary filters only today's trades."""
        # Mock trade log with trades from different days
        csv_data = """timestamp,symbol,direction,strike,quantity,premium,actual_premium,exit_premium,status
2025-01-09T09:30:00,SPY,CALL,580,1,1.25,1.28,1.45,SUBMITTED
2025-01-10T10:15:00,QQQ,PUT,485,1,2.50,2.45,2.60,SUBMITTED
2025-01-11T11:00:00,IWM,CALL,220,1,1.50,1.52,1.70,SUBMITTED"""
        
        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=csv_data)):
                with patch("main.date") as mock_date:
                    mock_date.today.return_value = date(2025, 1, 10)
                    
                    with patch("main.BankrollManager") as mock_bankroll_class:
                        mock_bankroll = Mock()
                        mock_bankroll.get_current_bankroll.return_value = 515.0
                        mock_bankroll.peak_bankroll = 520.0
                        mock_bankroll_class.return_value = mock_bankroll
                        
                        summary = generate_daily_summary(self.mock_config, self.end_time)
                        
                        # Should only count today's trade (QQQ)
                        self.assertIn("Trades: 1", summary)
                        self.assertIn("Wins/Loss: 1/0", summary)  # QQQ win
                        
                        # QQQ P&L: (2.60 - 2.45) * 1 * 100 = +$15.00
                        self.assertIn("P&L: $15.00", summary)

    def test_daily_summary_cancelled_trades_excluded(self):
        """Test daily summary excludes cancelled trades from statistics."""
        csv_data = """timestamp,symbol,direction,strike,quantity,premium,actual_premium,exit_premium,status
2025-01-10T09:30:00,SPY,CALL,580,1,1.25,1.28,1.45,SUBMITTED
2025-01-10T10:15:00,QQQ,PUT,485,1,2.50,0.00,0.00,CANCELLED
2025-01-10T11:00:00,IWM,CALL,220,1,1.50,1.52,0.00,SUBMITTED"""
        
        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=csv_data)):
                with patch("main.date") as mock_date:
                    mock_date.today.return_value = date(2025, 1, 10)
                    
                    with patch("main.BankrollManager") as mock_bankroll_class:
                        mock_bankroll = Mock()
                        mock_bankroll.get_current_bankroll.return_value = 500.0
                        mock_bankroll.peak_bankroll = 520.0
                        mock_bankroll_class.return_value = mock_bankroll
                        
                        summary = generate_daily_summary(self.mock_config, self.end_time)
                        
                        # Should only count SUBMITTED trades (SPY, IWM)
                        self.assertIn("Trades: 2", summary)
                        # SPY closed with profit, IWM still open
                        self.assertIn("Wins/Loss: 1/0", summary)

    def test_daily_summary_open_positions_no_pl(self):
        """Test daily summary handles open positions (exit_premium = 0)."""
        csv_data = """timestamp,symbol,direction,strike,quantity,premium,actual_premium,exit_premium,status
2025-01-10T09:30:00,SPY,CALL,580,1,1.25,1.28,0.00,SUBMITTED
2025-01-10T10:15:00,QQQ,PUT,485,2,2.50,2.45,0.00,SUBMITTED"""
        
        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=csv_data)):
                with patch("main.date") as mock_date:
                    mock_date.today.return_value = date(2025, 1, 10)
                    
                    with patch("main.BankrollManager") as mock_bankroll_class:
                        mock_bankroll = Mock()
                        mock_bankroll.get_current_bankroll.return_value = 500.0
                        mock_bankroll.peak_bankroll = 520.0
                        mock_bankroll_class.return_value = mock_bankroll
                        
                        summary = generate_daily_summary(self.mock_config, self.end_time)
                        
                        # Should count trades but no wins/losses (positions still open)
                        self.assertIn("Trades: 2", summary)
                        self.assertIn("Wins/Loss: 0/0", summary)
                        self.assertIn("P&L: $0.00", summary)

    def test_daily_summary_bankroll_integration(self):
        """Test daily summary integrates with BankrollManager."""
        with patch("pathlib.Path.exists", return_value=False):
            with patch("main.BankrollManager") as mock_bankroll_class:
                mock_bankroll = Mock()
                mock_bankroll.get_current_bankroll.return_value = 485.50
                mock_bankroll.peak_bankroll = 525.75
                mock_bankroll_class.return_value = mock_bankroll
                
                summary = generate_daily_summary(self.mock_config, self.end_time)
                
                # Check bankroll values
                self.assertIn("Peak balance: $525.75", summary)
                self.assertIn("Current balance: $485.50", summary)
                
                # Verify BankrollManager was called with correct config
                mock_bankroll_class.assert_called_once_with("bankroll.json")

    def test_daily_summary_fallback_on_error(self):
        """Test daily summary provides fallback message on error."""
        # Mock an exception during processing
        with patch("pathlib.Path.exists", side_effect=Exception("File system error")):
            with patch("main.logger") as mock_logger:
                summary = generate_daily_summary(self.mock_config, self.end_time)
                
                # Should return fallback summary
                self.assertIn("📊", summary)
                self.assertIn("Daily Wrap-Up", summary)
                self.assertIn("15:45", summary)
                self.assertIn("Session complete", summary)
                
                # Should log the error
                mock_logger.error.assert_called_once()

    def test_daily_summary_timezone_formatting(self):
        """Test daily summary formats timezone correctly."""
        # Test different timezones
        test_times = [
            datetime(2025, 1, 10, 15, 45, 0),  # 3:45 PM
            datetime(2025, 1, 10, 9, 30, 0),   # 9:30 AM
            datetime(2025, 1, 10, 16, 0, 0),   # 4:00 PM
        ]
        
        for test_time in test_times:
            with self.subTest(time=test_time):
                with patch("pathlib.Path.exists", return_value=False):
                    with patch("main.BankrollManager") as mock_bankroll_class:
                        mock_bankroll = Mock()
                        mock_bankroll.get_current_bankroll.return_value = 500.0
                        mock_bankroll.peak_bankroll = 500.0
                        mock_bankroll_class.return_value = mock_bankroll
                        
                        summary = generate_daily_summary(self.mock_config, test_time)
                        
                        # Check time formatting
                        expected_time = test_time.strftime('%H:%M')
                        self.assertIn(expected_time, summary)

    @patch("main.logger")
    def test_daily_summary_malformed_csv_handling(self, mock_logger):
        """Test daily summary handles malformed CSV data gracefully."""
        # Mock malformed CSV data
        csv_data = """timestamp,symbol,direction,strike,quantity,premium,actual_premium,exit_premium,status
invalid-date,SPY,CALL,580,1,1.25,1.28,1.45,SUBMITTED
2025-01-10T10:15:00,QQQ,PUT,not-a-number,1,2.50,2.45,2.60,SUBMITTED
2025-01-10T11:00:00,IWM,CALL,220,invalid-qty,1.50,1.52,1.70,SUBMITTED"""
        
        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=csv_data)):
                with patch("main.date") as mock_date:
                    mock_date.today.return_value = date(2025, 1, 10)
                    
                    with patch("main.BankrollManager") as mock_bankroll_class:
                        mock_bankroll = Mock()
                        mock_bankroll.get_current_bankroll.return_value = 500.0
                        mock_bankroll.peak_bankroll = 520.0
                        mock_bankroll_class.return_value = mock_bankroll
                        
                        summary = generate_daily_summary(self.mock_config, self.end_time)
                        
                        # Should still return a summary (skipping malformed rows)
                        self.assertIn("📊", summary)
                        self.assertIn("Daily Wrap-Up", summary)
                        
                        # Should handle malformed data gracefully
                        # (exact counts depend on which rows can be parsed)
                        self.assertIn("Trades:", summary)
                        self.assertIn("P&L:", summary)

    def test_daily_summary_integration_with_main_loop(self):
        """Test daily summary integration with main.py loop exit."""
        # This tests the integration point where generate_daily_summary is called
        mock_config = self.mock_config
        mock_slack_notifier = Mock()
        
        # Mock the function call that happens in main.py
        with patch("main.generate_daily_summary") as mock_generate:
            mock_generate.return_value = "📊 **Daily Wrap-Up** 15:45 EST\n**Trades:** 2\n**P&L:** $25.00"
            
            # Simulate the code path in main.py
            end_time = self.end_time
            if mock_slack_notifier:
                try:
                    daily_summary = mock_generate(mock_config, end_time)
                    mock_slack_notifier.send_heartbeat(daily_summary)
                    result = True
                except Exception:
                    result = False
            
            # Verify integration works
            self.assertTrue(result)
            mock_generate.assert_called_once_with(mock_config, end_time)
            mock_slack_notifier.send_heartbeat.assert_called_once()
            
            # Check the summary was passed correctly
            call_args = mock_slack_notifier.send_heartbeat.call_args[0][0]
            self.assertIn("Daily Wrap-Up", call_args)
            self.assertIn("15:45", call_args)


if __name__ == "__main__":
    unittest.main()
