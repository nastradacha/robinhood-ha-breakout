#!/usr/bin/env python3
"""
Position Monitoring Module

Monitors existing positions for profit/loss targets and provides real-time alerts.
This is the Priority 1 feature for the robinhood-ha-breakout system.
"""

import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import yfinance as yf
from utils.portfolio import PortfolioManager, Position
from utils.slack import SlackNotifier

logger = logging.getLogger(__name__)

def monitor_positions_mode(config: Dict, args, env_vars: Dict, bankroll_manager, 
                          portfolio_manager: PortfolioManager, llm_client, 
                          slack_notifier: Optional[SlackNotifier], end_time: Optional[datetime]):
    """
    Monitor existing positions for profit/loss targets.
    
    This function implements the Priority 1 feature: Position Monitoring Automation.
    It checks open positions every N minutes and sends alerts when:
    - Profit target (15%) is reached
    - Stop loss (25%) is triggered  
    - End-of-day exit time approaches
    
    Args:
        config: Trading configuration
        args: CLI arguments (interval, end_time, etc.)
        env_vars: Environment variables
        bankroll_manager: Bankroll management instance
        portfolio_manager: Portfolio tracking instance
        llm_client: LLM client (unused in monitoring)
        slack_notifier: Slack notification instance
        end_time: Optional end time for monitoring
    """
    
    logger.info("[MONITOR] Starting position monitoring mode")
    
    # Load existing positions
    positions = portfolio_manager.load_positions()
    
    if not positions:
        logger.info("[MONITOR] No open positions found")
        if slack_notifier:
            slack_notifier.send_heartbeat("No open positions to monitor")
        return
    
    logger.info(f"[MONITOR] Found {len(positions)} open position(s)")
    
    # Show positions being monitored
    for i, pos in enumerate(positions, 1):
        logger.info(f"[POSITION {i}] {pos.contracts} {pos.symbol} ${pos.strike} {pos.side} @ ${pos.entry_premium:.2f}")
        
        # Calculate targets
        profit_target = pos.entry_premium * 1.15  # 15% profit
        stop_loss = pos.entry_premium * 0.75      # 25% loss
        
        logger.info(f"[TARGETS {i}] Profit: ${profit_target:.2f} | Stop Loss: ${stop_loss:.2f}")
    
    # Send initial monitoring notification
    if slack_notifier:
        position_summary = "\n".join([
            f"• {pos.contracts} {pos.symbol} ${pos.strike} {pos.side} @ ${pos.entry_premium:.2f}"
            for pos in positions
        ])
        slack_notifier.send_heartbeat(f"Monitoring {len(positions)} position(s):\n{position_summary}")
    
    # Monitoring loop
    cycle_count = 0
    last_alert_times = {}  # Track when we last sent alerts to avoid spam
    
    try:
        while True:
            cycle_count += 1
            current_time = datetime.now()
            
            # Check if we should stop monitoring
            if end_time and current_time >= end_time:
                logger.info(f"[MONITOR] Reached end time {end_time.strftime('%H:%M')} - stopping monitoring")
                if slack_notifier:
                    slack_notifier.send_heartbeat(f"Monitoring ended at {current_time.strftime('%H:%M')} - remember to close positions!")
                break
            
            logger.info(f"[CYCLE {cycle_count}] Checking positions at {current_time.strftime('%H:%M:%S')}")
            
            # Check each position
            for i, position in enumerate(positions):
                check_position_targets(position, i+1, slack_notifier, last_alert_times)
            
            # Send periodic heartbeat (every 10 cycles = ~20 minutes)
            if cycle_count % 10 == 0 and slack_notifier:
                slack_notifier.send_heartbeat(f"Still monitoring {len(positions)} position(s) - Cycle {cycle_count}")
            
            # Wait for next check
            logger.info(f"[MONITOR] Waiting {args.interval} minutes until next check...")
            time.sleep(args.interval * 60)  # Convert minutes to seconds
            
    except KeyboardInterrupt:
        logger.info("[MONITOR] Monitoring stopped by user (Ctrl+C)")
        if slack_notifier:
            slack_notifier.send_heartbeat("Position monitoring stopped by user")

def check_position_targets(position: Position, position_num: int, 
                          slack_notifier: Optional[SlackNotifier], 
                          last_alert_times: Dict) -> None:
    """
    Check a single position against profit/loss targets.
    
    Args:
        position: Position to check
        position_num: Position number for logging
        slack_notifier: Slack notifier instance
        last_alert_times: Dict to track when alerts were last sent
    """
    
    try:
        # Get current option price (simplified - using stock price as proxy)
        # In a full implementation, this would use options data API
        ticker = yf.Ticker(position.symbol)
        current_stock_price = ticker.history(period="1d")['Close'].iloc[-1]
        
        # Estimate current option value based on intrinsic value
        # This is a simplified calculation - real implementation would use Black-Scholes
        if position.side.upper() == "CALL":
            intrinsic_value = max(0, current_stock_price - position.strike)
        else:  # PUT
            intrinsic_value = max(0, position.strike - current_stock_price)
        
        # Simple estimation: current premium = intrinsic + time value decay
        # For 0DTE options, time value decays rapidly
        estimated_premium = intrinsic_value + (position.entry_premium - max(0, position.entry_premium * 0.1))
        estimated_premium = max(0.01, estimated_premium)  # Minimum $0.01
        
        # Calculate P&L
        pnl_per_contract = estimated_premium - position.entry_premium
        pnl_percentage = (pnl_per_contract / position.entry_premium) * 100
        total_pnl = pnl_per_contract * position.contracts * 100  # $100 per contract
        
        # Calculate targets
        profit_target = position.entry_premium * 1.15  # 15% profit
        stop_loss = position.entry_premium * 0.75      # 25% loss
        
        # Log current status
        logger.info(f"[POSITION {position_num}] {position.symbol} ${position.strike} {position.side}")
        logger.info(f"[PRICE {position_num}] Stock: ${current_stock_price:.2f} | Estimated Premium: ${estimated_premium:.2f}")
        logger.info(f"[P&L {position_num}] {pnl_percentage:+.1f}% (${total_pnl:+.0f})")
        
        # Check for alerts
        position_key = f"{position.symbol}_{position.strike}_{position.side}"
        current_time = datetime.now()
        
        # Profit target alert (15% gain)
        if estimated_premium >= profit_target:
            if should_send_alert(position_key, "profit", last_alert_times, current_time):
                logger.warning(f"[PROFIT TARGET] Position {position_num} hit 15% profit target!")
                if slack_notifier:
                    slack_notifier.send_profit_alert(
                        symbol=position.symbol,
                        strike=position.strike,
                        side=position.side,
                        entry_premium=position.entry_premium,
                        current_premium=estimated_premium,
                        pnl_percentage=pnl_percentage,
                        total_pnl=total_pnl
                    )
                last_alert_times[f"{position_key}_profit"] = current_time
        
        # Stop loss alert (25% loss)
        elif estimated_premium <= stop_loss:
            if should_send_alert(position_key, "stop_loss", last_alert_times, current_time):
                logger.warning(f"[STOP LOSS] Position {position_num} hit 25% stop loss!")
                if slack_notifier:
                    slack_notifier.send_stop_loss_alert(
                        symbol=position.symbol,
                        strike=position.strike,
                        side=position.side,
                        entry_premium=position.entry_premium,
                        current_premium=estimated_premium,
                        pnl_percentage=pnl_percentage,
                        total_pnl=total_pnl
                    )
                last_alert_times[f"{position_key}_stop_loss"] = current_time
        
        # End-of-day warning (3:30 PM ET)
        if current_time.hour == 15 and current_time.minute >= 30:
            if should_send_alert(position_key, "eod_warning", last_alert_times, current_time):
                logger.warning(f"[END OF DAY] Position {position_num} should be closed soon!")
                if slack_notifier:
                    slack_notifier.send_eod_warning(
                        symbol=position.symbol,
                        strike=position.strike,
                        side=position.side,
                        current_premium=estimated_premium,
                        pnl_percentage=pnl_percentage
                    )
                last_alert_times[f"{position_key}_eod_warning"] = current_time
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to check position {position_num}: {e}")

def should_send_alert(position_key: str, alert_type: str, last_alert_times: Dict, 
                     current_time: datetime, cooldown_minutes: int = 15) -> bool:
    """
    Check if enough time has passed since the last alert to avoid spam.
    
    Args:
        position_key: Unique position identifier
        alert_type: Type of alert (profit, stop_loss, eod_warning)
        last_alert_times: Dict tracking last alert times
        current_time: Current datetime
        cooldown_minutes: Minutes to wait between same alerts
    
    Returns:
        bool: True if alert should be sent
    """
    alert_key = f"{position_key}_{alert_type}"
    last_alert = last_alert_times.get(alert_key)
    
    if last_alert is None:
        return True  # First time sending this alert
    
    time_since_last = current_time - last_alert
    return time_since_last >= timedelta(minutes=cooldown_minutes)
