"""
Unit tests for bankroll management utilities.
"""

import pytest
import json
import tempfile
import os
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.bankroll import BankrollManager


class TestBankrollManager:
    """Test bankroll manager initialization and basic operations."""

    def test_bankroll_manager_init_new_file(self):
        """Test bankroll manager initialization with new file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            bankroll_file = Path(temp_dir) / "test_bankroll.json"

            manager = BankrollManager(str(bankroll_file), start_capital=50.0)

            # Check that file was created
            assert bankroll_file.exists()

            # Check initial data
            data = manager._load_bankroll()
            assert data["current_bankroll"] == 50.0
            assert data["start_capital"] == 50.0
            assert data["total_trades"] == 0
            assert data["winning_trades"] == 0
            assert data["total_pnl"] == 0.0

    def test_bankroll_manager_init_existing_file(self):
        """Test bankroll manager initialization with existing file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            bankroll_file = Path(temp_dir) / "existing_bankroll.json"

            # Create existing file
            existing_data = {
                "current_bankroll": 75.0,
                "start_capital": 50.0,
                "total_trades": 5,
                "winning_trades": 3,
                "total_pnl": 25.0,
                "max_drawdown": 5.0,
                "peak_bankroll": 80.0,
                "created_at": "2023-01-01T00:00:00",
                "last_updated": "2023-01-02T00:00:00",
                "trade_history": [],
            }

            with open(bankroll_file, "w") as f:
                json.dump(existing_data, f)

            manager = BankrollManager(str(bankroll_file), start_capital=100.0)

            # Should load existing data, not create new
            data = manager._load_bankroll()
            assert data["current_bankroll"] == 75.0
            assert data["start_capital"] == 50.0  # From existing file
            assert data["total_trades"] == 5

    def test_get_current_bankroll(self):
        """Test getting current bankroll amount."""
        with tempfile.TemporaryDirectory() as temp_dir:
            bankroll_file = Path(temp_dir) / "test_bankroll.json"
            manager = BankrollManager(str(bankroll_file), start_capital=40.0)

            bankroll = manager.get_current_bankroll()
            assert bankroll == 40.0

    def test_get_bankroll_stats(self):
        """Test getting comprehensive bankroll statistics."""
        with tempfile.TemporaryDirectory() as temp_dir:
            bankroll_file = Path(temp_dir) / "test_bankroll.json"
            manager = BankrollManager(str(bankroll_file), start_capital=40.0)

            stats = manager.get_bankroll_stats()

            required_keys = [
                "current_bankroll",
                "start_capital",
                "total_trades",
                "winning_trades",
                "total_pnl",
                "max_drawdown",
                "peak_bankroll",
                "created_at",
                "last_updated",
                "trade_history",
            ]

            for key in required_keys:
                assert key in stats


class TestPositionSizing:
    """Test position sizing calculations."""

    def test_calculate_position_size_fixed_qty(self):
        """Test position sizing with fixed quantity rule."""
        with tempfile.TemporaryDirectory() as temp_dir:
            bankroll_file = Path(temp_dir) / "test_bankroll.json"
            manager = BankrollManager(str(bankroll_file), start_capital=100.0)

            # Test within risk limits (premium=0.25, qty=2, total_risk=$50 < $50 limit)
            qty = manager.calculate_position_size(
                premium=0.25, risk_fraction=0.5, size_rule="fixed-qty", fixed_qty=2
            )
            assert qty == 2

            # Test exceeding risk limits
            qty = manager.calculate_position_size(
                premium=30.0,  # 30 * 2 = 60, which is > 50% of 100
                risk_fraction=0.5,
                size_rule="fixed-qty",
                fixed_qty=2,
            )
            assert qty == 0  # Should block the trade

    def test_calculate_position_size_dynamic_qty(self):
        """Test position sizing with dynamic quantity rule."""
        with tempfile.TemporaryDirectory() as temp_dir:
            bankroll_file = Path(temp_dir) / "test_bankroll.json"
            manager = BankrollManager(str(bankroll_file), start_capital=100.0)

            # Test normal case (premium=0.10, max_risk=$50, 50/(0.10*100)=5 contracts)
            qty = manager.calculate_position_size(
                premium=0.10, risk_fraction=0.5, size_rule="dynamic-qty"
            )
            # Max risk = 100 * 0.5 = 50, so 50 / (0.10 * 100) = 5 contracts
            assert qty == 5

            # Test with expensive premium (0.40*100=$40 per contract)
            qty = manager.calculate_position_size(
                premium=0.40, risk_fraction=0.5, size_rule="dynamic-qty"
            )
            # Max risk = 50, so 50 / (0.40 * 100) = 1.25, floor to 1
            assert qty == 1

            # Test with very expensive premium (0.60*100=$60 per contract > $50 max risk)
            qty = manager.calculate_position_size(
                premium=0.60, risk_fraction=0.5, size_rule="dynamic-qty"
            )
            # Max risk = 50, so 50 / (0.60 * 100) = 0.83, but minimum is 1
            assert qty == 1

    def test_calculate_position_size_invalid_rule(self):
        """Test position sizing with invalid rule."""
        with tempfile.TemporaryDirectory() as temp_dir:
            bankroll_file = Path(temp_dir) / "test_bankroll.json"
            manager = BankrollManager(str(bankroll_file), start_capital=100.0)

            with pytest.raises(ValueError, match="Unknown size rule"):
                manager.calculate_position_size(premium=10.0, size_rule="invalid-rule")

    def test_validate_trade_risk_within_limits(self):
        """Test trade risk validation within limits."""
        with tempfile.TemporaryDirectory() as temp_dir:
            bankroll_file = Path(temp_dir) / "test_bankroll.json"
            manager = BankrollManager(str(bankroll_file), start_capital=100.0)

            # Risk = 0.20 * 2 * 100 = 40, which is 40% of 100 (within 50% limit)
            is_valid = manager.validate_trade_risk(
                premium=0.20, quantity=2, max_risk_pct=50.0
            )
            assert is_valid is True

    def test_validate_trade_risk_exceeds_limits(self):
        """Test trade risk validation exceeding limits."""
        with tempfile.TemporaryDirectory() as temp_dir:
            bankroll_file = Path(temp_dir) / "test_bankroll.json"
            manager = BankrollManager(str(bankroll_file), start_capital=100.0)

            # Risk = 30 * 2 = 60, which is 60% of 100 (exceeds 50% limit)
            is_valid = manager.validate_trade_risk(
                premium=30.0, quantity=2, max_risk_pct=50.0
            )
            assert is_valid is False


class TestTradeRecording:
    """Test trade recording and history management."""

    def test_record_trade_basic(self):
        """Test basic trade recording."""
        with tempfile.TemporaryDirectory() as temp_dir:
            bankroll_file = Path(temp_dir) / "test_bankroll.json"
            manager = BankrollManager(str(bankroll_file), start_capital=100.0)

            trade_details = {
                "symbol": "SPY",
                "direction": "CALL",
                "strike": 450.0,
                "expiry": "2023-12-15",
                "quantity": 1,
                "premium": 5.0,
                "total_cost": 5.0,
                "confidence": 0.75,
                "reason": "Strong bullish signal",
            }

            result = manager.record_trade(trade_details)

            # Check that trade was added to history
            assert result["total_trades"] == 1
            assert len(result["trade_history"]) == 1

            trade_record = result["trade_history"][0]
            assert trade_record["symbol"] == "SPY"
            assert trade_record["direction"] == "CALL"
            assert trade_record["strike"] == 450.0
            assert trade_record["quantity"] == 1
            assert trade_record["premium"] == 5.0

    def test_record_trade_with_realized_pnl(self):
        """Test trade recording with realized P/L."""
        with tempfile.TemporaryDirectory() as temp_dir:
            bankroll_file = Path(temp_dir) / "test_bankroll.json"
            manager = BankrollManager(str(bankroll_file), start_capital=100.0)

            trade_details = {
                "symbol": "SPY",
                "direction": "CALL",
                "quantity": 1,
                "premium": 5.0,
                "realized_pnl": 10.0,  # Profitable trade
            }

            result = manager.record_trade(trade_details)

            # Check bankroll update
            assert result["current_bankroll"] == 110.0  # 100 + 10
            assert result["total_pnl"] == 10.0
            assert result["winning_trades"] == 1
            assert result["peak_bankroll"] == 110.0

    def test_record_trade_with_loss(self):
        """Test trade recording with loss."""
        with tempfile.TemporaryDirectory() as temp_dir:
            bankroll_file = Path(temp_dir) / "test_bankroll.json"
            manager = BankrollManager(str(bankroll_file), start_capital=100.0)

            trade_details = {
                "symbol": "SPY",
                "direction": "PUT",
                "quantity": 1,
                "premium": 5.0,
                "realized_pnl": -3.0,  # Losing trade
            }

            result = manager.record_trade(trade_details)

            # Check bankroll update
            assert result["current_bankroll"] == 97.0  # 100 - 3
            assert result["total_pnl"] == -3.0
            assert result["winning_trades"] == 0
            assert result["peak_bankroll"] == 100.0  # No new peak
            assert result["max_drawdown"] == 3.0  # 3% drawdown

    def test_update_bankroll_manual(self):
        """Test manual bankroll update."""
        with tempfile.TemporaryDirectory() as temp_dir:
            bankroll_file = Path(temp_dir) / "test_bankroll.json"
            manager = BankrollManager(str(bankroll_file), start_capital=100.0)

            result = manager.update_bankroll(
                120.0, "Manual adjustment after realized gains"
            )

            assert result["current_bankroll"] == 120.0
            assert result["total_pnl"] == 20.0
            assert result["peak_bankroll"] == 120.0

            # Check update record
            assert "bankroll_updates" in result
            assert len(result["bankroll_updates"]) == 1

            update_record = result["bankroll_updates"][0]
            assert update_record["old_amount"] == 100.0
            assert update_record["new_amount"] == 120.0
            assert update_record["change"] == 20.0
            assert update_record["reason"] == "Manual adjustment after realized gains"

    def test_get_win_history(self):
        """Test getting win/loss history."""
        with tempfile.TemporaryDirectory() as temp_dir:
            bankroll_file = Path(temp_dir) / "test_bankroll.json"
            manager = BankrollManager(str(bankroll_file), start_capital=100.0)

            # Record some trades with P/L
            trades = [
                {"realized_pnl": 5.0, "status": "CLOSED"},  # Win
                {"realized_pnl": -2.0, "status": "CLOSED"},  # Loss
                {"realized_pnl": 8.0, "status": "CLOSED"},  # Win
                {"realized_pnl": -1.0, "status": "CLOSED"},  # Loss
                {"realized_pnl": 3.0, "status": "CLOSED"},  # Win
            ]

            for trade in trades:
                manager.record_trade(trade)

            win_history = manager.get_win_history(last_n=20)
            expected = [True, False, True, False, True]  # Wins and losses
            assert win_history == expected

            # Test with smaller window
            win_history_3 = manager.get_win_history(last_n=3)
            expected_3 = [True, False, True]  # Last 3 trades
            assert win_history_3 == expected_3

    def test_get_win_history_no_completed_trades(self):
        """Test getting win history with no completed trades."""
        with tempfile.TemporaryDirectory() as temp_dir:
            bankroll_file = Path(temp_dir) / "test_bankroll.json"
            manager = BankrollManager(str(bankroll_file), start_capital=100.0)

            win_history = manager.get_win_history()
            assert win_history == []

    def test_get_performance_summary(self):
        """Test getting performance summary."""
        with tempfile.TemporaryDirectory() as temp_dir:
            bankroll_file = Path(temp_dir) / "test_bankroll.json"
            manager = BankrollManager(str(bankroll_file), start_capital=100.0)

            # Record some trades
            manager.record_trade({"realized_pnl": 10.0})  # Win
            manager.record_trade({"realized_pnl": -5.0})  # Loss
            manager.record_trade({"realized_pnl": 15.0})  # Win

            summary = manager.get_performance_summary()

            assert summary["current_bankroll"] == 120.0  # 100 + 10 - 5 + 15
            assert summary["start_capital"] == 100.0
            assert summary["total_pnl"] == 20.0
            assert summary["total_return_pct"] == 20.0  # 20/100 * 100
            assert summary["total_trades"] == 3
            assert summary["winning_trades"] == 2
            assert summary["win_rate_pct"] == 66.67  # 2/3 * 100, rounded
            assert summary["peak_bankroll"] == 120.0

    def test_reset_bankroll(self):
        """Test bankroll reset functionality."""
        with tempfile.TemporaryDirectory() as temp_dir:
            bankroll_file = Path(temp_dir) / "test_bankroll.json"
            manager = BankrollManager(str(bankroll_file), start_capital=100.0)

            # Make some trades first
            manager.record_trade({"realized_pnl": 10.0})
            manager.record_trade({"realized_pnl": -5.0})

            # Reset with new capital
            result = manager.reset_bankroll(150.0)

            assert result["current_bankroll"] == 150.0
            assert result["start_capital"] == 150.0
            assert result["total_trades"] == 0
            assert result["winning_trades"] == 0
            assert result["total_pnl"] == 0.0
            assert result["trade_history"] == []
            assert result["peak_bankroll"] == 150.0

    def test_reset_bankroll_default_capital(self):
        """Test bankroll reset with default capital."""
        with tempfile.TemporaryDirectory() as temp_dir:
            bankroll_file = Path(temp_dir) / "test_bankroll.json"
            manager = BankrollManager(str(bankroll_file), start_capital=100.0)

            # Make some trades first
            manager.record_trade({"realized_pnl": 10.0})

            # Reset without specifying new capital
            result = manager.reset_bankroll()

            assert result["current_bankroll"] == 100.0  # Back to original start_capital
            assert result["start_capital"] == 100.0


class TestErrorHandling:
    """Test error handling in bankroll operations."""

    def test_load_bankroll_file_not_found(self):
        """Test loading non-existent bankroll file after initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            bankroll_file = Path(temp_dir) / "test_bankroll.json"
            manager = BankrollManager(str(bankroll_file), start_capital=100.0)

            # Delete the file after initialization
            os.remove(bankroll_file)

            with pytest.raises(FileNotFoundError):
                manager._load_bankroll()

    def test_save_bankroll_permission_error(self):
        """Test saving bankroll with permission error."""
        with tempfile.TemporaryDirectory() as temp_dir:
            bankroll_file = Path(temp_dir) / "readonly_bankroll.json"
            manager = BankrollManager(str(bankroll_file), start_capital=100.0)

            # Make file read-only (on Windows this might not work as expected)
            try:
                os.chmod(bankroll_file, 0o444)

                with pytest.raises(PermissionError):
                    manager.record_trade({"symbol": "SPY", "realized_pnl": 5.0})
            except (OSError, PermissionError):
                # Skip test if we can't make file read-only
                pytest.skip("Cannot make file read-only on this system")
            finally:
                # Restore permissions for cleanup
                try:
                    os.chmod(bankroll_file, 0o666)
                except:
                    pass


if __name__ == "__main__":
    pytest.main([__file__])
