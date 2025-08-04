#!/usr/bin/env python3
"""
Test Slack configuration
"""

import os
from dotenv import load_dotenv
from utils.slack import SlackNotifier

def test_slack():
    """Test Slack webhook configuration."""
    
    print("=== SLACK CONFIGURATION TEST ===")
    print()
    
    # Load environment variables
    load_dotenv()
    
    # Check if webhook URL is loaded
    webhook_url = os.getenv('SLACK_WEBHOOK_URL')
    
    if webhook_url:
        print(f"[OK] Slack webhook URL found: {webhook_url[:50]}...")
        
        # Test SlackNotifier
        try:
            slack_notifier = SlackNotifier()
            if slack_notifier.enabled:
                print("[OK] SlackNotifier initialized successfully")
                
                # Send test message
                success = slack_notifier.send_heartbeat("🧪 Test message from position monitoring system")
                if success:
                    print("[OK] Test message sent successfully!")
                    print("Check your Slack channel for the test message.")
                else:
                    print("[ERROR] Failed to send test message")
            else:
                print("[ERROR] SlackNotifier not enabled")
        except Exception as e:
            print(f"[ERROR] SlackNotifier failed: {e}")
    else:
        print("[ERROR] No SLACK_WEBHOOK_URL found in environment")
        print()
        print("Add this to your .env file:")
        print("SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL")
    
    print()
    print("=== ENVIRONMENT VARIABLES ===")
    slack_vars = [k for k in os.environ.keys() if 'SLACK' in k.upper()]
    if slack_vars:
        for var in slack_vars:
            value = os.getenv(var)
            masked_value = value[:20] + "..." if value and len(value) > 20 else value
            print(f"{var}: {masked_value}")
    else:
        print("No Slack environment variables found")

if __name__ == "__main__":
    test_slack()
