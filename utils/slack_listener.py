"""
Slack Event Listener for Trade Confirmations

Simple polling-based Slack message listener that checks for trade confirmation
messages without requiring webhook infrastructure.
"""

import time
import logging
from typing import Optional, Callable
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)


class SlackTradeListener:
    """Polls Slack for trade confirmation messages."""
    
    def __init__(self, slack_token: str, channel_id: Optional[str] = None):
        """
        Initialize Slack listener.
        
        Args:
            slack_token: Slack bot token
            channel_id: Channel ID to monitor (None for DMs)
        """
        self.client = WebClient(token=slack_token)
        self.channel_id = channel_id
        self.last_timestamp = None
        self.running = False
        
    def start_listening(self, message_handler: Callable[[str], bool], poll_interval: int = 5):
        """
        Start polling for messages.
        
        Args:
            message_handler: Function to process messages (returns True if handled)
            poll_interval: Seconds between polls
        """
        self.running = True
        logger.info(f"[SLACK-LISTENER] Started polling every {poll_interval}s")
        
        while self.running:
            try:
                self._check_for_messages(message_handler)
                time.sleep(poll_interval)
            except KeyboardInterrupt:
                logger.info("[SLACK-LISTENER] Stopped by user")
                break
            except Exception as e:
                logger.error(f"[SLACK-LISTENER] Error: {e}")
                time.sleep(poll_interval)
    
    def stop_listening(self):
        """Stop the polling loop."""
        self.running = False
        
    def _check_for_messages(self, message_handler: Callable[[str], bool]):
        """Check for new messages and process them."""
        try:
            # Get conversations (DMs or channels)
            if self.channel_id:
                # Monitor specific channel
                response = self.client.conversations_history(
                    channel=self.channel_id,
                    oldest=self.last_timestamp,
                    limit=10
                )
            else:
                # Monitor DMs to the bot
                response = self.client.conversations_list(
                    types="im",
                    limit=10
                )
                
                if not response["channels"]:
                    return
                    
                # Get messages from the first DM channel
                dm_channel = response["channels"][0]["id"]
                response = self.client.conversations_history(
                    channel=dm_channel,
                    oldest=self.last_timestamp,
                    limit=10
                )
            
            messages = response.get("messages", [])
            
            # Process new messages (excluding bot's own messages)
            for message in reversed(messages):  # Process oldest first
                if message.get("bot_id"):
                    continue  # Skip bot messages
                    
                text = message.get("text", "").strip()
                if text:
                    logger.info(f"[SLACK-LISTENER] Received: '{text}'")
                    handled = message_handler(text)
                    if handled:
                        logger.info(f"[SLACK-LISTENER] Message processed successfully")
                        
                # Update timestamp to avoid reprocessing
                self.last_timestamp = message.get("ts")
                
        except SlackApiError as e:
            logger.error(f"[SLACK-LISTENER] Slack API error: {e}")
        except Exception as e:
            logger.error(f"[SLACK-LISTENER] Unexpected error: {e}")


def create_trade_confirmation_listener(slack_token: str, trade_confirmation_manager) -> SlackTradeListener:
    """
    Create a Slack listener specifically for trade confirmations.
    
    Args:
        slack_token: Slack bot token
        trade_confirmation_manager: TradeConfirmationManager instance
        
    Returns:
        Configured SlackTradeListener
    """
    listener = SlackTradeListener(slack_token)
    
    def handle_trade_message(message: str) -> bool:
        """Handle incoming Slack messages for trade confirmation."""
        return trade_confirmation_manager.process_slack_message(message)
    
    return listener, handle_trade_message
