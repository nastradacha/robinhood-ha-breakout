#!/usr/bin/env python3
"""
Unit tests for scoped bankroll ledgers (v0.9.0)

Tests the broker/environment separation functionality to ensure:
- Different ledgers are created and isolated
- Changing ALPACA_ENV from paper→live does not alter the paper JSON
- Proper file naming and scoping
"""

import pytest
import tempfile
import shutil
import json
from pathlib import Path
from unittest.mock import patch

from utils.bankroll import BankrollManager
from utils.scoped_files import get_scoped_paths, ensure_scoped_files


class TestScopedBankrolls:
    """Test scoped bankroll functionality."""

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

    def test_scoped_bankroll_file_naming(self):
        """Test that bankroll files are named correctly for different broker/env combinations."""
        # Test Alpaca paper
        manager_alpaca_paper = BankrollManager(
            start_capital=1000.0, broker="alpaca", env="paper"
        )
        assert manager_alpaca_paper.bankroll_file.name == "bankroll_alpaca_paper.json"
        assert manager_alpaca_paper.ledger_id() == "alpaca:paper"

        # Test Alpaca live
        manager_alpaca_live = BankrollManager(
            start_capital=1000.0, broker="alpaca", env="live"
        )
        assert manager_alpaca_live.bankroll_file.name == "bankroll_alpaca_live.json"
        assert manager_alpaca_live.ledger_id() == "alpaca:live"

        # Test Robinhood live
        manager_rh_live = BankrollManager(
            start_capital=1000.0, broker="robinhood", env="live"
        )
        assert manager_rh_live.bankroll_file.name == "bankroll_robinhood_live.json"
        assert manager_rh_live.ledger_id() == "robinhood:live"

    def test_scoped_bankroll_isolation(self):
        """Test that different broker/env combinations create isolated ledgers."""
        # Create two different managers
        manager_paper = BankrollManager(
            start_capital=1000.0, broker="alpaca", env="paper"
        )
        manager_live = BankrollManager(
            start_capital=2000.0, broker="alpaca", env="live"
        )

        # Verify they have different files
        assert manager_paper.bankroll_file != manager_live.bankroll_file
        assert manager_paper.bankroll_file.exists()
        assert manager_live.bankroll_file.exists()

        # Verify different starting capitals
        assert manager_paper.get_current_bankroll() == 1000.0
        assert manager_live.get_current_bankroll() == 2000.0

        # Update one manager
        manager_paper.update_bankroll(1500.0, "Test update")

        # Verify the other is unchanged
        assert manager_paper.get_current_bankroll() == 1500.0
        assert manager_live.get_current_bankroll() == 2000.0

    def test_env_switch_isolation(self):
        """Test that switching from paper to live doesn't affect paper ledger."""
        # Create paper manager and make changes
        manager_paper = BankrollManager(
            start_capital=1000.0, broker="alpaca", env="paper"
        )
        manager_paper.update_bankroll(1200.0, "Paper profit")
        paper_balance = manager_paper.get_current_bankroll()

        # Create live manager (simulating environment switch)
        manager_live = BankrollManager(
            start_capital=500.0, broker="alpaca", env="live"
        )
        manager_live.update_bankroll(600.0, "Live profit")

        # Verify paper manager is unchanged
        manager_paper_check = BankrollManager(
            start_capital=1000.0, broker="alpaca", env="paper"
        )
        assert manager_paper_check.get_current_bankroll() == paper_balance

        # Verify live manager has its own state
        assert manager_live.get_current_bankroll() == 600.0

    def test_backward_compatibility(self):
        """Test that custom bankroll file names still work."""
        manager = BankrollManager(
            bankroll_file="custom_bankroll.json",
            start_capital=750.0,
            broker="alpaca",
            env="paper"
        )
        assert manager.bankroll_file.name == "custom_bankroll.json"
        assert manager.get_current_bankroll() == 750.0

    def test_scoped_paths_generation(self):
        """Test scoped file path generation."""
        paths_alpaca_paper = get_scoped_paths("alpaca", "paper")
        assert paths_alpaca_paper["bankroll"] == "bankroll_alpaca_paper.json"
        assert paths_alpaca_paper["trade_history"] == "logs/trade_history_alpaca_paper.csv"
        assert paths_alpaca_paper["positions"] == "positions_alpaca_paper.csv"

        paths_rh_live = get_scoped_paths("robinhood", "live")
        assert paths_rh_live["bankroll"] == "bankroll_robinhood_live.json"
        assert paths_rh_live["trade_history"] == "logs/trade_history_robinhood_live.csv"
        assert paths_rh_live["positions"] == "positions_robinhood_live.csv"

    def test_ensure_scoped_files_creation(self):
        """Test that scoped files are created with proper headers."""
        paths = get_scoped_paths("alpaca", "paper")
        ensure_scoped_files(paths)

        # Check that files were created
        assert Path(paths["trade_history"]).exists()
        assert Path(paths["positions"]).exists()

        # Check trade history headers
        with open(paths["trade_history"], 'r') as f:
            header = f.readline().strip()
            expected_headers = [
                'timestamp', 'symbol', 'decision', 'confidence', 'current_price',
                'strike', 'premium', 'quantity', 'total_cost', 'reason', 'status',
                'fill_price', 'pnl_pct', 'pnl_amount', 'exit_reason'
            ]
            assert header == ','.join(expected_headers)

        # Check positions headers
        with open(paths["positions"], 'r') as f:
            header = f.readline().strip()
            expected_headers = [
                'symbol', 'strike', 'option_type', 'expiry', 'quantity', 'contracts',
                'entry_price', 'current_price', 'pnl_pct', 'pnl_amount', 'timestamp'
            ]
            assert header == ','.join(expected_headers)

    def test_multiple_brokers_coexist(self):
        """Test that multiple broker/env combinations can coexist."""
        # Create managers for different combinations
        managers = {
            "alpaca_paper": BankrollManager(start_capital=1000.0, broker="alpaca", env="paper"),
            "alpaca_live": BankrollManager(start_capital=2000.0, broker="alpaca", env="live"),
            "robinhood_live": BankrollManager(start_capital=500.0, broker="robinhood", env="live"),
        }

        # Verify all have different files and balances
        files = set()
        for name, manager in managers.items():
            files.add(str(manager.bankroll_file))
            assert manager.bankroll_file.exists()

        # All files should be unique
        assert len(files) == len(managers)

        # Update each manager differently
        managers["alpaca_paper"].update_bankroll(1100.0, "Paper trade")
        managers["alpaca_live"].update_bankroll(1800.0, "Live trade")
        managers["robinhood_live"].update_bankroll(550.0, "RH trade")

        # Verify isolation
        assert managers["alpaca_paper"].get_current_bankroll() == 1100.0
        assert managers["alpaca_live"].get_current_bankroll() == 1800.0
        assert managers["robinhood_live"].get_current_bankroll() == 550.0


if __name__ == "__main__":
    pytest.main([__file__])
