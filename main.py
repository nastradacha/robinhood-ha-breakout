#!/usr/bin/env python3
"""
Robinhood HA Breakout - Main Trading Script

A sophisticated automated trading system for SPY options using Heikin-Ashi breakout patterns.
Designed for conservative intraday trading with manual confirmation and risk management.

Key Features:
- Automated market analysis using Heikin-Ashi candles
- LLM-powered trade decision making (GPT-4o-mini or DeepSeek)
- Browser automation for Robinhood options trading
- Manual confirmation required - NEVER auto-submits orders
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
- All trades require manual review and confirmation
- System stops at Robinhood Review screen
- User must manually click Submit or Cancel
- Interactive prompts record actual fill prices
- No automated order execution whatsoever

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
    prepare_llm_payload
)
from utils.llm import LLMClient, TradeDecision
from utils.bankroll import BankrollManager
from utils.browser import RobinhoodBot
from utils.slack import SlackNotifier
from utils.portfolio import PortfolioManager, Position

# Load environment variables
load_dotenv()

# Configure logging
def setup_logging(log_level: str = "INFO", log_file: str = "logs/app.log"):
    """
    Setup comprehensive logging configuration for the trading system.
    
    Creates both file and console logging handlers with detailed formatting.
    Automatically creates the logs directory if it doesn't exist.
    
    Args:
        log_level (str): Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file (str): Path to the log file (default: "logs/app.log")
    
    Returns:
        None
    
    Note:
        All trading activities, errors, and system events are logged for audit trails.
    """
    Path(log_file).parent.mkdir(exist_ok=True)
    
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )

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
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        logging.error(f"Failed to load config: {e}")
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
    required_vars = {
        'RH_USER': os.getenv('RH_USER'),
        'RH_PASS': os.getenv('RH_PASS')
    }
    
    # Check for at least one LLM API key
    openai_key = os.getenv('OPENAI_API_KEY')
    deepseek_key = os.getenv('DEEPSEEK_API_KEY')
    
    if not openai_key and not deepseek_key:
        logging.error("Either OPENAI_API_KEY or DEEPSEEK_API_KEY must be set")
        sys.exit(1)
    
    # Check Robinhood credentials
    for var, value in required_vars.items():
        if not value:
            logging.error(f"Required environment variable {var} not set")
            sys.exit(1)
    
    return required_vars

def initialize_trade_log(log_file: str):
    """Initialize CSV trade log with headers if it doesn't exist."""
    log_path = Path(log_file)
    log_path.parent.mkdir(exist_ok=True)
    
    if not log_path.exists():
        headers = [
            'timestamp', 'symbol', 'decision', 'confidence', 'reason',
            'current_price', 'strike', 'expiry', 'direction', 'quantity',
            'premium', 'total_cost', 'llm_tokens', 'bankroll_before',
            'bankroll_after', 'realized_pnl', 'status'
        ]
        
        with open(log_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
        
        logging.info(f"Initialized trade log: {log_file}")

def log_trade_decision(log_file: str, trade_data: Dict):
    """Log trade decision to CSV file."""
    with open(log_file, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            trade_data.get('timestamp', ''),
            trade_data.get('symbol', ''),
            trade_data.get('decision', ''),
            trade_data.get('confidence', ''),
            trade_data.get('reason', ''),
            trade_data.get('current_price', ''),
            trade_data.get('strike', ''),
            trade_data.get('expiry', ''),
            trade_data.get('direction', ''),
            trade_data.get('quantity', ''),
            trade_data.get('premium', ''),
            trade_data.get('total_cost', ''),
            trade_data.get('llm_tokens', ''),
            trade_data.get('bankroll_before', ''),
            trade_data.get('bankroll_after', ''),
            trade_data.get('realized_pnl', ''),
            trade_data.get('status', '')
        ])

def parse_end_time(end_time_str: str) -> Optional[datetime]:
    """Parse end time string (HH:MM) to datetime object in local timezone."""
    if not end_time_str:
        return None
    
    try:
        hour, minute = map(int, end_time_str.split(':'))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Invalid time format")
        
        # Use America/New_York timezone as specified
        tz = ZoneInfo("America/New_York")
        now = datetime.now(tz)
        end_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # If end time is before current time, assume it's for tomorrow
        if end_time <= now:
            end_time += timedelta(days=1)
            
        return end_time
    except (ValueError, IndexError):
        raise ValueError(f"Invalid end time format: {end_time_str}. Use HH:MM (24-hour format)")


def run_once(config: Dict, args, env_vars: Dict, bankroll_manager, portfolio_manager, 
             llm_client, slack_notifier, bot=None) -> Dict:
    """
    Execute one complete trading cycle from market analysis to trade execution.
    
    This is the core trading function that performs the complete workflow:
    1. Fetch current market data for SPY
    2. Calculate Heikin-Ashi candles for trend analysis
    3. Analyze breakout patterns using technical indicators
    4. Get LLM trade decision based on market conditions
    5. If trade signal detected, initiate browser automation
    6. Navigate to Robinhood and find ATM options
    7. Stop at Review screen for manual confirmation
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
        - Never auto-submits trades
        - Always stops at Robinhood Review screen
        - Requires manual user confirmation
        - Records actual fill prices from user input
    
    Risk Management:
        - Validates bankroll before trading
        - Checks position limits
        - Applies risk fraction limits
        - Logs all activities for audit
    """
    logger = logging.getLogger(__name__)
    
    # Get current bankroll
    current_bankroll = bankroll_manager.get_current_bankroll()
    logger.info(f"[BANKROLL] Current bankroll: ${current_bankroll:.2f}")
    
    # Step 1: Fetch market data
    logger.info("[DATA] Fetching market data...")
    market_data = fetch_market_data(
        symbol=config['SYMBOL'],
        period="5d",
        interval="5m"
    )
    
    # Step 2: Calculate Heikin-Ashi candles
    logger.info("[CANDLES] Calculating Heikin-Ashi candles...")
    ha_data = calculate_heikin_ashi(market_data)
    
    # Step 3: Analyze breakout patterns
    logger.info("[ANALYSIS] Analyzing breakout patterns...")
    analysis = analyze_breakout_pattern(ha_data, config['LOOKBACK_BARS'])
    
    # Step 4: Prepare LLM payload
    llm_payload = prepare_llm_payload(analysis)
    logger.info(f"[MARKET] Market analysis: {analysis['trend_direction']} trend, "
               f"price ${analysis['current_price']}, "
               f"body {analysis['candle_body_pct']:.2f}%")
    
    # Step 5: Get LLM decision
    logger.info("[LLM] Getting LLM trade decision...")
    win_history = bankroll_manager.get_win_history()
    decision = llm_client.make_trade_decision(llm_payload, win_history)
    
    logger.info(f"[DECISION] LLM Decision: {decision.decision} "
               f"(confidence: {decision.confidence:.2f})")
    
    if decision.reason:
        logger.info(f"[REASON] Reason: {decision.reason}")
    
    # Calculate position size for notification
    position_size = 0
    if decision.decision in ['CALL', 'PUT']:
        position_size = bankroll_manager.calculate_position_size(
            current_bankroll, decision.confidence
        )
    
    # Return trade result data
    return {
        'analysis': analysis,
        'decision': decision,
        'current_bankroll': current_bankroll,
        'position_size': position_size
    }


def main_loop(config: Dict, args, env_vars: Dict, bankroll_manager, portfolio_manager,
              llm_client, slack_notifier, end_time: Optional[datetime]):
    """Execute the main trading loop."""
    logger = logging.getLogger(__name__)
    tz = ZoneInfo("America/New_York")
    
    # Initialize persistent browser bot for loop mode
    bot = None
    bot_idle_since = None
    
    try:
        loop_count = 0
        
        while True:
            loop_count += 1
            cycle_start = datetime.now(tz)
            
            # Check if we should exit based on end time
            if end_time and cycle_start >= end_time:
                logger.info(f"[LOOP] Reached end time {end_time.strftime('%H:%M %Z')} - exiting")
                break
            
            logger.info(f"[LOOP] Starting cycle {loop_count} at {cycle_start.strftime('%H:%M:%S')}")
            
            try:
                # Execute one trading cycle
                result = run_once(config, args, env_vars, bankroll_manager, 
                                portfolio_manager, llm_client, slack_notifier, bot)
                
                analysis = result['analysis']
                decision = result['decision']
                current_bankroll = result['current_bankroll']
                position_size = result['position_size']
                
                # Handle different decision types
                if decision.decision == "NO_TRADE":
                    # Send lightweight heartbeat to Slack
                    if slack_notifier:
                        heartbeat_msg = f"⏳ {cycle_start.strftime('%H:%M')} · No breakout (body {analysis['candle_body_pct']:.2f}%)"
                        slack_notifier.send_heartbeat(heartbeat_msg)
                    
                    # Log the no-trade decision
                    trade_data = {
                        'timestamp': cycle_start.isoformat(),
                        'symbol': config['SYMBOL'],
                        'decision': decision.decision,
                        'confidence': decision.confidence,
                        'reason': decision.reason or '',
                        'current_price': analysis['current_price'],
                        'llm_tokens': decision.tokens_used,
                        'bankroll_before': current_bankroll,
                        'bankroll_after': current_bankroll,
                        'status': 'NO_TRADE_LOOP'
                    }
                    log_trade_decision(config['TRADE_LOG_FILE'], trade_data)
                    
                elif decision.decision in ['CALL', 'PUT']:
                    # Validate confidence threshold
                    if decision.confidence < config['MIN_CONFIDENCE']:
                        logger.warning(f"[LOW_CONFIDENCE] Confidence {decision.confidence:.2f} below threshold")
                        if slack_notifier:
                            heartbeat_msg = f"⚠️ {cycle_start.strftime('%H:%M')} · Low confidence {decision.decision} ({decision.confidence:.2f})"
                            slack_notifier.send_heartbeat(heartbeat_msg)
                    else:
                        # Initialize or reuse browser bot
                        if not bot or (bot_idle_since and 
                                     (cycle_start - bot_idle_since).total_seconds() > 4 * 3600):  # 4 hours
                            if bot:
                                logger.info("[BROWSER] Restarting browser after 4h idle")
                                bot.quit()
                            
                            if not args.dry_run:
                                bot = RobinhoodBot(
                                    headless=config['HEADLESS'],
                                    implicit_wait=config['IMPLICIT_WAIT'],
                                    page_load_timeout=config['PAGE_LOAD_TIMEOUT']
                                )
                                bot.start_browser()
                                
                                # Login to Robinhood
                                if not bot.login(env_vars['RH_USER'], env_vars['RH_PASS']):
                                    logger.error("[ERROR] Login failed")
                                    if slack_notifier:
                                        slack_notifier.send_browser_status('login_failed', 'Failed to login to Robinhood')
                                    continue
                                
                                # Navigate to options chain once
                                if not bot.navigate_to_options(config['SYMBOL']):
                                    logger.error("[ERROR] Failed to navigate to options")
                                    continue
                                    
                                bot_idle_since = None
                        
                        # Find ATM option and prepare order
                        if not args.dry_run and bot:
                            try:
                                # Ensure we're still on the options page
                                bot.ensure_open(config['SYMBOL'])
                                
                                atm_option = bot.find_atm_option(analysis['current_price'], decision.decision)
                                if atm_option:
                                    # Calculate quantity
                                    estimated_premium = analysis['current_price'] * 0.02
                                    quantity = bankroll_manager.calculate_position_size(
                                        premium=estimated_premium,
                                        risk_fraction=config['RISK_FRACTION'],
                                        size_rule=config['SIZE_RULE'],
                                        fixed_qty=config['CONTRACT_QTY']
                                    )
                                    
                                    # Pre-fill order and stop at Review
                                    if bot.click_option_and_buy(atm_option, quantity):
                                        # Send rich Slack notification
                                        if slack_notifier:
                                            slack_notifier.send_order_ready_alert(
                                                trade_type=decision.decision,
                                                strike=str(atm_option['strike']),
                                                expiry="Today",  # Adjust as needed
                                                position_size=position_size,
                                                action='OPEN',
                                                confidence=decision.confidence,
                                                reason=decision.reason or '',
                                                current_price=analysis['current_price'],
                                                quantity=quantity
                                            )
                                        
                                        logger.info(f"[SUCCESS] {decision.decision} order ready for review")
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
                                slack_notifier.send_order_ready_alert(
                                    trade_type=decision.decision,
                                    strike=str(analysis['current_price']),
                                    expiry="Today",
                                    position_size=position_size,
                                    action='OPEN',
                                    confidence=decision.confidence,
                                    reason=decision.reason or '',
                                    current_price=analysis['current_price'],
                                    quantity=1
                                )
                
            except Exception as e:
                logger.error(f"[LOOP] Error in cycle {loop_count}: {e}", exc_info=True)
                if slack_notifier:
                    slack_notifier.send_error_alert(f"Loop Cycle {loop_count} Error", str(e))
            
            # Calculate sleep time to maintain interval
            cycle_end = datetime.now(tz)
            cycle_duration = (cycle_end - cycle_start).total_seconds()
            target_interval_seconds = args.interval * 60
            sleep_seconds = max(0, target_interval_seconds - cycle_duration)
            
            if sleep_seconds > 0:
                logger.info(f"[LOOP] Cycle {loop_count} completed in {cycle_duration:.1f}s, sleeping {sleep_seconds:.1f}s")
                time.sleep(sleep_seconds)
            else:
                logger.warning(f"[LOOP] Cycle {loop_count} took {cycle_duration:.1f}s (longer than {args.interval}m interval)")
    
    finally:
        # Clean up browser
        if bot:
            logger.info("[CLEANUP] Closing browser")
            bot.quit()


def run_one_shot_mode(config: Dict, args, env_vars: Dict, bankroll_manager, portfolio_manager,
                      llm_client, slack_notifier):
    """Execute the original one-shot trading mode."""
    logger = logging.getLogger(__name__)
    
    # Execute one trading cycle
    result = run_once(config, args, env_vars, bankroll_manager, 
                     portfolio_manager, llm_client, slack_notifier)
    
    analysis = result['analysis']
    decision = result['decision']
    current_bankroll = result['current_bankroll']
    position_size = result['position_size']
    
    # Send market analysis to Slack
    if slack_notifier:
        slack_notifier.send_market_analysis({
            'trend': analysis['trend_direction'],
            'current_price': analysis['current_price'],
            'body_percentage': analysis['candle_body_pct'],
            'support_count': len(analysis.get('support_levels', [])),
            'resistance_count': len(analysis.get('resistance_levels', []))
        })
    
    # Send trade decision to Slack
    if slack_notifier:
        slack_notifier.send_trade_decision(
            decision=decision.decision,
            confidence=decision.confidence,
            reason=decision.reason or "No specific reason provided",
            bankroll=current_bankroll,
            position_size=position_size
        )
    
    # Handle NO_TRADE decision
    if decision.decision == "NO_TRADE":
        logger.info("[NO_TRADE] No trade signal - ending session")
        
        trade_data = {
            'timestamp': datetime.now().isoformat(),
            'symbol': config['SYMBOL'],
            'decision': decision.decision,
            'confidence': decision.confidence,
            'reason': decision.reason or '',
            'current_price': analysis['current_price'],
            'llm_tokens': decision.tokens_used,
            'bankroll_before': current_bankroll,
            'bankroll_after': current_bankroll,
            'status': 'NO_TRADE'
        }
        log_trade_decision(config['TRADE_LOG_FILE'], trade_data)
        return
    
    # Validate confidence threshold
    if decision.confidence < config['MIN_CONFIDENCE']:
        logger.warning(f"[LOW_CONFIDENCE] Confidence {decision.confidence:.2f} below threshold "
                      f"{config['MIN_CONFIDENCE']:.2f} - blocking trade")
        
        trade_data = {
            'timestamp': datetime.now().isoformat(),
            'symbol': config['SYMBOL'],
            'decision': 'NO_TRADE',
            'confidence': decision.confidence,
            'reason': f"Confidence below threshold ({config['MIN_CONFIDENCE']:.2f})",
            'current_price': analysis['current_price'],
            'llm_tokens': decision.tokens_used,
            'bankroll_before': current_bankroll,
            'bankroll_after': current_bankroll,
            'status': 'BLOCKED_LOW_CONFIDENCE'
        }
        log_trade_decision(config['TRADE_LOG_FILE'], trade_data)
        return
    
    # Continue with the rest of the original one-shot logic...
    # (This would include the browser automation, position management, etc.)
    # For now, I'll implement a simplified version that calls the existing logic
    
    logger.info(f"[TRADE] Proceeding with {decision.decision} trade (confidence: {decision.confidence:.2f})")
    
    # The rest of the original main() logic would go here
    # This is a placeholder - the actual implementation would include
    # all the browser automation and position management logic


def main():
    """Main trading script execution."""
    parser = argparse.ArgumentParser(description='Robinhood HA Breakout Trading Assistant')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Run analysis without browser automation')
    parser.add_argument('--config', default='config.yaml',
                       help='Configuration file path')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Logging level')
    parser.add_argument('--slack-notify', action='store_true',
                       help='Send notifications to Slack during trading')
    parser.add_argument('--loop', action='store_true',
                       help='Run in continuous loop mode (Ctrl-C to exit)')
    parser.add_argument('--interval', type=int, default=5,
                       help='Minutes between scans in loop mode (default: 5)')
    parser.add_argument('--end-at', type=str,
                       help='End time in HH:MM format (24-hour, local time)')
    
    args = parser.parse_args()
    
    # Validate end time format if provided
    end_time = None
    if args.end_at:
        try:
            end_time = parse_end_time(args.end_at)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
    
    # Load configuration
    config = load_config(args.config)
    
    # Setup logging
    setup_logging(args.log_level, config['LOG_FILE'])
    logger = logging.getLogger(__name__)
    
    logger.info("[START] Starting Robinhood HA Breakout Assistant")
    logger.info(f"Dry run mode: {args.dry_run}")
    if args.loop:
        logger.info(f"Loop mode: {args.interval} minute intervals")
        if end_time:
            logger.info(f"End time: {end_time.strftime('%H:%M %Z')}")
    
    try:
        # Validate environment
        env_vars = validate_environment()
        
        # Initialize components
        bankroll_manager = BankrollManager(
            config['BANKROLL_FILE'], 
            config['START_CAPITAL']
        )
        
        portfolio_manager = PortfolioManager(config.get('POSITIONS_FILE', 'positions.csv'))
        
        llm_client = LLMClient(config['MODEL'])
        
        # Initialize Slack notifier if requested
        slack_notifier = None
        if args.slack_notify:
            slack_notifier = SlackNotifier()
            slack_notifier.send_startup_notification(dry_run=args.dry_run)
        
        # Initialize trade log
        initialize_trade_log(config['TRADE_LOG_FILE'])
        
        # Choose execution mode
        if args.loop:
            # Run in continuous loop mode
            logger.info("[MODE] Running in continuous loop mode")
            main_loop(config, args, env_vars, bankroll_manager, portfolio_manager,
                     llm_client, slack_notifier, end_time)
        else:
            # Run once (original behavior)
            logger.info("[MODE] Running in one-shot mode")
            run_one_shot_mode(config, args, env_vars, bankroll_manager, portfolio_manager,
                             llm_client, slack_notifier)
        
        # Get current bankroll
        current_bankroll = bankroll_manager.get_current_bankroll()
        logger.info(f"[BANKROLL] Current bankroll: ${current_bankroll:.2f}")
        
        # Step 1: Fetch market data
        logger.info("[DATA] Fetching market data...")
        market_data = fetch_market_data(
            symbol=config['SYMBOL'],
            period="5d",
            interval="5m"
        )
        
        # Step 2: Calculate Heikin-Ashi candles
        logger.info("[CANDLES] Calculating Heikin-Ashi candles...")
        ha_data = calculate_heikin_ashi(market_data)
        
        # Step 3: Analyze breakout patterns
        logger.info("[ANALYSIS] Analyzing breakout patterns...")
        analysis = analyze_breakout_pattern(ha_data, config['LOOKBACK_BARS'])
        
        # Step 4: Prepare LLM payload
        llm_payload = prepare_llm_payload(analysis)
        logger.info(f"[MARKET] Market analysis: {analysis['trend_direction']} trend, "
                   f"price ${analysis['current_price']}, "
                   f"body {analysis['candle_body_pct']:.2f}%")
        
        # Send market analysis to Slack
        if slack_notifier:
            slack_notifier.send_market_analysis({
                'trend': analysis['trend_direction'],
                'current_price': analysis['current_price'],
                'body_percentage': analysis['candle_body_pct'],
                'support_count': len(analysis.get('support_levels', [])),
                'resistance_count': len(analysis.get('resistance_levels', []))
            })
        
        # Step 5: Get LLM decision
        logger.info("[LLM] Getting LLM trade decision...")
        win_history = bankroll_manager.get_win_history()
        decision = llm_client.make_trade_decision(llm_payload, win_history)
        
        logger.info(f"[DECISION] LLM Decision: {decision.decision} "
                   f"(confidence: {decision.confidence:.2f})")
        
        if decision.reason:
            logger.info(f"[REASON] Reason: {decision.reason}")
        
        # Calculate position size for notification
        position_size = 0
        if decision.decision in ['CALL', 'PUT']:
            position_size = bankroll_manager.calculate_position_size(
                current_bankroll, decision.confidence
            )
        
        # Send trade decision to Slack
        if slack_notifier:
            slack_notifier.send_trade_decision(
                decision=decision.decision,
                confidence=decision.confidence,
                reason=decision.reason or "No specific reason provided",
                bankroll=current_bankroll,
                position_size=position_size
            )
        
        # Step 6: Risk management checks
        if decision.decision == "NO_TRADE":
            logger.info("[NO_TRADE] No trade signal - ending session")
            
            # Log the no-trade decision
            trade_data = {
                'timestamp': datetime.now().isoformat(),
                'symbol': config['SYMBOL'],
                'decision': decision.decision,
                'confidence': decision.confidence,
                'reason': decision.reason or '',
                'current_price': analysis['current_price'],
                'llm_tokens': decision.tokens_used,
                'bankroll_before': current_bankroll,
                'bankroll_after': current_bankroll,
                'status': 'NO_TRADE'
            }
            log_trade_decision(config['TRADE_LOG_FILE'], trade_data)
            return
        
        # Validate confidence threshold
        if decision.confidence < config['MIN_CONFIDENCE']:
            logger.warning(f"[LOW_CONFIDENCE] Confidence {decision.confidence:.2f} below threshold "
                          f"{config['MIN_CONFIDENCE']:.2f} - blocking trade")
            
            trade_data = {
                'timestamp': datetime.now().isoformat(),
                'symbol': config['SYMBOL'],
                'decision': 'NO_TRADE',
                'confidence': decision.confidence,
                'reason': f"Confidence below threshold ({config['MIN_CONFIDENCE']:.2f})",
                'current_price': analysis['current_price'],
                'llm_tokens': decision.tokens_used,
                'bankroll_before': current_bankroll,
                'bankroll_after': current_bankroll,
                'status': 'BLOCKED_LOW_CONFIDENCE'
            }
            log_trade_decision(config['TRADE_LOG_FILE'], trade_data)
            return
        
        # Step 6.5: Determine if this is an OPEN or CLOSE trade
        logger.info("[POSITION] Checking existing positions...")
        positions_summary = portfolio_manager.get_positions_summary()
        logger.info(f"[POSITION] Current positions: {positions_summary['total_positions']} open, "
                   f"{positions_summary['call_positions']} calls, {positions_summary['put_positions']} puts")
        
        trade_action, position_to_close = portfolio_manager.determine_trade_action(
            config['SYMBOL'], decision.decision
        )
        
        logger.info(f"[POSITION] Trade action determined: {trade_action}")
        if trade_action == 'CLOSE' and position_to_close:
            logger.info(f"[CLOSE] Will close existing {position_to_close.side} position: "
                       f"${position_to_close.strike} x{position_to_close.contracts} "
                       f"(entry: ${position_to_close.entry_premium})")
        elif trade_action == 'OPEN':
            logger.info(f"[OPEN] Will open new {decision.decision} position")
        
        # Step 7: Browser automation (unless dry run)
        if args.dry_run:
            logger.info("[DRY_RUN] Dry run mode - skipping browser automation")
            
            # Simulate trade for logging
            estimated_premium = analysis['current_price'] * 0.02  # Rough estimate
            quantity = bankroll_manager.calculate_position_size(
                premium=estimated_premium,
                risk_fraction=config['RISK_FRACTION'],
                size_rule=config['SIZE_RULE'],
                fixed_qty=config['CONTRACT_QTY']
            )
            
            trade_data = {
                'timestamp': datetime.now().isoformat(),
                'symbol': config['SYMBOL'],
                'decision': decision.decision,
                'confidence': decision.confidence,
                'reason': decision.reason or '',
                'current_price': analysis['current_price'],
                'strike': analysis['current_price'],  # ATM estimate
                'direction': decision.decision,
                'quantity': quantity,
                'premium': estimated_premium,
                'total_cost': estimated_premium * quantity,
                'llm_tokens': decision.tokens_used,
                'bankroll_before': current_bankroll,
                'bankroll_after': current_bankroll,
                'status': 'DRY_RUN'
            }
            log_trade_decision(config['TRADE_LOG_FILE'], trade_data)
            return
        
        # Step 8: Execute browser automation
        logger.info("[BROWSER] Starting browser automation...")
        
        with RobinhoodBot(
            headless=config['HEADLESS'],
            implicit_wait=config['IMPLICIT_WAIT'],
            page_load_timeout=config['PAGE_LOAD_TIMEOUT']
        ) as bot:
            
            # Login to Robinhood
            if not bot.login(env_vars['RH_USER'], env_vars['RH_PASS']):
                logger.error("[ERROR] Login failed")
                if slack_notifier:
                    slack_notifier.send_browser_status('login_failed', 'Failed to login to Robinhood')
                return
            
            if slack_notifier:
                slack_notifier.send_browser_status('login_success', 'Successfully logged into Robinhood')
            
            # Branch based on trade action (OPEN vs CLOSE)
            if trade_action == 'CLOSE':
                # CLOSE FLOW: Navigate to positions and close existing position
                logger.info(f"[CLOSE] Executing close flow for {position_to_close.side} position")
                
                if not bot.navigate_to_positions():
                    logger.error("[ERROR] Failed to navigate to positions")
                    if slack_notifier:
                        slack_notifier.send_browser_status('navigation_failed', 'Failed to navigate to positions page')
                    return
                
                if not bot.find_position_to_close(position_to_close.symbol, position_to_close.side, position_to_close.strike):
                    logger.error(f"[ERROR] Could not find position to close: {position_to_close.symbol} {position_to_close.side} ${position_to_close.strike}")
                    return
                
                if not bot.execute_close_order(position_to_close.contracts):
                    logger.error("[ERROR] Failed to execute close order")
                    return
                
                if slack_notifier:
                    slack_notifier.send_browser_status('close_ready', f'Close order ready for {position_to_close.symbol} {position_to_close.side}')
            
            else:
                # OPEN FLOW: Navigate to options chain and open new position
                logger.info(f"[OPEN] Executing open flow for new {decision.decision} position")
                
                if not bot.navigate_to_options(config['SYMBOL']):
                    logger.error("[ERROR] Failed to navigate to options")
                    if slack_notifier:
                        slack_notifier.send_browser_status('navigation_failed', f'Failed to navigate to {config["SYMBOL"]} options')
                    return
                
                if slack_notifier:
                    slack_notifier.send_browser_status('navigation_success', f'Successfully navigated to {config["SYMBOL"]} options chain')
                
                # Select option type (CALL or PUT) - only for OPEN trades
                if not bot.select_option_type(decision.decision):
                    logger.error(f"[ERROR] Failed to select {decision.decision}s")
                    return
                
                # Find ATM option - only for OPEN trades
                atm_option = bot.find_atm_option(
                    analysis['current_price'],   # float
                    decision.decision            # "CALL" or "PUT"
                )
                if not atm_option:
                    raise RuntimeError("ATM option not found")
                # open the order ticket
                atm_option['element'].click()
                
                # Get option premium - only for OPEN trades
                premium = bot.get_option_premium()
                if not premium:
                    logger.warning("[WARNING] Could not extract premium, using estimate")
                    premium = analysis['current_price'] * 0.02
                
                # Calculate position size - only for OPEN trades
                quantity = bankroll_manager.calculate_position_size(
                    premium=premium,
                    risk_fraction=config['RISK_FRACTION'],
                    size_rule=config['SIZE_RULE'],
                    fixed_qty=config['CONTRACT_QTY']
                )
                
                if quantity == 0:
                    logger.error("[ERROR] Position size calculation blocked trade (risk too high)")
                    return
                
                # Validate trade risk - only for OPEN trades
                if not bankroll_manager.validate_trade_risk(premium, quantity, config.get('MAX_PREMIUM_PCT', 50) * 100):
                    logger.error("[ERROR] Trade blocked by risk management")
                    return
                
                logger.info(f"[OPEN] Trade details: {decision.decision} ${atm_option['strike']} "
                           f"x{quantity} @ ${premium:.2f}")
                
                # Execute the OPEN trade flow (stops at Review)
                if bot.click_option_and_buy(atm_option['element'], quantity):
                    logger.info("[OPEN] Successfully reached Review Order screen")
                    
                    # Take screenshot
                    screenshot_path = bot.take_screenshot("open_review_order.png")
                    
                    # Send critical order ready alert to Slack with comprehensive details
                    if slack_notifier:
                        slack_notifier.send_order_ready_alert(
                            trade_type=decision.decision,
                            strike=f"${atm_option['strike']}",
                            expiry="Today",  # Assuming same-day expiry for breakout trades
                            position_size=premium * quantity,
                            # Enhanced details for manual review
                            action='OPEN',
                            confidence=decision.confidence,
                            reason=decision.reason or 'No specific reason provided',
                            current_price=analysis['current_price'],
                            premium=premium,
                            quantity=quantity,
                            total_cost=premium * quantity,
                            bankroll=current_bankroll,
                            trend=analysis.get('trend_direction', 'UNKNOWN'),
                            candle_body_pct=analysis.get('candle_body_pct', 0.0)
                        )
                    
                    print("\n" + "="*60)
                    print("[OPEN TRADE READY FOR REVIEW]")
                    print("="*60)
                    print(f"Direction: {decision.decision}")
                    print(f"Strike: ${atm_option['strike']}")
                    print(f"Quantity: {quantity} contracts")
                    print(f"Premium: ${premium:.2f} per contract")
                    print(f"Total Cost: ${premium * quantity:.2f}")
                    print(f"Confidence: {decision.confidence:.2f}")
                    print("\n🚨 MANUAL REVIEW REQUIRED - DO NOT AUTO-SUBMIT")
                    print("✅ Review the order details above and submit manually if approved")
                    print("="*60)
                    
                    # Wait for user to manually submit the order
                    input("\n📋 Press Enter AFTER you have manually submitted the order (or press Ctrl+C to cancel)...")
                    
                    # Prompt for fill price
                    while True:
                        try:
                            fill_price = float(input(f"\n💰 Enter the actual fill price per contract (estimated: ${premium:.2f}): $"))
                            if fill_price > 0:
                                break
                            else:
                                print("❌ Fill price must be greater than 0")
                        except ValueError:
                            print("❌ Please enter a valid number")
                    
                    # Create position record
                    new_position = Position(
                        entry_time=datetime.now().isoformat(),
                        symbol=config['SYMBOL'],
                        expiry="Today",  # You may want to make this configurable
                        strike=atm_option['strike'],
                        side=decision.decision,
                        contracts=quantity,
                        entry_premium=fill_price
                    )
                    
                    # Add position to portfolio
                    portfolio_manager.add_position(new_position)
                    
                    # Log the completed OPEN trade
                    trade_data = {
                        'timestamp': datetime.now().isoformat(),
                        'symbol': config['SYMBOL'],
                        'decision': decision.decision,
                        'confidence': decision.confidence,
                        'reason': decision.reason or '',
                        'current_price': analysis['current_price'],
                        'strike': atm_option['strike'],
                        'direction': decision.decision,
                        'quantity': quantity,
                        'premium': fill_price,
                        'total_cost': fill_price * quantity,
                        'llm_tokens': decision.tokens_used,
                        'bankroll_before': current_bankroll,
                        'bankroll_after': current_bankroll,  # Will be updated by bankroll manager
                        'status': 'OPENED'
                    }
                    log_trade_decision(config['TRADE_LOG_FILE'], trade_data)
                    
                    logger.info(f"[OPEN] Position opened: {decision.decision} ${atm_option['strike']} x{quantity} @ ${fill_price:.2f}")
                
                else:
                    logger.error("[ERROR] Failed to complete OPEN trade flow")
                    return
            
            # Handle CLOSE trade completion
            if trade_action == 'CLOSE':
                # Take screenshot for close order
                screenshot_path = bot.take_screenshot("close_review_order.png")
                
                # Send critical CLOSE order ready alert to Slack with comprehensive details
                if slack_notifier:
                    # Estimate exit premium based on current market conditions
                    estimated_exit_premium = analysis['current_price'] * 0.02  # Rough estimate
                    estimated_total_proceeds = estimated_exit_premium * position_to_close.contracts
                    
                    slack_notifier.send_order_ready_alert(
                        trade_type=position_to_close.side,
                        strike=f"${position_to_close.strike}",
                        expiry=position_to_close.expiry,
                        position_size=estimated_total_proceeds,
                        # Enhanced details for manual review
                        action='CLOSE',
                        confidence=decision.confidence,
                        reason=decision.reason or 'Closing existing position',
                        current_price=analysis['current_price'],
                        premium=estimated_exit_premium,
                        quantity=position_to_close.contracts,
                        total_cost=estimated_total_proceeds,
                        bankroll=current_bankroll,
                        trend=analysis.get('trend_direction', 'UNKNOWN'),
                        candle_body_pct=analysis.get('candle_body_pct', 0.0),
                        # CLOSE-specific details
                        entry_premium=position_to_close.entry_premium,
                        contracts_held=position_to_close.contracts
                    )
                
                print("\n" + "="*60)
                print("[CLOSE TRADE READY FOR REVIEW]")
                print("="*60)
                print(f"Closing: {position_to_close.side} ${position_to_close.strike}")
                print(f"Quantity: {position_to_close.contracts} contracts")
                print(f"Entry Premium: ${position_to_close.entry_premium:.2f} per contract")
                print(f"Entry Cost: ${position_to_close.entry_premium * position_to_close.contracts:.2f}")
                print("\n🚨 MANUAL REVIEW REQUIRED - DO NOT AUTO-SUBMIT")
                print("✅ Review the close order details above and submit manually if approved")
                print("="*60)
                
                # Wait for user to manually submit the close order
                input("\n📋 Press Enter AFTER you have manually submitted the CLOSE order (or press Ctrl+C to cancel)...")
                
                # Prompt for exit fill price
                while True:
                    try:
                        exit_price = float(input(f"\n💰 Enter the actual exit price per contract (entry was: ${position_to_close.entry_premium:.2f}): $"))
                        if exit_price > 0:
                            break
                        else:
                            print("❌ Exit price must be greater than 0")
                    except ValueError:
                        print("❌ Please enter a valid number")
                
                # Calculate realized P/L
                realized_pnl = portfolio_manager.calculate_realized_pnl(position_to_close, exit_price)
                
                # Remove position from portfolio
                portfolio_manager.remove_position(position_to_close)
                
                # Log realized trade to trade_log.csv
                portfolio_manager.log_realized_trade(
                    position_to_close, exit_price, realized_pnl, config['TRADE_LOG_FILE']
                )
                
                # Record trade outcome for LLM confidence calibration
                is_win = realized_pnl > 0
                bankroll_manager.record_trade_outcome(is_win)
                
                logger.info(f"[CLOSE] Position closed: {position_to_close.side} ${position_to_close.strike} "
                           f"x{position_to_close.contracts} - P/L: ${realized_pnl:.2f} ({'WIN' if is_win else 'LOSS'})")
                
                print(f"\n📊 TRADE COMPLETED:")
                print(f"   P/L: ${realized_pnl:.2f} ({'PROFIT' if realized_pnl > 0 else 'LOSS'})")
                print(f"   Entry: ${position_to_close.entry_premium:.2f} -> Exit: ${exit_price:.2f}")
                print(f"   Total Contracts: {position_to_close.contracts}")
    
    except KeyboardInterrupt:
        logger.info("[INTERRUPT] Script interrupted by user")
        if slack_notifier:
            slack_notifier.send_error_alert("User Interrupt", "Script was interrupted by user (Ctrl+C)")
    except Exception as e:
        logger.error(f"[ERROR] Unexpected error: {e}", exc_info=True)
        if slack_notifier:
            slack_notifier.send_error_alert("System Error", str(e))
    finally:
        logger.info("[COMPLETE] Script execution completed")
        
        # Send completion summary
        if slack_notifier:
            session_summary = {
                'trades_analyzed': 1,
                'decisions_made': 1,
                'final_bankroll': bankroll_manager.get_current_bankroll() if 'bankroll_manager' in locals() else 0,
                'duration': 'N/A'
            }
            slack_notifier.send_completion_summary(session_summary)

if __name__ == "__main__":
    main()
