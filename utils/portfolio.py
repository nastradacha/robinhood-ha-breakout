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
from utils.ledger.constants import (
    POSITIONS_SCHEMA_ALPACA_V1,
    POSITIONS_SCHEMA_VERSION,
)

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
        # Detect Alpaca-scoped positions files and switch to canonical schema
        self.is_alpaca_scoped = "positions_alpaca" in self.positions_file.name
        if self.is_alpaca_scoped:
            # Canonical Alpaca schema used by monitor_alpaca and AlpacaSync (imported from ledger.constants)
            self.fieldnames = POSITIONS_SCHEMA_ALPACA_V1
        else:
            # Legacy portfolio schema
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
        # Normalize existing Alpaca-scoped files to canonical schema to prevent column misalignment
        if self.is_alpaca_scoped:
            try:
                self._normalize_alpaca_positions_file()
                logger.info(f"[PORTFOLIO] Positions schema v{POSITIONS_SCHEMA_VERSION} normalized: {self.positions_file}")
            except Exception as e:
                logger.debug(f"[PORTFOLIO] Schema normalization skipped: {e}")

    def _ensure_positions_file(self):
        """Create positions file with headers if it doesn't exist."""
        if not self.positions_file.exists():
            with open(self.positions_file, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                writer.writeheader()
            logger.info(f"Created new positions file: {self.positions_file}")

    def _position_to_row(self, position: "Position") -> Dict:
        """Map Position object to the correct row schema for the target file."""
        if not self.is_alpaca_scoped:
            return position.to_dict()
        # Alpaca canonical schema mapping
        return {
            'symbol': position.symbol,
            'occ_symbol': '',  # let sync/monitor infer OCC if needed
            'strike': position.strike,
            'option_type': position.side,  # CALL/PUT
            'expiry': position.expiry,
            'quantity': position.contracts,
            'contracts': position.contracts,
            'entry_price': position.entry_premium,
            'current_price': None,
            'pnl_pct': None,
            'pnl_amount': None,
            'timestamp': position.entry_time,
            'status': 'open',
            'close_time': None,
            'market_value': None,
            'unrealized_pnl': None,
            'entry_time': position.entry_time,
            'source': 'interactive_entry',
            'sync_detected': False,
        }

    def _normalize_alpaca_positions_file(self) -> None:
        """Normalize Alpaca-scoped positions CSV to canonical schema with occ_symbol and fix misaligned rows.

        Rules:
        - Ensure header includes occ_symbol and columns are ordered per self.fieldnames
        - Detect rows where 'strike' mistakenly contains CALL/PUT (shifted right due to missing occ_symbol when written)
          and correct by moving fields back to their proper columns
        - If close_time contains a non-ISO token like 'closed_sync' and market_value looks like ISO timestamp,
          swap them so status/close_time are consistent
        """
        path = self.positions_file
        if not path.exists():
            return
        import re
        def is_iso_like(s: str) -> bool:
            try:
                if not s:
                    return False
                from datetime import datetime as _dt
                _ = _dt.fromisoformat(str(s).replace('Z',''))
                return True
            except Exception:
                return False
        def to_occ(symbol: str, expiry: str, opt_type: str, strike_val: str) -> str:
            try:
                sym = (symbol or '').strip().upper()
                exp = (expiry or '').strip()
                side = (opt_type or '').strip().upper()[:1]
                if not sym or not exp or side not in ('C','P'):
                    return ''
                # Expect YYYY-MM-DD
                if len(exp) == 10 and exp[4] == '-' and exp[7] == '-':
                    yymmdd = exp[2:4] + exp[5:7] + exp[8:10]
                else:
                    return ''
                strike_num = int(round(float(strike_val) * 1000))
                return f"{sym}{yymmdd}{side}{strike_num:08d}"
            except Exception:
                return ''

        # Read all rows with a flexible reader
        with open(path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            existing_header = reader.fieldnames or []

        # If the file uses an older header (no occ_symbol), add it
        header = list(existing_header)
        if 'occ_symbol' not in header:
            # Attempt to insert after 'symbol'
            if 'symbol' in header:
                idx = header.index('symbol') + 1
                header.insert(idx, 'occ_symbol')
            else:
                header.insert(1, 'occ_symbol')
            # Add empty occ_symbol to each row
            for r in rows:
                if 'occ_symbol' not in r:
                    r['occ_symbol'] = ''

        # Normalize each row to canonical keys
        normalized = []
        for r in rows:
            # Start with blank canonical row, copy shared keys
            nr = {k: r.get(k, '') for k in self.fieldnames}

            # Detect classic one-column shift (strike holds CALL/PUT)
            strike_val = str(r.get('strike', '')).strip().upper()
            occ_val = str(r.get('occ_symbol', '')).strip()
            opt_type = str(r.get('option_type', '')).strip().upper()
            expiry_val = str(r.get('expiry', '')).strip()
            if strike_val in ('CALL','PUT') and re.match(r'^\d{4}-\d{2}-\d{2}', str(r.get('option_type','')) or ''):
                # Shift back: side <- strike, strike <- occ_symbol (if numeric), expiry <- option_type
                nr['option_type'] = strike_val
                try:
                    nr['strike'] = float(occ_val) if occ_val not in ('', None) else nr.get('strike','')
                except Exception:
                    nr['strike'] = nr.get('strike','')
                nr['expiry'] = r.get('option_type','')
                # occ_symbol becomes unknown here; set blank so monitor/sync can infer
                nr['occ_symbol'] = ''

            # Fix close_time/status spillover where close_time has a non-ISO token
            ct = str(nr.get('close_time','')).strip()
            mv = str(nr.get('market_value','')).strip()
            st = str(nr.get('status','')).strip()
            closed_tokens = {'closed', 'closed_sync', 'closed_llm', 'closed_auto', 'closed_manual'}
            if ct and not is_iso_like(ct) and (ct.lower() in closed_tokens or is_iso_like(mv)):
                # If row says open but close_time holds a closed-token, treat it as spillover and keep it open
                if st.lower() == 'open':
                    nr['close_time'] = ''
                else:
                    # Move ISO from market_value to close_time if available; set status if empty
                    if not st and ct:
                        nr['status'] = ct
                    if is_iso_like(mv):
                        nr['close_time'] = mv
                        nr['market_value'] = ''

            # Contracts/entry_price misplacement fix: if contracts looks like a price and entry_price is empty
            contracts_raw = str(r.get('contracts','')).strip()
            quantity_raw = str(r.get('quantity','')).strip()
            entry_price_raw = str(r.get('entry_price','')).strip()
            try:
                if entry_price_raw in ('', None) and contracts_raw not in ('', None):
                    c_val = float(contracts_raw)
                    # If contracts has a non-integer decimal and quantity is valid, assume it's the entry price
                    if abs(c_val - round(c_val)) > 1e-9:
                        nr['entry_price'] = c_val
                        # Restore contracts from quantity (default 1)
                        try:
                            q_val = int(round(float(quantity_raw or 1)))
                        except Exception:
                            q_val = 1
                        nr['contracts'] = q_val
            except Exception:
                pass

            # Fill occ_symbol when possible
            if not nr.get('occ_symbol') and nr.get('symbol') and nr.get('expiry') and nr.get('option_type') and nr.get('strike'):
                occ_try = to_occ(nr.get('symbol'), nr.get('expiry'), nr.get('option_type'), nr.get('strike'))
                if occ_try:
                    nr['occ_symbol'] = occ_try

            normalized.append(nr)

        # Rewrite file with canonical header and normalized rows
        # De-duplicate open rows per occ_symbol (or composite key) keeping the latest by entry_time/timestamp
        def key_for(row: dict) -> str:
            occ = (row.get('occ_symbol') or '').strip()
            if occ:
                return f"occ:{occ}"
            return f"cmp:{row.get('symbol')}|{row.get('expiry')}|{row.get('option_type')}|{row.get('strike')}"

        # Index rows by key
        grouped = {}
        for nr in normalized:
            k = key_for(nr)
            grouped.setdefault(k, []).append(nr)

        deduped = []
        now_iso = datetime.now().isoformat()
        for k, rows_k in grouped.items():
            # Partition by open/closed
            open_rows = [r for r in rows_k if str(r.get('status','open')).strip().lower() == 'open' and not str(r.get('close_time','')).strip()]
            closed_rows = [r for r in rows_k if r not in open_rows]

            # If multiple open rows exist, keep the latest by entry_time/timestamp
            if len(open_rows) > 1:
                def latest_ts(r: dict) -> str:
                    return str(r.get('entry_time') or r.get('timestamp') or '')
                open_rows.sort(key=latest_ts)
                keep = open_rows[-1]
                deduped.append(keep)
                # Mark older ones as closed_sync; use ISO from market_value if present
                for r in open_rows[:-1]:
                    ct_mv = str(r.get('market_value','')).strip()
                    r['status'] = 'closed_sync'
                    r['close_time'] = ct_mv if is_iso_like(ct_mv) else now_iso
                    # Clear market_value if it held the ISO timestamp
                    if is_iso_like(ct_mv):
                        r['market_value'] = ''
                    closed_rows.append(r)
            elif len(open_rows) == 1:
                deduped.append(open_rows[0])

            # Append existing closed rows
            deduped.extend(closed_rows)

        # Write back
        with open(path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.fieldnames)
            writer.writeheader()
            for nr in deduped:
                writer.writerow(nr)
        logger.info(f"[PORTFOLIO] Normalized & de-duplicated positions file: {path}")

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
                    # Skip empty rows entirely
                    if not row or not any((v or "").strip() for v in row.values()):
                        continue

                    try:
                        if self.is_alpaca_scoped:
                            # Skip rows explicitly marked as closed or with a close_time set
                            status_str = str(row.get("status", "")).strip().lower()
                            if status_str.startswith("closed") or str(row.get("close_time", "")).strip():
                                continue

                            # Required fields with mapping
                            symbol = (row.get("symbol") or "").strip()
                            expiry = (row.get("expiry") or "").strip()
                            strike_raw = (row.get("strike") or "").strip()
                            side = (row.get("option_type") or row.get("side") or "").strip().upper()
                            qty_raw = (row.get("quantity") or row.get("contracts") or "1").strip()
                            entry_price_raw = (row.get("entry_price") or row.get("entry_premium") or "").strip()

                            # Validate required string fields
                            if not symbol or not expiry or side not in ("CALL", "PUT"):
                                logger.warning(f"Skipping incomplete position row (missing symbol/expiry/side): {row}")
                                continue

                            # Coerce numerics safely
                            try:
                                strike = float(strike_raw)
                            except Exception:
                                logger.warning(f"Skipping position row with invalid strike: {row}")
                                continue

                            try:
                                contracts = max(1, int(round(float(qty_raw or 1))))
                            except Exception:
                                contracts = 1

                            try:
                                entry_premium = float(entry_price_raw) if entry_price_raw not in ("", None) else 0.01
                            except Exception:
                                entry_premium = 0.01

                            # entry_time fallback
                            entry_time = (row.get("entry_time") or datetime.now().isoformat())

                            positions.append(
                                Position(
                                    entry_time=entry_time,
                                    symbol=symbol,
                                    expiry=expiry,
                                    strike=strike,
                                    side=side,
                                    contracts=contracts,
                                    entry_premium=entry_premium,
                                )
                            )
                        else:
                            # Legacy schema path
                            if row.get("entry_time") and any(row.values()):
                                positions.append(Position.from_dict(row))
                    except KeyError as ke:
                        logger.warning(f"Skipping position row missing column {ke}: {row}")
                        continue
                    except Exception as pe:
                        logger.warning(f"Skipping malformed position row: {pe}")
                        continue

            # Deduplicate identical open rows by (symbol, side, strike, expiry)
            try:
                unique_map = {}
                duplicates = 0
                for pos in positions:
                    key = (pos.symbol, pos.side, pos.strike, pos.expiry)
                    if key not in unique_map:
                        unique_map[key] = pos
                    else:
                        duplicates += 1
                if duplicates:
                    logger.warning(f"Deduplicated {duplicates} duplicate open position rows")
                positions = list(unique_map.values())
            except Exception as e:
                logger.debug(f"Deduplication skipped due to error: {e}")

            logger.info(f"Loaded {len(positions)} open positions")
            return positions

        except FileNotFoundError:
            logger.info("No positions file found, starting with empty positions")
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
                writer.writerow(self._position_to_row(position))

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
                    writer.writerow(self._position_to_row(pos))

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
