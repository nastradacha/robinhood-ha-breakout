#!/usr/bin/env python3
"""
Standalone Position Monitoring Script

Monitor your SPY $628 CALL trade for profit/loss targets.
This is a simplified version of the Priority 1 feature.
"""

import time
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import yfinance as yf
from dotenv import load_dotenv
from utils.portfolio import PortfolioManager
from utils.slack import SlackNotifier

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def monitor_positions():
    """Monitor existing positions for profit/loss targets."""
    
    parser = argparse.ArgumentParser(description='Monitor positions for profit/loss targets')
    parser.add_argument('--interval', type=int, default=2,
                       help='Minutes between checks (default: 2)')
    parser.add_argument('--end-at', type=str, default='15:45',
                       help='End time in HH:MM format (default: 15:45)')
    parser.add_argument('--slack-notify', action='store_true',
                       help='Send Slack notifications')
    
    args = parser.parse_args()
    
    # Parse end time
    try:
        end_hour, end_minute = map(int, args.end_at.split(':'))
        end_time = datetime.now().replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
        if end_time <= datetime.now():
            end_time += timedelta(days=1)
    except ValueError:
        logger.error(f"Invalid end time format: {args.end_at}. Use HH:MM")
        return
    
    logger.info(f"[START] Position monitoring - checking every {args.interval} minutes until {args.end_at}")
    
    # Load positions
    portfolio_manager = PortfolioManager("positions.csv")
    positions = portfolio_manager.load_positions()
    
    if not positions:
        logger.info("[NO POSITIONS] No open positions found")
        return
    
    logger.info(f"[MONITORING] Found {len(positions)} open position(s)")
    
    # Initialize Slack if requested
    slack_notifier = None
    if args.slack_notify:
        try:
            slack_notifier = SlackNotifier()
            if slack_notifier.enabled:
                slack_notifier.send_heartbeat(f"Starting position monitoring - {len(positions)} position(s)")
                logger.info("[SLACK] Notifications enabled")
            else:
                logger.warning("[SLACK] Slack not configured properly")
        except Exception as e:
            logger.warning(f"[SLACK] Failed to initialize: {e}")
    
    # Show positions being monitored
    for i, pos in enumerate(positions, 1):
        logger.info(f"[POSITION {i}] {pos.contracts} {pos.symbol} ${pos.strike} {pos.side} @ ${pos.entry_premium:.2f}")
        
        # Calculate targets
        profit_target = pos.entry_premium * 1.15  # 15% profit
        stop_loss = pos.entry_premium * 0.75      # 25% loss
        
        logger.info(f"[TARGETS {i}] Profit: ${profit_target:.2f} | Stop Loss: ${stop_loss:.2f}")
    
    # Monitoring loop
    cycle_count = 0
    last_alert_times = {}
    
    try:
        while True:
            cycle_count += 1
            current_time = datetime.now()
            
            # Check if we should stop
            if current_time >= end_time:
                logger.info(f"[END] Reached end time {end_time.strftime('%H:%M')} - stopping monitoring")
                if slack_notifier:
                    slack_notifier.send_heartbeat(f"Monitoring ended - remember to close positions!")
                break
            
            logger.info(f"[CYCLE {cycle_count}] Checking positions at {current_time.strftime('%H:%M:%S')}")
            
            # Check each position
            for i, position in enumerate(positions):
                check_position(position, i+1, slack_notifier, last_alert_times)
            
            # Periodic heartbeat
            if cycle_count % 10 == 0 and slack_notifier:
                slack_notifier.send_heartbeat(f"Still monitoring {len(positions)} position(s) - Cycle {cycle_count}")
            
            # Wait for next check
            logger.info(f"[WAIT] Next check in {args.interval} minutes...")
            time.sleep(args.interval * 60)
            
    except KeyboardInterrupt:
        logger.info("[STOP] Monitoring stopped by user (Ctrl+C)")
        if slack_notifier:
            slack_notifier.send_heartbeat("Position monitoring stopped by user")

def check_position(position, position_num, slack_notifier, last_alert_times):
    """Check a single position against profit/loss targets."""
    
    try:
        # Get current stock price
        ticker = yf.Ticker(position.symbol)
        current_stock_price = ticker.history(period="1d")['Close'].iloc[-1]
        
        # Simplified option value estimation
        if position.side.upper() == "CALL":
            intrinsic_value = max(0, current_stock_price - position.strike)
        else:  # PUT
            intrinsic_value = max(0, position.strike - current_stock_price)
        
        # Rough premium estimate (simplified)
        estimated_premium = intrinsic_value + max(0.01, position.entry_premium * 0.2)
        
        # Calculate P&L
        pnl_per_contract = estimated_premium - position.entry_premium
        pnl_percentage = (pnl_per_contract / position.entry_premium) * 100
        total_pnl = pnl_per_contract * position.contracts * 100
        
        # Targets
        profit_target = position.entry_premium * 1.15  # 15%
        stop_loss = position.entry_premium * 0.75      # 25%
        
        # Log status
        logger.info(f"[POS {position_num}] {position.symbol} ${position.strike} {position.side}")
        logger.info(f"[PRICE {position_num}] Stock: ${current_stock_price:.2f} | Est. Premium: ${estimated_premium:.2f}")
        logger.info(f"[P&L {position_num}] {pnl_percentage:+.1f}% (${total_pnl:+.0f})")
        
        # Check alerts
        position_key = f"{position.symbol}_{position.strike}_{position.side}"
        current_time = datetime.now()
        
        # Profit target (15%)
        if estimated_premium >= profit_target:
            if should_send_alert(position_key, "profit", last_alert_times, current_time):
                logger.warning(f"[PROFIT TARGET] Position {position_num} hit 15% profit!")
                if slack_notifier:
                    send_profit_alert(slack_notifier, position, estimated_premium, pnl_percentage, total_pnl)
                last_alert_times[f"{position_key}_profit"] = current_time
        
        # Stop loss (25%)
        elif estimated_premium <= stop_loss:
            if should_send_alert(position_key, "stop_loss", last_alert_times, current_time):
                logger.warning(f"[STOP LOSS] Position {position_num} hit 25% stop loss!")
                if slack_notifier:
                    send_stop_loss_alert(slack_notifier, position, estimated_premium, pnl_percentage, total_pnl)
                last_alert_times[f"{position_key}_stop_loss"] = current_time
        
        # End-of-day warning (3:30 PM)
        if current_time.hour == 15 and current_time.minute >= 30:
            if should_send_alert(position_key, "eod", last_alert_times, current_time):
                logger.warning(f"[END OF DAY] Position {position_num} should be closed soon!")
                if slack_notifier:
                    send_eod_alert(slack_notifier, position, estimated_premium, pnl_percentage)
                last_alert_times[f"{position_key}_eod"] = current_time
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to check position {position_num}: {e}")

def should_send_alert(position_key, alert_type, last_alert_times, current_time, cooldown_minutes=15):
    """Check if enough time has passed since last alert."""
    alert_key = f"{position_key}_{alert_type}"
    last_alert = last_alert_times.get(alert_key)
    
    if last_alert is None:
        return True
    
    return current_time - last_alert >= timedelta(minutes=cooldown_minutes)

def send_profit_alert(slack_notifier, position, current_premium, pnl_percentage, total_pnl):
    """Send profit target alert."""
    message = f"🎯 PROFIT TARGET HIT!\n{position.symbol} ${position.strike} {position.side}\nEntry: ${position.entry_premium:.2f} → Current: ${current_premium:.2f}\nP&L: {pnl_percentage:+.1f}% (${total_pnl:+.0f})\n\nConsider taking profits!"
    slack_notifier.send_heartbeat(message)

def send_stop_loss_alert(slack_notifier, position, current_premium, pnl_percentage, total_pnl):
    """Send stop loss alert."""
    message = f"🛑 STOP LOSS TRIGGERED!\n{position.symbol} ${position.strike} {position.side}\nEntry: ${position.entry_premium:.2f} → Current: ${current_premium:.2f}\nP&L: {pnl_percentage:+.1f}% (${total_pnl:+.0f})\n\nCLOSE POSITION to limit losses!"
    slack_notifier.send_heartbeat(message)

def send_eod_alert(slack_notifier, position, current_premium, pnl_percentage):
    """Send end-of-day alert."""
    message = f"⏰ END OF DAY WARNING\nClose {position.symbol} ${position.strike} {position.side} by 3:45 PM ET\nCurrent P&L: {pnl_percentage:+.1f}% (${current_premium:.2f})\n\nAvoid overnight risk!"
    slack_notifier.send_heartbeat(message)

if __name__ == "__main__":
    monitor_positions()
