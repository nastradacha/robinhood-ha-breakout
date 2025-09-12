#!/usr/bin/env python3
"""
Enhanced Position Monitoring with Alpaca Real-Time Data

This addresses the critical data accuracy issue where Yahoo Finance's
delayed data caused missed profit opportunities. Now uses Alpaca's
real-time market data for accurate profit/loss alerts.

Key Improvements:
- Real-time stock prices from Alpaca (vs 15-20min delayed Yahoo)
- Better option price estimation using current volatility
- More accurate profit/loss calculations
- Timely alerts when actual profit targets are hit
- Fallback to Yahoo Finance if Alpaca unavailable

Usage:
    python monitor_alpaca.py
"""

import os
import logging
import time
import csv
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.alpaca_client import AlpacaClient
from utils.enhanced_slack import EnhancedSlackIntegration
from utils.alpaca_sync import AlpacaSync
from utils.exit_strategies import (
    ExitStrategyManager,
    load_exit_config_from_file,
    ExitReason,
)
from utils.exit_confirmation import ExitConfirmationWorkflow
from utils.circuit_breaker_reset import check_and_process_file_reset
import yfinance as yf
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure centralized logging
from utils.logging_utils import setup_logging
setup_logging(log_level="INFO", log_file="logs/monitor_alpaca.log")
logger = logging.getLogger(__name__)


class EnhancedPositionMonitor:
    """
    Enhanced position monitoring with real-time Alpaca data.

    Provides accurate profit/loss tracking and timely alerts
    using professional-grade market data feeds.
    """

    def __init__(self):
        """Initialize monitor with Alpaca and fallback data sources."""
        self.slack = EnhancedSlackIntegration()

        # Load config and resolve broker/env-scoped positions file
        try:
            from utils.llm import load_config  # lazy import to avoid cycles
            config = load_config("config.yaml")
            self.config = config  # Store config for later use

            broker = config.get("BROKER", "robinhood")
            env = config.get("ALPACA_ENV", "paper") if broker == "alpaca" else "live"

            # Initialize Alpaca client with correct environment
            self.alpaca = AlpacaClient(env=env)

            # Prefer explicit POSITIONS_FILE from config (populated by load_config)
            positions_file = config.get("POSITIONS_FILE")
            if not positions_file:
                # Fallback to scoped resolver if needed
                from utils.scoped_files import get_scoped_paths  # type: ignore
                positions_file = get_scoped_paths(broker, env)["positions"]
        except Exception:
            # Ultimate fallback to legacy filename
            positions_file = "positions.csv"
            # Fallback Alpaca client (paper mode)
            self.alpaca = AlpacaClient(env="paper")
            self.config = None  # No config available

        self.positions_file = positions_file

        # Initialize advanced exit strategies
        try:
            exit_config = load_exit_config_from_file("config.yaml")
            self.exit_manager = ExitStrategyManager(exit_config)
            logger.info("[MONITOR] Advanced exit strategies enabled")
        except Exception as e:
            logger.warning(f"[MONITOR] Could not load exit strategies: {e}")
            self.exit_manager = ExitStrategyManager()  # Use defaults

        # Alert tracking to prevent spam
        self.last_alerts = {}
        self.alert_cooldown = 300  # 5 minutes between same alerts
        
        # Heartbeat tracking
        self.heartbeat_counter = 0
        self.heartbeat_interval = 5  # Send heartbeat every 5 monitoring cycles

        # Legacy profit alert levels (kept for compatibility)
        self.profit_levels = [5, 10, 15, 20, 25, 30, 50, 75, 100, 150, 200]  # Percentages
        self.stop_loss_threshold = 25  # 25% loss

        # Market hours (ET)
        self.market_close_warning = 15  # Minutes before close
        self.end_of_day_time = "15:45"  # 3:45 PM ET

        logger.info("[MONITOR] Enhanced position monitor initialized")
        logger.info(f"[MONITOR] Alpaca enabled: {self.alpaca.enabled}")
        logger.info(f"[MONITOR] Slack enabled: {self.slack.enabled}")
        logger.info(f"[MONITOR] Positions file: {self.positions_file}")

    def _parse_occ_option_symbol(self, occ: str) -> Optional[Dict]:
        """Parse OCC option symbol like 'XLF250912C00053000' into components.

        Returns dict with keys: underlying, expiry (YYYY-MM-DD), option_type (CALL/PUT), strike (float)
        """
        try:
            if not occ or len(occ) < 10:
                return None
            # Underlying is letters until first digit
            i = 0
            while i < len(occ) and not occ[i].isdigit():
                i += 1
            underlying = occ[:i]
            rest = occ[i:]
            # Expect YYMMDD
            y = int('20' + rest[0:2])
            m = int(rest[2:4])
            d = int(rest[4:6])
            expiry = f"{y:04d}-{m:02d}-{d:02d}"
            cp = rest[6].upper()
            option_type = 'CALL' if cp == 'C' else 'PUT'
            strike_pennies = rest[7:]
            # Strike encoded to 1/1000 dollars
            strike = float(int(strike_pennies) / 1000.0)
            return {
                'underlying': underlying,
                'expiry': expiry,
                'option_type': option_type,
                'strike': strike,
            }
        except Exception:
            return None

    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current stock price with Alpaca primary, Yahoo fallback.

        Args:
            symbol: Stock symbol (e.g., 'SPY')

        Returns:
            Current price or None if unavailable
        """
        # Try Alpaca first (real-time)
        if self.alpaca.enabled:
            price = self.alpaca.get_current_price(symbol)
            if price:
                logger.debug(f"[ALPACA] {symbol}: ${price:.2f}")
                return price
            else:
                logger.warning(
                    f"[ALPACA] Failed to get {symbol} price, trying Yahoo..."
                )

        # Fallback to Yahoo Finance (delayed)
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period="1d")
            if not data.empty:
                price = data["Close"].iloc[-1]
                logger.debug(f"[YAHOO] {symbol}: ${price:.2f} (delayed)")
                return float(price)
        except Exception as e:
            logger.error(f"[YAHOO] Failed to get {symbol} price: {e}")

        return None

    def estimate_option_price(
        self,
        symbol: str,
        strike: float,
        option_type: str,
        expiry: str,
        current_stock_price: float,
    ) -> Optional[float]:
        """
        Estimate option price with Alpaca enhanced estimation.

        Args:
            symbol: Underlying symbol
            strike: Option strike price
            option_type: 'CALL' or 'PUT'
            expiry: Expiration date
            current_stock_price: Current stock price

        Returns:
            Estimated option price
        """
        # Try Alpaca enhanced estimation first
        if self.alpaca.enabled:
            estimate = self.alpaca.get_option_estimate(
                symbol, strike, option_type, expiry, current_stock_price
            )
            if estimate:
                logger.debug(f"[ALPACA] Option estimate: ${estimate:.2f}")
                return estimate

        # Fallback to simple intrinsic + time value
        if option_type.upper() == "CALL":
            intrinsic_value = max(0, current_stock_price - strike)
        else:  # PUT
            intrinsic_value = max(0, strike - current_stock_price)

        # Simple time value for 0DTE
        time_value = 0.05 if expiry == datetime.now().strftime("%Y-%m-%d") else 0.10

        estimate = intrinsic_value + time_value
        estimate = max(0.01, estimate)  # Minimum $0.01

        logger.debug(f"[FALLBACK] Option estimate: ${estimate:.2f}")
        return estimate

    def load_positions(self) -> List[Dict]:
        """Load current positions from the scoped CSV file with robust schema handling."""
        positions: List[Dict] = []

        try:
            with open(self.positions_file, "r", newline="") as file:
                reader = csv.DictReader(file)
                for row in reader:
                    # Skip empty rows
                    if not any(row.values()):
                        continue

                    # Skip rows explicitly marked as closed or with a close_time
                    try:
                        status_str = str(row.get("status", "")).strip().lower()
                        close_time_val = str(row.get("close_time", "")).strip()
                        if status_str and status_str.startswith("closed"):
                            logger.debug(f"[MONITOR] Skipping closed position row: {row}")
                            continue
                        if close_time_val:
                            logger.debug(f"[MONITOR] Skipping row with close_time set: {row}")
                            continue
                    except Exception:
                        # Be permissive if schema missing
                        pass

                    try:
                        original_symbol = str(row.get("symbol", "")).strip()

                        # Determine contracts/quantity
                        qty_raw = row.get("contracts") or row.get("quantity") or "1"
                        try:
                            qty_f = float(str(qty_raw).strip())
                        except Exception:
                            qty_f = 1.0
                        quantity = max(1, int(round(qty_f)))

                        # Determine mapping for fields that may be missing
                        strike_val = row.get("strike")
                        option_type = row.get("option_type") or row.get("side")
                        expiry = row.get("expiry")
                        entry_price_raw = row.get("entry_price") or row.get("entry_premium")

                        # Detect alternate 'timestamp-first' schema and remap
                        # Example row (under header symbol,strike,option_type,expiry,quantity,contracts,entry_price,...):
                        #   2025-09-11T09:44:44.197176,XLF,2025-09-12,53.5,CALL,1,0.22
                        # Mapping should be: underlying=XLF, expiry=2025-09-12, strike=53.5, option_type=CALL, quantity=1, entry_price=0.22
                        is_timestamp_symbol = False
                        try:
                            # datetime.fromisoformat handles microseconds too
                            datetime.fromisoformat(original_symbol)
                            is_timestamp_symbol = True
                        except Exception:
                            is_timestamp_symbol = False
                        if is_timestamp_symbol:
                            # Remap fields from shifted columns
                            underlying = row.get("strike")  # actually underlying in this schema
                            remapped_expiry = row.get("option_type")
                            remapped_strike = row.get("expiry")
                            remapped_option_type = row.get("quantity")
                            remapped_qty = row.get("contracts") or "1"
                            # Apply remapped values
                            strike_val = remapped_strike
                            option_type = remapped_option_type
                            expiry = remapped_expiry
                            try:
                                qty_f = float(str(remapped_qty).strip())
                            except Exception:
                                qty_f = 1.0
                            quantity = max(1, int(round(qty_f)))
                        else:
                            underlying = None

                        # Parse OCC symbol if needed
                        parsed = None
                        if original_symbol and (not strike_val or not expiry or not option_type or len(original_symbol) > 8):
                            # Likely an OCC option symbol (e.g., XLF250912C00053000)
                            parsed = self._parse_occ_option_symbol(original_symbol)
                            if parsed:
                                underlying = parsed["underlying"]
                                if not strike_val:
                                    strike_val = parsed["strike"]
                                if not expiry:
                                    expiry = parsed["expiry"]
                                if not option_type:
                                    option_type = parsed["option_type"]

                        # Convert numeric strike
                        try:
                            strike = float(strike_val) if strike_val not in (None, "") else None
                        except Exception:
                            strike = None

                        # Compute entry_price if missing and we have market_value + unrealized_pnl
                        entry_price = None
                        if entry_price_raw not in (None, ""):
                            try:
                                entry_price = float(entry_price_raw)
                            except Exception:
                                entry_price = None
                        if entry_price is None:
                            mv_raw = row.get("market_value")
                            upl_raw = row.get("unrealized_pnl") or row.get("unrealized_pl") or row.get("unrealized_intraday_pl")
                            try:
                                mv = float(mv_raw) if mv_raw not in (None, "") else None
                                upl = float(upl_raw) if upl_raw not in (None, "") else 0.0
                                if mv is not None and quantity > 0:
                                    entry_value = mv - upl
                                    entry_price = max(0.01, entry_value / (quantity * 100.0))
                            except Exception:
                                entry_price = None

                        # Finalize underlying symbol for monitor price lookups
                        if underlying is None:
                            # If row had separate underlying column use it, else fall back to parsed or original
                            underlying = row.get("underlying") or row.get("base_symbol")
                            if not underlying:
                                # If original was OCC and parsed failed, try best-effort
                                parsed2 = self._parse_occ_option_symbol(original_symbol)
                                if parsed2:
                                    underlying = parsed2["underlying"]
                            if not underlying and original_symbol:
                                # Assume it is already the underlying (e.g., older schema)
                                underlying = original_symbol

                        # Normalize option_type
                        if option_type:
                            option_type = str(option_type).upper()
                            option_type = "CALL" if option_type.startswith("C") else ("PUT" if option_type.startswith("P") else option_type)

                        # Validate required fields
                        if not underlying or not expiry or option_type not in ("CALL", "PUT") or strike is None:
                            logger.warning(f"[MONITOR] Skipping incomplete position: {row}")
                            continue

                        # Only set occ_symbol when original symbol parses as OCC; otherwise leave blank
                        occ_symbol = original_symbol if parsed else ""

                        normalized = {
                            "symbol": underlying,
                            "occ_symbol": occ_symbol,
                            "strike": strike,
                            "option_type": option_type,
                            "expiry": expiry,
                            "quantity": quantity,
                            "entry_price": entry_price if entry_price is not None else 0.01,
                        }

                        positions.append(normalized)
                        logger.debug(f"[MONITOR] Loaded position: {normalized['symbol']} ${normalized['strike']} {normalized['option_type']} x{normalized['quantity']}")

                    except (ValueError, TypeError) as e:
                        logger.warning(f"[MONITOR] Skipping invalid position row: {row} - Error: {e}")
                        continue

            logger.info(f"[MONITOR] Loaded {len(positions)} positions")
            return positions

        except FileNotFoundError:
            logger.warning(f"[MONITOR] Positions file not found: {self.positions_file}")
            return []
        except Exception as e:
            logger.error(f"[MONITOR] Error loading positions: {e}")
            return []

    def check_position_alerts(
        self, position: Dict, current_price: float, estimated_option_price: float
    ) -> None:
        """
        Check and send alerts for profit targets and stop losses.

        Args:
            position: Position data
            current_price: Current stock price
            estimated_option_price: Current estimated option price
        """
        symbol = position["symbol"]
        strike = position["strike"]
        option_type = position["option_type"]
        entry_price = position["entry_price"]
        quantity = position["quantity"]

        # Calculate P&L
        current_value = (
            estimated_option_price * quantity * 100
        )  # Options are per 100 shares
        entry_value = entry_price * quantity * 100
        pnl = current_value - entry_value
        pnl_pct = (pnl / entry_value) * 100

        position_key = f"{symbol}_{strike}_{option_type}"
        current_time = datetime.now()

        # Check if we should send alerts (cooldown logic)
        last_alert_time = self.last_alerts.get(position_key, {}).get(
            "time", datetime.min
        )
        time_since_last = (current_time - last_alert_time).total_seconds()

        if time_since_last < self.alert_cooldown:
            return  # Still in cooldown

        # === ADVANCED EXIT STRATEGIES EVALUATION ===
        # Use ExitStrategyManager for sophisticated exit decisions
        exit_decision = self.exit_manager.evaluate_exit(
            position, current_price, estimated_option_price
        )

        # Handle exit decision based on strategy type
        if exit_decision.should_exit or exit_decision.reason != ExitReason.NO_EXIT:
            self.handle_exit_decision(
                position,
                current_price,
                estimated_option_price,
                pnl,
                pnl_pct,
                exit_decision,
            )

            # Update alert tracking
            self.last_alerts[position_key] = {
                "time": current_time,
                "type": exit_decision.reason.value,
                "urgency": exit_decision.urgency,
            }

        # === LEGACY FALLBACK (for compatibility) ===
        # Keep legacy profit level alerts as backup
        else:
            self.check_legacy_alerts(
                position,
                current_price,
                estimated_option_price,
                pnl,
                pnl_pct,
                position_key,
                current_time,
            )

    def handle_exit_decision(
        self,
        position: Dict,
        current_price: float,
        option_price: float,
        pnl: float,
        pnl_pct: float,
        exit_decision,
    ) -> None:
        """Handle advanced exit strategy decisions with appropriate alerts."""
        symbol = position["symbol"]
        strike = position["strike"]
        option_type = position["option_type"]

        # Create detailed message based on exit reason
        if exit_decision.reason == ExitReason.TRAILING_STOP:
            message = f"""
🔥 [TRAILING STOP] TRIGGERED!

Position: {symbol} ${strike} {option_type}
Entry Price: ${position['entry_price']:.2f}
Current Price: ${option_price:.2f}
Stock Price: ${current_price:.2f}

P&L: ${pnl:+.2f} ({pnl_pct:+.1f}%)

{exit_decision.message}

Data Source: {'Alpaca (Real-time)' if self.alpaca.enabled else 'Yahoo (Delayed)'}
Time: {datetime.now().strftime('%H:%M:%S ET')}

⚡ RECOMMEND IMMEDIATE EXIT ⚡
            """.strip()

            if self.slack.enabled:
                self.slack.send_stop_loss_alert(
                    symbol, strike, option_type, abs(pnl_pct)
                )
            
            # Launch interactive exit confirmation workflow for trailing stop
            self._launch_interactive_exit(position, exit_decision, current_price, option_price)

        elif exit_decision.reason == ExitReason.TIME_BASED:
            message = f"""
⏰ [TIME-BASED EXIT] Market Close Warning!

Position: {symbol} ${strike} {option_type}
Entry Price: ${position['entry_price']:.2f}
Current Price: ${option_price:.2f}
Stock Price: ${current_price:.2f}

P&L: ${pnl:+.2f} ({pnl_pct:+.1f}%)

{exit_decision.message}

Data Source: {'Alpaca (Real-time)' if self.alpaca.enabled else 'Yahoo (Delayed)'}
Time: {datetime.now().strftime('%H:%M:%S ET')}

🚨 CLOSE BEFORE MARKET CLOSE 🚨
            """.strip()

            if self.slack.enabled:
                self.slack.send_position_alert_with_chart(
                    position, current_price, pnl_pct, "time_based_exit", exit_decision
                )
            
            # Launch interactive exit confirmation workflow for time-based exit
            self._launch_interactive_exit(position, exit_decision, current_price, option_price)

        elif exit_decision.reason == ExitReason.STOP_LOSS:
            message = f"""
🛑 [STOP LOSS] TRIGGERED!

Position: {symbol} ${strike} {option_type}
Entry Price: ${position['entry_price']:.2f}
Current Price: ${option_price:.2f}
Stock Price: ${current_price:.2f}

P&L: ${pnl:+.2f} ({pnl_pct:+.1f}%)

{exit_decision.message}

Data Source: {'Alpaca (Real-time)' if self.alpaca.enabled else 'Yahoo (Delayed)'}
Time: {datetime.now().strftime('%H:%M:%S ET')}

⚠️ CONSIDER CLOSING POSITION ⚠️
            """.strip()

            if self.slack.enabled:
                self.slack.send_stop_loss_alert(
                    symbol, strike, option_type, abs(pnl_pct)
                )
            
            # Launch interactive exit confirmation workflow for stop loss
            self._launch_interactive_exit(position, exit_decision, current_price, option_price)

        elif exit_decision.reason == ExitReason.PROFIT_TARGET:
            # Extract profit level from message or use current P&L
            profit_level = int(pnl_pct) if pnl_pct > 0 else 15

            message = f"""
💰 [PROFIT TARGET] Reached!

Position: {symbol} ${strike} {option_type}
Entry Price: ${position['entry_price']:.2f}
Current Price: ${option_price:.2f}
Stock Price: ${current_price:.2f}

P&L: ${pnl:+.2f} ({pnl_pct:+.1f}%)

{exit_decision.message}

Data Source: {'Alpaca (Real-time)' if self.alpaca.enabled else 'Yahoo (Delayed)'}
Time: {datetime.now().strftime('%H:%M:%S ET')}

✨ Consider taking profits! ✨
            """.strip()

            if self.slack.enabled:
                self.slack.send_position_alert_with_chart(
                    position, current_price, pnl_pct, "profit_target", exit_decision
                )
            
            # Launch interactive exit confirmation workflow
            self._launch_interactive_exit(position, exit_decision, current_price, option_price)

        # If LLM exit just executed and status is closed, skip advisory output
        if str(position.get("status", "")).lower().startswith("closed"):
            logger.debug(f"[MONITOR] Skipping advisory for {symbol} ${strike} {option_type} - position closed this cycle")
            return

        # Log and print the alert
        logger.info(
            f"[EXIT-STRATEGY] {exit_decision.reason.value.upper()} for {symbol} ${strike} {option_type}"
        )
        print(message)

    def check_legacy_alerts(
        self,
        position: Dict,
        current_price: float,
        estimated_option_price: float,
        pnl: float,
        pnl_pct: float,
        position_key: str,
        current_time: datetime,
    ) -> None:
        """Legacy fallback alert handler (no-op by default).

        This preserves backward compatibility with prior simple threshold alerts
        without interrupting the monitoring loop. Advanced exit strategies should
        handle all actionable alerts; this method exists to avoid AttributeError
        and can be expanded if needed.
        """
        try:
            logger.debug(
                f"[MONITOR-LEGACY] No advanced exit triggered for {position_key} (P&L {pnl_pct:+.1f}%) — legacy fallback is a no-op"
            )
        except Exception:
            # Do not allow legacy path to break monitoring
            pass

    def _launch_interactive_exit(
        self,
        position: Dict,
        exit_decision,
        current_stock_price: float,
        current_option_price: float,
    ) -> None:
        """Launch interactive exit confirmation workflow or LLM decision if unattended."""
        # Check if unattended mode is enabled
        try:
            config = getattr(self, "config", None)
            if config is None:
                from utils.llm import load_config
                config = load_config("config.yaml")
            unattended = config.get("UNATTENDED", False)
            llm_decisions = config.get("LLM_DECISIONS", [])

            # Auto-sell on objective exit triggers when unattended (default OFF)
            auto_sell = (
                config.get("AUTO_SELL_ON_EXIT_TRIGGERS", False)
                or config.get("AUTO_SELL_ON_PROFIT_TARGET", False)
            )
            objective_reasons = {ExitReason.PROFIT_TARGET, ExitReason.STOP_LOSS, ExitReason.TRAILING_STOP, ExitReason.TIME_BASED}
            if unattended and auto_sell and exit_decision.reason in objective_reasons:
                logger.info("[EXIT] Auto-sell enabled and objective trigger fired - executing sell without LLM")
                self._execute_sell_order(position, current_stock_price, current_option_price, reason=str(exit_decision.reason.value))
                return

            if unattended and "exit" in llm_decisions:
                self._handle_llm_exit_decision(position, exit_decision, current_stock_price, current_option_price)
                return
        except Exception as e:
            logger.warning(f"[EXIT] Could not check unattended mode, falling back to interactive: {e}")
        
        try:
            # Import Windows-safe exit confirmation workflow
            from utils.exit_confirmation_safe import SafeExitConfirmationWorkflow
            exit_workflow = SafeExitConfirmationWorkflow()
        except ImportError as e:
            logger.error(f"[EXIT-CONFIRM] Failed to import exit confirmation workflow: {e}")
            exit_workflow = None

        if exit_workflow is not None:
            try:
                # Present interactive confirmation prompt
                result = exit_workflow.confirm_exit(
                    position, exit_decision, current_stock_price, current_option_price
                )
                
                # Handle user decision
                if result.confirmed:
                    logger.info(f"[EXIT-CONFIRM] User confirmed exit: {result.action} @ ${result.premium:.2f}")
                    
                    symbol = position["symbol"]
                    strike = position["strike"]
                    option_type = position["option_type"]
                    quantity = position["quantity"]
                    
                    print(f"\n[EXIT CONFIRMED!]")
                    print(f"Position: {symbol} ${strike} {option_type}")
                    print(f"Action: SELL {quantity} contract{'s' if quantity != 1 else ''}")
                    print(f"Price: ${result.premium:.2f}")
                    print(f"Total Value: ${result.premium * quantity * 100:.2f}")
                    print("\n[MANUAL ACTION REQUIRED:]")
                    print("   Log into your broker and execute this sell order manually")
                    print("\n[PROCESSING EXIT...]")
                    
                    # Process confirmed exit (remove position, log trade)
                    success = exit_workflow.process_confirmed_exit(position, result, exit_decision)
                    
                    if success:
                        print("[OK] Position removed from tracking")
                        print("[OK] Trade logged to history")
                        print("[OK] Monitoring will stop for this position")
                        logger.info(f"[EXIT-CONFIRM] Exit processing completed successfully")
                    else:
                        print("[WARNING] Some exit processing steps failed - check logs")
                        logger.warning(f"[EXIT-CONFIRM] Exit processing had errors")
                    
                else:
                    logger.info("[EXIT-CONFIRM] User cancelled exit - position remains open")
                    print("\n[CANCEL] Exit cancelled - position monitoring continues")
                    
            except Exception as e:
                logger.error(f"[EXIT-CONFIRM] Error in interactive exit workflow: {e}")
                print(f"\n[ERROR] Error in exit confirmation: {e}")
                print("Please exit manually through your broker if desired")
        else:
            logger.error("[EXIT-CONFIRM] No exit confirmation workflow available")
            print("\n[ERROR] Exit confirmation not available - please exit manually")

    def _handle_llm_exit_decision(
        self,
        position: Dict,
        exit_decision,
        current_stock_price: float,
        current_option_price: float,
    ) -> None:
        """Handle exit decision using LLM in unattended mode."""
        try:
            from utils.llm import load_config
            from utils.llm_decider import LLMDecider
            from utils.llm_json_client import LLMJsonClient
            from utils.ensemble_llm import EnsembleLLM
            from datetime import datetime
            from zoneinfo import ZoneInfo
            
            cfg = getattr(self, "config", None)
            if cfg is None:
                cfg = load_config("config.yaml")
            
            # Initialize LLM components
            ensemble_llm = EnsembleLLM()
            json_client = LLMJsonClient(ensemble_llm, logger)
            llm_decider = LLMDecider(json_client, cfg, logger, slack_notifier=self.slack)
            
            # Build context for LLM decision
            symbol = position.get("symbol", "UNKNOWN")
            # Compute P&L % using current option price vs entry price
            try:
                entry_price = float(position.get("entry_price", 0) or 0)
                qty = int(position.get("quantity", 1) or 1)
                if entry_price > 0:
                    pnl_pct = ((current_option_price - entry_price) / entry_price) * 100.0
                else:
                    pnl_pct = 0.0
            except Exception:
                pnl_pct = 0.0
            
            # Get market time info
            et_tz = ZoneInfo("America/New_York")
            now = datetime.now(et_tz)
            market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
            minutes_to_close = max(0, int((market_close - now).total_seconds() / 60))
            
            # Build comprehensive context
            ctx = {
                "symbol": symbol,
                "timestamp": now.isoformat(),
                "time_to_close_min": minutes_to_close,
                "hard_rails": {
                    "force_close_now": now.hour >= 15 and now.minute >= 45,
                    "kill_switch": False,  # Would be checked by circuit breaker
                    "circuit_breaker": False,  # Would be checked by circuit breaker
                },
                "pnl": {
                    "pct": pnl_pct,
                    "velocity_pct_4m": 0,  # Could be enhanced with historical tracking
                },
                "price": {
                    "last": current_stock_price,
                    "vwap_rel": 0,  # Could be enhanced with VWAP calculation
                    "spread_bps": 0,  # Could be enhanced with option spread data
                    "iv": 0,  # Could be enhanced with IV data
                },
                "trend": {
                    "ha_trend": "unknown",  # Could be enhanced with HA data
                    "rsi2": 50,  # Could be enhanced with RSI calculation
                    "vix": 20,  # Could be enhanced with VIX data
                },
                "policy": {
                    "profit_target_pct": 15.0,
                    "min_profit_consider_pct": 5.0,
                    "stop_loss_pct": -25.0
                },
                "memory": []  # Could be enhanced with trade history
            }
            
            # Get LLM decision
            decision = llm_decider.decide_exit(symbol, ctx)
            
            # Log the decision with audit trail
            audit_msg = (
                f"[EXIT-LLM] {symbol} {decision.action} ({decision.confidence:.2f}) – {decision.reason}\n"
                f"Inputs: pnl={pnl_pct:.1f}%, ttc={minutes_to_close}min, price=${current_stock_price:.2f}"
            )
            logger.info(audit_msg)
            
            # Send Slack notification
            slack_msg = f"""🤖 **LLM Exit Decision: {symbol}**
**Action:** {decision.action}
**Confidence:** {decision.confidence:.2f}
**Reason:** {decision.reason}
**Current P&L:** {pnl_pct:.1f}%
**Stock Price:** ${current_stock_price:.2f}
**Time to Close:** {minutes_to_close} minutes"""
            
            self.slack.send_message(slack_msg)
            
            # Execute the decision
            if decision.action == "SELL":
                print(f"\n🤖 [LLM-EXIT] Executing SELL decision for {symbol}")
                print(f"Reason: {decision.reason}")
                print(f"Confidence: {decision.confidence:.2f}")
                
                # Execute the sell order automatically
                try:
                    from utils.alpaca_options import create_alpaca_trader
                    # Determine paper/live from config/environment
                    broker_cfg = cfg.get("BROKER", os.getenv("BROKER", "robinhood"))
                    env_cfg = cfg.get("ALPACA_ENV", os.getenv("ALPACA_ENV", "paper" if broker_cfg == "alpaca" else "live"))
                    paper_mode = broker_cfg == "alpaca" and env_cfg == "paper"
                    trader = create_alpaca_trader(paper=paper_mode)
                    if trader is None:
                        logger.error(f"[AUTO-EXIT] Could not initialize Alpaca trader (paper={paper_mode})")
                        self.slack.send_message(f"❌ **Auto-Exit Error: {symbol}**\n**Error:** Alpaca trader initialization failed\n**Manual intervention required**")
                        return
                    
                    # Build/Get OCC contract symbol
                    contract_symbol = position.get("occ_symbol")
                    if not contract_symbol:
                        try:
                            from datetime import datetime as _dt
                            expiry_dt = _dt.strptime(position.get("expiry", ""), "%Y-%m-%d")
                            expiry_str = expiry_dt.strftime("%y%m%d")
                            strike_str = f"{int(float(position.get('strike', 0)) * 1000):08d}"
                            cp = (position.get("option_type", "C") or "C")[0].upper()
                            underlying = position.get("symbol", symbol)
                            contract_symbol = f"{underlying}{expiry_str}{cp}{strike_str}"
                        except Exception:
                            # Fallback to original symbol field if build fails
                            contract_symbol = position.get("symbol", symbol)
                    
                    # Quantity
                    quantity = int(position.get("quantity") or position.get("qty") or 1)
                    
                    logger.info(f"[LLM-EXIT] Placing SELL order: {contract_symbol} x{quantity} (paper={paper_mode})")
                    
                    # Place market sell order
                    order_id = trader.place_market_order(contract_symbol, quantity, "SELL")
                    
                    if order_id:
                        logger.info(f"[LLM-EXIT] Order placed successfully: {order_id}")
                        
                        # Poll for fill
                        fill_result = trader.poll_fill(order_id=order_id, timeout_s=90)
                        
                        if fill_result.status == "FILLED":
                            logger.info(f"[LLM-EXIT] Order filled: {fill_result.filled_qty} contracts at ${fill_result.avg_price:.2f}")
                            
                            # Send success notification
                            success_msg = f"""✅ **Automated Exit Executed: {symbol}**
**Order ID:** {order_id}
**Quantity:** {fill_result.filled_qty} contracts
**Fill Price:** ${fill_result.avg_price:.2f}
**P&L:** {((fill_result.avg_price - position.get('entry_price', 0)) / max(position.get('entry_price', 1), 1)) * 100:+.1f}%
**LLM Reason:** {decision.reason}
**Confidence:** {decision.confidence:.2f}"""
                            
                            self.slack.send_message(success_msg)
                            
                            # Mark closed in-memory to avoid duplicate advisories this cycle
                            try:
                                position["status"] = "closed_llm"
                                position["close_time"] = datetime.now().isoformat()
                            except Exception:
                                pass
                            
                            # Refresh local positions from Alpaca after exit
                            try:
                                from utils.alpaca_sync import AlpacaSync
                                sync = AlpacaSync(env=env_cfg if broker_cfg == "alpaca" else "live")
                                sync.sync_positions()
                            except Exception as _sync_e:
                                logger.warning(f"[LLM-EXIT] Post-exit sync failed: {_sync_e}")
                            
                        else:
                            logger.warning(f"[LLM-EXIT] Order not filled: {fill_result.status}")
                            
                            # Send warning notification
                            warning_msg = f"""⚠️ **Exit Order Not Filled: {symbol}**
**Order ID:** {order_id}
**Status:** {fill_result.status}
**Manual intervention may be required**"""
                            
                            self.slack.send_message(warning_msg)
                    else:
                        logger.error(f"[LLM-EXIT] Failed to place sell order for {symbol}")
                        
                        # Send error notification
                        error_msg = f"""❌ **Exit Order Failed: {symbol}**
**Error:** Order placement failed
**Manual intervention required**"""
                        
                        self.slack.send_message(error_msg)
                except Exception as order_error:
                    logger.error(f"[LLM-EXIT] Error executing sell order: {order_error}")
                    
                    # Send error notification
                    error_msg = f"""❌ **Exit Execution Error: {symbol}**
**Error:** {str(order_error)}
**Manual intervention required**"""
                    
                    self.slack.send_message(error_msg)
                
                
            elif decision.action in ["HOLD", "WAIT"]:
                defer_min = decision.defer_minutes or 2
                print(f"\n🤖 [LLM-EXIT] {decision.action} decision for {symbol}")
                print(f"Reason: {decision.reason}")
                print(f"Next check in {defer_min} minutes")
                
            elif decision.action == "ABSTAIN":
                print(f"\n🤖 [LLM-EXIT] ABSTAIN decision for {symbol}")
                print(f"Reason: {decision.reason}")
                print("Manual intervention may be required")
                
        except Exception as e:
            logger.error(f"[EXIT-LLM] Error in LLM exit decision: {e}")
            print(f"\n[ERROR] LLM exit decision failed: {e}")
            print("Falling back to manual exit confirmation")
            
            # Fallback to interactive mode
            try:
                from utils.exit_confirmation_safe import SafeExitConfirmationWorkflow
                exit_workflow = SafeExitConfirmationWorkflow()
                result = exit_workflow.confirm_exit(
                    position, exit_decision, current_stock_price, current_option_price
                )
            except Exception as fallback_error:
                logger.error(f"[EXIT-LLM] Fallback also failed: {fallback_error}")

    def _execute_sell_order(self, position: Dict, current_stock_price: float, current_option_price: float, reason: str = "Objective Exit", confidence: float = 1.0) -> None:
        """Directly execute a market SELL order via Alpaca (unattended objective exit)."""
        symbol = position.get("symbol", "UNKNOWN")
        try:
            from utils.alpaca_options import create_alpaca_trader
            cfg = getattr(self, "config", None)
            if cfg is None:
                from utils.llm import load_config
                cfg = load_config("config.yaml")

            broker_cfg = cfg.get("BROKER", os.getenv("BROKER", "alpaca"))
            env_cfg = cfg.get("ALPACA_ENV", os.getenv("ALPACA_ENV", "paper" if broker_cfg == "alpaca" else "live"))
            paper_mode = broker_cfg == "alpaca" and env_cfg == "paper"
            trader = create_alpaca_trader(paper=paper_mode)

            # Determine OCC symbol
            contract_symbol = position.get("occ_symbol")
            if not contract_symbol:
                try:
                    from datetime import datetime as _dt
                    expiry_dt = _dt.strptime(position.get("expiry", ""), "%Y-%m-%d")
                    expiry_str = expiry_dt.strftime("%y%m%d")
                    strike_str = f"{int(float(position.get('strike', 0)) * 1000):08d}"
                    cp = (position.get("option_type", "C") or "C")[0].upper()
                    underlying = position.get("symbol", symbol)
                    contract_symbol = f"{underlying}{expiry_str}{cp}{strike_str}"
                except Exception:
                    contract_symbol = position.get("symbol", symbol)

            quantity = int(position.get("quantity") or position.get("qty") or 1)

            logger.info(f"[AUTO-EXIT] Placing SELL order: {contract_symbol} x{quantity} (paper={paper_mode})")
            order_id = trader.place_market_order(contract_symbol, quantity, "SELL")

            if order_id:
                fill_result = trader.poll_fill(order_id=order_id, timeout_s=90)
                if fill_result.status == "FILLED":
                    logger.info(f"[AUTO-EXIT] Order filled: {fill_result.filled_qty} @ ${fill_result.avg_price:.2f}")
                    success_msg = f"""✅ **Automated Exit Executed: {symbol}**
**Order ID:** {order_id}
**Quantity:** {fill_result.filled_qty} contracts
**Fill Price:** ${fill_result.avg_price:.2f}
**P&L:** {((fill_result.avg_price - position.get('entry_price', 0)) / max(position.get('entry_price', 1), 1)) * 100:+.1f}%
**Reason:** {reason}
**Confidence:** {confidence:.2f}"""
                    self.slack.send_message(success_msg)
                    # Mark closed in-memory to avoid duplicate advisories this cycle
                    try:
                        position["status"] = "closed_auto"
                        position["close_time"] = datetime.now().isoformat()
                    except Exception:
                        pass
                    # Refresh local positions after confirmed fill
                    try:
                        from utils.alpaca_sync import AlpacaSync
                        sync = AlpacaSync(env=env_cfg if broker_cfg == "alpaca" else "live")
                        sync.sync_positions()
                    except Exception as _sync_e:
                        logger.warning(f"[AUTO-EXIT] Post-exit sync failed: {_sync_e}")
                else:
                    warning_msg = f"""⚠️ **Exit Order Not Filled: {symbol}**
**Order ID:** {order_id}
**Status:** {fill_result.status}
**Manual intervention may be required**"""
                    logger.warning(f"[AUTO-EXIT] Order not filled: {fill_result.status}")
                    self.slack.send_message(warning_msg)
            else:
                logger.error(f"[AUTO-EXIT] Failed to place sell order for {symbol}")
                self.slack.send_message(f"❌ **Exit Order Failed: {symbol}**\n**Error:** Order placement failed\n**Manual intervention required**")

            # Recording of exit outcome is handled by Alpaca sync; no local ledger writes here
        except Exception as e:
            logger.error(f"[AUTO-EXIT] Error executing auto-sell for {symbol}: {e}")
            self.slack.send_message(f"❌ **Auto-Exit Error: {symbol}**\n**Error:** {str(e)}\n**Manual intervention required**")

    def _legacy_alert_system(
        self,
        position: Dict,
        current_price: float,
        pnl_pct: float,
        position_key: str,
        current_time: datetime,
    ) -> None:
        """Legacy alert system for backward compatibility."""
        # Check profit levels
        for profit_level in self.profit_levels:
            if pnl_pct >= profit_level:
                last_profit_alert = self.last_alerts.get(position_key, {}).get(
                    "profit_level", 0
                )

                if profit_level > last_profit_alert:
                    # New profit level reached!
                    # Use enhanced Slack alert with chart
                    if self.slack.enabled:
                        self.slack.send_position_alert_with_chart(
                            position, current_price, pnl_pct, "profit_target"
                        )

                    # Update alert tracking
                    self.last_alerts[position_key] = {
                        "time": current_time,
                        "profit_level": profit_level,
                        "type": "profit",
                    }
                    break

        # Check stop loss
        if pnl_pct <= -self.stop_loss_threshold:
            last_alert_type = self.last_alerts.get(position_key, {}).get("type", "")

            if last_alert_type != "stop_loss":
                # Use enhanced Slack alert with chart
                if self.slack.enabled:
                    self.slack.send_position_alert_with_chart(
                        position, current_price, pnl_pct, "stop_loss"
                    )

                # Update alert tracking
                self.last_alerts[position_key] = {
                    "time": current_time,
                    "type": "stop_loss",
                }

    def send_profit_alert(
        self,
        position: Dict,
        current_price: float,
        option_price: float,
        pnl: float,
        pnl_pct: float,
        profit_level: int,
    ) -> None:
        """Send profit target alert."""
        symbol = position["symbol"]
        strike = position["strike"]
        option_type = position["option_type"]

        message = f"""
[PROFIT] TARGET HIT! (+{profit_level}%)

Position: {symbol} ${strike} {option_type}
Entry Price: ${position['entry_price']:.2f}
Current Price: ${option_price:.2f}
Stock Price: ${current_price:.2f}

P&L: ${pnl:+.2f} ({pnl_pct:+.1f}%)

Data Source: {'Alpaca (Real-time)' if self.alpaca.enabled else 'Yahoo (Delayed)'}
Time: {datetime.now().strftime('%H:%M:%S ET')}

Consider taking profits!
        """.strip()

        if self.slack.enabled:
            self.slack.send_profit_alert(
                symbol, strike, option_type, pnl_pct, profit_level
            )

        logger.info(
            f"[ALERT] Profit target {profit_level}% hit for {symbol} ${strike} {option_type}"
        )
        print(message)

    def send_heartbeat(self, message: str) -> None:
        """Send heartbeat message to confirm system is alive."""
        if self.slack.enabled:
            self.slack.send_heartbeat(message)
        logger.info(f"[HEARTBEAT] {message}")

    def send_stop_loss_alert(
        self,
        position: Dict,
        current_price: float,
        option_price: float,
        pnl: float,
        pnl_pct: float,
    ) -> None:
        """Send stop loss alert."""
        symbol = position["symbol"]
        strike = position["strike"]
        option_type = position["option_type"]

        message = f"""
[STOP LOSS] TRIGGERED! (-{abs(pnl_pct):.1f}%)

Position: {symbol} ${strike} {option_type}
Entry Price: ${position['entry_price']:.2f}
Current Price: ${option_price:.2f}
Stock Price: ${current_price:.2f}

P&L: ${pnl:+.2f} ({pnl_pct:+.1f}%)

Data Source: {'Alpaca (Real-time)' if self.alpaca.enabled else 'Yahoo (Delayed)'}
Time: {datetime.now().strftime('%H:%M:%S ET')}

CONSIDER CLOSING POSITION!
        """.strip()

        if self.slack.enabled:
            self.slack.send_stop_loss_alert(symbol, strike, option_type, abs(pnl_pct))

        logger.warning(
            f"[ALERT] Stop loss triggered for {symbol} ${strike} {option_type}"
        )
        print(message)

    def check_end_of_day_warning(self) -> None:
        """Send end-of-day warning to close positions."""
        now = datetime.now()
        end_time = datetime.strptime(self.end_of_day_time, "%H:%M").replace(
            year=now.year, month=now.month, day=now.day
        )

        time_to_close = (end_time - now).total_seconds() / 60  # Minutes

        if 0 <= time_to_close <= self.market_close_warning:
            # Send warning if not already sent today
            warning_key = f"eod_warning_{now.date()}"
            if warning_key not in self.last_alerts:

                message = f"""
[EOD] END OF DAY WARNING!

Market closes in {int(time_to_close)} minutes.
Consider closing all positions by {self.end_of_day_time} ET.

Avoid overnight risk!
                """.strip()

                if self.slack.enabled:
                    self.slack.send_end_of_day_warning(int(time_to_close))

                self.last_alerts[warning_key] = {"time": now}
                logger.info("[ALERT] End-of-day warning sent")
                print(message)

    def run_monitoring_cycle(self) -> None:
        """Run one complete monitoring cycle for all positions."""
        # Check for file-based circuit breaker reset at start of each cycle
        try:
            reset_executed, reset_message = check_and_process_file_reset(self.config)
            if reset_executed:
                logger.info(f"[MONITOR] Circuit breaker reset processed: {reset_message}")
                if self.slack.enabled:
                    self.slack.basic_notifier.send_message(f"🔄 **MONITOR UPDATE**: {reset_message}")
        except Exception as e:
            logger.error(f"[MONITOR] Error checking circuit breaker reset: {e}")

        positions = self.load_positions()
        
        # Increment heartbeat counter
        self.heartbeat_counter += 1

        if not positions:
            logger.debug("[MONITOR] No positions to monitor")
            if self.heartbeat_counter % self.heartbeat_interval == 0:
                self.send_heartbeat("📊 Position monitor active - no positions to track")
            return

        logger.info(f"[MONITOR] Monitoring {len(positions)} positions")
        # Send heartbeat every N cycles
        if self.heartbeat_counter % self.heartbeat_interval == 0:
            position_summary = []
            for pos in positions:
                position_summary.append(f"{pos['symbol']} ${pos['strike']} {pos['option_type']}")
            
            heartbeat_msg = f"💰 Position monitor active - tracking {len(positions)} position(s): {', '.join(position_summary)}"
            self.send_heartbeat(heartbeat_msg)

        for position in positions:
            try:
                symbol = position["symbol"]
                strike = position["strike"]
                option_type = position["option_type"]
                expiry = position["expiry"]

                # Get current stock price (real-time with Alpaca)
                current_price = self.get_current_price(symbol)
                if not current_price:
                    logger.error(f"[MONITOR] Could not get price for {symbol}")
                    continue

                # Estimate current option price
                estimated_option_price = self.estimate_option_price(
                    symbol, strike, option_type, expiry, current_price
                )

                if not estimated_option_price:
                    logger.error(
                        f"[MONITOR] Could not estimate option price for {symbol}"
                    )
                    continue

                # Check for alerts
                self.check_position_alerts(
                    position, current_price, estimated_option_price
                )

                # Log current status
                entry_price = position["entry_price"]
                pnl_pct = ((estimated_option_price - entry_price) / entry_price) * 100

                logger.info(
                    f"[MONITOR] {symbol} ${strike} {option_type}: "
                    f"${estimated_option_price:.2f} ({pnl_pct:+.1f}%)"
                )

            except Exception as e:
                logger.error(f"[MONITOR] Error checking position {position}: {e}")

        # Check end-of-day warning
        self.check_end_of_day_warning()

    def run(self, interval_minutes: int = 1) -> None:
        """
        Run continuous position monitoring.

        Args:
            interval_minutes: Minutes between monitoring cycles
        """
        logger.info(
            f"[MONITOR] Starting enhanced monitoring (interval: {interval_minutes}min)"
        )
        logger.info(
            f"[MONITOR] Data source: {'Alpaca (Real-time)' if self.alpaca.enabled else 'Yahoo (Delayed)'}"
        )

        try:
            while True:
                self.run_monitoring_cycle()

                # Sleep until next cycle
                time.sleep(interval_minutes * 60)

        except KeyboardInterrupt:
            logger.info("[MONITOR] Monitoring stopped by user")
        except Exception as e:
            logger.error(f"[MONITOR] Monitoring error: {e}")


def main():
    """Main entry point with configurable monitoring interval."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Enhanced Position Monitoring with Alpaca"
    )
    parser.add_argument(
        "--interval",
        "-i",
        type=int,
        default=15,
        help="Monitoring interval in seconds (default: 15s for active trading)",
    )
    parser.add_argument(
        "--slack-notify", action="store_true", help="Enable Slack notifications"
    )

    args = parser.parse_args()

    print("=== ENHANCED POSITION MONITORING WITH ALPACA ===")
    print()

    monitor = EnhancedPositionMonitor()

    # Show data source status
    if monitor.alpaca.enabled:
        print("[OK] Using Alpaca real-time data")
        account_info = monitor.alpaca.get_account_info()
        if account_info:
            print(f"[OK] Paper trading account: {account_info['account_number']}")
    else:
        print("[INFO] Using Yahoo Finance (delayed data)")

    print(f"[OK] Slack alerts: {'Enabled' if monitor.slack.enabled else 'Disabled'}")
    print(f"[OK] Monitoring interval: {args.interval} seconds")
    print()

    # Convert seconds to minutes for the run method
    interval_minutes = args.interval / 60.0

    # Start monitoring
    monitor.run(interval_minutes=interval_minutes)


if __name__ == "__main__":
    main()
