#!/usr/bin/env python3
"""
Unit tests for scoped history file paths (v0.9.0)

Tests that file names are broker/env specific and no cross-contamination occurs
between different broker/environment combinations.
"""

import pytest
import tempfile
import shutil
import csv
from pathlib import Path
from unittest.mock import patch

from utils.scoped_files import get_scoped_paths, ensure_scoped_files


class TestScopedHistoryPaths:
    """Test scoped history file path functionality."""

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

    def test_scoped_path_generation(self):
        """Test that scoped paths are generated correctly."""
        # Test different broker/env combinations
        test_cases = [
            ("alpaca", "paper", {
                "bankroll": "bankroll_alpaca_paper.json",
                "trade_history": "logs/trade_history_alpaca_paper.csv",
                "positions": "positions_alpaca_paper.csv"
            }),
            ("alpaca", "live", {
                "bankroll": "bankroll_alpaca_live.json",
                "trade_history": "logs/trade_history_alpaca_live.csv",
                "positions": "positions_alpaca_live.csv"
            }),
            ("robinhood", "live", {
                "bankroll": "bankroll_robinhood_live.json",
                "trade_history": "logs/trade_history_robinhood_live.csv",
                "positions": "positions_robinhood_live.csv"
            })
        ]

        for broker, env, expected_paths in test_cases:
            paths = get_scoped_paths(broker, env)
            assert paths == expected_paths

    def test_file_isolation(self):
        """Test that different broker/env combinations create isolated files."""
        # Create files for different combinations
        combinations = [
            ("alpaca", "paper"),
            ("alpaca", "live"),
            ("robinhood", "live")
        ]

        created_files = []
        for broker, env in combinations:
            paths = get_scoped_paths(broker, env)
            ensure_scoped_files(paths)
            
            # Verify files were created
            for file_type, file_path in paths.items():
                if file_type != "bankroll":  # bankroll is handled by BankrollManager
                    assert Path(file_path).exists()
                    created_files.append(file_path)

        # Verify all files are unique
        assert len(created_files) == len(set(created_files))

    def test_trade_history_isolation(self):
        """Test that trade history files are completely isolated."""
        # Create different trade history files
        alpaca_paper_paths = get_scoped_paths("alpaca", "paper")
        alpaca_live_paths = get_scoped_paths("alpaca", "live")
        
        ensure_scoped_files(alpaca_paper_paths)
        ensure_scoped_files(alpaca_live_paths)

        # Write test data to paper file
        paper_trade = [
            "2025-08-10T10:00:00", "SPY", "CALL", "0.75", "450.00",
            "451.0", "2.50", "1", "250.0", "Paper test trade", "SUBMITTED",
            "2.60", "4.0", "10.0", ""
        ]
        
        with open(alpaca_paper_paths["trade_history"], 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(paper_trade)

        # Write different test data to live file
        live_trade = [
            "2025-08-10T10:30:00", "QQQ", "PUT", "0.80", "380.00",
            "379.0", "3.00", "1", "300.0", "Live test trade", "SUBMITTED",
            "3.10", "3.3", "10.0", ""
        ]
        
        with open(alpaca_live_paths["trade_history"], 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(live_trade)

        # Verify isolation - paper file should only have paper trade
        with open(alpaca_paper_paths["trade_history"], 'r') as f:
            lines = f.readlines()
            assert len(lines) == 2  # header + 1 trade
            assert "Paper test trade" in lines[1]
            assert "Live test trade" not in lines[1]

        # Verify isolation - live file should only have live trade
        with open(alpaca_live_paths["trade_history"], 'r') as f:
            lines = f.readlines()
            assert len(lines) == 2  # header + 1 trade
            assert "Live test trade" in lines[1]
            assert "Paper test trade" not in lines[1]

    def test_positions_isolation(self):
        """Test that positions files are completely isolated."""
        # Create different positions files
        alpaca_paper_paths = get_scoped_paths("alpaca", "paper")
        robinhood_live_paths = get_scoped_paths("robinhood", "live")
        
        ensure_scoped_files(alpaca_paper_paths)
        ensure_scoped_files(robinhood_live_paths)

        # Write test position to Alpaca paper
        paper_position = [
            "SPY", "451.0", "CALL", "2025-08-15", "1", "1",
            "2.50", "2.60", "4.0", "10.0", "2025-08-10T10:00:00"
        ]
        
        with open(alpaca_paper_paths["positions"], 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(paper_position)

        # Write different test position to Robinhood live
        live_position = [
            "QQQ", "379.0", "PUT", "2025-08-15", "1", "1",
            "3.00", "3.10", "3.3", "10.0", "2025-08-10T10:30:00"
        ]
        
        with open(robinhood_live_paths["positions"], 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(live_position)

        # Verify isolation
        with open(alpaca_paper_paths["positions"], 'r') as f:
            lines = f.readlines()
            assert len(lines) == 2  # header + 1 position
            assert "SPY" in lines[1] and "CALL" in lines[1]
            assert "QQQ" not in lines[1]

        with open(robinhood_live_paths["positions"], 'r') as f:
            lines = f.readlines()
            assert len(lines) == 2  # header + 1 position
            assert "QQQ" in lines[1] and "PUT" in lines[1]
            assert "SPY" not in lines[1]

    def test_logs_directory_creation(self):
        """Test that logs directory is created automatically."""
        # Remove logs directory if it exists
        logs_dir = Path("logs")
        if logs_dir.exists():
            shutil.rmtree(logs_dir)

        # Create scoped files
        paths = get_scoped_paths("alpaca", "paper")
        ensure_scoped_files(paths)

        # Verify logs directory was created
        assert logs_dir.exists()
        assert logs_dir.is_dir()
        assert Path(paths["trade_history"]).exists()

    def test_file_headers_consistency(self):
        """Test that all scoped files have consistent headers."""
        combinations = [
            ("alpaca", "paper"),
            ("alpaca", "live"),
            ("robinhood", "live")
        ]

        expected_trade_headers = [
            'timestamp', 'symbol', 'decision', 'confidence', 'current_price',
            'strike', 'premium', 'quantity', 'total_cost', 'reason', 'status',
            'fill_price', 'pnl_pct', 'pnl_amount', 'exit_reason'
        ]

        expected_position_headers = [
            'symbol', 'strike', 'option_type', 'expiry', 'quantity', 'contracts',
            'entry_price', 'current_price', 'pnl_pct', 'pnl_amount', 'timestamp'
        ]

        for broker, env in combinations:
            paths = get_scoped_paths(broker, env)
            ensure_scoped_files(paths)

            # Check trade history headers
            with open(paths["trade_history"], 'r') as f:
                header = f.readline().strip()
                assert header == ','.join(expected_trade_headers)

            # Check positions headers
            with open(paths["positions"], 'r') as f:
                header = f.readline().strip()
                assert header == ','.join(expected_position_headers)

    def test_no_cross_contamination(self):
        """Test that operations on one broker/env don't affect others."""
        # Create multiple scoped file sets
        alpaca_paper = get_scoped_paths("alpaca", "paper")
        alpaca_live = get_scoped_paths("alpaca", "live")
        robinhood_live = get_scoped_paths("robinhood", "live")

        all_paths = [alpaca_paper, alpaca_live, robinhood_live]
        
        for paths in all_paths:
            ensure_scoped_files(paths)

        # Simulate trades in each environment
        test_data = [
            (alpaca_paper, "PAPER_SPY_CALL"),
            (alpaca_live, "LIVE_QQQ_PUT"), 
            (robinhood_live, "RH_IWM_CALL")
        ]

        for paths, trade_id in test_data:
            # Add trade to history
            with open(paths["trade_history"], 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "2025-08-10T10:00:00", "TEST", "CALL", "0.75", "450.00",
                    "451.0", "2.50", "1", "250.0", trade_id, "SUBMITTED",
                    "2.60", "4.0", "10.0", ""
                ])

            # Add position
            with open(paths["positions"], 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "TEST", "451.0", "CALL", "2025-08-15", "1", "1",
                    "2.50", "2.60", "4.0", "10.0", trade_id
                ])

        # Verify each file only contains its own data
        for paths, expected_trade_id in test_data:
            with open(paths["trade_history"], 'r') as f:
                content = f.read()
                assert expected_trade_id in content
                # Verify other trade IDs are not present
                for other_paths, other_trade_id in test_data:
                    if other_trade_id != expected_trade_id:
                        assert other_trade_id not in content

            with open(paths["positions"], 'r') as f:
                content = f.read()
                assert expected_trade_id in content
                # Verify other trade IDs are not present
                for other_paths, other_trade_id in test_data:
                    if other_trade_id != expected_trade_id:
                        assert other_trade_id not in content


if __name__ == "__main__":
    pytest.main([__file__])
