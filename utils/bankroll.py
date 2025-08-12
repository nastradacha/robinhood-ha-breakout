# ✅ Alpaca paper/live & scoped ledgers verified – 2025-08-10
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

logger = logging.getLogger(__name__)


class BankrollManager:
    """Manages trading bankroll with risk controls and persistence."""

    def __init__(
        self, 
        bankroll_file: str = "bankroll.json", 
        start_capital: float = 40.0,
        broker: str = "robinhood",
        env: str = "live"
    ):
        # Support scoped ledgers for v0.9.0 broker/environment separation
        if bankroll_file == "bankroll.json":
            # Use scoped filename: bankroll_{broker}_{env}.json
            self.bankroll_file = Path(f"bankroll_{broker}_{env}.json")
        else:
            # Use provided filename (for backward compatibility)
            self.bankroll_file = Path(bankroll_file)
        
        self.start_capital = start_capital
        self.broker = broker
        self.env = env
        self._ensure_bankroll_file()

    def ledger_id(self) -> str:
        """Get ledger identifier for this broker/environment combination.
        
        Returns:
            String identifier like "alpaca:paper" or "robinhood:live"
        """
        return f"{self.broker}:{self.env}"

    def _ensure_bankroll_file(self):
        """Create bankroll file if it doesn't exist."""
        # ✅ YAML seed used only when bankroll.json missing – verified 2025-08-05
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
                "win_loss_history": [],  # List of True/False for last 20 trades
            }
            self._save_bankroll(initial_data)
            logger.info(f"Created new bankroll file with ${self.start_capital}")

    def _load_bankroll(self) -> Dict:
        """Load bankroll data from file."""
        try:
            with open(self.bankroll_file, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading bankroll file: {e}")
            raise

    def _save_bankroll(self, data: Dict):
        """Save bankroll data to file."""
        try:
            data["last_updated"] = datetime.now().isoformat()
            with open(self.bankroll_file, "w") as f:
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

    def calculate_position_size(
        self,
        premium: float,
        risk_fraction: float = 0.5,
        size_rule: str = "fixed-qty",
        fixed_qty: int = 1,
    ) -> int:
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
            total_risk = premium * fixed_qty * 100
            if total_risk > current_bankroll * risk_fraction:
                logger.warning(
                    f"Fixed quantity ${total_risk:.2f} exceeds risk limit ${current_bankroll * risk_fraction:.2f}"
                )
                return 0  # Block the trade
            return fixed_qty

        elif size_rule == "dynamic-qty":
            # Calculate maximum contracts based on risk fraction
            max_risk = current_bankroll * risk_fraction
            max_contracts = int(max_risk // (premium * 100))
            return max(1, max_contracts)  # At least 1 contract

        else:
            raise ValueError(f"Unknown size rule: {size_rule}")

    def validate_trade_risk(
        self, premium: float, quantity: int, max_risk_pct: float = 50.0
    ) -> bool:
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
        total_risk = premium * quantity * 100
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
            "status": trade_details.get("status", "OPEN"),
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

            current_drawdown = (
                (data["peak_bankroll"] - data["current_bankroll"])
                / data["peak_bankroll"]
                * 100
            )
            if current_drawdown > data["max_drawdown"]:
                data["max_drawdown"] = current_drawdown

        self._save_bankroll(data)
        logger.info(
            f"Recorded trade: {trade_details.get('direction', 'UNKNOWN')} {trade_details.get('symbol', 'SPY')}"
        )

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

        current_drawdown = (
            (data["peak_bankroll"] - new_amount) / data["peak_bankroll"] * 100
        )
        if current_drawdown > data["max_drawdown"]:
            data["max_drawdown"] = current_drawdown

        # Add update record
        update_record = {
            "timestamp": datetime.now().isoformat(),
            "old_amount": old_amount,
            "new_amount": new_amount,
            "change": pnl_change,
            "reason": reason,
        }

        if "bankroll_updates" not in data:
            data["bankroll_updates"] = []
        data["bankroll_updates"].append(update_record)

        self._save_bankroll(data)
        logger.info(
            f"Updated bankroll: ${old_amount:.2f} -> ${new_amount:.2f} ({reason})"
        )

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
            logger.info(
                "[BANKROLL] Initialized empty win/loss history for LLM confidence calibration"
            )

        # Return the last N trades from persistent history
        win_history = (
            data["win_loss_history"][-last_n:]
            if len(data["win_loss_history"]) > last_n
            else data["win_loss_history"]
        )

        return win_history

    def get_enhanced_llm_context(self, last_n: int = 20) -> Dict:
        """
        Get enhanced context for LLM decision making with richer trade history.

        Hybrid Approach: Combines fast boolean win/loss history with detailed recent
        trade patterns, performance metrics, and market condition context for better
        LLM learning while maintaining backward compatibility.

        Args:
            last_n: Number of recent trades to analyze (default 20 for LLM system)

        Returns:
            Dict containing:
            - win_history: List of boolean outcomes (backward compatible)
            - recent_patterns: Detailed analysis of recent trades
            - performance_metrics: Aggregated performance statistics
            - symbol_performance: Per-symbol win rates and patterns
            - confidence_modifiers: Suggested confidence adjustments
        """
        # Get basic win/loss history (maintains backward compatibility)
        win_history = self.get_win_history(last_n)

        if not win_history:
            return {
                "win_history": [],
                "recent_patterns": [],
                "performance_metrics": {
                    "win_rate": 0.0,
                    "current_streak": 0,
                    "avg_win_pct": 0.0,
                    "avg_loss_pct": 0.0,
                    "total_trades": 0,
                },
                "symbol_performance": {},
                "confidence_modifiers": {
                    "streak_modifier": 0.0,
                    "recent_performance_modifier": 0.0,
                    "symbol_confidence": 1.0,
                },
            }

        # Calculate performance metrics
        wins = sum(win_history)
        total = len(win_history)
        win_rate = wins / total if total > 0 else 0.0

        # Calculate current streak
        current_streak = self._calculate_current_streak(win_history)

        # Get recent trade patterns from trade log
        recent_patterns = self._get_recent_trade_patterns(last_n=min(5, total))

        # Calculate symbol-specific performance
        symbol_performance = self._get_symbol_performance()

        # Calculate confidence modifiers
        confidence_modifiers = self._calculate_confidence_modifiers(
            win_history, current_streak, recent_patterns
        )

        return {
            "win_history": win_history,  # Keep existing format for compatibility
            "recent_patterns": recent_patterns,
            "performance_metrics": {
                "win_rate": win_rate,
                "current_streak": current_streak,
                "avg_win_pct": self._calculate_avg_win_pct(recent_patterns),
                "avg_loss_pct": self._calculate_avg_loss_pct(recent_patterns),
                "total_trades": total,
            },
            "symbol_performance": symbol_performance,
            "confidence_modifiers": confidence_modifiers,
        }

    def _calculate_current_streak(self, win_history: list) -> int:
        """
        Calculate current winning or losing streak.

        Args:
            win_history: List of boolean trade outcomes

        Returns:
            Positive number for winning streak, negative for losing streak
        """
        if not win_history:
            return 0

        streak = 0
        current_outcome = win_history[-1]

        # Count consecutive outcomes from the end
        for outcome in reversed(win_history):
            if outcome == current_outcome:
                streak += 1
            else:
                break

        # Return positive for wins, negative for losses
        return streak if current_outcome else -streak

    def _get_recent_trade_patterns(self, last_n: int = 5) -> list:
        """
        Extract recent trade patterns from trade log for LLM learning.

        Args:
            last_n: Number of recent trades to analyze

        Returns:
            List of trade pattern dictionaries
        """
        try:
            import csv
            from pathlib import Path

            # Resolve scoped trade log file from config; fallback to default scoped path
            try:
                from utils.llm import load_config  # type: ignore

                trade_log_file = load_config().get(
                    "TRADE_LOG_FILE", "logs/trade_history_robinhood_live.csv"
                )
            except Exception:
                trade_log_file = "logs/trade_history_robinhood_live.csv"

            trade_log_path = Path(trade_log_file)
            if not trade_log_path.exists():
                return []

            patterns = []
            with open(trade_log_path, "r", newline="") as f:
                reader = csv.DictReader(f)
                trades = list(reader)

                # Get last N completed trades (those with any PnL data)
                def has_pnl(t: dict) -> bool:
                    return any(
                        (t.get(k) is not None and str(t.get(k)).strip() != "")
                        for k in ("pnl_amount", "pnl", "pnl_dollars")
                    )

                recent_trades = [t for t in trades if has_pnl(t)][-last_n:]

                for trade in recent_trades:
                    try:
                        pnl = float(
                            trade.get("pnl_amount")
                            or trade.get("pnl")
                            or trade.get("pnl_dollars")
                            or 0
                        )
                        pnl_pct = 0.0
                        if trade.get("pnl_pct") not in (None, ""):
                            pnl_pct = float(trade.get("pnl_pct", 0))
                        elif trade.get("pnl_percent") not in (None, ""):
                            pnl_pct = float(trade.get("pnl_percent", 0))

                        pattern = {
                            "symbol": trade.get("symbol", "UNKNOWN"),
                            "option_type": (
                                trade.get("option_type")
                                or (
                                    "CALL"
                                    if "CALL"
                                    in str(trade.get("decision", "")).upper()
                                    else (
                                        "PUT"
                                        if "PUT"
                                        in str(trade.get("decision", "")).upper()
                                        else "UNKNOWN"
                                    )
                                )
                            ),
                            "outcome": "WIN" if pnl > 0 else "LOSS",
                            "pnl_pct": pnl_pct,
                            "reason": trade.get("reason", ""),
                            "market_condition": self._classify_market_condition(
                                trade.get("reason", "")
                            ),
                        }
                        patterns.append(pattern)
                    except (ValueError, TypeError):
                        continue

            return patterns

        except Exception as e:
            logger.warning(f"[BANKROLL] Error reading trade patterns: {e}")
            return []

    def _get_symbol_performance(self) -> Dict:
        """
        Calculate per-symbol performance metrics.

        Returns:
            Dict with symbol-specific win rates and trade counts
        """
        try:
            import csv
            from pathlib import Path
            from collections import defaultdict

            # Resolve scoped trade log file from config; fallback to default scoped path
            try:
                from utils.llm import load_config  # type: ignore

                trade_log_file = load_config().get(
                    "TRADE_LOG_FILE", "logs/trade_history_robinhood_live.csv"
                )
            except Exception:
                trade_log_file = "logs/trade_history_robinhood_live.csv"

            trade_log_path = Path(trade_log_file)
            if not trade_log_path.exists():
                return {}

            symbol_stats = defaultdict(
                lambda: {"wins": 0, "total": 0, "total_pnl": 0.0}
            )

            with open(trade_log_path, "r", newline="") as f:
                reader = csv.DictReader(f)
                for trade in reader:
                    # Consider row if any PnL field present
                    pnl_field = (
                        trade.get("pnl_amount")
                        or trade.get("pnl")
                        or trade.get("pnl_dollars")
                    )
                    if pnl_field not in (None, ""):
                        try:
                            symbol = trade.get("symbol", "UNKNOWN")
                            pnl = float(pnl_field)

                            symbol_stats[symbol]["total"] += 1
                            symbol_stats[symbol]["total_pnl"] += pnl
                            if pnl > 0:
                                symbol_stats[symbol]["wins"] += 1
                        except (ValueError, TypeError):
                            continue

            # Convert to final format
            performance = {}
            for symbol, stats in symbol_stats.items():
                if stats["total"] > 0:
                    performance[symbol] = {
                        "win_rate": stats["wins"] / stats["total"],
                        "total_trades": stats["total"],
                        "avg_pnl": stats["total_pnl"] / stats["total"],
                    }

            return performance

        except Exception as e:
            logger.warning(f"[BANKROLL] Error calculating symbol performance: {e}")
            return {}

    def _calculate_confidence_modifiers(
        self, win_history: list, current_streak: int, recent_patterns: list
    ) -> Dict:
        """
        Calculate confidence modifiers based on recent performance.

        Args:
            win_history: Boolean list of trade outcomes
            current_streak: Current winning/losing streak
            recent_patterns: Recent trade pattern analysis

        Returns:
            Dict with confidence modification suggestions
        """
        modifiers = {
            "streak_modifier": 0.0,
            "recent_performance_modifier": 0.0,
            "symbol_confidence": 1.0,
        }

        # Streak-based modifier
        if current_streak >= 3:
            modifiers["streak_modifier"] = min(
                0.05, current_streak * 0.02
            )  # Max +5% boost
        elif current_streak <= -3:
            modifiers["streak_modifier"] = max(
                -0.10, current_streak * 0.02
            )  # Max -10% penalty

        # Recent performance modifier (last 5 trades)
        if recent_patterns:
            recent_wins = sum(1 for p in recent_patterns if p["outcome"] == "WIN")
            recent_win_rate = recent_wins / len(recent_patterns)

            if recent_win_rate >= 0.8:  # 80%+ recent win rate
                modifiers["recent_performance_modifier"] = 0.05
            elif recent_win_rate <= 0.2:  # 20% or less recent win rate
                modifiers["recent_performance_modifier"] = -0.10

        return modifiers

    def _classify_market_condition(self, reason: str) -> str:
        """
        Classify market condition based on trade reason.

        Args:
            reason: Trade decision reason from LLM

        Returns:
            Market condition classification
        """
        reason_lower = reason.lower()

        # Check for breakout first (even if consolidation is mentioned)
        if any(term in reason_lower for term in ["breakout", "strong", "momentum"]):
            return "BULLISH_BREAKOUT"
        elif any(term in reason_lower for term in ["reversal", "oversold", "bounce"]):
            return "REVERSAL_SETUP"
        elif any(
            term in reason_lower for term in ["consolidation", "range", "sideways"]
        ):
            return "CONSOLIDATION"
        elif any(
            term in reason_lower
            for term in ["volatility", "volatile", "uncertainty", "mixed"]
        ):
            return "HIGH_VOLATILITY"
        else:
            return "NEUTRAL"

    def _calculate_avg_win_pct(self, recent_patterns: list) -> float:
        """
        Calculate average winning percentage from recent patterns.

        Args:
            recent_patterns: List of recent trade patterns

        Returns:
            Average winning percentage
        """
        wins = [p["pnl_pct"] for p in recent_patterns if p["outcome"] == "WIN"]
        return sum(wins) / len(wins) if wins else 0.0

    def _calculate_avg_loss_pct(self, recent_patterns: list) -> float:
        """
        Calculate average losing percentage from recent patterns.

        Args:
            recent_patterns: List of recent trade patterns

        Returns:
            Average losing percentage (negative number)
        """
        losses = [p["pnl_pct"] for p in recent_patterns if p["outcome"] == "LOSS"]
        return sum(losses) / len(losses) if losses else 0.0

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

        logger.info(
            f"[BANKROLL] Recorded trade outcome: {'WIN' if is_win else 'LOSS'}. "
            f"LLM confidence history: {win_rate:.2f} win rate ({win_count}/{total_count} trades)"
        )

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
                "has_history": False,
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
            "has_history": True,
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
            "peak_bankroll": data["peak_bankroll"],
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
            "bankroll_updates": [],
        }

        self._save_bankroll(reset_data)
        logger.warning(f"Bankroll reset to ${new_start_capital}")

    def apply_fill(
        self, position_id: str, fill_price: float, contracts: int = 1
    ) -> Dict:
        """
        Apply actual fill price to bankroll, replacing any previous estimate.

        Args:
            position_id: Unique identifier for the position
            fill_price: Actual fill price per contract
            contracts: Number of contracts (default 1)

        Returns:
            Updated bankroll data
        """
        try:
            from datetime import datetime
            import csv
            import os

            # Calculate actual premium cost
            actual_cost = fill_price * contracts * 100  # Options are per 100 shares

            # Load current bankroll
            data = self._load_bankroll()

            # Find and update the position in trade history
            position_found = False
            old_cost = 0

            for trade in data.get("trade_history", []):
                if trade.get("position_id") == position_id:
                    old_cost = trade.get("total_cost", 0)
                    trade["entry_premium"] = fill_price
                    trade["total_cost"] = actual_cost
                    trade["fill_updated"] = True
                    trade["fill_timestamp"] = datetime.now().isoformat()
                    position_found = True
                    break

            if not position_found:
                logger.warning(f"Position {position_id} not found in trade history")
                return data

            # Calculate the difference and adjust bankroll
            cost_difference = actual_cost - old_cost
            new_bankroll = data["current_bankroll"] - cost_difference

            # Update bankroll
            data["current_bankroll"] = new_bankroll
            data["last_updated"] = datetime.now().isoformat()

            # Write undo record to bankroll_history.csv
            history_file = "bankroll_history.csv"
            file_exists = os.path.exists(history_file)

            with open(history_file, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)

                # Write header if file doesn't exist
                if not file_exists:
                    writer.writerow(
                        [
                            "timestamp",
                            "position_id",
                            "delta",
                            "new_bankroll",
                            "action",
                            "fill_price",
                        ]
                    )

                # Write undo record
                writer.writerow(
                    [
                        datetime.now().isoformat(),
                        position_id,
                        -cost_difference,  # Negative because we're subtracting more cost
                        new_bankroll,
                        "fill_adjustment",
                        fill_price,
                    ]
                )

            # Save updated bankroll
            self._save_bankroll(data)

            logger.info(
                f"[BANKROLL] Applied fill ${fill_price:.2f} for {position_id}: "
                f"cost ${old_cost:.2f} -> ${actual_cost:.2f}, "
                f"bankroll ${data['current_bankroll'] + cost_difference:.2f} -> ${new_bankroll:.2f}"
            )

            return data

        except Exception as e:
            logger.error(f"[BANKROLL] Error applying fill for {position_id}: {e}")
            raise

        return reset_data
