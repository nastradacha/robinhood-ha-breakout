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
from datetime import datetime
from typing import Dict, List, Optional
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.alpaca_client import AlpacaClient
from utils.enhanced_slack import EnhancedSlackIntegration
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
        """Load current positions from the scoped CSV file."""
        positions = []

        try:
            with open(self.positions_file, "r", newline="") as file:
                reader = csv.DictReader(file)
                for row in reader:
                    # Skip empty rows
                    if not any(row.values()):
                        continue
                        
                    # Convert numeric fields and map CSV columns to expected fields
                    try:
                        row["quantity"] = int(row.get("contracts", 1))  # Map contracts -> quantity with default
                        row["entry_price"] = float(row.get("entry_premium", 0))  # Map entry_premium -> entry_price
                        row["strike"] = float(row.get("strike", 0))
                        row["option_type"] = row.get("side", "CALL")  # Map side -> option_type
                        
                        # Ensure required fields exist
                        if not row.get("symbol") or not row.get("expiry"):
                            logger.warning(f"[MONITOR] Skipping incomplete position: {row}")
                            continue
                            
                        positions.append(row)
                        logger.debug(f"[MONITOR] Loaded position: {row['symbol']} ${row['strike']} {row['option_type']}")
                        
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

        # Log and print the alert
        logger.info(
            f"[EXIT-STRATEGY] {exit_decision.reason.value.upper()} for {symbol} ${strike} {option_type}"
        )
        print(message)

    def _launch_interactive_exit(
        self,
        position: Dict,
        exit_decision,
        current_stock_price: float,
        current_option_price: float,
    ) -> None:
        """Launch interactive exit confirmation workflow."""
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
            logger.warning("[EXIT-CONFIRM] Exit workflow not available - please exit manually")

    def check_legacy_alerts(
        self,
        position: Dict,
        current_price: float,
        option_price: float,
        pnl: float,
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
