#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick Slack Configuration Test Script
Run this after adding SLACK_BOT_TOKEN and SLACK_CHANNEL_ID to .env
"""

import os
import sys
from dotenv import load_dotenv

# Fix Windows console encoding issues
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def test_slack_config():
    """Test Slack configuration and send a test message."""
    
    # Load environment variables
    load_dotenv()
    
    # Check for required Slack credentials
    bot_token = os.getenv("SLACK_BOT_TOKEN")
    channel_id = os.getenv("SLACK_CHANNEL_ID")
    
    print("Checking Slack Configuration...")
    print(f"SLACK_BOT_TOKEN: {'Found' if bot_token else 'Missing'}")
    print(f"SLACK_CHANNEL_ID: {'Found' if channel_id else 'Missing'}")
    
    if not bot_token or not channel_id:
        print("\nSlack configuration incomplete!")
        print("\nTo fix this, add these lines to your .env file:")
        print("SLACK_BOT_TOKEN=xoxb-your-bot-token-here")
        print("SLACK_CHANNEL_ID=C1234567890")
        print("\nHow to get these values:")
        print("1. Bot Token: https://api.slack.com/apps -> Your App -> OAuth & Permissions")
        print("2. Channel ID: Right-click channel -> Copy link -> Extract ID after /archives/")
        return False
    
    # Test Slack integration
    try:
        from utils.enhanced_slack import EnhancedSlackIntegration
        
        print("\nTesting Slack integration...")
        slack = EnhancedSlackIntegration()
        
        if not slack.enabled:
            print("Slack integration disabled or failed to initialize")
            return False
        
        # Send test message using the basic Slack notifier
        from utils.slack import SlackNotifier
        basic_slack = SlackNotifier()
        success = basic_slack.send_message("🧪 Slack integration test successful! Alpaca trading notifications are now working.")
        
        if success:
            print("Test message sent successfully!")
            print("Check your Slack channel for the test message.")
            return True
        else:
            print("Failed to send test message")
            return False
            
    except Exception as e:
        print(f"Error testing Slack integration: {e}")
        return False

if __name__ == "__main__":
    print("Alpaca Trading - Slack Configuration Test")
    print("=" * 50)
    
    success = test_slack_config()
    
    if success:
        print("\nSUCCESS! Slack notifications are now configured and working.")
        print("You should now receive Slack alerts for:")
        print("- Breakout opportunities detected")
        print("- Trade confirmations and fills")
        print("- Position monitoring alerts")
        print("- Exit strategy notifications")
    else:
        print("\nFAILED! Please fix the configuration and try again.")
