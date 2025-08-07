"""
Simple Slack Test - Verify webhook configuration and send sample v0.7.0 alerts
"""

import os
import time
import requests
from dotenv import load_dotenv

def test_slack_webhook():
    """Test Slack webhook with v0.7.0 sample alerts."""
    # Load environment variables
    load_dotenv()
    
    webhook_url = os.getenv('SLACK_WEBHOOK_URL')
    
    if not webhook_url:
        print("[ERROR] SLACK_WEBHOOK_URL not found in .env file")
        return False
    
    print(f"[INFO] Found webhook URL: {webhook_url[:50]}...")
    
    # Test messages for all v0.7.0 features
    test_messages = [
        {
            "text": "🎬 **Slack UX Demo - v0.7.0 Features**\nTesting all four Slack UX improvements!"
        },
        {
            "text": "🟢 Monitor started for SPY"
        },
        {
            "text": "⏳ Cycle 3 (19:30) · SPY $580.25 · NO_TRADE"
        },
        {
            "text": "✅ Trade recorded: CALL 580 @ $1.28 · Qty 1"
        },
        {
            "text": """📊 **Daily Wrap-Up** 15:45 EST
**Trades:** 3
**Wins/Loss:** 2/1
**P&L:** $45.50
**Peak balance:** $545.50
**Current balance:** $540.25"""
        },
        {
            "text": "🔴 Monitor stopped for SPY"
        },
        {
            "text": "🎉 **Demo Complete!** All v0.7.0 Slack UX features demonstrated successfully!"
        }
    ]
    
    print(f"[INFO] Sending {len(test_messages)} test messages to Slack...")
    
    for i, message in enumerate(test_messages, 1):
        try:
            response = requests.post(webhook_url, json=message, timeout=10)
            if response.status_code == 200:
                print(f"[OK] Message {i}/{len(test_messages)} sent successfully")
            else:
                print(f"[ERROR] Message {i} failed: {response.status_code} - {response.text}")
                return False
            
            # Small delay between messages
            time.sleep(2)
            
        except Exception as e:
            print(f"[ERROR] Failed to send message {i}: {e}")
            return False
    
    print("[SUCCESS] All test messages sent! Check your Slack channel.")
    return True

if __name__ == "__main__":
    print("=" * 60)
    print("Slack UX Demo - v0.7.0 Features Test")
    print("=" * 60)
    
    success = test_slack_webhook()
    
    if success:
        print("\n🎉 Demo complete! You should see all the v0.7.0 alerts in Slack:")
        print("• S1: Monitor start/stop breadcrumbs")
        print("• S2: Throttled heartbeat messages")
        print("• S3: Fill-price echo confirmations")
        print("• S4: Daily summary block")
        print("\nThis is what you'll see during live trading sessions!")
    else:
        print("\n❌ Demo failed. Please check your Slack webhook configuration.")
