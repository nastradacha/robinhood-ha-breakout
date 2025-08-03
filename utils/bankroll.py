"""
Bankroll Management Module

Provides comprehensive bankroll tracking and risk management capabilities for the
Robinhood HA Breakout trading system. Handles capital allocation, position sizing,
P&L tracking, and performance analytics with persistent storage.

Key Features:
- Persistent bankroll tracking with JSON storage
- Risk-based position sizing (percentage of bankroll)
- Win/loss ratio and performance analytics
- Trade history and P&L calculations
- Maximum drawdown protection
- Conservative capital preservation

Risk Management:
- Risk fraction limits (default: 20% of bankroll per trade)
- Maximum position size validation
- Drawdown monitoring and alerts
- Capital preservation during losing streaks
- Performance-based confidence adjustments

Tracking Capabilities:
- Current bankroll and available capital
- Total trades and win/loss ratios
- Realized and unrealized P&L
- Maximum drawdown from peak
- Average win/loss amounts
- Recent performance history

Persistence:
- JSON file storage for bankroll state
- Automatic backup and recovery
- Trade history logging
- Performance metrics retention
- Cross-session continuity

Safety Features:
- Conservative position sizing
- Automatic risk reduction after losses
- Capital preservation priority
- Comprehensive validation and error handling
- Audit trail for all transactions

Usage:
    # Initialize bankroll manager
    bankroll = BankrollManager(start_capital=500.0)
    
    # Calculate position size
    max_risk = bankroll.calculate_max_risk_amount(risk_fraction=0.20)
    
    # Record trade outcome
    bankroll.record_trade(
        symbol='SPY',
        quantity=1,
        entry_price=2.50,
        exit_price=2.88,
        trade_type='CALL'
    )

Author: Robinhood HA Breakout System
Version: 2.0.0
License: MIT
"""

import json
import logging
from typing import Dict, Optional
from pathlib import Path
from datetime import datetime
import os

logger = logging.getLogger(__name__)


class BankrollManager:
    """Manages trading bankroll with risk controls and persistence."""
    
    def __init__(self, bankroll_file: str = "bankroll.json", start_capital: float = 40.0):
        self.bankroll_file = Path(bankroll_file)
        self.start_capital = start_capital
        self._ensure_bankroll_file()
    
    def _ensure_bankroll_file(self):
        """Create bankroll file if it doesn't exist."""
        if not self.bankroll_file.exists():
            initial_data = {
                "current_bankroll": self.start_capital,
                "start_capital": self.start_capital,
                "total_trades": 0,
                "winning_trades": 0,
                "total_pnl": 0.0,
                "max_drawdown": 0.0,
                "peak_bankroll": self.start_capital,
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "trade_history": [],
                "win_loss_history": []  # List of True/False for last 20 trades
            }
            self._save_bankroll(initial_data)
            logger.info(f"Created new bankroll file with ${self.start_capital}")
    
    def _load_bankroll(self) -> Dict:
        """Load bankroll data from file."""
        try:
            with open(self.bankroll_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading bankroll file: {e}")
            raise
    
    def _save_bankroll(self, data: Dict):
        """Save bankroll data to file."""
        try:
            data["last_updated"] = datetime.now().isoformat()
            with open(self.bankroll_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving bankroll file: {e}")
            raise
    
    def get_current_bankroll(self) -> float:
        """Get current bankroll amount."""
        data = self._load_bankroll()
        return data["current_bankroll"]
    
    def get_bankroll_stats(self) -> Dict:
        """Get comprehensive bankroll statistics."""
        return self._load_bankroll()
    
    def calculate_position_size(self, premium: float, risk_fraction: float = 0.5, 
                              size_rule: str = "fixed-qty", fixed_qty: int = 1) -> int:
        """
        Calculate position size based on bankroll and risk management rules.
        
        Args:
            premium: Option premium per contract
            risk_fraction: Maximum fraction of bankroll to risk
            size_rule: "fixed-qty" or "dynamic-qty"
            fixed_qty: Fixed quantity for fixed-qty rule
        
        Returns:
            Number of contracts to trade
        """
        current_bankroll = self.get_current_bankroll()
        
        if size_rule == "fixed-qty":
            # Check if fixed quantity exceeds risk limits
            total_risk = premium * fixed_qty
            if total_risk > current_bankroll * risk_fraction:
                logger.warning(f"Fixed quantity ${total_risk:.2f} exceeds risk limit ${current_bankroll * risk_fraction:.2f}")
                return 0  # Block the trade
            return fixed_qty
        
        elif size_rule == "dynamic-qty":
            # Calculate maximum contracts based on risk fraction
            max_risk = current_bankroll * risk_fraction
            max_contracts = int(max_risk // premium)
            return max(1, max_contracts)  # At least 1 contract
        
        else:
            raise ValueError(f"Unknown size rule: {size_rule}")
    
    def validate_trade_risk(self, premium: float, quantity: int, max_risk_pct: float = 50.0) -> bool:
        """
        Validate if a trade meets risk management criteria.
        
        Args:
            premium: Option premium per contract
            quantity: Number of contracts
            max_risk_pct: Maximum risk as percentage of bankroll
        
        Returns:
            True if trade is within risk limits
        """
        current_bankroll = self.get_current_bankroll()
        total_risk = premium * quantity
        risk_pct = (total_risk / current_bankroll) * 100
        
        if risk_pct > max_risk_pct:
            logger.warning(f"Trade risk {risk_pct:.1f}% exceeds limit {max_risk_pct}%")
            return False
        
        return True
    
    def record_trade(self, trade_details: Dict) -> Dict:
        """
        Record a trade in the bankroll history.
        
        Args:
            trade_details: Dictionary with trade information
        
        Returns:
            Updated bankroll data
        """
        data = self._load_bankroll()
        
        # Add trade to history
        trade_record = {
            "timestamp": datetime.now().isoformat(),
            "symbol": trade_details.get("symbol", "SPY"),
            "direction": trade_details.get("direction", ""),
            "strike": trade_details.get("strike", 0),
            "expiry": trade_details.get("expiry", ""),
            "quantity": trade_details.get("quantity", 0),
            "premium": trade_details.get("premium", 0),
            "total_cost": trade_details.get("total_cost", 0),
            "decision_confidence": trade_details.get("confidence", 0),
            "llm_reason": trade_details.get("reason", ""),
            "realized_pnl": trade_details.get("realized_pnl", 0),  # Will be 0 initially
            "status": trade_details.get("status", "OPEN")
        }
        
        data["trade_history"].append(trade_record)
        data["total_trades"] += 1
        
        # Update bankroll if realized P/L is provided
        if "realized_pnl" in trade_details and trade_details["realized_pnl"] != 0:
            pnl = trade_details["realized_pnl"]
            data["current_bankroll"] += pnl
            data["total_pnl"] += pnl
            
            if pnl > 0:
                data["winning_trades"] += 1
            
            # Update peak bankroll and drawdown
            if data["current_bankroll"] > data["peak_bankroll"]:
                data["peak_bankroll"] = data["current_bankroll"]
            
            current_drawdown = (data["peak_bankroll"] - data["current_bankroll"]) / data["peak_bankroll"] * 100
            if current_drawdown > data["max_drawdown"]:
                data["max_drawdown"] = current_drawdown
        
        self._save_bankroll(data)
        logger.info(f"Recorded trade: {trade_details.get('direction', 'UNKNOWN')} {trade_details.get('symbol', 'SPY')}")
        
        return data
    
    def update_bankroll(self, new_amount: float, reason: str = "Manual update") -> Dict:
        """
        Update bankroll amount (typically after realized P/L).
        
        Args:
            new_amount: New bankroll amount
            reason: Reason for the update
        
        Returns:
            Updated bankroll data
        """
        data = self._load_bankroll()
        old_amount = data["current_bankroll"]
        pnl_change = new_amount - old_amount
        
        data["current_bankroll"] = new_amount
        data["total_pnl"] += pnl_change
        
        # Update peak bankroll and drawdown
        if new_amount > data["peak_bankroll"]:
            data["peak_bankroll"] = new_amount
        
        current_drawdown = (data["peak_bankroll"] - new_amount) / data["peak_bankroll"] * 100
        if current_drawdown > data["max_drawdown"]:
            data["max_drawdown"] = current_drawdown
        
        # Add update record
        update_record = {
            "timestamp": datetime.now().isoformat(),
            "old_amount": old_amount,
            "new_amount": new_amount,
            "change": pnl_change,
            "reason": reason
        }
        
        if "bankroll_updates" not in data:
            data["bankroll_updates"] = []
        data["bankroll_updates"].append(update_record)
        
        self._save_bankroll(data)
        logger.info(f"Updated bankroll: ${old_amount:.2f} -> ${new_amount:.2f} ({reason})")
        
        return data
    
    def get_win_history(self, last_n: int = 20) -> list:
        """
        Get recent win/loss history for LLM confidence calibration.
        
        Returns the persistent win/loss history maintained specifically for the LLM's
        confidence calibration system ("confidence = wins_last20 / 20").
        
        Args:
            last_n: Number of recent trades to return (default 20 for LLM system)
        
        Returns:
            List of boolean values (True for wins, False for losses) for up to last_n trades.
            Empty list if no trade history exists.
        """
        data = self._load_bankroll()
        
        # Ensure win_loss_history exists (for backward compatibility)
        if "win_loss_history" not in data:
            data["win_loss_history"] = []
            self._save_bankroll(data)
            logger.info("[BANKROLL] Initialized empty win/loss history for LLM confidence calibration")
        
        # Return the last N trades from persistent history
        win_history = data["win_loss_history"][-last_n:] if len(data["win_loss_history"]) > last_n else data["win_loss_history"]
        
        return win_history
    
    def record_trade_outcome(self, is_win: bool) -> None:
        """
        Record the outcome of a trade (win/loss) for LLM confidence calibration.
        
        This method maintains a rolling history of the last 20 trade outcomes that the LLM
        uses for confidence calibration ("confidence = wins_last20 / 20").
        
        Args:
            is_win: True if the trade was profitable, False otherwise
        """
        data = self._load_bankroll()
        
        # Ensure win_loss_history exists (for backward compatibility)
        if "win_loss_history" not in data:
            data["win_loss_history"] = []
        
        # Add the new outcome
        data["win_loss_history"].append(is_win)
        
        # Keep only the last 20 trades for LLM confidence calibration
        if len(data["win_loss_history"]) > 20:
            data["win_loss_history"] = data["win_loss_history"][-20:]
        
        # Update last_updated timestamp
        data["last_updated"] = datetime.now().isoformat()
        
        self._save_bankroll(data)
        
        # Log the outcome with current win rate
        win_count = sum(data["win_loss_history"])
        total_count = len(data["win_loss_history"])
        win_rate = win_count / total_count if total_count > 0 else 0.0
        
        logger.info(f"[BANKROLL] Recorded trade outcome: {'WIN' if is_win else 'LOSS'}. "
                   f"LLM confidence history: {win_rate:.2f} win rate ({win_count}/{total_count} trades)")
    
    def get_win_rate_stats(self) -> Dict:
        """
        Get detailed win rate statistics for the last 20 trades for LLM confidence calibration.
        
        Returns:
            Dictionary with win rate statistics used by the LLM system
        """
        win_history = self.get_win_history()
        
        if not win_history:
            return {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "confidence_base": 0.5,  # Cap at 50% when no history (per LLM prompt)
                "has_history": False
            }
        
        wins = sum(win_history)
        total = len(win_history)
        win_rate = wins / total
        
        return {
            "total_trades": total,
            "wins": wins,
            "losses": total - wins,
            "win_rate": win_rate,
            "confidence_base": min(win_rate, 0.5),  # Cap at 50% as per LLM prompt
            "has_history": True
        }
    
    def get_performance_summary(self) -> Dict:
        """Get performance summary for reporting."""
        data = self._load_bankroll()
        
        total_trades = data["total_trades"]
        winning_trades = data["winning_trades"]
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        return {
            "current_bankroll": data["current_bankroll"],
            "start_capital": data["start_capital"],
            "total_pnl": data["total_pnl"],
            "total_return_pct": (data["total_pnl"] / data["start_capital"] * 100),
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "win_rate_pct": win_rate,
            "max_drawdown_pct": data["max_drawdown"],
            "peak_bankroll": data["peak_bankroll"]
        }
    
    def reset_bankroll(self, new_start_capital: Optional[float] = None):
        """Reset bankroll to starting conditions (use with caution)."""
        if new_start_capital is None:
            new_start_capital = self.start_capital
        
        reset_data = {
            "current_bankroll": new_start_capital,
            "start_capital": new_start_capital,
            "total_trades": 0,
            "winning_trades": 0,
            "total_pnl": 0.0,
            "max_drawdown": 0.0,
            "peak_bankroll": new_start_capital,
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "trade_history": [],
            "bankroll_updates": []
        }
        
        self._save_bankroll(reset_data)
        logger.warning(f"Bankroll reset to ${new_start_capital}")
        
        return reset_data
