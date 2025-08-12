#!/usr/bin/env python3
"""
Unit tests for scoped file writes (v0.9.0)

Tests that simulate two trades: one on alpaca:paper, one on alpaca:live.
Asserts each appends to its own trade_history CSV with no cross-contamination.
"""

import pytest
import tempfile
import shutil
import csv
from pathlib import Path
from unittest.mock import patch
from datetime import datetime

from utils.scoped_files import get_scoped_paths, ensure_scoped_files
from utils.bankroll import BankrollManager


class TestScopedFilesWrites:
    """Test scoped file write operations."""

    def setup_method(self):
        """Set up test environment with temporary directory."""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = Path.cwd()
        Path(self.test_dir).mkdir(exist_ok=True)
        # Change to test directory
        import os
        os.chdir(self.test_dir)

    def teardown_method(self):
        """Clean up test environment."""
        import os
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def simulate_trade_logging(self, broker: str, env: str, trade_data: dict):
        """Simulate logging a trade to the appropriate scoped files."""
        paths = get_scoped_paths(broker, env)
        ensure_scoped_files(paths)
        
        # Append to trade history
        with open(paths["trade_history"], 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                trade_data['timestamp'],
                trade_data['symbol'],
                trade_data['decision'],
                trade_data['confidence'],
                trade_data['current_price'],
                trade_data['strike'],
                trade_data['premium'],
                trade_data['quantity'],
                trade_data['total_cost'],
                trade_data['reason'],
                trade_data['status'],
                trade_data.get('fill_price', ''),
                trade_data.get('pnl_pct', ''),
                trade_data.get('pnl_amount', ''),
                trade_data.get('exit_reason', '')
            ])
        
        # Append to positions (if trade was submitted)
        if trade_data['status'] == 'SUBMITTED':
            with open(paths["positions"], 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    trade_data['symbol'],
                    trade_data['strike'],
                    'CALL' if trade_data['decision'] == 'CALL' else 'PUT',
                    trade_data.get('expiry', '2025-08-15'),
                    trade_data['quantity'],
                    trade_data['quantity'],  # contracts = quantity for options
                    trade_data['premium'],
                    trade_data.get('fill_price', trade_data['premium']),
                    trade_data.get('pnl_pct', '0.0'),
                    trade_data.get('pnl_amount', '0.0'),
                    trade_data['timestamp']
                ])
        
        return paths

    def test_alpaca_paper_vs_live_isolation(self):
        """Test that Alpaca paper and live trades are completely isolated."""
        # Simulate paper trade
        paper_trade = {
            'timestamp': '2025-08-10T10:00:00',
            'symbol': 'SPY',
            'decision': 'CALL',
            'confidence': '0.75',
            'current_price': '450.00',
            'strike': '451.0',
            'premium': '2.50',
            'quantity': '1',
            'total_cost': '250.0',
            'reason': 'Paper trading test - strong breakout signal',
            'status': 'SUBMITTED',
            'fill_price': '2.55',
            'expiry': '2025-08-15'
        }
        
        # Simulate live trade
        live_trade = {
            'timestamp': '2025-08-10T10:30:00',
            'symbol': 'QQQ',
            'decision': 'PUT',
            'confidence': '0.80',
            'current_price': '380.00',
            'strike': '379.0',
            'premium': '3.00',
            'quantity': '1',
            'total_cost': '300.0',
            'reason': 'Live trading test - bearish reversal pattern',
            'status': 'SUBMITTED',
            'fill_price': '3.10',
            'expiry': '2025-08-15'
        }
        
        # Log trades to their respective environments
        paper_paths = self.simulate_trade_logging("alpaca", "paper", paper_trade)
        live_paths = self.simulate_trade_logging("alpaca", "live", live_trade)
        
        # Verify files are different
        assert paper_paths["trade_history"] != live_paths["trade_history"]
        assert paper_paths["positions"] != live_paths["positions"]
        
        # Verify paper trade history isolation
        with open(paper_paths["trade_history"], 'r') as f:
            paper_content = f.read()
            assert "Paper trading test" in paper_content
            assert "SPY" in paper_content
            assert "CALL" in paper_content
            assert "Live trading test" not in paper_content
            assert "QQQ" not in paper_content
        
        # Verify live trade history isolation
        with open(live_paths["trade_history"], 'r') as f:
            live_content = f.read()
            assert "Live trading test" in live_content
            assert "QQQ" in live_content
            assert "PUT" in live_content
            assert "Paper trading test" not in live_content
            assert "SPY" not in live_content

    def test_robinhood_vs_alpaca_isolation(self):
        """Test isolation between different brokers."""
        # Simulate trades on different brokers
        alpaca_trade = {
            'timestamp': '2025-08-10T10:00:00',
            'symbol': 'SPY',
            'decision': 'CALL',
            'confidence': '0.75',
            'current_price': '450.00',
            'strike': '451.0',
            'premium': '2.50',
            'quantity': '1',
            'total_cost': '250.0',
            'reason': 'Alpaca paper trade',
            'status': 'SUBMITTED'
        }
        
        robinhood_trade = {
            'timestamp': '2025-08-10T10:30:00',
            'symbol': 'QQQ',
            'decision': 'PUT',
            'confidence': '0.80',
            'current_price': '380.00',
            'strike': '379.0',
            'premium': '3.00',
            'quantity': '1',
            'total_cost': '300.0',
            'reason': 'Robinhood live trade',
            'status': 'SUBMITTED'
        }
        
        # Log to different brokers
        alpaca_paths = self.simulate_trade_logging("alpaca", "paper", alpaca_trade)
        rh_paths = self.simulate_trade_logging("robinhood", "live", robinhood_trade)
        
        # Verify complete isolation
        with open(alpaca_paths["trade_history"], 'r') as f:
            alpaca_content = f.read()
            assert "Alpaca paper trade" in alpaca_content
            assert "Robinhood live trade" not in alpaca_content
        
        with open(rh_paths["trade_history"], 'r') as f:
            rh_content = f.read()
            assert "Robinhood live trade" in rh_content
            assert "Alpaca paper trade" not in rh_content


if __name__ == "__main__":
    pytest.main([__file__])
