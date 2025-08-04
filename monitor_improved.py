#!/usr/bin/env python3
"""
Improved Position Monitoring with Better Profit Detection

Key improvements:
1. Lower profit alert threshold (10% instead of 15%)
2. Multiple alert levels (5%, 10%, 15%, 20%+)
3. Better option price estimation
4. More frequent alerts for better timing
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
    """Improved position monitoring with better profit detection."""
    
    parser = argparse.ArgumentParser(description='Monitor positions with improved profit detection')
    parser.add_argument('--interval', type=int, default=1,
                       help='Minutes between checks (default: 1 for faster detection)')
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
    
    logger.info(f"[START] IMPROVED monitoring - checking every {args.interval} minute(s) until {args.end_at}")
    
    # Load positions
    portfolio_manager = PortfolioManager("positions.csv")
    positions = portfolio_manager.load_positions()
    
    if not positions:
        logger.info("[NO POSITIONS] No open positions found")
        return
    
    logger.info(f"[MONITORING] Found {len(positions)} open position(s)")
    
    # Initialize Slack
    slack_notifier = None
    if args.slack_notify:
        try:
            slack_notifier = SlackNotifier()
            if slack_notifier.enabled:
                slack_notifier.send_heartbeat(f"🚀 IMPROVED monitoring started - {len(positions)} position(s)")
                logger.info("[SLACK] Notifications enabled")
        except Exception as e:
            logger.warning(f"[SLACK] Failed to initialize: {e}")
    
    # Show positions with improved targets
    for i, pos in enumerate(positions, 1):
        logger.info(f"[POSITION {i}] {pos.contracts} {pos.symbol} ${pos.strike} {pos.side} @ ${pos.entry_premium:.2f}")
        
        # Multiple profit levels for better timing
        profit_5 = pos.entry_premium * 1.05   # 5% - early warning
        profit_10 = pos.entry_premium * 1.10  # 10% - consider selling
        profit_15 = pos.entry_premium * 1.15  # 15% - strong sell signal
        stop_loss = pos.entry_premium * 0.75  # 25% - stop loss
        
        logger.info(f"[TARGETS {i}] 5%: ${profit_5:.2f} | 10%: ${profit_10:.2f} | 15%: ${profit_15:.2f} | Stop: ${stop_loss:.2f}")
    
    # Monitoring loop with improved detection
    cycle_count = 0
    last_alert_times = {}
    
    try:
        while True:
            cycle_count += 1
            current_time = datetime.now()
            
            # Check if we should stop
            if current_time >= end_time:
                logger.info(f"[END] Reached end time {end_time.strftime('%H:%M')}")
                if slack_notifier:
                    slack_notifier.send_heartbeat("⏰ Monitoring ended - remember to close positions!")
                break
            
            logger.info(f"[CYCLE {cycle_count}] Checking positions at {current_time.strftime('%H:%M:%S')}")
            
            # Check each position with improved logic
            for i, position in enumerate(positions):
                check_position_improved(position, i+1, slack_notifier, last_alert_times)
            
            # More frequent heartbeats for active monitoring
            if cycle_count % 5 == 0 and slack_notifier:
                slack_notifier.send_heartbeat(f"📊 Active monitoring - Cycle {cycle_count}")
            
            # Wait for next check (shorter interval for better timing)
            logger.info(f"[WAIT] Next check in {args.interval} minute(s)...")
            time.sleep(args.interval * 60)
            
    except KeyboardInterrupt:
        logger.info("[STOP] Monitoring stopped by user")
        if slack_notifier:
            slack_notifier.send_heartbeat("⏹️ Position monitoring stopped by user")

def check_position_improved(position, position_num, slack_notifier, last_alert_times):
    """Improved position checking with better profit detection."""
    
    try:
        # Get current stock price
        ticker = yf.Ticker(position.symbol)
        current_stock_price = ticker.history(period="1d")['Close'].iloc[-1]
        
        # Improved option value estimation
        if position.side.upper() == "CALL":
            intrinsic_value = max(0, current_stock_price - position.strike)
        else:  # PUT
            intrinsic_value = max(0, position.strike - current_stock_price)
        
        # Better premium estimation (more realistic for 0DTE)
        # For ATM/ITM options, intrinsic value is primary component
        time_value = max(0.05, position.entry_premium * 0.1)  # Minimal time value for 0DTE
        estimated_premium = intrinsic_value + time_value
        estimated_premium = max(0.01, estimated_premium)  # Minimum $0.01
        
        # Calculate P&L
        pnl_per_contract = estimated_premium - position.entry_premium
        pnl_percentage = (pnl_per_contract / position.entry_premium) * 100
        total_pnl = pnl_per_contract * position.contracts * 100
        
        # Multiple profit targets
        profit_5 = position.entry_premium * 1.05   # 5%
        profit_10 = position.entry_premium * 1.10  # 10%
        profit_15 = position.entry_premium * 1.15  # 15%
        stop_loss = position.entry_premium * 0.75  # 25%
        
        # Enhanced logging
        logger.info(f"[POS {position_num}] {position.symbol} ${position.strike} {position.side}")
        logger.info(f"[PRICE {position_num}] Stock: ${current_stock_price:.2f} | Intrinsic: ${intrinsic_value:.2f} | Est: ${estimated_premium:.2f}")
        logger.info(f"[P&L {position_num}] {pnl_percentage:+.1f}% (${total_pnl:+.0f})")
        
        # Check multiple profit levels
        position_key = f"{position.symbol}_{position.strike}_{position.side}"
        current_time = datetime.now()
        
        # 15%+ profit (strong sell signal)
        if estimated_premium >= profit_15:
            if should_send_alert(position_key, "profit_15", last_alert_times, current_time, 10):
                logger.warning(f"[PROFIT 15%+] Position {position_num} hit 15%+ profit target!")
                if slack_notifier:
                    send_profit_alert(slack_notifier, position, estimated_premium, pnl_percentage, total_pnl, "15%+ STRONG SELL SIGNAL")
                last_alert_times[f"{position_key}_profit_15"] = current_time
        
        # 10% profit (consider selling)
        elif estimated_premium >= profit_10:
            if should_send_alert(position_key, "profit_10", last_alert_times, current_time, 10):
                logger.warning(f"[PROFIT 10%] Position {position_num} hit 10% profit - consider selling!")
                if slack_notifier:
                    send_profit_alert(slack_notifier, position, estimated_premium, pnl_percentage, total_pnl, "10% Consider Selling")
                last_alert_times[f"{position_key}_profit_10"] = current_time
        
        # 5% profit (early warning)
        elif estimated_premium >= profit_5:
            if should_send_alert(position_key, "profit_5", last_alert_times, current_time, 15):
                logger.info(f"[PROFIT 5%] Position {position_num} hit 5% profit - watch closely!")
                if slack_notifier:
                    send_profit_alert(slack_notifier, position, estimated_premium, pnl_percentage, total_pnl, "5% Early Profit")
                last_alert_times[f"{position_key}_profit_5"] = current_time
        
        # Stop loss
        elif estimated_premium <= stop_loss:
            if should_send_alert(position_key, "stop_loss", last_alert_times, current_time, 5):
                logger.warning(f"[STOP LOSS] Position {position_num} hit 25% stop loss!")
                if slack_notifier:
                    send_stop_loss_alert(slack_notifier, position, estimated_premium, pnl_percentage, total_pnl)
                last_alert_times[f"{position_key}_stop_loss"] = current_time
        
        # End-of-day warning
        if current_time.hour == 15 and current_time.minute >= 30:
            if should_send_alert(position_key, "eod", last_alert_times, current_time, 10):
                logger.warning(f"[END OF DAY] Position {position_num} should be closed soon!")
                if slack_notifier:
                    send_eod_alert(slack_notifier, position, estimated_premium, pnl_percentage)
                last_alert_times[f"{position_key}_eod"] = current_time
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to check position {position_num}: {e}")

def should_send_alert(position_key, alert_type, last_alert_times, current_time, cooldown_minutes=10):
    """Check if enough time has passed since last alert."""
    alert_key = f"{position_key}_{alert_type}"
    last_alert = last_alert_times.get(alert_key)
    
    if last_alert is None:
        return True
    
    return current_time - last_alert >= timedelta(minutes=cooldown_minutes)

def send_profit_alert(slack_notifier, position, current_premium, pnl_percentage, total_pnl, alert_level):
    """Send improved profit alert."""
    message = f"🎯 {alert_level}!\n{position.symbol} ${position.strike} {position.side}\nEntry: ${position.entry_premium:.2f} → Current: ${current_premium:.2f}\nP&L: {pnl_percentage:+.1f}% (${total_pnl:+.0f})\n\n{'STRONG SELL SIGNAL!' if '15%' in alert_level else 'Consider taking profits!'}"
    slack_notifier.send_heartbeat(message)

def send_stop_loss_alert(slack_notifier, position, current_premium, pnl_percentage, total_pnl):
    """Send stop loss alert."""
    message = f"🛑 STOP LOSS!\n{position.symbol} ${position.strike} {position.side}\nEntry: ${position.entry_premium:.2f} → Current: ${current_premium:.2f}\nP&L: {pnl_percentage:+.1f}% (${total_pnl:+.0f})\n\nCLOSE POSITION NOW!"
    slack_notifier.send_heartbeat(message)

def send_eod_alert(slack_notifier, position, current_premium, pnl_percentage):
    """Send end-of-day alert."""
    message = f"⏰ END OF DAY!\nClose {position.symbol} ${position.strike} {position.side} by 3:45 PM\nCurrent: ${current_premium:.2f} ({pnl_percentage:+.1f}%)\n\nAvoid overnight risk!"
    slack_notifier.send_heartbeat(message)

if __name__ == "__main__":
    monitor_positions()
