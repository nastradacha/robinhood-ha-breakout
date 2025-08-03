#!/usr/bin/env python3
"""
Enhanced Slack Bot integration for two-way communication.

This module provides both webhook (outgoing) and Bot Token (two-way) functionality
for trade confirmations and notifications.
"""

import os
import json
import time
import logging
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class SlackBot:
    """Enhanced Slack integration with Bot Token for two-way communication."""
    
    def __init__(self, bot_token: Optional[str] = None, channel_id: Optional[str] = None, 
                 webhook_url: Optional[str] = None):
        """Initialize Slack bot with token and channel."""
        self.bot_token = bot_token or os.getenv('SLACK_BOT_TOKEN')
        self.channel_id = channel_id or os.getenv('SLACK_CHANNEL_ID')
        self.webhook_url = webhook_url or os.getenv('SLACK_WEBHOOK_URL')
        
        self.logger = logging.getLogger(__name__)
        
        # Check what's available
        self.bot_enabled = bool(self.bot_token and self.channel_id)
        self.webhook_enabled = bool(self.webhook_url)
        
        if self.bot_enabled:
            self.headers = {
                'Authorization': f'Bearer {self.bot_token}',
                'Content-Type': 'application/json'
            }
            self.logger.info("Slack Bot Token integration enabled (two-way)")
        
        if self.webhook_enabled:
            self.logger.info("Slack Webhook integration enabled (outgoing only)")
        
        if not (self.bot_enabled or self.webhook_enabled):
            self.logger.warning("No Slack integration configured")
    
    def send_message(self, text: str, blocks: Optional[List[Dict]] = None) -> bool:
        """Send message using Bot Token (preferred) or webhook fallback."""
        if self.bot_enabled:
            return self._send_bot_message(text, blocks)
        elif self.webhook_enabled:
            return self._send_webhook_message(text, blocks)
        else:
            self.logger.warning("No Slack integration available")
            return False
    
    def _send_bot_message(self, text: str, blocks: Optional[List[Dict]] = None) -> bool:
        """Send message using Bot Token API."""
        try:
            payload = {
                'channel': self.channel_id,
                'text': text
            }
            
            if blocks:
                payload['blocks'] = blocks
            
            response = requests.post(
                'https://slack.com/api/chat.postMessage',
                headers=self.headers,
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    self.logger.debug("Bot message sent successfully")
                    return True
                else:
                    self.logger.error(f"Bot API error: {result.get('error', 'Unknown')}")
                    return False
            else:
                self.logger.error(f"Bot API HTTP error: {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to send bot message: {e}")
            return False
    
    def _send_webhook_message(self, text: str, blocks: Optional[List[Dict]] = None) -> bool:
        """Send message using webhook (fallback)."""
        try:
            payload = {'text': text}
            if blocks:
                payload['blocks'] = blocks
            
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                self.logger.debug("Webhook message sent successfully")
                return True
            else:
                self.logger.error(f"Webhook HTTP error: {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to send webhook message: {e}")
            return False
    
    def get_recent_messages(self, limit: int = 10, minutes_back: int = 5) -> List[Dict]:
        """Get recent messages from the channel (Bot Token required)."""
        if not self.bot_enabled:
            self.logger.warning("Bot Token required to read messages")
            return []
        
        try:
            # Calculate timestamp for X minutes ago
            oldest_time = datetime.now() - timedelta(minutes=minutes_back)
            oldest_ts = str(oldest_time.timestamp())
            
            response = requests.get(
                'https://slack.com/api/conversations.history',
                headers=self.headers,
                params={
                    'channel': self.channel_id,
                    'limit': limit,
                    'oldest': oldest_ts
                },
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    messages = result.get('messages', [])
                    # Filter out bot messages (only get user messages)
                    user_messages = [
                        msg for msg in messages 
                        if not msg.get('bot_id') and msg.get('user')
                    ]
                    return user_messages
                else:
                    self.logger.error(f"API error getting messages: {result.get('error')}")
                    return []
            else:
                self.logger.error(f"HTTP error getting messages: {response.status_code}")
                return []
                
        except Exception as e:
            self.logger.error(f"Failed to get messages: {e}")
            return []
    
    def check_for_trade_confirmations(self, minutes_back: int = 5) -> List[str]:
        """Check for trade confirmation messages in recent chat."""
        messages = self.get_recent_messages(limit=20, minutes_back=minutes_back)
        
        confirmations = []
        for msg in messages:
            text = msg.get('text', '').lower().strip()
            
            # Look for confirmation patterns
            if any(pattern in text for pattern in [
                'filled', 'cancelled', 'cancel', 'submit', 'submitted'
            ]):
                confirmations.append(text)
        
        return confirmations
    
    def send_trade_alert(self, trade_details: Dict) -> bool:
        """Send rich trade alert with confirmation request."""
        direction = trade_details.get('direction', 'CALL')
        strike = trade_details.get('strike', 0)
        premium = trade_details.get('premium', 0)
        confidence = trade_details.get('confidence', 0)
        
        # Create rich blocks
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🎯 {direction} Trade Ready"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Strike:* ${strike}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Premium:* ${premium:.2f}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Confidence:* {confidence:.1%}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Symbol:* {trade_details.get('symbol', 'SPY')}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Reason:* {trade_details.get('reason', 'No reason provided')}"
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "📱 *Confirm your decision:*\n• Type `filled 1.28` if submitted at $1.28\n• Type `cancelled` if you cancelled the trade"
                }
            }
        ]
        
        text = f"🎯 {direction} ${strike} @ ${premium:.2f} - Review screen ready!"
        return self.send_message(text, blocks)
    
    def send_heartbeat(self, message: str) -> bool:
        """Send simple heartbeat message."""
        return self.send_message(f"⏳ {message}")
    
    def send_confirmation(self, message: str) -> bool:
        """Send confirmation message."""
        return self.send_message(f"✅ {message}")


def create_slack_bot() -> SlackBot:
    """Factory function to create SlackBot instance."""
    return SlackBot()


if __name__ == "__main__":
    # Test the Slack bot integration
    bot = create_slack_bot()
    
    if bot.bot_enabled:
        print("Testing Bot Token integration...")
        
        # Test sending message
        success = bot.send_message("🧪 Test message from robinhood-ha-breakout")
        print(f"Send message: {'✅' if success else '❌'}")
        
        # Test getting messages
        messages = bot.get_recent_messages(limit=5, minutes_back=10)
        print(f"Recent messages: {len(messages)} found")
        
        # Test trade alert
        trade_details = {
            'direction': 'CALL',
            'strike': 635.0,
            'premium': 1.25,
            'confidence': 0.68,
            'symbol': 'SPY',
            'reason': 'Strong bullish breakout above resistance'
        }
        
        success = bot.send_trade_alert(trade_details)
        print(f"Trade alert: {'✅' if success else '❌'}")
        
    elif bot.webhook_enabled:
        print("Testing Webhook integration...")
        success = bot.send_message("🧪 Test webhook message")
        print(f"Webhook message: {'✅' if success else '❌'}")
        
    else:
        print("❌ No Slack integration configured")
        print("Set SLACK_BOT_TOKEN + SLACK_CHANNEL_ID or SLACK_WEBHOOK_URL in .env")
