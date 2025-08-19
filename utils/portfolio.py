"""
Portfolio Management Module

Provides comprehensive position tracking and P&L management for the Robinhood HA
Breakout trading system. Handles open position monitoring, trade action determination,
realized P&L calculations, and persistent position storage.

Key Features:
- Persistent position tracking with CSV storage
- Automatic open/close trade action determination
- Realized P&L calculation and logging
- Position lifecycle management
- Trade history and performance tracking
- Cross-session position continuity

Position Management:
- Track open options positions with full details
- Automatic position matching for closing trades
- Entry and exit premium tracking
- Contract quantity and strike price monitoring
- Expiration date and side (CALL/PUT) tracking

Trade Logic:
- Determine if new trade opens or closes position
- Match existing positions by symbol and side
- Calculate realized P&L on position closure
- Update position files automatically
- Log completed trades with full details

P&L Calculations:
- Realized profit/loss on closed positions
- Premium-based P&L calculations
- Performance metrics and statistics
- Win/loss ratio tracking
- Average profit/loss analysis

Persistence:
- CSV file storage for position data
- Automatic file creation and header management
- Cross-session position continuity
- Trade log integration
- Backup and recovery capabilities

Intraday Trading Support:
- Same-day position opening and closing
- Multiple positions per symbol support
- Real-time position status updates
- End-of-day position cleanup
- Risk monitoring and alerts

Usage:
    # Initialize portfolio manager
    portfolio = PortfolioManager(positions_file='positions.csv')

    # Determine trade action
    action, existing_pos = portfolio.determine_trade_action('SPY', 'CALL')

    if action == 'OPEN':
        # Opening new position
        position = Position(
            entry_time=datetime.now().isoformat(),
            symbol='SPY',
            expiry='2024-01-19',
            strike=635.0,
            side='CALL',
            contracts=1,
            entry_premium=2.50
        )
        portfolio.add_position(position)

    elif action == 'CLOSE':
        # Closing existing position
        realized_pnl = portfolio.calculate_realized_pnl(existing_pos, exit_premium=2.88)
        portfolio.remove_position(existing_pos)
        portfolio.log_realized_trade(existing_pos, 2.88, realized_pnl)

Author: Robinhood HA Breakout System
Version: 2.0.0
License: MIT
"""

import csv
import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Data class representing an open options position."""

    entry_time: str
    symbol: str
    expiry: str
    strike: float
    side: str  # 'CALL' or 'PUT'
    contracts: int
    entry_premium: float

    def to_dict(self) -> Dict:
        """Convert position to dictionary for CSV writing."""
        return {
            "entry_time": self.entry_time,
            "symbol": self.symbol,
            "expiry": self.expiry,
            "strike": self.strike,
            "side": self.side,
            "contracts": self.contracts,
            "entry_premium": self.entry_premium,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Position":
        """Create position from dictionary (CSV row)."""
        return cls(
            entry_time=data["entry_time"],
            symbol=data["symbol"],
            expiry=data["expiry"],
            strike=float(data["strike"]),
            side=data["side"],
            contracts=int(data["contracts"]),
            entry_premium=float(data["entry_premium"]),
        )

    def matches_close_criteria(self, symbol: str, side: str) -> bool:
        """
        Check if this position would be closed by a new trade.

        Args:
            symbol: Symbol of the new trade
            side: Side of the new trade ('CALL' or 'PUT')

        Returns:
            True if the new trade would close this position
        """
        return (
            self.symbol == symbol and self.side != side
        )  # Opposite side closes the position


class PortfolioManager:
    """Manages open positions and realized P/L tracking."""

    def __init__(self, positions_file: str = "positions.csv"):
        self.positions_file = Path(positions_file)
        self.fieldnames = [
            "entry_time",
            "symbol",
            "expiry",
            "strike",
            "side",
            "contracts",
            "entry_premium",
        ]
        self._ensure_positions_file()

    def _ensure_positions_file(self):
        """Create positions file with headers if it doesn't exist."""
        if not self.positions_file.exists():
            with open(self.positions_file, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                writer.writeheader()
            logger.info(f"Created new positions file: {self.positions_file}")

    def load_positions(self) -> List[Position]:
        """
        Load all open positions from the CSV file.

        Returns:
            List of Position objects
        """
        positions = []

        try:
            with open(self.positions_file, "r", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row["entry_time"]:  # Skip empty rows
                        positions.append(Position.from_dict(row))

            logger.info(f"Loaded {len(positions)} open positions")
            return positions

        except Exception as e:
            logger.error(f"Error loading positions: {e}")
            return []

    def add_position(self, position: Position) -> None:
        """
        Add a new position to the positions file.

        Args:
            position: Position object to add
        """
        try:
            with open(self.positions_file, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                writer.writerow(position.to_dict())

            logger.info(
                f"Added position: {position.symbol} {position.side} "
                f"${position.strike} x{position.contracts} @ ${position.entry_premium}"
            )

        except Exception as e:
            logger.error(f"Error adding position: {e}")
            raise

    def remove_position(self, position_to_remove: Position) -> None:
        """
        Remove a position from the positions file.

        Args:
            position_to_remove: Position to remove from the file
        """
        try:
            positions = self.load_positions()

            # Filter out the position to remove
            remaining_positions = []
            removed = False

            for pos in positions:
                if (
                    pos.symbol == position_to_remove.symbol
                    and pos.side == position_to_remove.side
                    and pos.strike == position_to_remove.strike
                    and pos.expiry == position_to_remove.expiry
                ):
                    removed = True
                    logger.info(
                        f"Removing position: {pos.symbol} {pos.side} "
                        f"${pos.strike} x{pos.contracts}"
                    )
                else:
                    remaining_positions.append(pos)

            if not removed:
                logger.warning("Position to remove not found in positions file")
                return

            # Rewrite the file with remaining positions
            with open(self.positions_file, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                writer.writeheader()
                for pos in remaining_positions:
                    writer.writerow(pos.to_dict())

            logger.info(
                f"Position removed. {len(remaining_positions)} positions remaining"
            )

        except Exception as e:
            logger.error(f"Error removing position: {e}")
            raise

    def find_position_to_close(self, symbol: str, side: str) -> Optional[Position]:
        """
        Find an existing position that would be closed by a new trade.

        Args:
            symbol: Symbol of the new trade
            side: Side of the new trade ('CALL' or 'PUT')

        Returns:
            Position object if found, None otherwise
        """
        positions = self.load_positions()

        for position in positions:
            if position.matches_close_criteria(symbol, side):
                logger.info(
                    f"Found position to close: {position.symbol} {position.side} "
                    f"${position.strike} x{position.contracts}"
                )
                return position

        return None

    def determine_trade_action(
        self, symbol: str, side: str
    ) -> Tuple[str, Optional[Position]]:
        """
        Determine if a new trade should OPEN or CLOSE a position.

        Args:
            symbol: Symbol of the new trade
            side: Side of the new trade ('CALL' or 'PUT')

        Returns:
            Tuple of (action, position_to_close) where action is 'OPEN' or 'CLOSE'
        """
        position_to_close = self.find_position_to_close(symbol, side)

        if position_to_close:
            return ("CLOSE", position_to_close)
        else:
            return ("OPEN", None)

    def calculate_realized_pnl(self, position: Position, exit_premium: float) -> float:
        """
        Calculate realized P/L for a closed position.

        Args:
            position: The position being closed
            exit_premium: Premium received when closing the position

        Returns:
            Realized P/L (positive = profit, negative = loss)
        """
        # For options: P/L = (exit_premium - entry_premium) * contracts * 100
        # Note: This assumes we're always selling to close (taking profit/loss)
        pnl = (exit_premium - position.entry_premium) * position.contracts * 100

        logger.info(
            f"Calculated P/L: Entry ${position.entry_premium} -> Exit ${exit_premium} "
            f"= ${pnl:.2f} for {position.contracts} contracts"
        )

        return pnl

    def get_positions_summary(self) -> Dict:
        """
        Get a summary of current positions.

        Returns:
            Dictionary with position statistics
        """
        positions = self.load_positions()

        if not positions:
            return {
                "total_positions": 0,
                "call_positions": 0,
                "put_positions": 0,
                "total_contracts": 0,
                "total_premium_paid": 0.0,
                "symbols": [],
            }

        call_positions = [p for p in positions if p.side == "CALL"]
        put_positions = [p for p in positions if p.side == "PUT"]
        total_contracts = sum(p.contracts for p in positions)
        total_premium = sum(p.entry_premium * p.contracts for p in positions)
        symbols = list(set(p.symbol for p in positions))

        return {
            "total_positions": len(positions),
            "call_positions": len(call_positions),
            "put_positions": len(put_positions),
            "total_contracts": total_contracts,
            "total_premium_paid": total_premium,
            "symbols": symbols,
        }

    def log_realized_trade(
        self,
        position: Position,
        exit_premium: float,
        realized_pnl: float,
        trade_log_file: str = "logs/trade_history.csv",
    ) -> None:
        """
        Log a completed trade with realized P/L to the trade log with VIX context.

        Args:
            position: The closed position
            exit_premium: Premium received when closing
            realized_pnl: Calculated realized P/L
            trade_log_file: Path to the trade log CSV file
        """
        try:
            from .logging_utils import log_trade_decision

            # Get VIX context for trade logging
            vix_level = None
            vix_adjustment_factor = 1.0
            vix_regime = "UNKNOWN"
            
            try:
                from .vix_position_sizing import get_vix_position_sizer
                vix_sizer = get_vix_position_sizer()
                
                # Get VIX data
                factor, reason, vix_value = vix_sizer.get_vix_adjustment_factor()
                regime, _ = vix_sizer.get_volatility_regime()
                
                vix_level = vix_value
                vix_adjustment_factor = factor
                vix_regime = regime
                
            except Exception as vix_error:
                logger.debug(f"[VIX-LOG] Could not get VIX context: {vix_error}")

            # Map to 18-field scoped ledger schema with VIX data
            trade_data = {
                "timestamp": datetime.now().isoformat(),
                "symbol": position.symbol,
                "decision": f"CLOSE_{position.side}",
                "confidence": 1.0,
                "current_price": "",
                "strike": position.strike,
                "premium": position.entry_premium,  # entry premium
                "quantity": position.contracts,
                "total_cost": position.entry_premium * position.contracts * 100,
                "reason": f"Closing {position.side} position",
                "status": "CLOSED",
                "fill_price": exit_premium,  # exit premium
                "pnl_pct": "",
                "pnl_amount": realized_pnl,
                "exit_reason": "",
                "vix_level": vix_level,
                "vix_adjustment_factor": vix_adjustment_factor,
                "vix_regime": vix_regime,
            }

            log_trade_decision(trade_log_file, trade_data)

            logger.info(
                f"Logged realized trade: {position.symbol} {position.side} P/L: ${realized_pnl:.2f} "
                f"(VIX: {vix_level:.1f} {vix_regime})" if vix_level else f"Logged realized trade: {position.symbol} {position.side} P/L: ${realized_pnl:.2f}"
            )

        except Exception as e:
            logger.error(f"Error logging realized trade: {e}")
            raise
