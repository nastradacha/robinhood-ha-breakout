#!/usr/bin/env python3
"""
Unit test for bankroll seeding logic verification.

Tests that START_CAPITAL from config.yaml is only used when bankroll.json
doesn't exist, and subsequent loads ignore YAML changes.
"""

import pytest
import json
import tempfile
import os
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.bankroll import BankrollManager


class TestBankrollSeed:
    """Test bankroll seeding behavior with config.yaml START_CAPITAL."""
    
    def test_bankroll_seeding_logic(self):
        """
        Test that:
        1. First load() seeds ledger from YAML START_CAPITAL
        2. Second load() ignores YAML (even if YAML is changed)
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create temporary bankroll file path
            bankroll_file = Path(temp_dir) / "test_bankroll.json"
            
            # Ensure the file doesn't exist initially
            assert not bankroll_file.exists(), "Bankroll file should not exist initially"
            
            # STEP 1: First initialization should seed from YAML START_CAPITAL
            initial_capital = 500.0
            manager1 = BankrollManager(str(bankroll_file), start_capital=initial_capital)
            
            # Verify file was created
            assert bankroll_file.exists(), "Bankroll file should be created"
            
            # Verify content matches initial capital
            with open(bankroll_file, 'r') as f:
                data = json.load(f)
            
            assert data["current_bankroll"] == initial_capital, f"Expected {initial_capital}, got {data['current_bankroll']}"
            assert data["start_capital"] == initial_capital, f"Expected {initial_capital}, got {data['start_capital']}"
            assert data["peak_bankroll"] == initial_capital, f"Expected {initial_capital}, got {data['peak_bankroll']}"
            
            # STEP 2: Second initialization with different START_CAPITAL should ignore YAML
            different_capital = 1000.0  # Different from initial
            manager2 = BankrollManager(str(bankroll_file), start_capital=different_capital)
            
            # Load data again and verify it still uses original values (ignores new YAML)
            current_bankroll = manager2.get_current_bankroll()
            data2 = manager2.get_bankroll_stats()
            
            # Should still have original values, not the new START_CAPITAL
            assert current_bankroll == initial_capital, f"Should ignore new YAML value. Expected {initial_capital}, got {current_bankroll}"
            assert data2["start_capital"] == initial_capital, f"Should ignore new YAML value. Expected {initial_capital}, got {data2['start_capital']}"
            assert data2["peak_bankroll"] == initial_capital, f"Should ignore new YAML value. Expected {initial_capital}, got {data2['peak_bankroll']}"
            
            # STEP 3: Verify the manager's internal start_capital reflects YAML but doesn't affect persisted data
            assert manager2.start_capital == different_capital, "Manager should store YAML value internally"
            
            # But the persisted data should remain unchanged
            assert data2["current_bankroll"] == initial_capital, "Persisted data should ignore YAML changes"
    
    def test_multiple_load_calls_consistent(self):
        """Test that multiple load calls on same manager return consistent data."""
        with tempfile.TemporaryDirectory() as temp_dir:
            bankroll_file = Path(temp_dir) / "test_bankroll.json"
            
            # Initialize with specific capital
            test_capital = 750.0
            manager = BankrollManager(str(bankroll_file), start_capital=test_capital)
            
            # Multiple calls should return same data
            bankroll1 = manager.get_current_bankroll()
            bankroll2 = manager.get_current_bankroll()
            bankroll3 = manager.get_current_bankroll()
            
            assert bankroll1 == bankroll2 == bankroll3 == test_capital, "Multiple loads should be consistent"
    
    def test_file_deletion_recreates_with_yaml(self):
        """Test that deleting bankroll.json and recreating uses current YAML value."""
        with tempfile.TemporaryDirectory() as temp_dir:
            bankroll_file = Path(temp_dir) / "test_bankroll.json"
            
            # Create initial bankroll
            initial_capital = 400.0
            manager1 = BankrollManager(str(bankroll_file), start_capital=initial_capital)
            assert manager1.get_current_bankroll() == initial_capital
            
            # Delete the file
            bankroll_file.unlink()
            assert not bankroll_file.exists(), "File should be deleted"
            
            # Create new manager with different capital - should use new YAML value
            new_capital = 800.0
            manager2 = BankrollManager(str(bankroll_file), start_capital=new_capital)
            
            # Should now use the new YAML value since file was missing
            assert manager2.get_current_bankroll() == new_capital, f"Should use new YAML value after file deletion. Expected {new_capital}, got {manager2.get_current_bankroll()}"


if __name__ == '__main__':
    pytest.main([__file__])
