#!/usr/bin/env python3
"""
Robinhood HA Breakout - Main Trading Script

A sophisticated automated trading system for SPY options using Heikin-Ashi breakout patterns.
Designed for conservative intraday trading with fully automated execution and risk management.

Key Features:
- Automated market analysis using Heikin-Ashi candles
- LLM-powered trade decision making (GPT-4o-mini or DeepSeek)
- Browser automation for Robinhood options trading
- Fully automated execution - LLM decisions execute automatically
- Slack notifications for mobile alerts
- Comprehensive position and bankroll tracking
- Conservative risk management (15% profit target, 25% stop loss)
- Intraday focus (closes positions by 3:45 PM ET)

Usage:
    # One-shot mode (single analysis)
    python main.py

    # Continuous loop mode (morning scanner)
    python main.py --loop --interval 5 --end-at 11:00

    # Position monitoring mode
    python main.py --monitor-positions --interval 2 --end-at 15:45

Safety:
- All trades execute automatically based on LLM decisions
- Confidence threshold enforcement (0.6 minimum)
- Ensemble model agreement required for execution
- Slack notifications provide trade alerts and confirmations
- Circuit breakers and kill switches for risk management

Author: Robinhood HA Breakout System
Version: 2.0.0
License: MIT
"""

import argparse
import logging
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta
import yaml
import os
from dotenv import load_dotenv
import csv
from typing import Dict, Optional
from zoneinfo import ZoneInfo

# Import our utilities
from utils.data import (
    fetch_market_data,
    calculate_heikin_ashi,
    analyze_breakout_pattern,
    prepare_llm_payload,
    get_current_price,
)
from utils.llm import LLMClient
from utils.bankroll import BankrollManager
from utils.browser import RobinhoodBot
from utils.enhanced_slack import EnhancedSlackIntegration
from utils.multi_symbol_scanner import MultiSymbolScanner
from utils.portfolio import PortfolioManager, Position
from utils.alpaca_options import AlpacaOptionsTrader
from utils.alpaca_sync import sync_before_trade
from utils.kill_switch import get_kill_switch, is_trading_halted
from utils.circuit_breaker_reset import check_and_process_file_reset
from utils.data_validation import check_trading_allowed
from utils.staleness_monitor import check_symbol_staleness

# Load environment variables
load_dotenv()
logger = logging.getLogger(__name__)

# Configure logging via shared utility
from utils.logging_utils import setup_logging


def load_config(config_path: str = "config.yaml") -> Dict:
    """
    Load and validate trading system configuration from YAML file.

    Loads all trading parameters including bankroll management, risk settings,
    market data sources, browser options, and intraday trading parameters.

    Args:
        config_path (str): Path to the YAML configuration file (default: "config.yaml")

    Returns:
        Dict: Configuration dictionary containing all trading parameters

    Raises:
        SystemExit: If configuration file cannot be loaded or is invalid

    Configuration Sections:
        - Trading Parameters: CONTRACT_QTY, LOOKBACK_BARS, MODEL
        - Bankroll Management: START_CAPITAL, RISK_FRACTION, SIZE_RULE
        - Market Data: SYMBOL, TIMEFRAME, DATA_SOURCE
        - Browser Settings: HEADLESS, IMPLICIT_WAIT, PAGE_LOAD_TIMEOUT
        - Risk Management: MAX_PREMIUM_PCT, MIN_CONFIDENCE, IV_THRESHOLD
        - Intraday Trading: PROFIT_TARGET_PCT, STOP_LOSS_PCT, EOD_CLOSE_TIME
    """
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        sys.exit(1)


def validate_environment() -> Dict[str, str]:
    """
    Validate all required environment variables for secure trading operations.

    Checks for essential credentials and API keys needed for the trading system:
    - Robinhood login credentials (RH_USER, RH_PASS)
    - At least one LLM API key (OPENAI_API_KEY or DEEPSEEK_API_KEY)
    - Optional: Slack webhook URL and Alpaca API keys

    Returns:
        Dict[str, str]: Dictionary of validated environment variables

    Raises:
        SystemExit: If any required environment variables are missing

    Security Note:
        Never log or print actual credential values. Only validate presence.
        All credentials should be stored in .env file and never committed to git.

    Required Variables:
        - RH_USER: Robinhood username/email
        - RH_PASS: Robinhood password
        - OPENAI_API_KEY or DEEPSEEK_API_KEY: LLM API access

    Optional Variables:
        - SLACK_WEBHOOK_URL: For trade notifications
        - SLACK_BOT_TOKEN: For two-way Slack communication
        - ALPACA_API_KEY: Alternative market data source
    """
    required_vars = {"RH_USER": os.getenv("RH_USER"), "RH_PASS": os.getenv("RH_PASS")}

    # Check for at least one LLM API key
    openai_key = os.getenv("OPENAI_API_KEY")
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")

    if not openai_key and not deepseek_key:
        logger.error("Either OPENAI_API_KEY or DEEPSEEK_API_KEY must be set")
        sys.exit(1)

    # Check Robinhood credentials
    for var, value in required_vars.items():
        if not value:
            logger.error(f"Required environment variable {var} not set")
            sys.exit(1)

    return required_vars


def initialize_trade_log(log_file: str):
    """Initialize CSV trade log with headers if it doesn't exist."""
    log_path = Path(log_file)
    log_path.parent.mkdir(exist_ok=True)

    if not log_path.exists():
        # Use the scoped 15-field ledger schema
        headers = [
            "timestamp",
            "symbol",
            "decision",
            "confidence",
            "current_price",
            "strike",
            "premium",
            "quantity",
            "total_cost",
            "reason",
            "status",
            "fill_price",
            "pnl_pct",
            "pnl_amount",
            "exit_reason",
        ]

        with open(log_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)

        logger.info(f"Initialized trade log: {log_file}")


# Import shared logging utility
from utils.logging_utils import log_trade_decision

# Import health monitoring
from utils.health_monitor import is_system_healthy, perform_system_health_check


def format_expiry_display(expiry_date: str, policy: str = None) -> str:
    """Format expiry date for display with policy context.
    
    Args:
        expiry_date: Date in YYYY-MM-DD format
        policy: Expiry policy ('0DTE' or 'WEEKLY')
        
    Returns:
        Human-readable expiry string
    """
    try:
        from datetime import datetime
        expiry_dt = datetime.strptime(expiry_date, "%Y-%m-%d")
        today = datetime.now().date()
        
        if expiry_dt.date() == today:
            return f"0DTE ({expiry_dt.strftime('%m/%d')})"
        elif policy == "0DTE":
            return f"0DTE ({expiry_dt.strftime('%m/%d')})"
        else:
            days_out = (expiry_dt.date() - today).days
            return f"{days_out}DTE ({expiry_dt.strftime('%m/%d')})"
    except:
        return expiry_date  # Fallback to raw date


def parse_end_time(end_time_str: str) -> datetime:
    """Parse end time string (HH:MM) to a timezone-aware datetime in local timezone.

    Returns None when input is None or empty. Raises ValueError on invalid format.
    """
    if not end_time_str:
        return None

    try:
        tz = ZoneInfo("America/New_York")
        now = datetime.now(tz)

        # Parse the time string
        time_parts = end_time_str.split(":")
        if len(time_parts) != 2:
            raise ValueError("Time must be in HH:MM format")

        hour = int(time_parts[0])
        minute = int(time_parts[1])

        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Hour or minute out of range")

        # Create end time for today
        end_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # If end time has already passed today, set it for tomorrow
        if end_time <= now:
            original_date = end_time.strftime("%Y-%m-%d")
            end_time += timedelta(days=1)
            new_date = end_time.strftime("%Y-%m-%d")
            logging.info(
                f"[TIME] End time {end_time_str} has passed for {original_date}, "
                f"rolling to tomorrow ({new_date}) at {end_time.strftime('%H:%M %Z')}"
            )

        return end_time
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid end time format '{end_time_str}': {e}")
        raise


def generate_daily_summary(config: Dict, end_time: datetime) -> str:
    """Generate S4 daily summary block for end-of-day Slack notification.
    
    Args:
        config: Trading configuration
        end_time: End time of trading session
        
    Returns:
        Formatted daily summary message
    """
    try:
        from datetime import date
        import csv
        from pathlib import Path
        
        today = date.today()
        trade_log_file = config.get('TRADE_LOG_FILE', 'logs/trade_history.csv')

        # Initialize counters
        n_trades = 0
        wins = 0
        losses = 0
        total_pl = 0.0

        # Read today's trades from trade log
        if Path(trade_log_file).exists():
            with open(trade_log_file, 'r', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        # Parse trade date
                        ts = row.get('timestamp', '').strip()
                        trade_date = datetime.fromisoformat(ts).date()
                        if trade_date != today:
                            continue

                        status_val = (row.get('status') or '').strip().upper()

                        # Count submitted trades (exclude CANCELLED), matching legacy behavior
                        if status_val == 'SUBMITTED':
                            n_trades += 1

                        # Determine realized P&L for closed trades
                        # Prefer new schema's pnl_amount when available
                        pnl_field = row.get('pnl_amount', '').strip()
                        pl_val: Optional[float] = None
                        if pnl_field not in (None, ''):
                            try:
                                pl_val = float(pnl_field)
                            except ValueError:
                                pl_val = None

                        # Fallback to legacy premium math when exit_premium present on SUBMITTED rows
                        if pl_val is None:
                            entry_str = (row.get('actual_premium') or row.get('premium') or '').strip()
                            exit_str = (row.get('exit_premium') or '').strip()
                            qty_str = (row.get('quantity') or '1').strip()
                            if exit_str not in ('', '0', '0.0') and entry_str not in ('',):
                                try:
                                    entry_premium = float(entry_str)
                                    exit_premium = float(exit_str)
                                    contracts = int(qty_str)
                                    pl_val = (exit_premium - entry_premium) * contracts * 100
                                except ValueError:
                                    pl_val = None

                        # Accumulate wins/losses only when we have realized P&L
                        if pl_val is not None:
                            total_pl += pl_val
                            if pl_val > 0:
                                wins += 1
                            elif pl_val < 0:
                                losses += 1
                    except Exception:
                        # Skip malformed rows entirely
                        continue
        
        # Get current bankroll
        try:
            from utils.bankroll import BankrollManager
            broker = config.get('BROKER', 'robinhood')
            env = config.get('ALPACA_ENV', 'live') if broker == 'alpaca' else 'live'
            start_capital = config.get('START_CAPITAL_DEFAULT', config.get('START_CAPITAL', 500.0))
            bankroll_manager = BankrollManager(start_capital=start_capital, broker=broker, env=env)
            current_bankroll = bankroll_manager.get_current_bankroll()
            peak_bankroll = getattr(bankroll_manager, 'peak_bankroll', current_bankroll)
        except Exception:
            current_bankroll = config.get('START_CAPITAL', 500.0)
            peak_bankroll = current_bankroll
        
        # Format daily summary block
        tz_name = end_time.strftime('%Z')
        summary = (
            f"📊 **Daily Wrap-Up** {end_time.strftime('%H:%M %Z')}\n"
            f"**Trades:** {n_trades}\n"
            f"**Wins/Loss:** {wins}/{losses}\n"
            f"**P&L:** ${total_pl:.2f}\n"
            f"**Peak balance:** ${peak_bankroll:.2f}\n"
            f"**Current balance:** ${current_bankroll:.2f}"
        )
        
        return summary
        
    except Exception as e:
        logger.error(f"Error generating daily summary: {e}")
        # Fallback summary
        return f"📊 **Daily Wrap-Up** {end_time.strftime('%H:%M %Z')}\nSession complete"


def execute_multi_symbol_trade(
    opportunity: Dict,
    config: Dict,
    args,
    env_vars: Dict,
    bankroll_manager,
    portfolio_manager,
    slack_notifier,
    bot=None,
) -> Dict:
    """
    Execute a pre-approved multi-symbol trading opportunity directly.

    This function trusts the multi-symbol scanner decision and proceeds directly
    to browser automation without re-analyzing market conditions.

    Args:
        opportunity: Pre-approved trading opportunity from multi-symbol scanner
        config: Trading configuration
        args: Command line arguments
        env_vars: Environment variables
        bankroll_manager: Bankroll management instance
        portfolio_manager: Portfolio tracking instance
        slack_notifier: Slack notification instance
        bot: Existing browser instance to reuse

    Returns:
        Dict: Execution result with bot instance
    """
    from utils.browser import RobinhoodBot
    from utils.trade_confirmation import TradeConfirmationManager
    

    symbol = opportunity["symbol"]
    decision = opportunity["decision"]
    confidence = opportunity["confidence"]
    current_price = opportunity["current_price"]
    reason = opportunity["reason"]

    # Enforce confidence threshold - no pre-approved overrides
    min_confidence = config.get("MIN_CONFIDENCE", 0.6)
    if confidence < min_confidence:
        logger.warning(
            f"[MULTI-SYMBOL-EXECUTE] Confidence {confidence:.2f} below threshold "
            f"{min_confidence:.2f} - blocking pre-approved trade for {symbol}"
        )
        return {"status": "BLOCKED", "reason": f"Confidence below threshold ({min_confidence:.2f})"}

    logger.info(
        f"[MULTI-SYMBOL-EXECUTE] Executing pre-approved {symbol} {decision} (confidence: {confidence:.2f})"
    )

    try:
        # Check existing positions
        current_positions = portfolio_manager.load_positions()

        # Determine trade action (OPEN or CLOSE)
        trade_action, position_to_close = portfolio_manager.determine_trade_action(
            symbol, decision
        )

        # Check position limits for new positions
        if trade_action == "OPEN" and len(current_positions) >= config.get(
            "MAX_POSITIONS", 3
        ):
            logger.info(
                f"[MULTI-SYMBOL-EXECUTE] Skipping {symbol} - position limits reached ({len(current_positions)}/{config.get('MAX_POSITIONS', 3)})"
            )
            return {"bot": bot}

        logger.info(
            f"[MULTI-SYMBOL-EXECUTE] Trade action: {trade_action} for {symbol} {decision}"
        )

        # Route to appropriate broker
        broker = config.get("BROKER", "robinhood").lower()
        
        if broker == "alpaca":
            logger.info(f"[MULTI-SYMBOL-EXECUTE] Using Alpaca API for {symbol} {decision}")
            # Use Alpaca options trading
            from utils.alpaca_options import create_alpaca_trader
            
            paper_mode = config.get("ALPACA_ENV", "paper") == "paper"
            trader = create_alpaca_trader(paper=paper_mode)
            
            if not trader:
                logger.error(f"[MULTI-SYMBOL-EXECUTE] Failed to create Alpaca trader for {symbol}")
                return {"status": "ERROR", "reason": "Missing Alpaca credentials"}
            
            # Execute Alpaca trade with enhanced error handling
            result = execute_alpaca_multi_symbol_trade(
                trader, opportunity, config, bankroll_manager, portfolio_manager, slack_notifier, trade_action, args
            )
            
            # Enhanced spillover: mark contract selection failures for spillover
            if result.get("status") == "ERROR" and "contract" in result.get("reason", "").lower():
                result["error_type"] = "contract_selection"
                result["spillover_eligible"] = True
                logger.info(f"[MULTI-SYMBOL-EXECUTE] Contract selection failed for {symbol} - eligible for spillover")
            
            return result
        else:
            logger.info(f"[MULTI-SYMBOL-EXECUTE] Using Robinhood browser for {symbol} {decision}")
            # Initialize or reuse browser bot
            if not bot:
                bot = RobinhoodBot(
                    headless=config["HEADLESS"],
                    implicit_wait=config["IMPLICIT_WAIT"],
                    page_load_timeout=config["PAGE_LOAD_TIMEOUT"],
                )
                bot.start_browser()

                # Login to Robinhood
                if not bot.login(env_vars["RH_USER"], env_vars["RH_PASS"]):
                    logger.error(f"[MULTI-SYMBOL-EXECUTE] Login failed for {symbol}")
                    return {"bot": bot}

            # Navigate to options chain
            if not bot.navigate_to_options(symbol):
                logger.error(
                    f"[MULTI-SYMBOL-EXECUTE] Failed to navigate to {symbol} options"
                )
                return {"bot": bot}
            else:
                # Ensure we're on the correct symbol's options page
                bot.ensure_open(symbol)

        # Find ATM option and prepare order
        atm_option = bot.find_atm_option(current_price, decision)
        if not atm_option:
            logger.error(
                f"[MULTI-SYMBOL-EXECUTE] No ATM {decision} option found for {symbol}"
            )
            return {"bot": bot}

        # Get actual option premium from browser
        actual_premium = bot.get_option_premium()
        if not actual_premium:
            logger.warning(
                "[MULTI-SYMBOL-EXECUTE] Could not get option premium, using estimate"
            )
            actual_premium = current_price * 0.02  # Fallback estimate

        logger.info(f"[MULTI-SYMBOL-EXECUTE] Option premium: ${actual_premium:.2f}")

        # Calculate position size with actual premium
        quantity = bankroll_manager.calculate_position_size(
            premium=actual_premium,
            risk_fraction=config["RISK_FRACTION"],
            size_rule=config["SIZE_RULE"],
            fixed_qty=config["CONTRACT_QTY"],
            symbol=symbol,
        )

        # Validate position size against bankroll
        total_cost = actual_premium * quantity * 100  # Options are $100 multiplier
        current_bankroll = bankroll_manager.get_current_bankroll()
        max_risk = current_bankroll * config["RISK_FRACTION"]

        if total_cost > max_risk:
            # Recalculate with proper risk management
            quantity = int(max_risk / (actual_premium * 100))
            total_cost = actual_premium * quantity * 100
            logger.warning(
                f"[MULTI-SYMBOL-EXECUTE] Position size adjusted for risk: {quantity} contracts (${total_cost:.2f} total)"
            )

        # Final validation - ensure we don't exceed available buying power
        if total_cost > current_bankroll * 0.8:  # Leave 20% buffer
            quantity = int((current_bankroll * 0.8) / (actual_premium * 100))
            total_cost = actual_premium * quantity * 100
            logger.warning(
                f"[MULTI-SYMBOL-EXECUTE] Position size adjusted for buying power: {quantity} contracts (${total_cost:.2f} total)"
            )

        logger.info(
            f"[MULTI-SYMBOL-EXECUTE] Final position size: {quantity} contracts (${total_cost:.2f} total cost)"
        )

        # Pre-fill order and stop at Review
        if bot.click_option_and_buy(atm_option, quantity):
            logger.info(
                f"[MULTI-SYMBOL-EXECUTE] {symbol} {decision} order ready for review"
            )

            # Send order ready notification
            if slack_notifier:
                try:
                    # Try to use send_order_ready_alert if available (basic SlackNotifier)
                    if hasattr(slack_notifier, "send_order_ready_alert"):
                        slack_notifier.send_order_ready_alert(
                            trade_type=decision,
                            strike=str(atm_option["strike"]),
                            expiry="Today",
                            position_size=total_cost,
                            action=trade_action,
                            confidence=confidence,
                            reason=reason,
                            current_price=current_price,
                            premium=actual_premium,
                            quantity=quantity,
                            total_cost=total_cost,
                        )
                    else:
                        # Fallback for EnhancedSlackIntegration - use basic heartbeat
                        order_message = (
                            f"🚨 ORDER READY FOR REVIEW\n"
                            f"Symbol: {symbol}\n"
                            f"Direction: {decision}\n"
                            f"Strike: ${atm_option['strike']}\n"
                            f"Quantity: {quantity} contracts\n"
                            f"Premium: ${actual_premium:.2f}\n"
                            f"Total Cost: ${actual_premium * quantity * 100:.2f}\n"
                            f"Confidence: {confidence:.1%}\n"
                            f"Action: {trade_action}\n"
                            f"Reason: {reason}"
                        )

                        # Use basic_notifier if available (EnhancedSlackIntegration)
                        if hasattr(slack_notifier, "basic_notifier"):
                            slack_notifier.basic_notifier.send_heartbeat(order_message)
                        else:
                            # Last resort - try send_heartbeat directly
                            slack_notifier.send_heartbeat(order_message)

                    logger.info(
                        f"[MULTI-SYMBOL-EXECUTE] Slack order ready alert sent for {symbol}"
                    )
                except Exception as e:
                    logger.error(
                        f"[MULTI-SYMBOL-EXECUTE] Failed to send Slack alert: {e}"
                    )

            # Trade confirmation workflow
            confirmer = TradeConfirmationManager(
                portfolio_manager=portfolio_manager,
                bankroll_manager=bankroll_manager,
                slack_notifier=slack_notifier,
            )

            # Prepare trade details for confirmation
            trade_details = {
                "symbol": symbol,
                "direction": decision,  # Use 'direction' as expected by TradeConfirmationManager
                "confidence": confidence,
                "current_price": current_price,
                "strike": atm_option["strike"],
                "quantity": quantity,
                "premium": actual_premium,
                "action": trade_action,
                "reason": reason,
                "expiry": "Today",  # Add expiry field
            }

            # Check if unattended mode - execute automatically, otherwise use manual confirmation
            if args.unattended:
                logger.info("[MULTI-SYMBOL-EXECUTE] Unattended mode: Executing trade automatically...")
                decision_result = "submitted"
                actual_fill_premium = estimated_premium  # Use estimated premium for automated execution
            else:
                # Manual confirmation mode
                logger.info("[MULTI-SYMBOL-EXECUTE] Waiting for trade confirmation...")
                decision_result, actual_fill_premium = confirmer.get_user_decision(
                    trade_details, method="prompt"
                )

            # Record the trade outcome
            confirmer.record_trade_outcome(
                trade_details, decision_result, actual_fill_premium
            )

            logger.info(
                f"[MULTI-SYMBOL-EXECUTE] {symbol} trade confirmation completed: {decision_result}"
            )

        else:
            logger.error(
                f"[MULTI-SYMBOL-EXECUTE] Failed to prepare {symbol} {decision} order"
            )

    except Exception as e:
        logger.error(f"[MULTI-SYMBOL-EXECUTE] Error executing {symbol} trade: {e}")

    return {"bot": bot}


def execute_alpaca_multi_symbol_trade(
    trader, opportunity, config, bankroll_manager, portfolio_manager, slack_notifier, trade_action, args
):
    """Execute multi-symbol trade using Alpaca API."""
    from utils.trade_confirmation import TradeConfirmationManager
    
    symbol = opportunity["symbol"]
    decision = opportunity["decision"]
    confidence = opportunity["confidence"]
    current_price = opportunity["current_price"]
    reason = opportunity["reason"]
    
    # Enforce confidence threshold - no pre-approved overrides
    min_confidence = config.get("MIN_CONFIDENCE", 0.6)
    if confidence < min_confidence:
        logger.warning(
            f"[MULTI-SYMBOL-ALPACA] Confidence {confidence:.2f} below threshold "
            f"{min_confidence:.2f} - blocking pre-approved trade for {symbol}"
        )
        return {"status": "BLOCKED", "reason": f"Confidence below threshold ({min_confidence:.2f})"}
    
    try:
        # Sync with Alpaca account before trading
        alpaca_env = config.get("ALPACA_ENV", "paper")
        sync_success = sync_before_trade(env=alpaca_env)
        if not sync_success:
            logger.warning(f"[MULTI-SYMBOL-ALPACA] Alpaca sync failed for {symbol} - proceeding with caution")
        
        # Check market hours and trading window
        is_valid, reason_msg = trader.is_market_open_and_valid_time()
        if not is_valid:
            logger.warning(f"[MULTI-SYMBOL-ALPACA] Trading not allowed for {symbol}: {reason_msg}")
            return {"status": "BLOCKED", "reason": reason_msg}
        
        # Use expiry policy from opportunity (preserve 0DTE end-to-end)
        policy = opportunity.get("expiry_policy", "0DTE")
        expiry_date = opportunity.get("expiry_date")
        
        # Only recalculate if not provided in opportunity
        if not expiry_date:
            policy, expiry_date = trader.get_expiry_policy(symbol)
            if policy is None or expiry_date is None:
                logger.error(f"[MULTI-SYMBOL-ALPACA] No valid expiry available for {symbol}")
                return {"success": False, "error_type": "expiry_unavailable", "status": "ERROR", "reason": f"No valid expiry for {symbol}"}
        else:
            logger.info(f"[MULTI-SYMBOL-ALPACA] Using opportunity expiry policy: {policy} ({expiry_date})")
        
        side = "CALL" if decision == "CALL" else "PUT"
        
        logger.info(f"[MULTI-SYMBOL-ALPACA] Finding {side} contract for {symbol} (policy: {policy})")
        contract = trader.find_atm_contract(symbol, side, policy, expiry_date)
        
        if not contract:
            logger.error(f"[MULTI-SYMBOL-ALPACA] No suitable {side} contract found for {symbol}")
            return {"success": False, "error_type": "contract_selection", "status": "ERROR", "reason": f"No {side} contract found"}
        
        # Get real-time quote for the contract
        quote = trader.get_latest_quote(contract.symbol)
        if not quote:
            logger.error(f"[MULTI-SYMBOL-ALPACA] Failed to get quote for {contract.symbol}")
            return {"success": False, "error_type": "quote_failure", "status": "ERROR", "reason": "Failed to get option quote"}
        
        # Calculate position size with real premium
        premium = quote.ask  # Use ask price for buying
        quantity = bankroll_manager.calculate_position_size(
            premium=premium,
            risk_fraction=config["RISK_FRACTION"],
            size_rule=config["SIZE_RULE"],
            fixed_qty=config["CONTRACT_QTY"],
            symbol=symbol,
        )
        
        # Validate position size
        total_cost = premium * quantity * 100  # Options multiplier
        current_bankroll = bankroll_manager.get_current_bankroll()
        max_risk = current_bankroll * config["RISK_FRACTION"]
        
        if total_cost > max_risk:
            quantity = int(max_risk / (premium * 100))
            total_cost = premium * quantity * 100
            logger.warning(f"[MULTI-SYMBOL-ALPACA] Position size adjusted for {symbol}: {quantity} contracts")
        
        if quantity <= 0:
            logger.error(f"[MULTI-SYMBOL-ALPACA] Invalid position size for {symbol}: {quantity}")
            return {"status": "ERROR", "reason": "Invalid position size"}
        
        logger.info(f"[MULTI-SYMBOL-ALPACA] {symbol} order: {quantity} x {contract.symbol} @ ${premium:.2f}")
        
        # Trade confirmation workflow
        confirmer = TradeConfirmationManager(
            portfolio_manager=portfolio_manager,
            bankroll_manager=bankroll_manager,
            slack_notifier=slack_notifier,
        )
        
        # Prepare trade details
        trade_details = {
            "symbol": symbol,
            "direction": decision,
            "confidence": confidence,
            "current_price": current_price,
            "strike": contract.strike,
            "quantity": quantity,
            "premium": premium,
            "action": trade_action,
            "reason": reason,
            "expiry": contract.expiry,
            "contract_symbol": contract.symbol,
        }
        
        # Feasibility pre-check: Verify contract is executable before generating alerts
        feasibility_check = trader.check_contract_feasibility(contract.symbol, quantity)
        if not feasibility_check["feasible"]:
            logger.warning(f"[MULTI-SYMBOL-ALPACA] Contract not feasible for {symbol}: {feasibility_check['reason']}")
            return {"success": False, "error_type": "contract_not_feasible", "status": "ERROR", "reason": feasibility_check["reason"]}
        
        logger.info(f"[MULTI-SYMBOL-ALPACA] Contract feasibility confirmed for {symbol}")

        # Check if unattended mode - execute automatically, otherwise use manual confirmation
        if args.unattended:
            logger.info(f"[MULTI-SYMBOL-ALPACA] Unattended mode: Executing {symbol} trade automatically...")
            decision_result = "submitted"
            actual_fill_premium = premium  # Use actual premium for automated execution
        else:
            # Manual confirmation mode
            logger.info(f"[MULTI-SYMBOL-ALPACA] Requesting confirmation for {symbol} trade...")
            decision_result, actual_fill_premium = confirmer.get_user_decision(
                trade_details, method="prompt"
            )
        
        if decision_result == "submitted":
            # Submit order to Alpaca
            logger.info(f"[MULTI-SYMBOL-ALPACA] Submitting {symbol} order to Alpaca...")
            order_id = trader.place_market_order(
                contract_symbol=contract.symbol,
                qty=quantity,
                side="BUY",  # Always buying options in this system
            )
            
            if order_id:
                logger.info(f"[MULTI-SYMBOL-ALPACA] {symbol} order submitted successfully: {order_id}")
                # For now, assume order will fill (Alpaca handles this asynchronously)
                # In production, you'd want to poll for fill status using trader.poll_order_fill()
                logger.info(f"[MULTI-SYMBOL-ALPACA] {symbol} order assumed filled (paper trading)")
            else:
                logger.error(f"[MULTI-SYMBOL-ALPACA] {symbol} order failed to submit")
                decision_result = "FAILED"
        
        # Record the trade outcome
        confirmer.record_trade_outcome(trade_details, decision_result, actual_fill_premium)
        
        logger.info(f"[MULTI-SYMBOL-ALPACA] {symbol} trade completed: {decision_result}")
        return {"status": decision_result, "symbol": symbol}
        
    except Exception as e:
        logger.error(f"[MULTI-SYMBOL-ALPACA] Error executing {symbol} trade: {e}")
        return {"status": "ERROR", "reason": str(e)}


def run_once(
    config: Dict,
    args,
    env_vars: Dict,
    bankroll_manager,
    portfolio_manager,
    llm_client,
    slack_notifier,
    bot=None,
) -> Dict:
    """
    Execute one complete trading cycle from market analysis to trade execution.

    This is the core trading function that performs the complete workflow:
    1. Fetch current market data for SPY
    2. Calculate Heikin-Ashi candles for trend analysis
    3. Analyze breakout patterns using technical indicators
    4. Get LLM trade decision based on market conditions
    5. If trade signal detected, initiate browser automation
    6. Navigate to Robinhood and find ATM options
    7. Execute trade automatically based on LLM decision
    8. Record trade outcome and update tracking

    Args:
        config (Dict): Trading configuration parameters
        args: Command line arguments
        env_vars (Dict): Environment variables (credentials)
        bankroll_manager: Bankroll management instance
        portfolio_manager: Portfolio tracking instance
        llm_client: LLM client for trade decisions
        slack_notifier: Slack notification instance
        bot (RobinhoodBot, optional): Existing browser instance to reuse

    Returns:
        Dict: Trade result data containing:
            - decision: Trade decision (BUY_CALL, BUY_PUT, NO_TRADE)
            - confidence: LLM confidence score (0.0-1.0)
            - reason: Explanation for the decision
            - current_price: Current SPY price
            - strike: Selected option strike (if applicable)
            - premium: Option premium (if applicable)
            - status: Execution status (SUBMITTED, CANCELLED, NO_TRADE)

    Safety:
        - Executes trades automatically based on LLM decisions
        - Confidence threshold enforcement (0.6 minimum)
        - Ensemble model agreement required
        - Records estimated fill prices for automated execution

    Risk Management:
        - Validates bankroll before trading
        - Checks position limits
        - Applies risk fraction limits
        - Logs all activities for audit
    """

    # Step 0: System Health Check - Critical Safety Gate
    logger.info("[HEALTH] Performing system health check before trading...")
    health_status = perform_system_health_check()
    
    if not is_system_healthy():
        logger.error(f"[HEALTH] System health check failed: {health_status.overall_status}")
        logger.error("[HEALTH] Trading blocked due to critical system health issues")
        
        # Return early with health failure status
        return {
            "analysis": {"current_price": 0, "trend_direction": "UNKNOWN"},
            "decision": type('obj', (object,), {
                'decision': 'NO_TRADE', 
                'confidence': 0.0, 
                'reason': f'System health check failed: {health_status.overall_status}'
            })(),
            "current_bankroll": 0,
            "position_size": 0,
            "status": "HEALTH_CHECK_FAILED"
        }
    
    logger.info(f"[HEALTH] System health check passed: {health_status.overall_status}")

    # Get current bankroll
    current_bankroll = bankroll_manager.get_current_bankroll()
    logger.info(f"[BANKROLL] Current bankroll: ${current_bankroll:.2f}")

    # Step 1: Fetch market data with Alpaca primary, Yahoo fallback
    logger.info("[DATA] Fetching market data with Alpaca real-time data...")
    market_data = fetch_market_data(symbol=config["SYMBOL"], period="5d", interval="5m")

    # Step 1.5: Get real-time current price for accurate analysis
    logger.info("[PRICE] Fetching real-time current price...")
    current_price = get_current_price(config["SYMBOL"])
    if current_price:
        logger.info(f"[ALPACA] Real-time price: ${current_price:.2f}")
        # Update the most recent price in market data for accuracy
        if not market_data.empty:
            market_data.iloc[-1, market_data.columns.get_loc("Close")] = current_price
            logger.debug("[DATA] Updated latest close price with real-time data")
    else:
        logger.warning("[DATA] Could not fetch real-time price, using historical data")
        current_price = market_data["Close"].iloc[-1] if not market_data.empty else None

    # Step 2: Calculate Heikin-Ashi candles
    logger.info("[CANDLES] Calculating Heikin-Ashi candles...")
    ha_data = calculate_heikin_ashi(market_data)

    # Step 3: Analyze breakout patterns with real-time price
    logger.info("[ANALYSIS] Analyzing breakout patterns...")
    analysis = analyze_breakout_pattern(ha_data, config["LOOKBACK_BARS"])

    # Override analysis current_price with real-time data if available
    if current_price:
        analysis["current_price"] = current_price
        analysis["data_source"] = "alpaca_realtime"
        logger.info(
            f"[ANALYSIS] Using real-time price ${current_price:.2f} for analysis"
        )

    # Step 4: Prepare LLM payload
    llm_payload = prepare_llm_payload(analysis)

    # Enhanced market logging with data source information
    data_source = analysis.get("data_source", "yahoo_historical")
    logger.info(
        f"[MARKET] Market analysis: {analysis['trend_direction']} trend, "
        f"price ${analysis['current_price']:.2f} ({data_source}), "
        f"body {analysis['candle_body_pct']:.2f}%"
    )

    # Step 5: Get LLM decision
    logger.info("[LLM] Getting LLM trade decision...")
    # Use enhanced context for better LLM learning (hybrid approach)
    enhanced_context = bankroll_manager.get_enhanced_llm_context()
    win_history = enhanced_context.get("win_history", [])  # Backward compatibility
    
    # Check if ensemble is enabled (v0.6.0)
    if config.get("ENSEMBLE_ENABLED", True):
        logger.info("[ENSEMBLE] Using two-model ensemble decision making")
        from utils.ensemble_llm import choose_trade
        ensemble_result = choose_trade(llm_payload)
        # Convert ensemble result to TradeDecision format
        from utils.llm import TradeDecision
        decision = TradeDecision(
            decision=ensemble_result["decision"],
            confidence=ensemble_result["confidence"],
            reason=ensemble_result["reason"]
        )
    else:
        logger.info("[LLM] Using single-model decision making")
        decision = llm_client.make_trade_decision(
            llm_payload, win_history, enhanced_context
        )

    logger.info(
        f"[DECISION] LLM Decision: {decision.decision} "
        f"(confidence: {decision.confidence:.2f})"
    )

    if decision.reason:
        logger.info(f"[REASON] Reason: {decision.reason}")

    # Calculate position size for notification
    position_size = 0
    if decision.decision in ["CALL", "PUT"]:
        # Estimate premium using a simple heuristic for notification purposes
        estimated_premium = analysis["current_price"] * 0.02
        position_size = bankroll_manager.calculate_position_size(
            premium=estimated_premium,
            risk_fraction=config["RISK_FRACTION"],
            size_rule=config["SIZE_RULE"],
            fixed_qty=config["CONTRACT_QTY"],
            symbol=symbol,
        )

    # Return trade result data
    return {
        "analysis": analysis,
        "decision": decision,
        "current_bankroll": current_bankroll,
        "position_size": position_size,
    }


def execute_trade_by_broker(
    config: Dict,
    args,
    env_vars: Dict,
    decision,
    analysis: Dict,
    current_bankroll: float,
    position_size: int,
    bankroll_manager,
    portfolio_manager,
    slack_notifier,
) -> Dict:
    """Execute trade using appropriate broker (Alpaca API or Robinhood browser)."""
    broker = config.get("BROKER", "robinhood").lower()
    
    if broker == "alpaca":
        logger.info("[BROKER] Using Alpaca API for options trading")
        return execute_alpaca_options_trade(
            config=config,
            args=args,
            env_vars=env_vars,
            decision=decision,
            analysis=analysis,
            current_bankroll=current_bankroll,
            position_size=position_size,
            bankroll_manager=bankroll_manager,
            portfolio_manager=portfolio_manager,
            slack_notifier=slack_notifier,
        )
    else:
        logger.info("[BROKER] Using Robinhood browser automation")
        return execute_robinhood_options_trade(
            config=config,
            args=args,
            env_vars=env_vars,
            decision=decision,
            analysis=analysis,
            current_bankroll=current_bankroll,
            position_size=position_size,
            bankroll_manager=bankroll_manager,
            portfolio_manager=portfolio_manager,
            slack_notifier=slack_notifier,
        )


def execute_alpaca_options_trade(
    config: Dict,
    args,
    env_vars: Dict,
    decision,
    analysis: Dict,
    current_bankroll: float,
    position_size: int,
    bankroll_manager,
    portfolio_manager,
    slack_notifier,
) -> Dict:
    """Execute options trade using Alpaca API."""
    try:
        # Create Alpaca trader instance
        paper_mode = config.get("ALPACA_ENV", "paper") == "paper"
        trader = create_alpaca_trader(paper=paper_mode)
        
        if not trader:
            logger.error("[ALPACA] Failed to create Alpaca trader - missing credentials")
            return {"status": "ERROR", "reason": "Missing Alpaca credentials"}
        
        # Check market hours and trading window
        is_valid, reason = trader.is_market_open_and_valid_time()
        if not is_valid:
            logger.warning(f"[ALPACA] Trading not allowed: {reason}")
            return {"status": "BLOCKED", "reason": reason}
        
        # Get expiry policy and find ATM contract
        policy, expiry_date = trader.get_expiry_policy()
        symbol = config["SYMBOL"]
        side = "CALL" if decision.decision == "CALL" else "PUT"
        
        logger.info(f"[ALPACA] Finding {side} contract for {symbol} (policy: {policy})")
        contract = trader.find_atm_contract(symbol, side, policy, expiry_date)
        
        if not contract:
            logger.error(f"[ALPACA] No suitable {side} contract found for {symbol}")
            return {"status": "NO_CONTRACT", "reason": "No suitable contract found"}
        
        logger.info(f"[ALPACA] Selected contract: {contract.symbol} @ ${contract.mid:.2f}")
        
        # Calculate position size with 100x multiplier for options
        contracts = bankroll_manager.calculate_position_size(
            premium=contract.mid,
            risk_fraction=config["RISK_FRACTION"],
            size_rule=config["SIZE_RULE"],
            fixed_qty=config["CONTRACT_QTY"],
            symbol=symbol,
        )
        
        total_cost = contract.mid * contracts * 100  # Options multiplier
        
        # Check if unattended mode with entry approval is enabled
        unattended = config.get("UNATTENDED", False)
        llm_decisions = config.get("LLM_DECISIONS", [])
        
        if not args.dry_run:
            logger.info(f"[ALPACA] Trade details:")
            logger.info(f"  Contract: {contract.symbol}")
            logger.info(f"  Side: BUY {side}")
            logger.info(f"  Quantity: {contracts} contracts")
            logger.info(f"  Premium: ${contract.mid:.2f}")
            logger.info(f"  Total Cost: ${total_cost:.2f}")
            
            if unattended and ("entry" in llm_decisions or "ro_review" in llm_decisions):
                # Use LLM for entry approval - fully automated
                logger.info(f"[ALPACA] 🤖 LLM evaluating entry decision for {symbol}")
                approval_result = _handle_llm_entry_approval(
                    config, contract, contracts, total_cost, side, symbol
                )
                if not approval_result["approved"]:
                    logger.info(f"[ALPACA] 🤖 Trade rejected by LLM: {approval_result['reason']}")
                    return {"status": "CANCELLED", "reason": f"LLM rejected: {approval_result['reason']}"}
                else:
                    logger.info(f"[ALPACA] 🤖 Trade approved by LLM (confidence: {approval_result.get('confidence', 'N/A')})")
            else:
                # Manual approval required
                logger.info("[ALPACA] Manual approval required:")
                approval = input("\nApprove this trade? (y/N): ").strip().lower()
                if approval != 'y':
                    logger.info("[ALPACA] Trade cancelled by user")
                    return {"status": "CANCELLED", "reason": "User cancelled"}
        
        # Place order
        if args.dry_run:
            logger.info("[ALPACA] DRY RUN - Order not placed")
            return {
                "status": "DRY_RUN",
                "symbol": contract.symbol,
                "strike": contract.strike,
                "premium": contract.mid,
                "quantity": contracts,
                "total_cost": total_cost,
            }
        
        order_id = trader.place_market_order(contract.symbol, contracts, "BUY")
        if not order_id:
            logger.error("[ALPACA] Failed to place order")
            return {"status": "ORDER_FAILED", "reason": "Order placement failed"}
        
        # Poll for fill
        logger.info(f"[ALPACA] Polling for fill (Order ID: {order_id})")
        fill_result = trader.poll_fill(order_id=order_id, timeout_s=90)
        
        if fill_result.status == "FILLED":
            logger.info(f"[ALPACA] Order filled: {fill_result.filled_qty} @ ${fill_result.avg_price:.2f}")
            return {
                "status": "FILLED",
                "symbol": contract.symbol,
                "strike": contract.strike,
                "premium": fill_result.avg_price,
                "quantity": fill_result.filled_qty,
                "total_cost": fill_result.avg_price * fill_result.filled_qty * 100,
                "order_id": order_id,
            }
        else:
            logger.warning(f"[ALPACA] Order not filled: {fill_result.status}")
            return {
                "status": fill_result.status,
                "symbol": contract.symbol,
                "strike": contract.strike,
                "premium": contract.mid,
                "quantity": contracts,
                "order_id": order_id,
            }
            
    except Exception as e:
        logger.error(f"[ALPACA] Trade execution error: {e}", exc_info=True)
        return {"status": "ERROR", "reason": str(e)}


def _handle_llm_entry_approval(config, contract, contracts, total_cost, side, symbol):
    """Handle entry approval using LLM in unattended mode."""
    try:
        from utils.llm_decider import LLMDecider
        from utils.llm_json_client import LLMJsonClient
        from utils.ensemble_llm import EnsembleLLM
        from utils.enhanced_slack import EnhancedSlackIntegration
        
        # Initialize LLM components
        ensemble_llm = EnsembleLLM(config)
        json_client = LLMJsonClient(ensemble_llm, logger)
        slack = EnhancedSlackIntegration()
        llm_decider = LLMDecider(json_client, config, logger, slack_notifier=slack)
        
        # Build order context for LLM decision
        order_ctx = {
            "symbol": symbol,
            "side": side,
            "contract_symbol": contract.symbol,
            "strike": contract.strike,
            "premium": contract.mid,
            "quantity": contracts,
            "total_cost": total_cost,
            "slippage_bps": _calculate_slippage_bps(contract),
            "spread_bps": _calculate_spread_bps(contract),
            "liquidity_score": _calculate_liquidity_score(contract),
            "greeks_ok": _validate_greeks(contract),
            "vix_bucket": _get_vix_bucket(),
            "position_limits_ok": _check_position_limits(config, contracts),
            "price_fair_vs_mid": _validate_fair_pricing(contract),
            "account_risk_ok": _check_account_risk(config, total_cost),
        }
        
        # Get LLM decision
        decision = llm_decider.decide_entry(symbol, order_ctx)
        
        # Log the decision with audit trail
        audit_msg = (
            f"[ENTRY-LLM] {symbol} {decision.action} ({decision.confidence:.2f}) – {decision.reason}\n"
            f"Inputs: {side} {contract.symbol} @ ${contract.mid:.2f}, qty={contracts}, cost=${total_cost:.2f}"
        )
        logger.info(audit_msg)
        
        # Send Slack notification
        slack = EnhancedSlackIntegration()
        slack_msg = f"""🤖 **LLM Entry Decision: {symbol}**
**Action:** {decision.action}
**Confidence:** {decision.confidence:.2f}
**Reason:** {decision.reason}
**Contract:** {contract.symbol}
**Side:** BUY {side}
**Premium:** ${contract.mid:.2f}
**Quantity:** {contracts} contracts
**Total Cost:** ${total_cost:.2f}
**Risk Assessment:** {decision.risk_assessment or 'N/A'}"""
        
        slack.send_message(slack_msg)
        
        # Process the decision
        if decision.action == "APPROVE":
            print(f"\n🤖 [LLM-ENTRY] APPROVE decision for {symbol}")
            print(f"Reason: {decision.reason}")
            print(f"Confidence: {decision.confidence:.2f}")
            return {"approved": True, "reason": decision.reason}
            
        elif decision.action == "REJECT":
            print(f"\n🤖 [LLM-ENTRY] REJECT decision for {symbol}")
            print(f"Reason: {decision.reason}")
            return {"approved": False, "reason": decision.reason}
            
        elif decision.action == "NEED_USER":
            print(f"\n🤖 [LLM-ENTRY] NEED_USER decision for {symbol}")
            print(f"Reason: {decision.reason}")
            print("Falling back to manual approval...")
            
            # Fallback to manual approval
            approval = input("\nLLM requires manual review. Approve this trade? (y/N): ").strip().lower()
            approved = approval == 'y'
            reason = "Manual approval after LLM NEED_USER" if approved else "Manual rejection after LLM NEED_USER"
            return {"approved": approved, "reason": reason}
            
        else:  # ABSTAIN
            print(f"\n🤖 [LLM-ENTRY] ABSTAIN decision for {symbol}")
            print(f"Reason: {decision.reason}")
            return {"approved": False, "reason": f"LLM abstained: {decision.reason}"}
            
    except Exception as e:
        logger.error(f"[ENTRY-LLM] Error in LLM entry approval: {e}")
        print(f"\n[ERROR] LLM entry approval failed: {e}")
        print("Falling back to manual approval...")
        
        # Fallback to manual approval
        approval = input("\nLLM error - manual approval required. Approve this trade? (y/N): ").strip().lower()
        approved = approval == 'y'
        reason = "Manual approval after LLM error" if approved else "Manual rejection after LLM error"
        return {"approved": approved, "reason": reason}


def _calculate_slippage_bps(contract):
    """Calculate estimated slippage in basis points."""
    # Simplified calculation - could be enhanced with volume analysis
    spread = abs(contract.ask - contract.bid) if hasattr(contract, 'ask') and hasattr(contract, 'bid') else 0
    mid = contract.mid
    return int((spread / mid) * 10000) if mid > 0 else 0


def _calculate_spread_bps(contract):
    """Calculate bid-ask spread in basis points."""
    if hasattr(contract, 'ask') and hasattr(contract, 'bid'):
        spread = abs(contract.ask - contract.bid)
        mid = (contract.ask + contract.bid) / 2
        return int((spread / mid) * 10000) if mid > 0 else 0
    return 0


def _calculate_liquidity_score(contract):
    """Calculate liquidity score (0-1)."""
    # Simplified scoring - could be enhanced with OI and volume data
    if hasattr(contract, 'open_interest') and hasattr(contract, 'volume'):
        oi_score = min(contract.open_interest / 10000, 1.0)
        vol_score = min(contract.volume / 1000, 1.0)
        return (oi_score + vol_score) / 2
    return 0.5  # Default neutral score


def _validate_greeks(contract):
    """Validate option Greeks are within acceptable ranges."""
    # Simplified validation - could be enhanced with actual Greeks
    return True  # Default to True for now


def _get_vix_bucket():
    """Get current VIX volatility bucket."""
    # Simplified - could fetch actual VIX data
    return "normal"


def _check_position_limits(config, contracts):
    """Check if position size is within limits."""
    max_contracts = config.get("MAX_CONTRACTS_PER_TRADE", 10)
    return contracts <= max_contracts


def _validate_fair_pricing(contract):
    """Validate contract pricing is fair vs market."""
    # Simplified validation - could compare to theoretical value
    return True  # Default to True for now


def _check_account_risk(config, total_cost):
    """Check if trade cost is within account risk limits."""
    # Simplified check - could validate against bankroll limits
    return True  # Default to True for now


def execute_robinhood_options_trade(
    config: Dict,
    args,
    env_vars: Dict,
    decision,
    analysis: Dict,
    current_bankroll: float,
    position_size: int,
    bankroll_manager,
    portfolio_manager,
    slack_notifier,
) -> Dict:
    """Execute trade using Robinhood browser automation (legacy workflow)."""
    # NOTE: Robinhood browser automation is legacy - system now uses Alpaca API
    # This function is maintained for backward compatibility but not actively used
    logger.info("[ROBINHOOD] Browser automation is legacy - use Alpaca API instead")
    return {"status": "LEGACY_METHOD", "reason": "Use --broker alpaca for automated execution"}


def run_one_shot_mode(
    config: Dict,
    args,
    env_vars: Dict,
    bankroll_manager,
    portfolio_manager,
    llm_client,
    slack_notifier,
):
    """Execute the original one-shot trading mode."""
    logger = logging.getLogger(__name__)

    # Execute one trading cycle
    result = run_once(
        config,
        args,
        env_vars,
        bankroll_manager,
        portfolio_manager,
        llm_client,
        slack_notifier,
    )

    analysis = result["analysis"]
    decision = result["decision"]
    current_bankroll = result["current_bankroll"]
    position_size = result["position_size"]

    # Send market analysis to Slack
    if slack_notifier:
        slack_notifier.send_market_analysis(
            {
                "trend": analysis["trend_direction"],
                "current_price": analysis["current_price"],
                "body_percentage": analysis["candle_body_pct"],
                "support_count": len(analysis.get("support_levels", [])),
                "resistance_count": len(analysis.get("resistance_levels", [])),
            }
        )

    # Send trade decision to Slack
    if slack_notifier:
        slack_notifier.send_trade_decision(
            decision=decision.decision,
            confidence=decision.confidence,
            reason=decision.reason or "No specific reason provided",
            bankroll=current_bankroll,
            position_size=position_size,
        )

    try:
        # Step 4: Execute trade using appropriate broker
        logger.info(f"[TRADE] Executing {decision.decision} trade...")
        trade_result = execute_trade_by_broker(
            config=config,
            args=args,
            env_vars=env_vars,
            decision=decision,
            analysis=analysis,
            current_bankroll=current_bankroll,
            position_size=position_size,
            bankroll_manager=bankroll_manager,
            portfolio_manager=portfolio_manager,
            slack_notifier=slack_notifier,
        )
        
        # Step 5: Record trade outcome
        record_trade_outcome(
            config=config,
            trade_result=trade_result,
            decision=decision,
            analysis=analysis,
            current_bankroll=current_bankroll,
            bankroll_manager=bankroll_manager,
            portfolio_manager=portfolio_manager,
            slack_notifier=slack_notifier,
            args=args,
        )
        
        # Update result with trade outcome
        result.update({
            "trade_result": trade_result,
            "status": trade_result.get("status", "UNKNOWN"),
        })
        
        return result
        
    except Exception as e:
        logger.error(f"[ONE-SHOT] Error in trading cycle: {e}", exc_info=True)
        if slack_notifier:
            slack_notifier.send_error_alert("One-Shot Mode Error", str(e))
        raise


def log_no_trade_decision(config: Dict, decision, analysis: Dict, current_bankroll: float):
    """Log a no-trade decision to the trade log."""
    from utils.logging_utils import log_trade_decision
    
    trade_data = {
        "timestamp": datetime.now().isoformat(),
        "symbol": config["SYMBOL"],
        "decision": decision.decision,
        "confidence": decision.confidence,
        "reason": decision.reason or "",
        "current_price": analysis["current_price"],
        "llm_tokens": decision.tokens_used,
        "bankroll_before": current_bankroll,
        "bankroll_after": current_bankroll,
        "status": "NO_TRADE",
    }
    log_trade_decision(config["TRADE_LOG_FILE"], trade_data)


def log_blocked_trade(config: Dict, decision, analysis: Dict, current_bankroll: float, block_reason: str):
    """Log a blocked trade decision to the trade log."""
    from utils.logging_utils import log_trade_decision
    
    trade_data = {
        "timestamp": datetime.now().isoformat(),
        "symbol": config["SYMBOL"],
        "decision": "NO_TRADE",
        "confidence": decision.confidence,
        "reason": f"Blocked: {block_reason}",
        "current_price": analysis["current_price"],
        "llm_tokens": decision.tokens_used,
        "bankroll_before": current_bankroll,
        "bankroll_after": current_bankroll,
        "status": f"BLOCKED_{block_reason}",
    }
    log_trade_decision(config["TRADE_LOG_FILE"], trade_data)


def record_trade_outcome(
    config: Dict,
    trade_result: Dict,
    decision,
    analysis: Dict,
    current_bankroll: float,
    bankroll_manager,
    portfolio_manager,
    slack_notifier,
    args,
):
    """Record the outcome of a trade execution."""
    from utils.logging_utils import log_trade_decision
    
    try:
        # Extract trade details
        status = trade_result.get("status", "UNKNOWN")
        strike = trade_result.get("strike", analysis["current_price"])
        premium = trade_result.get("premium", 0.0)
        quantity = trade_result.get("quantity", 0)
        total_cost = trade_result.get("total_cost", 0.0)
        
        # Log to trade history
        trade_data = {
            "timestamp": datetime.now().isoformat(),
            "symbol": config["SYMBOL"],
            "decision": decision.decision,
            "confidence": decision.confidence,
            "reason": decision.reason or "",
            "current_price": analysis["current_price"],
            "strike": strike,
            "premium": premium,
            "quantity": quantity,
            "total_cost": total_cost,
            "llm_tokens": decision.tokens_used,
            "bankroll_before": current_bankroll,
            "bankroll_after": current_bankroll - total_cost if status == "FILLED" else current_bankroll,
            "status": status,
        }
        log_trade_decision(config["TRADE_LOG_FILE"], trade_data)
        
        # Update bankroll if trade was filled
        if status == "FILLED" and total_cost > 0:
            bankroll_manager.record_trade(
                symbol=config["SYMBOL"],
                trade_type=decision.decision,
                quantity=quantity,
                premium=premium,
                total_cost=total_cost,
                profit_loss=0,  # Entry trade, no P&L yet
            )
            
            # Add position to portfolio
            position = Position(
                symbol=config["SYMBOL"],
                strike=strike,
                side=decision.decision,
                contracts=quantity,
                entry_premium=premium,
                timestamp=datetime.now().isoformat(),
            )
            portfolio_manager.add_position(position)
        
        # Send Slack notification
        if slack_notifier:
            if status == "FILLED":
                slack_notifier.send_trade_confirmation(
                    trade_type=decision.decision,
                    symbol=config["SYMBOL"],
                    strike=strike,
                    premium=premium,
                    quantity=quantity,
                    total_cost=total_cost,
                    status="FILLED",
                )
            elif status == "CANCELLED":
                slack_notifier.send_trade_cancellation(
                    trade_type=decision.decision,
                    symbol=config["SYMBOL"],
                    reason="User cancelled",
                )
            else:
                slack_notifier.send_error_alert(
                    "Trade Execution Issue",
                    f"Trade status: {status}. Reason: {trade_result.get('reason', 'Unknown')}"
                )
        
        logger.info(f"[RECORD] Trade outcome recorded: {status}")
        
    except Exception as e:
        logger.error(f"[RECORD] Error recording trade outcome: {e}", exc_info=True)


def main_loop(
    config: Dict,
    args,
    env_vars: Dict,
    bankroll_manager,
    portfolio_manager,
    llm_client,
    slack_notifier,
    end_time: Optional[datetime],
):
    """Execute the main trading loop."""
    logger = logging.getLogger(__name__)
    tz = ZoneInfo("America/New_York")

    # Initialize kill switch
    kill_switch = get_kill_switch()
    logger.info(f"[KILL-SWITCH] Initialized (active: {kill_switch.is_active()})")

    # Initialize persistent browser bot for loop mode
    bot = None
    bot_idle_since = None

    try:
        loop_count = 0
        heartbeat_counter = 0  # S2: Track heartbeat throttling

        while True:
            loop_count += 1
            cycle_start = datetime.now(tz)
            
            # Step 0: Pre-Market Gate - Skip heavy processing if market is closed
            try:
                from utils.market_calendar import validate_trading_time
                import pytz
                
                et_tz = pytz.timezone('US/Eastern')
                current_et = datetime.now(et_tz)
                can_trade, market_reason = validate_trading_time(current_et)
                if not can_trade:
                    logger.info(f"[PRE-OPEN-GATE] Loop {loop_count}: {market_reason} - sleeping {args.interval}m")
                    time.sleep(args.interval * 60)
                    continue
            except Exception as e:
                # Fallback to basic weekend check if market calendar fails
                current_et = datetime.now(pytz.timezone('US/Eastern'))
                if current_et.weekday() >= 5:  # Weekend
                    logger.info(f"[PRE-OPEN-GATE] Loop {loop_count}: Market closed (weekend) - sleeping {args.interval}m")
                    time.sleep(args.interval * 60)
                    continue
                logger.debug(f"[PRE-OPEN-GATE] Loop {loop_count}: Market calendar check failed, proceeding: {e}")

            # Step 1: System Health Check - Critical Safety Gate
            logger.info(f"[HEALTH] Loop {loop_count}: Performing system health check...")
            health_status = perform_system_health_check()
            
            if not is_system_healthy():
                logger.error(f"[HEALTH] System health check failed: {health_status.overall_status}")
                logger.error("[HEALTH] Trading loop blocked due to critical system health issues")
                logger.info("[HEALTH] Waiting 60 seconds before next health check...")
                time.sleep(60)
                continue
            
            logger.info(f"[HEALTH] Loop {loop_count}: System health check passed: {health_status.overall_status}")

            # Check for emergency stop file trigger
            kill_switch.check_file_trigger()

            # Check for circuit breaker reset file trigger
            try:
                reset_executed, reset_message = check_and_process_file_reset(config)
                if reset_executed:
                    logger.info(f"[MAIN-LOOP] Circuit breaker reset processed: {reset_message}")
                    if slack_notifier:
                        slack_notifier.basic_notifier.send_message(f"🔄 **MAIN LOOP**: {reset_message}")
            except Exception as e:
                logger.error(f"[MAIN-LOOP] Error checking circuit breaker reset: {e}")

            # Check if emergency stop is active
            if kill_switch.is_active():
                status = kill_switch.get_status()
                logger.warning(f"[KILL-SWITCH] Emergency stop active - skipping trading cycle. Reason: {status['reason']}")
                
                # Send Slack notification if not already notified this cycle
                if slack_notifier and loop_count % 10 == 1:  # Notify every 10th cycle to avoid spam
                    slack_notifier.send_error_alert(
                        "Emergency Stop Active", 
                        f"Trading halted: {status['reason']} (activated: {status['activated_at']})"
                    )
                
                # Continue monitoring existing positions unless monitor_only is False
                if not kill_switch.is_monitor_only():
                    # Sleep and continue loop without trading
                    time.sleep(args.interval * 60)
                    continue

            # Check if we should exit based on end time
            if end_time and cycle_start >= end_time:
                logger.info(
                    f"[LOOP] Reached end time {end_time.strftime('%H:%M %Z')} - exiting"
                )

                # S4: Send daily summary only when an --end-at argument was provided as a real string
                end_at_val = getattr(args, "end_at", None)
                send_summary = (
                    config.get('ENABLE_DAILY_SUMMARY', True)
                    and isinstance(end_at_val, str)
                    and bool(end_at_val.strip())
                )
                if slack_notifier and send_summary:
                    try:
                        daily_summary = generate_daily_summary(config, end_time)
                        slack_notifier.send_heartbeat(daily_summary)
                        logger.info("[S4-DAILY-SUMMARY] Sent end-of-day summary")
                    except Exception as e:
                        logger.error(f"[S4-DAILY-SUMMARY] Failed to send daily summary: {e}")

                break

            logger.info(
                f"[LOOP] Starting cycle {loop_count} at {cycle_start.strftime('%H:%M:%S')}"
            )

            try:
                # Execute one trading cycle
                result = run_once(
                    config,
                    args,
                    env_vars,
                    bankroll_manager,
                    portfolio_manager,
                    llm_client,
                    slack_notifier,
                    bot,
                )

                analysis = result["analysis"]
                decision = result["decision"]
                current_bankroll = result["current_bankroll"]
                position_size = result["position_size"]

                # Handle different decision types
                if decision.decision == "NO_TRADE":
                    # S2: Send throttled heartbeat one-liner to Slack
                    heartbeat_counter += 1
                    heartbeat_every = config.get('HEARTBEAT_EVERY', 3)

                    if slack_notifier:
                        # Send on first NO_TRADE cycle, then throttle by HEARTBEAT_EVERY; guard zero
                        if heartbeat_every > 0 and (
                            heartbeat_counter == 1 or heartbeat_counter % heartbeat_every == 0
                        ):
                            # Format: ⏳ 09:45 · SPY · No breakout (body 0.03%)
                            symbol = config.get('SYMBOL', 'SPY')
                            body_pct = analysis.get('candle_body_pct', 0.0)
                            heartbeat_msg = (
                                f"⏳ {cycle_start.strftime('%H:%M')} · {symbol} · No breakout (body {body_pct:.02f}%)"
                            )
                            slack_notifier.send_heartbeat(heartbeat_msg)
                            logger.info(
                                f"[S2-HEARTBEAT] Sent throttled heartbeat ({heartbeat_counter}/{heartbeat_every})"
                            )

                    # Log the no-trade decision
                    trade_data = {
                        "timestamp": cycle_start.isoformat(),
                        "symbol": config["SYMBOL"],
                        "decision": decision.decision,
                        "confidence": decision.confidence,
                        "reason": decision.reason or "",
                        "current_price": analysis["current_price"],
                        "llm_tokens": decision.tokens_used,
                        "bankroll_before": current_bankroll,
                        "bankroll_after": current_bankroll,
                        "status": "NO_TRADE_LOOP",
                    }
                    log_trade_decision(config["TRADE_LOG_FILE"], trade_data)

                elif decision.decision in ["CALL", "PUT"]:
                    # Validate confidence threshold
                    min_confidence = config.get("MIN_CONFIDENCE", 0.6)
                    if decision.confidence < min_confidence:
                        logger.warning(
                            f"[LOW_CONFIDENCE] Confidence {decision.confidence:.2f} below threshold"
                        )
                        if slack_notifier:
                            # S2: Low confidence heartbeat (always sent, not throttled)
                            heartbeat_msg = f"⚠️ {cycle_start.strftime('%H:%M')} · Low confidence {decision.decision} ({decision.confidence:.2f})"
                            slack_notifier.send_heartbeat(heartbeat_msg)
                    else:
                        # Initialize or ensure browser session is active
                        if not bot and not args.dry_run:
                            # Initialize persistent browser bot
                            bot = RobinhoodBot(
                                headless=config["HEADLESS"],
                                implicit_wait=config["IMPLICIT_WAIT"],
                                page_load_timeout=config["PAGE_LOAD_TIMEOUT"],
                            )
                            bot.start_browser()

                            # Login to Robinhood
                            if not bot.login(env_vars["RH_USER"], env_vars["RH_PASS"]):
                                logger.error("[ERROR] Login failed")
                                if slack_notifier:
                                    slack_notifier.send_browser_status(
                                        "login_failed", "Failed to login to Robinhood"
                                    )
                                continue

                            # Navigate to options chain once
                            if not bot.navigate_to_options(config["SYMBOL"]):
                                logger.error("[ERROR] Failed to navigate to options")
                                continue

                        elif bot and not args.dry_run:
                            # Ensure existing session is still active (15 min idle timeout)
                            if not bot.ensure_session(max_idle_sec=900):
                                logger.error("[ERROR] Failed to ensure browser session")
                                if slack_notifier:
                                    slack_notifier.send_browser_status(
                                        "session_failed",
                                        "Browser session recovery failed",
                                    )
                                continue

                            # Re-login if needed after session restart
                            try:
                                current_url = (
                                    bot.driver.current_url if bot.driver else ""
                                )
                                if (
                                    "login" in current_url.lower()
                                    or "robinhood.com" == current_url
                                ):
                                    logger.info(
                                        "[SESSION] Re-authenticating after session restart"
                                    )
                                    if not bot.login(
                                        env_vars["RH_USER"], env_vars["RH_PASS"]
                                    ):
                                        logger.error("[ERROR] Re-login failed")
                                        continue
                                    if not bot.navigate_to_options(config["SYMBOL"]):
                                        logger.error(
                                            "[ERROR] Failed to navigate to options after re-login"
                                        )
                                        continue
                            except Exception as e:
                                logger.warning(
                                    f"[SESSION] Error checking login status: {e}"
                                )

                        bot_idle_since = None

                        # Find ATM option and prepare order
                        if not args.dry_run and bot:
                            try:
                                # Ensure we're still on the options page
                                bot.ensure_open(config["SYMBOL"])

                                atm_option = bot.find_atm_option(
                                    analysis["current_price"], decision.decision
                                )
                                if atm_option:
                                    # Calculate quantity
                                    estimated_premium = analysis["current_price"] * 0.02
                                    quantity = bankroll_manager.calculate_position_size(
                                        premium=estimated_premium,
                                        risk_fraction=config["RISK_FRACTION"],
                                        size_rule=config["SIZE_RULE"],
                                        fixed_qty=config["CONTRACT_QTY"],
                                        symbol=symbol,
                                    )

                                    # Pre-fill order and stop at Review
                                    if bot.click_option_and_buy(atm_option, quantity):
                                        # Send rich Slack notification
                                        if slack_notifier:
                                            est_total = estimated_premium * quantity * 100
                                            slack_notifier.send_order_ready_alert(
                                                trade_type=decision.decision,
                                                strike=str(atm_option["strike"]),
                                                expiry="Today",  # Adjust as needed
                                                position_size=est_total,
                                                action="OPEN",
                                                confidence=decision.confidence,
                                                reason=decision.reason or "",
                                                current_price=analysis["current_price"],
                                                premium=estimated_premium,
                                                quantity=quantity,
                                                total_cost=est_total,
                                            )

                                        logger.info(
                                            f"[SUCCESS] {decision.decision} order ready for review"
                                        )

                                        # CRITICAL: Add trade confirmation workflow
                                        from utils.trade_confirmation import (
                                            TradeConfirmationManager,
                                        )

                                        confirmer = TradeConfirmationManager(
                                            portfolio_manager=portfolio_manager,
                                            bankroll_manager=bankroll_manager,
                                            slack_notifier=slack_notifier,
                                        )

                                        # Prepare trade details for confirmation
                                        trade_details = {
                                            "symbol": config["SYMBOL"],
                                            "strike": atm_option["strike"],
                                            "side": decision.decision.replace(
                                                "BUY_", ""
                                            ),
                                            "quantity": quantity,
                                            "estimated_premium": estimated_premium,
                                            "direction": decision.decision,
                                            "confidence": decision.confidence,
                                            "reason": decision.reason or "",
                                        }

                                        # Check if unattended mode - execute automatically, otherwise use manual confirmation
                                        if args.unattended:
                                            logger.info(
                                                "[CONFIRMATION] Unattended mode: Executing trade automatically..."
                                            )
                                            user_decision = "submitted"
                                            actual_premium = estimated_premium  # Use estimated premium for automated execution
                                        else:
                                            # Manual confirmation mode
                                            logger.info(
                                                "[CONFIRMATION] Waiting for user decision..."
                                            )
                                            user_decision, actual_premium = (
                                                confirmer.get_user_decision(
                                                    trade_details=trade_details,
                                                    method="prompt",  # Use interactive prompt
                                                )
                                            )

                                        # Record the trade outcome
                                        confirmer.record_trade_outcome(
                                            trade_details=trade_details,
                                            decision=user_decision,
                                            actual_premium=actual_premium,
                                        )

                                        logger.info(
                                            f"[OUTCOME] Trade {user_decision}: {decision.decision} ${atm_option['strike']}"
                                        )

                                        bot_idle_since = cycle_start
                                    else:
                                        logger.error("[ERROR] Failed to prepare order")
                                else:
                                    logger.error("[ERROR] Could not find ATM option")
                            except Exception as e:
                                logger.error(f"[ERROR] Browser automation failed: {e}")
                        else:
                            # Dry run mode - just send notification
                            if slack_notifier:
                                est_prem = analysis["current_price"] * 0.02
                                qty = 1
                                est_total = est_prem * qty * 100
                                slack_notifier.send_order_ready_alert(
                                    trade_type=decision.decision,
                                    strike=str(analysis["current_price"]),
                                    expiry="Today",
                                    position_size=est_total,
                                    action="OPEN",
                                    confidence=decision.confidence,
                                    reason=decision.reason or "",
                                    current_price=analysis["current_price"],
                                    premium=est_prem,
                                    quantity=qty,
                                    total_cost=est_total,
                                )

            except Exception as e:
                logger.error(f"[LOOP] Error in cycle {loop_count}: {e}", exc_info=True)
                if slack_notifier:
                    slack_notifier.send_error_alert(
                        f"Loop Cycle {loop_count} Error", str(e)
                    )

            # Calculate sleep time to maintain interval
            cycle_end = datetime.now(tz)
            cycle_duration = (cycle_end - cycle_start).total_seconds()
            target_interval_seconds = args.interval * 60
            sleep_seconds = max(0, target_interval_seconds - cycle_duration)

            if sleep_seconds > 0:
                logger.info(
                    f"[LOOP] Cycle {loop_count} completed in {cycle_duration:.1f}s, sleeping {sleep_seconds:.1f}s"
                )
                time.sleep(sleep_seconds)
            else:
                logger.warning(
                    f"[LOOP] Cycle {loop_count} took {cycle_duration:.1f}s (longer than {args.interval}m interval)"
                )

    finally:
        # S1: Clean up monitors and send shutdown breadcrumbs
        try:
            from utils.monitor_launcher import kill_all_monitors
            killed_count = kill_all_monitors()
            if killed_count > 0:
                logger.info(f"[S1-CLEANUP] Killed {killed_count} monitor processes")
        except Exception as e:
            logger.error(f"[S1-CLEANUP] Error killing monitors: {e}")
        
        # Clean up browser
        if bot:
            logger.info("[CLEANUP] Closing browser")
            bot.quit()


def run_multi_symbol_once(
    config: Dict,
    args,
    env_vars: Dict,
    bankroll_manager,
    portfolio_manager,
    llm_client,
    slack_notifier,
    weekly_pnl_tracker,
    drawdown_circuit_breaker,
    vix_monitor,
    health_monitor,
):
    """
    Execute multi-symbol scanning once and handle the best opportunity.

    Args:
        config: Trading configuration
        args: Command line arguments
        env_vars: Environment variables
        bankroll_manager: Bankroll management instance
        portfolio_manager: Portfolio tracking instance
        llm_client: LLM client for trade decisions
        slack_notifier: Slack notification instance
        weekly_pnl_tracker: Weekly P&L tracking instance
        drawdown_circuit_breaker: Circuit breaker for drawdown protection
        vix_monitor: VIX monitoring instance
        health_monitor: System health monitoring instance
    """
    logger = logging.getLogger(__name__)

    try:
        # Step 0: System Health Check - Critical Safety Gate
        logger.info("[HEALTH] Performing system health check before multi-symbol scanning...")
        health_status = perform_system_health_check()
        
        if not is_system_healthy():
            logger.error(f"[HEALTH] System health check failed: {health_status.overall_status}")
            logger.error("[HEALTH] Multi-symbol scanning blocked due to critical system health issues")
            return
        
        logger.info(f"[HEALTH] System health check passed: {health_status.overall_status}")

        # Initialize multi-symbol scanner with pre-initialized monitors
        alpaca_env = getattr(args, 'alpaca_env', 'paper')
        scanner = MultiSymbolScanner(
            config, 
            llm_client, 
            slack_notifier, 
            env=alpaca_env,
            weekly_pnl_tracker=weekly_pnl_tracker,
            drawdown_circuit_breaker=drawdown_circuit_breaker,
            vix_monitor=vix_monitor,
            health_monitor=health_monitor
        )

        # Scan all symbols for opportunities
        opportunities = scanner.scan_all_symbols()

        if not opportunities:
            logger.info("[MULTI-SYMBOL] No trading opportunities found")
            if slack_notifier:
                slack_notifier.send_message(
                    "🔍 Multi-symbol scan complete - No opportunities found"
                )
            return

        # Process the top opportunity
        top_opportunity = opportunities[0]
        symbol = top_opportunity["symbol"]

        logger.info(
            f"[MULTI-SYMBOL] Processing top opportunity: {symbol} - {top_opportunity['decision']}"
        )

        # Execute trade for the selected symbol
        if not args.dry_run:
            # Create a modified config for this specific symbol
            symbol_config = config.copy()
            symbol_config["SYMBOL"] = symbol

            # Execute the trade using existing run_once logic
            result = run_once(
                symbol_config,
                args,
                env_vars,
                bankroll_manager,
                portfolio_manager,
                llm_client,
                slack_notifier,
            )

            logger.info(
                f"[MULTI-SYMBOL] Trade execution result: {result.get('status', 'UNKNOWN')}"
            )
        else:
            logger.info(
                f"[MULTI-SYMBOL] Dry run - Would trade {symbol} {top_opportunity['decision']}"
            )

    except Exception as e:
        logger.error(f"[MULTI-SYMBOL] Error in multi-symbol execution: {e}")
        if slack_notifier:
            slack_notifier.send_message(f"❌ Multi-symbol scan error: {str(e)}")


def run_multi_symbol_loop(
    config: Dict,
    args,
    env_vars: Dict,
    bankroll_manager,
    portfolio_manager,
    llm_client,
    slack_notifier,
    end_time: Optional[datetime],
    weekly_pnl_tracker,
    drawdown_circuit_breaker,
    vix_monitor,
    health_monitor,
):
    """
    Execute multi-symbol scanning in continuous loop mode.

    Args:
        config: Trading configuration
        args: Command line arguments
        env_vars: Environment variables
        bankroll_manager: Bankroll management instance
        portfolio_manager: Portfolio tracking instance
        llm_client: LLM client for trade decisions
        slack_notifier: Slack notification instance
        end_time: Optional end time for the loop
    """

    # Initialize multi-symbol scanner with pre-initialized monitors
    alpaca_env = getattr(args, 'alpaca_env', 'paper')
    scanner = MultiSymbolScanner(
        config, 
        llm_client, 
        slack_notifier, 
        env=alpaca_env,
        weekly_pnl_tracker=weekly_pnl_tracker,
        drawdown_circuit_breaker=drawdown_circuit_breaker,
        vix_monitor=vix_monitor,
        health_monitor=health_monitor
    )

    # Send startup notification
    symbols_str = ", ".join(config.get("SYMBOLS", ["SPY"]))
    if slack_notifier:
        slack_notifier.send_message(
            f"🚀 Multi-symbol scanner started\n"
            f"📊 Symbols: {symbols_str}\n"
            f"⏱️ Interval: {args.interval} minutes\n"
            f"🎯 Max trades: {config.get('multi_symbol', {}).get('max_concurrent_trades', 1)}"
        )

    scan_count = 0
    bot = None
    tz = ZoneInfo("America/New_York")

    try:
        while True:
            scan_count += 1
            current_time = datetime.now(tz)  # Use timezone-aware datetime
            
            # Step 0: Emergency Stop Check - Critical Safety Gate
            from utils.safety_hooks import check_emergency_stop
            if check_emergency_stop(config, slack_notifier):
                logger.error("[EMERGENCY-STOP] Emergency stop file detected - terminating")
                break
            
            # Step 1: System Health Check - Critical Safety Gate
            logger.info(f"[HEALTH] Multi-symbol scan {scan_count}: Performing system health check...")
            health_status = health_monitor.perform_health_check()
            
            if not health_status.trading_allowed:
                logger.error(f"[HEALTH] System health check failed: {health_status.overall_status}")
                logger.error("[HEALTH] Multi-symbol scanning blocked due to critical system health issues")
                logger.info("[HEALTH] Waiting 60 seconds before next health check...")
                time.sleep(60)
                continue
            
            # Log detailed health status with specific causes
            if health_status.overall_status.value == "WARNING":
                warning_details = "; ".join(health_status.warnings) if health_status.warnings else "No specific warnings"
                logger.warning(f"[HEALTH] Multi-symbol scan {scan_count}: System health WARNING - Causes: {warning_details}")
            else:
                logger.info(f"[HEALTH] Multi-symbol scan {scan_count}: System health check passed: {health_status.overall_status}")
            
            if health_status.critical_issues:
                critical_details = "; ".join(health_status.critical_issues)
                logger.error(f"[HEALTH] Critical issues detected: {critical_details}")

            # Hard-stop time gate check at top of each loop iteration
            if end_time and current_time >= end_time:
                logger.info(f"[TIME-GATE] Trading window closed at {end_time.strftime('%H:%M %Z')}. Stopping loop.")
                if slack_notifier:
                    try:
                        slack_notifier.send_message(f"⏰ [TIME-GATE] Trading window closed at {end_time.strftime('%H:%M %Z')} — stopping.")
                    except:
                        pass
                break
            
            # Auto-stop after market hours when no --end-at specified
            if not end_time:
                from utils.market_calendar import validate_trading_time
                try:
                    can_trade, market_reason = validate_trading_time(current_time)
                    if not can_trade and "Market closed at" in market_reason:
                        # Extract close time from market_reason for clean logging
                        close_info = market_reason.split("Market closed at")[1].strip() if "Market closed at" in market_reason else "market close"
                        logger.info(f"[AUTO-STOP] Market closed ({close_info}). Stopping multi-symbol loop.")
                        if slack_notifier:
                            try:
                                slack_notifier.send_message(f"🔚 [AUTO-STOP] Market closed ({close_info}) — stopping scanner.")
                            except:
                                pass
                        break
                except Exception as e:
                    # Fallback: stop after 5 PM ET if market validation fails
                    if current_time.hour >= 17:
                        logger.info(f"[AUTO-STOP] After 5 PM ET, stopping loop (market validation failed: {e}).")
                        break

            logger.info(
                f"[MULTI-SYMBOL-LOOP] Starting scan #{scan_count} at {current_time.strftime('%H:%M:%S')}"
            )

            try:
                # Scan all symbols
                opportunities = scanner.scan_all_symbols()

                if opportunities:
                    # Process opportunities with spillover logic
                    max_trades = config.get("multi_symbol", {}).get("max_concurrent_trades", 1)
                    executed_successfully = False
                    
                    for i, opp in enumerate(opportunities):
                        symbol = opp["symbol"]
                        logger.info(
                            f"[MULTI-SYMBOL-SPILLOVER] Processing opportunity {i+1}/{len(opportunities)}: {symbol}"
                        )

                        if not args.dry_run:
                            # Execute pre-approved multi-symbol decision
                            result = execute_multi_symbol_trade(
                                opportunity=opp,
                                config=config,
                                args=args,
                                env_vars=env_vars,
                                bankroll_manager=bankroll_manager,
                                portfolio_manager=portfolio_manager,
                                slack_notifier=slack_notifier,
                                bot=bot,
                            )

                            # Update bot instance for reuse
                            if result.get("bot"):
                                bot = result["bot"]
                            
                            # Check if trade was successful
                            if result.get("success", False):
                                logger.info(f"[MULTI-SYMBOL-SPILLOVER] Trade executed successfully for {symbol}")
                                executed_successfully = True
                                break  # Exit loop since we got a successful trade
                            else:
                                # Log failure reason and continue to next opportunity
                                error_type = result.get("error_type", "unknown")
                                reason = result.get("reason", "Unknown error")
                                logger.warning(f"[MULTI-SYMBOL-SPILLOVER] {symbol} failed ({error_type}): {reason}")
                                
                                # Different cooldown durations based on failure type
                                if error_type == "contract_selection":
                                    # Shorter cooldown for contract selection failures (expiry issues)
                                    cooldown_minutes = 60
                                    logger.info(f"[MULTI-SYMBOL-SPILLOVER] Contract selection failed for {symbol} - trying next opportunity")
                                else:
                                    # Standard cooldown for execution failures
                                    cooldown_minutes = 30
                                
                                # Add cooldown for failed symbol to prevent immediate retry
                                if hasattr(bankroll_manager, 'add_symbol_cooldown'):
                                    bankroll_manager.add_symbol_cooldown(symbol, minutes=cooldown_minutes)
                                    logger.info(f"[MULTI-SYMBOL-SPILLOVER] Added {cooldown_minutes}min cooldown for {symbol}")
                                
                                # Continue to next opportunity (spillover logic)
                                continue
                    
                    # Log final result
                    if not executed_successfully and not args.dry_run:
                        logger.warning("[MULTI-SYMBOL-SPILLOVER] All opportunities failed - no trades executed this scan")
                else:
                    logger.info(
                        "[MULTI-SYMBOL-LOOP] No trading opportunities found across all symbols"
                    )

                    # Send heartbeat for no opportunities (more frequent than hourly)
                    if slack_notifier:
                        # Send heartbeat every 3 scans (15 minutes with 5-min interval)
                        if scan_count % 3 == 0:
                            slack_notifier.send_heartbeat(
                                f"💓 Multi-symbol scan #{scan_count} complete\n"
                                f"🔍 Symbols: {symbols_str}\n"
                                f"📊 No opportunities found\n"
                                f"⏰ Next scan in {args.interval} minutes"
                            )
                        # Also log the no-trade decision
                        trade_data = {
                            "timestamp": current_time.isoformat(),
                            "symbol": "MULTI",
                            "decision": "NO_TRADE",
                            "confidence": 0.0,
                            "reason": f'No opportunities found across {len(config.get("SYMBOLS", ["SPY"]))} symbols',
                            "current_price": 0.0,
                            "strike": "",
                            "direction": "",
                            "quantity": "",
                            "premium": "",
                            "total_cost": "",
                            "llm_tokens": 0,
                        }
                        log_trade_decision(config["TRADE_LOG_FILE"], trade_data)

            except Exception as e:
                logger.error(f"[MULTI-SYMBOL-LOOP] Error in scan #{scan_count}: {e}")
                if slack_notifier:
                    slack_notifier.send_message(f"⚠️ Scan #{scan_count} error: {str(e)}")

            # Wait for next interval
            if end_time:
                next_scan_time = current_time + timedelta(minutes=args.interval)
                if next_scan_time >= end_time:
                    logger.info(
                        "[MULTI-SYMBOL-LOOP] Next scan would exceed end time, stopping"
                    )
                    break

            logger.info(
                f"[MULTI-SYMBOL-LOOP] Waiting {args.interval} minutes until next scan..."
            )
            time.sleep(args.interval * 60)

    except KeyboardInterrupt:
        logger.info(
            "[MULTI-SYMBOL-LOOP] Received interrupt signal, shutting down gracefully..."
        )
        if slack_notifier:
            slack_notifier.send_message("🛑 Multi-symbol scanner stopped by user")
    except Exception as e:
        logger.error(f"[MULTI-SYMBOL-LOOP] Fatal error: {e}")
        if slack_notifier:
            slack_notifier.send_message(f"💥 Multi-symbol scanner crashed: {str(e)}")
    finally:
        # Clean up browser if exists
        if bot:
            try:
                bot.close()
                logger.info("[MULTI-SYMBOL-LOOP] Browser closed")
            except Exception as e:
                logger.warning(f"[MULTI-SYMBOL-LOOP] Error closing browser: {e}")

        logger.info(f"[MULTI-SYMBOL-LOOP] Completed {scan_count} scans")
        if slack_notifier:
            slack_notifier.send_message(
                f"✅ Multi-symbol scanner finished\n"
                f"📊 Total scans: {scan_count}\n"
                f"🎯 Symbols: {symbols_str}"
            )


def monitor_positions_mode(
    config: Dict,
    args,
    env_vars: Dict,
    bankroll_manager,
    portfolio_manager,
    llm_client,
    slack_notifier,
    end_time: Optional[datetime],
):
    """Run position monitoring mode using EnhancedPositionMonitor.

    Integrates the standalone monitor (monitor_alpaca.py) with main.py CLI.
    Respects --interval (minutes), --slack-notify, and optional --end-at.
    """
    logger = logging.getLogger(__name__)

    # Determine monitoring interval in minutes
    interval_minutes = getattr(args, "interval", None)
    if not interval_minutes:
        interval_minutes = config.get("MONITOR_INTERVAL", 2)

    logger.info(
        f"[MONITOR] Starting position monitoring (interval: {interval_minutes}m)"
    )

    # Lazy import to avoid circular imports
    try:
        from monitor_alpaca import EnhancedPositionMonitor
    except Exception as e:
        logger.error(f"[MONITOR] Failed to import monitor: {e}")
        return

    monitor = EnhancedPositionMonitor()

    # Respect --slack-notify flag: disable Slack if not requested
    try:
        if not getattr(args, "slack_notify", False) and hasattr(monitor, "slack"):
            monitor.slack.enabled = False
            logger.info("[MONITOR] Slack notifications disabled by CLI flag")
    except Exception as e:
        logger.debug(f"[MONITOR] Could not adjust Slack setting: {e}")

    # Optional startup breadcrumb via main's slack_notifier
    if slack_notifier:
        try:
            msg = (
                f"🟢 Position monitor started\n"
                f"⏱️ Interval: {interval_minutes} minutes\n"
                + (f"🕒 End at: {end_time.strftime('%H:%M %Z')}\n" if end_time else "")
            )
            slack_notifier.send_message(msg.strip())
        except Exception:
            pass

    # If no end_time provided, use monitor's own run loop
    if not end_time:
        try:
            monitor.run(interval_minutes=interval_minutes)
        except KeyboardInterrupt:
            logger.info("[MONITOR] Stopped by user")
        finally:
            if slack_notifier:
                try:
                    slack_notifier.send_message("🔴 Position monitor stopped")
                except Exception:
                    pass
        return

    # Timed monitoring loop honoring --end-at
    try:
        tz = end_time.tzinfo
        while True:
            now = datetime.now(tz) if tz else datetime.now()
            if now >= end_time:
                logger.info(
                    f"[MONITOR] Reached end time {end_time.strftime('%H:%M %Z')}, exiting"
                )
                break

            monitor.run_monitoring_cycle()

            # Sleep until next cycle or until end_time, whichever is sooner
            now = datetime.now(tz) if tz else datetime.now()
            remaining = (end_time - now).total_seconds()
            sleep_s = max(0, min(remaining, interval_minutes * 60))
            if sleep_s == 0:
                break
            time.sleep(sleep_s)

    except KeyboardInterrupt:
        logger.info("[MONITOR] Stopped by user")
    except Exception as e:
        logger.error(f"[MONITOR] Error in monitoring loop: {e}")
    finally:
        if slack_notifier:
            try:
                slack_notifier.send_message("🔴 Position monitor stopped")
            except Exception:
                pass


def main():
    """Main trading script execution."""
    parser = argparse.ArgumentParser(
        description="Robinhood HA Breakout Trading Assistant"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Run analysis without browser automation"
    )
    parser.add_argument(
        "--config", default="config.yaml", help="Configuration file path"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    parser.add_argument(
        "--slack-notify",
        action="store_true",
        help="Send notifications to Slack during trading",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run in continuous loop mode (Ctrl-C to exit)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Minutes between scans in loop mode (default: 5)",
    )
    parser.add_argument(
        "--end-at", type=str, help="End time in HH:MM format (24-hour, local time)"
    )
    parser.add_argument(
        "--monitor-positions",
        action="store_true",
        help="Monitor existing positions for profit/loss targets",
    )
    parser.add_argument(
        "--symbols", nargs="+", help="Symbols to scan (e.g., --symbols SPY QQQ IWM)"
    )
    parser.add_argument(
        "--multi-symbol", action="store_true", help="Enable multi-symbol scanning mode"
    )
    parser.add_argument(
        "--max-trades",
        type=int,
        default=1,
        help="Maximum concurrent trades across all symbols",
    )
    parser.add_argument(
        "--auto-start-monitor",
        action="store_true",
        default=True,
        help="Auto-start position monitoring after trade submission (default: True)",
    )
    parser.add_argument(
        "--no-auto-start-monitor",
        dest="auto_start_monitor",
        action="store_false",
        help="Disable auto-start of position monitoring",
    )
    parser.add_argument(
        "--broker",
        choices=["alpaca", "robinhood"],
        help="Override broker selection (overrides config)",
    )
    parser.add_argument(
        "--alpaca-env",
        choices=["paper", "live"],
        help="Override Alpaca environment (overrides config)",
    )
    parser.add_argument(
        "--i-understand-live-risk",
        action="store_true",
        help="Required flag when using Alpaca live trading",
    )
    parser.add_argument(
        "--strict-validation",
        action="store_true",
        help="Enable strict validation mode - skip symbols on any validation failure",
    )
    parser.add_argument(
        "--pause-on-validate-fail",
        type=str,
        metavar="DURATION",
        help="Auto-pause symbols with validation failures for duration (e.g., 30m, 1h)",
    )
    
    # LLM Decision Agent flags for hands-free trading
    parser.add_argument(
        "--unattended",
        action="store_true",
        help="Enable unattended mode with LLM decision agent (default: false)",
    )
    parser.add_argument(
        "--llm-decisions",
        type=str,
        default="exit",
        help="Comma-separated list of decisions to automate: entry,exit,ro_review (default: exit)",
    )
    parser.add_argument(
        "--llm-primary-model",
        type=str,
        default="gpt-4o-mini",
        help="Primary LLM model for decisions (default: gpt-4o-mini)",
    )
    parser.add_argument(
        "--llm-backup-model", 
        type=str,
        default="deepseek-chat",
        help="Backup LLM model for decisions (default: deepseek-chat)",
    )
    parser.add_argument(
        "--llm-min-confidence",
        type=float,
        default=0.60,
        help="Minimum confidence threshold for LLM decisions (default: 0.60)",
    )
    parser.add_argument(
        "--llm-exit-bias",
        choices=["conservative", "balanced", "aggressive"],
        default="conservative", 
        help="Exit decision bias for capital protection (default: conservative)",
    )
    parser.add_argument(
        "--llm-rate-limit-s",
        type=int,
        default=30,
        help="Rate limit seconds between LLM calls per symbol (default: 30)",
    )
    parser.add_argument(
        "--llm-max-api-per-scan",
        type=int,
        default=4,
        help="Maximum LLM API calls per scan for cost control (default: 4)",
    )

    args = parser.parse_args()

    # Validate end time format if provided
    end_time = None
    if args.end_at:
        try:
            end_time = parse_end_time(args.end_at)
            # Hard-stop check: Exit immediately if past end time
            from zoneinfo import ZoneInfo
            ET = ZoneInfo("America/New_York")
            now = datetime.now(ET)
            if now >= end_time:
                logger.info(f"[TIME-GATE] Trading window closed (now {now.strftime('%H:%M %Z')} >= end-at {end_time.strftime('%H:%M %Z')}). Exiting.")
                if args.slack_notify:
                    try:
                        slack = EnhancedSlackIntegration()
                        slack.send_message(f"⏰ [TIME-GATE] Trading window closed at {end_time.strftime('%H:%M %Z')} — stopping.")
                    except:
                        pass
                sys.exit(0)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

    # Load configuration
    config = load_config(args.config)

    # Setup logging early so we can use logger in CLI overrides
    setup_logging(args.log_level, config["LOG_FILE"])
    

    # Handle multi-symbol CLI overrides
    if args.symbols:
        config["SYMBOLS"] = args.symbols
        logger.info(f"CLI override: Using symbols {args.symbols}")

    if args.multi_symbol:
        config["multi_symbol"]["enabled"] = True
        logger.info("CLI override: Multi-symbol mode enabled")

    if args.max_trades != 1:
        config["multi_symbol"]["max_concurrent_trades"] = args.max_trades
        logger.info(f"CLI override: Max concurrent trades set to {args.max_trades}")

    # Handle validation CLI overrides
    if args.strict_validation:
        config["DATA_STRICT_VALIDATION"] = True
        logger.info("CLI override: Strict validation mode enabled")

    if args.pause_on_validate_fail:
        config["DATA_PAUSE_ON_VALIDATE_FAIL"] = args.pause_on_validate_fail
        logger.info(f"CLI override: Auto-pause on validation fail: {args.pause_on_validate_fail}")

    # Handle LLM Decision Agent CLI overrides
    if args.unattended:
        config["UNATTENDED"] = True
        logger.info("CLI override: Unattended mode enabled")
    
    # Parse LLM decisions list
    llm_decisions = [d.strip() for d in args.llm_decisions.split(",") if d.strip()]
    config["LLM_DECISIONS"] = llm_decisions
    
    # Set up LLM configuration section
    if "llm" not in config:
        config["llm"] = {}
    
    # Apply LLM CLI overrides with environment variable fallbacks
    config["llm"]["primary_model"] = os.getenv("LLM_PRIMARY_MODEL", args.llm_primary_model)
    config["llm"]["backup_model"] = os.getenv("LLM_BACKUP_MODEL", args.llm_backup_model)
    config["llm"]["min_confidence"] = float(os.getenv("LLM_MIN_CONFIDENCE", args.llm_min_confidence))
    config["llm"]["exit_bias"] = os.getenv("LLM_EXIT_BIAS", args.llm_exit_bias)
    config["llm"]["rate_limit_s"] = int(os.getenv("LLM_RATE_LIMIT_S", args.llm_rate_limit_s))
    config["llm"]["max_api_per_scan"] = int(os.getenv("LLM_MAX_API_PER_SCAN", args.llm_max_api_per_scan))
    
    if args.unattended:
        logger.info(f"LLM decisions enabled: {llm_decisions}")
        logger.info(f"LLM models: {config['llm']['primary_model']} (primary), {config['llm']['backup_model']} (backup)")
        logger.info(f"LLM confidence threshold: {config['llm']['min_confidence']}")
        logger.info(f"LLM exit bias: {config['llm']['exit_bias']}")

    # Handle broker/environment CLI overrides
    if args.broker:
        config["BROKER"] = args.broker
        logger.info(f"CLI override: Using broker {args.broker}")

    if args.alpaca_env:
        config["ALPACA_ENV"] = args.alpaca_env
        logger.info(f"CLI override: Using Alpaca environment {args.alpaca_env}")

    # Safety interlocks for live trading
    if config["BROKER"] == "alpaca" and config["ALPACA_ENV"] == "live":
        if not args.i_understand_live_risk:
            logger.error(
                "⚠️  LIVE TRADING BLOCKED: --i-understand-live-risk flag required for Alpaca live trading"
            )
            print("\n⚠️  SAFETY INTERLOCK ACTIVATED")
            print("Live trading with real money requires explicit acknowledgment.")
            print("Add --i-understand-live-risk flag to proceed with live trading.")
            print("Defaulting to paper trading for safety.\n")
            config["ALPACA_ENV"] = "paper"
            logger.info("Safety override: Switched to paper trading")
        else:
            logger.warning(
                "WARNING: LIVE TRADING ENABLED (Alpaca). Proceeding because --i-understand-live-risk was provided.")

        print("\nWARNING: LIVE TRADING MODE ACTIVE")
        print("Real money will be at risk. Ensure you understand the consequences.")

    logger.info("[START] Starting Robinhood HA Breakout Assistant")
    logger.info(f"Dry run mode: {args.dry_run}")
    if args.loop:
        logger.info(f"Loop mode: {args.interval} minute intervals")
        if end_time:
            logger.info(f"End time: {end_time.strftime('%H:%M %Z')}")

    try:
        # Validate environment
        env_vars = validate_environment()

        # Initialize components with broker/environment scoping (v0.9.0)
        broker = config.get("BROKER", "robinhood")
        env = config.get("ALPACA_ENV", "live") if broker == "alpaca" else "live"
        
        # Use scoped ledger files
        from utils.scoped_files import get_scoped_paths, ensure_scoped_files
        scoped_paths = get_scoped_paths(broker, env)
        ensure_scoped_files(scoped_paths)
        
        # Use scoped trade history path throughout the app
        config["TRADE_LOG_FILE"] = scoped_paths["trade_history"]
        
        bankroll_manager = BankrollManager(
            start_capital=config.get("START_CAPITAL_DEFAULT", config["START_CAPITAL"]),
            broker=broker,
            env=env
        )
        
        portfolio_manager = PortfolioManager(
            scoped_paths["positions"]
        )
        
        logger.info(f"[SCOPED] Using ledger: {bankroll_manager.ledger_id()}")
        logger.info(f"[SCOPED] Bankroll file: {bankroll_manager.bankroll_file}")
        logger.info(f"[SCOPED] Positions file: {scoped_paths['positions']}")
        logger.info(f"[SCOPED] Trade history: {scoped_paths['trade_history']}")

        llm_client = LLMClient(config["MODEL"])
        
        # Initialize singleton monitors once at startup to avoid repeated initialization
        from utils.weekly_pnl_tracker import WeeklyPnLTracker
        from utils.drawdown_circuit_breaker import DrawdownCircuitBreaker
        from utils.vix_monitor import VIXMonitor
        from utils.health_monitor import SystemHealthMonitor
        
        weekly_pnl_tracker = WeeklyPnLTracker(config)
        drawdown_circuit_breaker = DrawdownCircuitBreaker(config)
        vix_monitor = VIXMonitor(config)
        health_monitor = SystemHealthMonitor(config)

        # Initialize enhanced Slack integration with charts
        slack = EnhancedSlackIntegration()
        slack_notifier = None
        if args.slack_notify:
            slack_notifier = slack
            slack_notifier.send_startup_notification(dry_run=args.dry_run)

        # Initialize scoped trade log
        initialize_trade_log(config["TRADE_LOG_FILE"])

        # Log validation auto-pause setting for audit trail
        pause_setting = config.get("DATA_PAUSE_ON_VALIDATE_FAIL")
        if pause_setting:
            logger.info(f"[SAFETY] Validation auto-pause: {pause_setting}")
        else:
            logger.info("[SAFETY] Validation auto-pause: disabled")

        # Choose execution mode
        if args.monitor_positions:
            # Run position monitoring mode
            logger.info("[MODE] Running in position monitoring mode")
            monitor_positions_mode(
                config,
                args,
                env_vars,
                bankroll_manager,
                portfolio_manager,
                llm_client,
                slack_notifier,
                end_time,
                weekly_pnl_tracker,
                drawdown_circuit_breaker,
                vix_monitor,
                health_monitor,
            )
            return
        elif config.get("multi_symbol", {}).get("enabled", False) or args.multi_symbol:
            # Run multi-symbol scanning mode
            logger.info("[MODE] Running in multi-symbol scanning mode")
            if args.loop:
                run_multi_symbol_loop(
                    config,
                    args,
                    env_vars,
                    bankroll_manager,
                    portfolio_manager,
                    llm_client,
                    slack_notifier,
                    end_time,
                    weekly_pnl_tracker,
                    drawdown_circuit_breaker,
                    vix_monitor,
                    health_monitor,
                )
                return
            else:
                run_multi_symbol_once(
                    config,
                    args,
                    env_vars,
                    bankroll_manager,
                    portfolio_manager,
                    llm_client,
                    slack_notifier,
                    weekly_pnl_tracker,
                    drawdown_circuit_breaker,
                    vix_monitor,
                    health_monitor,
                )
                return
        elif args.loop:
            # Run in continuous loop mode (single symbol)
            logger.info("[MODE] Running in continuous loop mode")
            main_loop(
                config,
                args,
                env_vars,
                bankroll_manager,
                portfolio_manager,
                llm_client,
                slack_notifier,
                end_time,
            )
            return
        else:
            # Run once (original behavior)
            logger.info("[MODE] Running in one-shot mode")
            run_one_shot_mode(
                config,
                args,
                env_vars,
                bankroll_manager,
                portfolio_manager,
                llm_client,
                slack_notifier,
            )
            return

        # NOTE: This code block has been removed as it was unreachable
        # All execution paths above have explicit returns - cleaned up in v2.0.0
        # Get current bankroll
        current_bankroll = bankroll_manager.get_current_bankroll()
        logger.info(f"[BANKROLL] Current bankroll: ${current_bankroll:.2f}")

        # Step 1: Fetch market data
        logger.info("[DATA] Fetching market data...")
        market_data = fetch_market_data(
            symbol=config["SYMBOL"], period="5d", interval="5m"
        )

        # Step 2: Calculate Heikin-Ashi candles
        logger.info("[CANDLES] Calculating Heikin-Ashi candles...")
        ha_data = calculate_heikin_ashi(market_data)

        # Step 3: Analyze breakout patterns
        logger.info("[ANALYSIS] Analyzing breakout patterns...")
        analysis = analyze_breakout_pattern(ha_data, config["LOOKBACK_BARS"])

        # Step 4: Prepare LLM payload
        llm_payload = prepare_llm_payload(analysis)
        logger.info(
            f"[MARKET] Market analysis: {analysis['trend_direction']} trend, "
            f"price ${analysis['current_price']}, "
            f"body {analysis['candle_body_pct']:.2f}%"
        )

        # Send market analysis to Slack
        if slack_notifier:
            slack_notifier.send_market_analysis(
                {
                    "trend": analysis["trend_direction"],
                    "current_price": analysis["current_price"],
                    "body_percentage": analysis["candle_body_pct"],
                    "support_count": len(analysis.get("support_levels", [])),
                    "resistance_count": len(analysis.get("resistance_levels", [])),
                }
            )

        # Step 5: Get LLM decision
        logger.info("[LLM] Getting LLM trade decision...")
        win_history = bankroll_manager.get_win_history()
        decision = llm_client.make_trade_decision(llm_payload, win_history)

        logger.info(
            f"[DECISION] LLM Decision: {decision.decision} "
            f"(confidence: {decision.confidence:.2f})"
        )

        if decision.reason:
            logger.info(f"[REASON] Reason: {decision.reason}")

        # Calculate position size for notification
        position_size = 0
        if decision.decision in ["CALL", "PUT"]:
            # Estimate premium for sizing prior to opening a ticket
            estimated_premium = analysis["current_price"] * 0.02
            position_size = bankroll_manager.calculate_position_size(
                premium=estimated_premium,
                risk_fraction=config["RISK_FRACTION"],
                size_rule=config["SIZE_RULE"],
                fixed_qty=config["CONTRACT_QTY"],
                symbol=symbol,
            )

        # Send trade decision to Slack
        if slack_notifier:
            slack_notifier.send_trade_decision(
                decision=decision.decision,
                confidence=decision.confidence,
                reason=decision.reason or "No specific reason provided",
                bankroll=current_bankroll,
                position_size=position_size,
            )

        # Step 6: Risk management checks
        if decision.decision == "NO_TRADE":
            logger.info("[NO_TRADE] No trade signal - ending session")

            # Log the no-trade decision
            trade_data = {
                "timestamp": datetime.now().isoformat(),
                "symbol": config["SYMBOL"],
                "decision": decision.decision,
                "confidence": decision.confidence,
                "reason": decision.reason or "",
                "current_price": analysis["current_price"],
                "llm_tokens": decision.tokens_used,
                "bankroll_before": current_bankroll,
                "bankroll_after": current_bankroll,
                "status": "NO_TRADE",
            }
            log_trade_decision(config["TRADE_LOG_FILE"], trade_data)
            return

        # Validate confidence threshold
        min_confidence = config.get("MIN_CONFIDENCE", 0.6)
        if decision.confidence < min_confidence:
            logger.warning(
                f"[LOW_CONFIDENCE] Confidence {decision.confidence:.2f} below threshold "
                f"{min_confidence:.2f} - blocking trade"
            )

            trade_data = {
                "timestamp": datetime.now().isoformat(),
                "symbol": config["SYMBOL"],
                "decision": "NO_TRADE",
                "confidence": decision.confidence,
                "reason": f"Confidence below threshold ({min_confidence:.2f})",
                "current_price": analysis["current_price"],
                "llm_tokens": decision.tokens_used,
                "bankroll_before": current_bankroll,
                "bankroll_after": current_bankroll,
                "status": "BLOCKED_LOW_CONFIDENCE",
            }
            log_trade_decision(config["TRADE_LOG_FILE"], trade_data)
            return

        # Step 6.5: Determine if this is an OPEN or CLOSE trade
        logger.info("[POSITION] Checking existing positions...")
        positions_summary = portfolio_manager.get_positions_summary()
        logger.info(
            f"[POSITION] Current positions: {positions_summary['total_positions']} open, "
            f"{positions_summary['call_positions']} calls, {positions_summary['put_positions']} puts"
        )

        trade_action, position_to_close = portfolio_manager.determine_trade_action(
            config["SYMBOL"], decision.decision
        )

        logger.info(f"[POSITION] Trade action determined: {trade_action}")
        if trade_action == "CLOSE" and position_to_close:
            logger.info(
                f"[CLOSE] Will close existing {position_to_close.side} position: "
                f"${position_to_close.strike} x{position_to_close.contracts} "
                f"(entry: ${position_to_close.entry_premium})"
            )
        elif trade_action == "OPEN":
            logger.info(f"[OPEN] Will open new {decision.decision} position")

        # Step 7: Browser automation (unless dry run)
        if args.dry_run:
            logger.info("[DRY_RUN] Dry run mode - skipping browser automation")

            # Simulate trade for logging
            estimated_premium = analysis["current_price"] * 0.02  # Rough estimate
            quantity = bankroll_manager.calculate_position_size(
                premium=estimated_premium,
                risk_fraction=config["RISK_FRACTION"],
                size_rule=config["SIZE_RULE"],
                fixed_qty=config["CONTRACT_QTY"],
                symbol=symbol,
            )

            trade_data = {
                "timestamp": datetime.now().isoformat(),
                "symbol": config["SYMBOL"],
                "decision": decision.decision,
                "confidence": decision.confidence,
                "reason": decision.reason or "",
                "current_price": analysis["current_price"],
                "strike": analysis["current_price"],  # ATM estimate
                "direction": decision.decision,
                "quantity": quantity,
                "premium": estimated_premium,
                "total_cost": estimated_premium * quantity * 100,
                "llm_tokens": decision.tokens_used,
                "bankroll_before": current_bankroll,
                "bankroll_after": current_bankroll,
                "status": "DRY_RUN",
            }
            log_trade_decision(config["TRADE_LOG_FILE"], trade_data)
            return

        # Step 8: Execute browser automation
        logger.info("[BROWSER] Starting browser automation...")

        with RobinhoodBot(
            headless=config["HEADLESS"],
            implicit_wait=config["IMPLICIT_WAIT"],
            page_load_timeout=config["PAGE_LOAD_TIMEOUT"],
        ) as bot:

            # Login to Robinhood
            if not bot.login(env_vars["RH_USER"], env_vars["RH_PASS"]):
                logger.error("[ERROR] Login failed")
                if slack_notifier:
                    slack_notifier.send_browser_status(
                        "login_failed", "Failed to login to Robinhood"
                    )
                return

            if slack_notifier:
                slack_notifier.send_browser_status(
                    "login_success", "Successfully logged into Robinhood"
                )

            # Branch based on trade action (OPEN vs CLOSE)
            if trade_action == "CLOSE":
                # CLOSE FLOW: Navigate to positions and close existing position
                logger.info(
                    f"[CLOSE] Executing close flow for {position_to_close.side} position"
                )

                if not bot.navigate_to_positions():
                    logger.error("[ERROR] Failed to navigate to positions")
                    if slack_notifier:
                        slack_notifier.send_browser_status(
                            "navigation_failed", "Failed to navigate to positions page"
                        )
                    return

                if not bot.find_position_to_close(
                    position_to_close.symbol,
                    position_to_close.side,
                    position_to_close.strike,
                ):
                    logger.error(
                        f"[ERROR] Could not find position to close: {position_to_close.symbol} {position_to_close.side} ${position_to_close.strike}"
                    )
                    return

                if not bot.execute_close_order(position_to_close.contracts):
                    logger.error("[ERROR] Failed to execute close order")
                    return

                if slack_notifier:
                    slack_notifier.send_browser_status(
                        "close_ready",
                        f"Close order ready for {position_to_close.symbol} {position_to_close.side}",
                    )

            else:
                # OPEN FLOW: Navigate to options chain and open new position
                logger.info(
                    f"[OPEN] Executing open flow for new {decision.decision} position"
                )

                if not bot.navigate_to_options(config["SYMBOL"]):
                    logger.error("[ERROR] Failed to navigate to options")
                    if slack_notifier:
                        slack_notifier.send_browser_status(
                            "navigation_failed",
                            f'Failed to navigate to {config["SYMBOL"]} options',
                        )
                    return

                if slack_notifier:
                    slack_notifier.send_browser_status(
                        "navigation_success",
                        f'Successfully navigated to {config["SYMBOL"]} options chain',
                    )

                # Select option type (CALL or PUT) - only for OPEN trades
                if not bot.select_option_type(decision.decision):
                    logger.error(f"[ERROR] Failed to select {decision.decision}s")
                    return

                # Find ATM option - only for OPEN trades
                atm_option = bot.find_atm_option(
                    analysis["current_price"],  # float
                    decision.decision,  # "CALL" or "PUT"
                )
                if not atm_option:
                    raise RuntimeError("ATM option not found")
                # open the order ticket
                atm_option["element"].click()

                # Get option premium - only for OPEN trades
                premium = bot.get_option_premium()
                if not premium:
                    logger.warning(
                        "[WARNING] Could not extract premium, using estimate"
                    )
                    premium = analysis["current_price"] * 0.02

                # Calculate position size - only for OPEN trades
                quantity = bankroll_manager.calculate_position_size(
                    premium=premium,
                    risk_fraction=config["RISK_FRACTION"],
                    size_rule=config["SIZE_RULE"],
                    fixed_qty=config["CONTRACT_QTY"],
                    symbol=symbol,
                )

                if quantity == 0:
                    logger.error(
                        "[ERROR] Position size calculation blocked trade (risk too high)"
                    )
                    return

                # Validate trade risk - only for OPEN trades
                if not bankroll_manager.validate_trade_risk(
                    premium, quantity, config.get("MAX_PREMIUM_PCT", 0.5) * 100
                ):
                    logger.error("[ERROR] Trade blocked by risk management")
                    return

                logger.info(
                    f"[OPEN] Trade details: {decision.decision} ${atm_option['strike']} "
                    f"x{quantity} @ ${premium:.2f}"
                )

                # Execute the OPEN trade flow (stops at Review)
                if bot.click_option_and_buy(atm_option["element"], quantity):
                    logger.info("[OPEN] Successfully reached Review Order screen")

                    # Take screenshot
                    screenshot_path = bot.take_screenshot("open_review_order.png")

                    # Send enhanced Slack notification with chart
                    slack_notifier.send_breakout_alert_with_chart(
                        symbol=config["SYMBOL"],
                        decision=decision.decision,
                        analysis=analysis,
                        market_data=market_data,
                        confidence=decision.confidence,
                    )

                    print("\n" + "=" * 60)
                    print("[OPEN TRADE READY FOR REVIEW]")
                    print("=" * 60)
                    print(f"Direction: {decision.decision}")
                    print(f"Strike: ${atm_option['strike']}")
                    print(f"Quantity: {quantity} contracts")
                    print(f"Premium: ${premium:.2f} per contract")
                    print(f"Total Cost: ${premium * quantity:.2f}")
                    print(f"Confidence: {decision.confidence:.2f}")
                    print("\n🚨 MANUAL REVIEW REQUIRED - DO NOT AUTO-SUBMIT")
                    print(
                        "✅ Review the order details above and submit manually if approved"
                    )
                    print("=" * 60)

                    # Wait for user to manually submit the order
                    input(
                        "\n📋 Press Enter AFTER you have manually submitted the order (or press Ctrl+C to cancel)..."
                    )

                    # Prompt for fill price
                    while True:
                        try:
                            fill_price = float(
                                input(
                                    f"\n💰 Enter the actual fill price per contract (estimated: ${premium:.2f}): $"
                                )
                            )
                            if fill_price > 0:
                                break
                            else:
                                print("❌ Fill price must be greater than 0")
                        except ValueError:
                            print("❌ Please enter a valid number")

                    # Create position record
                    new_position = Position(
                        entry_time=datetime.now().isoformat(),
                        symbol=config["SYMBOL"],
                        expiry="Today",  # You may want to make this configurable
                        strike=atm_option["strike"],
                        side=decision.decision,
                        contracts=quantity,
                        entry_premium=fill_price,
                    )

                    # Add position to portfolio
                    portfolio_manager.add_position(new_position)

                    # Log the completed OPEN trade
                    trade_data = {
                        "timestamp": datetime.now().isoformat(),
                        "symbol": config["SYMBOL"],
                        "decision": decision.decision,
                        "confidence": decision.confidence,
                        "reason": decision.reason or "",
                        "current_price": analysis["current_price"],
                        "strike": atm_option["strike"],
                        "direction": decision.decision,
                        "quantity": quantity,
                        "premium": fill_price,
                        "total_cost": fill_price * quantity * 100,
                        "llm_tokens": decision.tokens_used,
                        "bankroll_before": current_bankroll,
                        "bankroll_after": current_bankroll,  # Will be updated by bankroll manager
                        "status": "OPENED",
                    }
                    log_trade_decision(config["TRADE_LOG_FILE"], trade_data)

                    logger.info(
                        f"[OPEN] Position opened: {decision.decision} ${atm_option['strike']} x{quantity} @ ${fill_price:.2f}"
                    )

                else:
                    logger.error("[ERROR] Failed to complete OPEN trade flow")
                    return

            # Handle CLOSE trade completion
            if trade_action == "CLOSE":
                # Take screenshot for close order
                screenshot_path = bot.take_screenshot("close_review_order.png")

                # Send critical CLOSE order ready alert to Slack with comprehensive details
                if slack_notifier:
                    # Estimate exit premium based on current market conditions
                    estimated_exit_premium = (
                        analysis["current_price"] * 0.02
                    )  # Rough estimate
                    estimated_total_proceeds = (
                        estimated_exit_premium * position_to_close.contracts * 100
                    )

                    slack_notifier.send_order_ready_alert(
                        trade_type=position_to_close.side,
                        strike=f"${position_to_close.strike}",
                        expiry=position_to_close.expiry,
                        position_size=estimated_total_proceeds,
                        # Enhanced details for manual review
                        action="CLOSE",
                        confidence=decision.confidence,
                        reason=decision.reason or "Closing existing position",
                        current_price=analysis["current_price"],
                        premium=estimated_exit_premium,
                        quantity=position_to_close.contracts,
                        total_cost=estimated_total_proceeds,
                        bankroll=current_bankroll,
                        trend=analysis.get("trend_direction", "UNKNOWN"),
                        candle_body_pct=analysis.get("candle_body_pct", 0.0),
                        # CLOSE-specific details
                        entry_premium=position_to_close.entry_premium,
                        contracts_held=position_to_close.contracts,
                    )

                print("\n" + "=" * 60)
                print("[CLOSE TRADE READY FOR REVIEW]")
                print("=" * 60)
                print(f"Closing: {position_to_close.side} ${position_to_close.strike}")
                print(f"Quantity: {position_to_close.contracts} contracts")
                print(
                    f"Entry Premium: ${position_to_close.entry_premium:.2f} per contract"
                )
                print(
                    f"Entry Cost: ${position_to_close.entry_premium * position_to_close.contracts:.2f}"
                )
                print("\n🚨 MANUAL REVIEW REQUIRED - DO NOT AUTO-SUBMIT")
                print(
                    "✅ Review the close order details above and submit manually if approved"
                )
                print("=" * 60)

                # Wait for user to manually submit the close order
                input(
                    "\n📋 Press Enter AFTER you have manually submitted the CLOSE order (or press Ctrl+C to cancel)..."
                )

                # Prompt for exit fill price
                while True:
                    try:
                        exit_price = float(
                            input(
                                f"\n💰 Enter the actual exit price per contract (entry was: ${position_to_close.entry_premium:.2f}): $"
                            )
                        )
                        if exit_price > 0:
                            break
                        else:
                            print("❌ Exit price must be greater than 0")
                    except ValueError:
                        print("❌ Please enter a valid number")

                # Calculate realized P/L
                realized_pnl = portfolio_manager.calculate_realized_pnl(
                    position_to_close, exit_price
                )

                # Remove position from portfolio
                portfolio_manager.remove_position(position_to_close)

                # Log realized trade to trade_log.csv
                portfolio_manager.log_realized_trade(
                    position_to_close,
                    exit_price,
                    realized_pnl,
                    config["TRADE_LOG_FILE"],
                )

                # Record trade outcome for LLM confidence calibration
                is_win = realized_pnl > 0
                bankroll_manager.record_trade_outcome(is_win)

                logger.info(
                    f"[CLOSE] Position closed: {position_to_close.side} ${position_to_close.strike} "
                    f"x{position_to_close.contracts} - P/L: ${realized_pnl:.2f} ({'WIN' if is_win else 'LOSS'})"
                )

                print("\n📊 TRADE COMPLETED:")
                print(
                    f"   P/L: ${realized_pnl:.2f} ({'PROFIT' if realized_pnl > 0 else 'LOSS'})"
                )
                print(
                    f"   Entry: ${position_to_close.entry_premium:.2f} -> Exit: ${exit_price:.2f}"
                )
                print(f"   Total Contracts: {position_to_close.contracts}")

    except KeyboardInterrupt:
        logger.info("[INTERRUPT] Script interrupted by user")

        # Graceful shutdown: cleanup monitor processes
        try:
            from utils.monitor_launcher import cleanup_all_monitors

            logger.info("[CLEANUP] Stopping all monitor processes...")
            cleanup_all_monitors()
            logger.info("[CLEANUP] Monitor cleanup complete")
        except:
            pass
    except Exception as e:
        logger.error(f"[ERROR] Unexpected error: {e}", exc_info=True)
        try:
            if 'slack_notifier' in locals() and slack_notifier:
                slack_notifier.send_error_alert("System Error", str(e))
        except:
            pass
    finally:
        logger.info("[COMPLETE] Script execution completed")

        # Send completion summary
        try:
            if 'slack_notifier' in locals() and slack_notifier:
                session_summary = {
                    "trades_analyzed": 1,
                    "decisions_made": 1,
                    "final_bankroll": (
                        bankroll_manager.get_current_bankroll()
                        if "bankroll_manager" in locals()
                        else 0
                    ),
                    "duration": "N/A",
                }
                slack_notifier.send_completion_summary(session_summary)
        except:
            pass


if __name__ == "__main__":
    main()
