"""
Slack Events API Webhook Server

Simple Flask server to receive Slack events and process trade confirmations
in real-time instead of polling.
"""

import os
import time
import logging
from flask import Flask, request, jsonify
from typing import Optional
import threading
import queue

logger = logging.getLogger(__name__)

class SlackWebhookServer:
    """Flask server for handling Slack Events API webhooks."""
    
    def __init__(self, port: int = 3000):
        self.app = Flask(__name__)
        self.port = port
        self.message_queue = queue.Queue()
        self.trade_confirmation_manager = None
        self._setup_routes()
        
    def _setup_routes(self):
        """Setup Flask routes for Slack events."""
        
        @self.app.route('/slack/events', methods=['POST'])
        def handle_slack_event():
            """Handle incoming Slack events."""
            try:
                # Get raw data first
                raw_data = request.get_data(as_text=True)
                logger.info(f"[SLACK-WEBHOOK] Raw request: {raw_data}")
                
                data = request.get_json(force=True)
                logger.info(f"[SLACK-WEBHOOK] Parsed JSON: {data}")
                
                # Handle URL verification challenge
                if data and data.get('type') == 'url_verification':
                    challenge = data.get('challenge')
                    logger.info(f"[SLACK-WEBHOOK] Returning challenge: {challenge}")
                    return challenge, 200
                
                # Handle actual events
                if data and data.get('type') == 'event_callback':
                    event = data.get('event', {})
                    
                    # Only process message events
                    if event.get('type') == 'message':
                        # Skip bot messages
                        if event.get('bot_id'):
                            return jsonify({'status': 'ok'})
                            
                        text = event.get('text', '').strip()
                        user_id = event.get('user')
                        channel = event.get('channel')
                        
                        logger.info(f"[SLACK-WEBHOOK] Received message: '{text}' from {user_id}")
                        
                        # Process trade confirmation message
                        if self.trade_confirmation_manager:
                            handled = self.trade_confirmation_manager.process_slack_message(text)
                            if handled:
                                logger.info("[SLACK-WEBHOOK] Trade confirmation processed")
                        
                return jsonify({'status': 'ok'})
                
            except Exception as e:
                logger.error(f"[SLACK-WEBHOOK] Error processing event: {e}")
                import traceback
                logger.error(f"[SLACK-WEBHOOK] Traceback: {traceback.format_exc()}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/health', methods=['GET'])
        def health_check():
            """Health check endpoint."""
            return jsonify({'status': 'healthy', 'service': 'slack-webhook'})
    
    def set_trade_confirmation_manager(self, manager):
        """Set the trade confirmation manager for processing messages."""
        self.trade_confirmation_manager = manager
    
    def start_server(self, host: str = '0.0.0.0'):
        """Start the Flask server in a background thread."""
        def run_server():
            logger.info(f"[SLACK-WEBHOOK] Starting server on {host}:{self.port}")
            self.app.run(host=host, port=self.port, debug=False, use_reloader=False)
        
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        logger.info(f"[SLACK-WEBHOOK] Server started in background thread")
        
        return f"http://{host}:{self.port}/slack/events"


def create_slack_webhook_server(port: int = 3000) -> SlackWebhookServer:
    """
    Create and configure a Slack webhook server.
    
    Args:
        port: Port to run the server on
        
    Returns:
        Configured SlackWebhookServer instance
    """
    return SlackWebhookServer(port=port)


if __name__ == "__main__":
    # For testing the webhook server standalone
    server = create_slack_webhook_server()
    server.start_server()
    
    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Webhook server stopped")
