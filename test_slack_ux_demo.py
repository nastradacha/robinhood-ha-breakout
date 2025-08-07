"""
Slack UX Demo Script - v0.7.0 Features Test

This script demonstrates all four Slack UX improvements:
- S1: Monitor start/stop breadcrumbs
- S2: Throttled heartbeat one-liner
- S3: Fill-price echo after confirmation
- S4: End-of-day summary block

Run this to see what the alerts look like in your Slack channel.
"""

import time
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from utils.enhanced_slack import EnhancedSlackIntegration
from utils.llm import load_config


def demo_s1_breadcrumbs(slack: EnhancedSlackIntegration):
    """Demo S1: Monitor start/stop breadcrumbs."""
    print("[S1] Sending Monitor breadcrumbs...")
    
    # Monitor start breadcrumb
    slack.send_info("🟢 Monitor started for SPY")
    time.sleep(2)
    
    # Monitor start for multiple symbols
    slack.send_info("🟢 Monitor started for QQQ")
    time.sleep(2)
    
    slack.send_info("🟢 Monitor started for IWM")
    time.sleep(3)
    
    # Monitor stop breadcrumbs
    slack.send_info("🔴 Monitor stopped for SPY")
    time.sleep(2)
    
    slack.send_info("🔴 Monitor stopped for QQQ")
    time.sleep(2)
    
    slack.send_info("🔴 Monitor stopped for IWM")
    print("[OK] S1 breadcrumbs sent!")


def demo_s2_heartbeat(slack: EnhancedSlackIntegration):
    """Demo S2: Throttled heartbeat one-liner."""
    print("[S2] Sending Heartbeat messages...")
    
    current_time = datetime.now().strftime("%H:%M")
    
    # Single symbol heartbeat
    heartbeat_msg = f"⏳ Cycle 3 ({current_time}) · SPY $580.25 · NO_TRADE"
    slack.send_heartbeat(heartbeat_msg)
    time.sleep(3)
    
    # Multi-symbol heartbeat
    heartbeat_msg = f"⏳ Cycle 6 ({current_time}) · SPY $582.10, QQQ $485.50, IWM $220.75 · NO_TRADE"
    slack.send_heartbeat(heartbeat_msg)
    time.sleep(3)
    
    # Different cycle
    heartbeat_msg = f"⏳ Cycle 9 ({current_time}) · SPY $579.85 · NO_TRADE"
    slack.send_heartbeat(heartbeat_msg)
    print("[OK] S2 heartbeat messages sent!")


def demo_s3_fill_echo(slack: EnhancedSlackIntegration):
    """Demo S3: Fill-price echo after confirmation."""
    print("[S3] Sending Fill-price echo messages...")
    
    # Successful trade confirmations
    fill_echo_msg = "✅ Trade recorded: CALL 580 @ $1.28 · Qty 1"
    slack.send_heartbeat(fill_echo_msg)
    time.sleep(3)
    
    fill_echo_msg = "✅ Trade recorded: PUT 485 @ $2.45 · Qty 2"
    slack.send_heartbeat(fill_echo_msg)
    time.sleep(3)
    
    fill_echo_msg = "✅ Trade recorded: CALL 220 @ $0.85 · Qty 3"
    slack.send_heartbeat(fill_echo_msg)
    time.sleep(3)
    
    # Cancelled trade
    cancel_msg = "❌ Trade cancelled: PUT 580"
    slack.send_heartbeat(cancel_msg)
    print("[OK] S3 fill-price echo messages sent!")


def demo_s4_daily_summary(slack: EnhancedSlackIntegration):
    """Demo S4: End-of-day summary block."""
    print("[S4] Sending Daily summary block...")
    
    # Generate sample daily summary
    end_time = datetime.now()
    daily_summary = f"""📊 **Daily Wrap-Up** {end_time.strftime('%H:%M %Z')}
**Trades:** 5
**Wins/Loss:** 3/2
**P&L:** $127.50
**Peak balance:** $627.50
**Current balance:** $615.25"""
    
    slack.send_heartbeat(daily_summary)
    print("[OK] S4 daily summary sent!")


def demo_rich_trade_alert(slack: EnhancedSlackIntegration):
    """Demo rich trade alert with charts (bonus)."""
    print("[BONUS] Sending rich trade alert...")
    
    try:
        # Sample trade alert
        slack.send_order_ready_alert(
            trade_type="CALL",
            strike="580",
            expiry="Today",
            position_size="$128",
            action="OPEN",
            confidence=0.78,
            reason="Strong bullish breakout with volume confirmation above resistance",
            current_price=579.85,
            quantity=1
        )
        print("[OK] Rich trade alert sent!")
    except Exception as e:
        print(f"[WARN] Rich trade alert failed (expected if missing dependencies): {e}")
        # Fallback to simple alert
        alert_msg = """🚨 **TRADE OPPORTUNITY**
**Symbol:** SPY
**Action:** CALL 580
**Confidence:** 78%
**Reason:** Strong bullish breakout with volume confirmation
**Current Price:** $579.85
**Position Size:** $128 (1 contract)

⚠️ **Review Required** - Check browser for order details"""
        slack.send_heartbeat(alert_msg)
        print("[OK] Fallback trade alert sent!")


def main():
    """Run comprehensive Slack UX demo."""
    print("[DEMO] Starting Slack UX Demo - v0.7.0 Features")
    print("=" * 50)
    
    try:
        # Load configuration
        config = load_config()
        
        # Initialize Slack integration
        slack = EnhancedSlackIntegration()
        
        # Send demo start message
        demo_start_msg = """🎬 **Slack UX Demo Starting**
Testing all v0.7.0 features:
• S1: Monitor breadcrumbs
• S2: Throttled heartbeat
• S3: Fill-price echo
• S4: Daily summary block"""
        
        slack.send_heartbeat(demo_start_msg)
        time.sleep(3)
        
        # Demo each feature
        demo_s1_breadcrumbs(slack)
        time.sleep(2)
        
        demo_s2_heartbeat(slack)
        time.sleep(2)
        
        demo_s3_fill_echo(slack)
        time.sleep(2)
        
        demo_s4_daily_summary(slack)
        time.sleep(2)
        
        # Bonus: Rich trade alert
        demo_rich_trade_alert(slack)
        time.sleep(2)
        
        # Demo completion message
        demo_end_msg = """🎬 **Slack UX Demo Complete**
All v0.7.0 features demonstrated!

**What you just saw:**
✅ S1: Monitor start/stop breadcrumbs
✅ S2: Throttled heartbeat messages
✅ S3: Fill-price echo confirmations
✅ S4: End-of-day summary block
✅ Rich trade alerts with charts

**Impact:** Zero manual terminal watching required!"""
        
        slack.send_heartbeat(demo_end_msg)
        
        print("=" * 50)
        print("[DEMO] Slack UX Demo Complete!")
        print("Check your Slack channel to see all the alerts.")
        print("This is what you'll see during live trading sessions.")
        
    except Exception as e:
        print(f"[ERROR] Demo failed: {e}")
        print("Make sure your Slack configuration is correct in config.yaml and .env")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
