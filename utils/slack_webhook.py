"""
Slack Events API Webhook Server

Simple Flask server to receive Slack events and process trade confirmations
in real-time instead of polling.
"""

import os
import time
import logging
import hmac
import hashlib
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
        
    def _handle_trading_status_command(self, data):
        """Handle /trading-status slash command."""
        try:
            from utils.system_status import get_system_status
            
            # Get complete system status
            status_report = get_system_status()
            
            # Format as Slack message blocks
            blocks = self._format_status_blocks(status_report)
            
            # Return immediate response
            return jsonify({
                "response_type": "ephemeral",
                "blocks": blocks
            })
            
        except Exception as e:
            logger.error(f"[SLACK-WEBHOOK] Error handling trading status command: {e}")
            return jsonify({
                "response_type": "ephemeral",
                "text": f"❌ Error retrieving system status: {str(e)}"
            })
    
    def _format_status_blocks(self, status_report):
        """Format system status as Slack message blocks."""
        blocks = []
        
        # Header block
        health_emoji = {
            "healthy": "🟢",
            "degraded": "🟡", 
            "critical": "🔴"
        }.get(status_report.system_health.status, "⚪")
        
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{health_emoji} Trading System Status"
            }
        })
        
        # System health section
        blocks.append({
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Status:* {status_report.system_health.status.title()}"
                },
                {
                    "type": "mrkdwn", 
                    "text": f"*Uptime:* {status_report.system_health.uptime}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Last Update:* {status_report.system_health.last_update}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Recovery Active:* {'Yes' if status_report.system_health.recovery_active else 'No'}"
                }
            ]
        })
        
        # Positions section
        if status_report.positions:
            position_text = ""
            for pos in status_report.positions[:5]:  # Show top 5
                pnl_emoji = "🟢" if pos.unrealized_pnl >= 0 else "🔴"
                position_text += f"{pnl_emoji} {pos.symbol} ({pos.broker.upper()}/{pos.environment.upper()}): "
                position_text += f"${pos.unrealized_pnl:.2f} ({pos.unrealized_pnl_pct:+.1f}%)\n"
            
            if len(status_report.positions) > 5:
                position_text += f"... and {len(status_report.positions) - 5} more positions"
                
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Active Positions ({status_report.total_positions}):*\n{position_text}"
                }
            })
        else:
            blocks.append({
                "type": "section", 
                "text": {
                    "type": "mrkdwn",
                    "text": "*Active Positions:* None"
                }
            })
        
        # Daily summary section
        win_emoji = "🎯" if status_report.daily_summary.win_rate >= 70 else "📊"
        pnl_emoji = "🟢" if status_report.daily_summary.realized_pnl >= 0 else "🔴"
        
        blocks.append({
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Trades Today:* {status_report.daily_summary.trades_today}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Daily P&L:* {pnl_emoji} ${status_report.daily_summary.realized_pnl:.2f}"
                },
                {
                    "type": "mrkdwn", 
                    "text": f"*Win Rate:* {win_emoji} {status_report.daily_summary.win_rate:.1f}%"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Total Unrealized:* ${status_report.total_unrealized_pnl:.2f}"
                }
            ]
        })
        
        # Market conditions section
        market_emoji = "🟢" if status_report.market_conditions.market_open else "🔴"
        vix_emoji = {
            "low": "🟢",
            "normal": "🟡", 
            "elevated": "🟠",
            "high": "🔴"
        }.get(status_report.market_conditions.vix_status, "⚪")
        
        vix_text = f"{status_report.market_conditions.vix:.1f}" if status_report.market_conditions.vix else "N/A"
        
        blocks.append({
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Market:* {market_emoji} {'Open' if status_report.market_conditions.market_open else 'Closed'}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*VIX:* {vix_emoji} {vix_text}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Hours:* {status_report.market_conditions.market_hours}"
                },
                {
                    "type": "mrkdwn", 
                    "text": f"*Time to Close:* {status_report.market_conditions.time_to_close}"
                }
            ]
        })
        
        # API connectivity section
        api_status = []
        for api, connected in status_report.system_health.api_connectivity.items():
            emoji = "🟢" if connected else "🔴"
            api_status.append(f"{emoji} {api.title()}")
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn", 
                "text": f"*API Status:* {' | '.join(api_status)}"
            }
        })
        
        # Footer with timestamp
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"📅 Generated at {status_report.timestamp} | Use `/trading-status` to refresh"
                }
            ]
        })
        
        return blocks
        
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
                
                # Handle slash commands
                if data and data.get('type') == 'slash_command':
                    command = data.get('command')
                    if command == '/trading-status':
                        return self._handle_trading_status_command(data)
                
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
        
        @self.app.route('/slack/commands', methods=['POST'])
        def handle_slack_command():
            """Handle Slack slash commands."""
            try:
                # Verify Slack signature
                if not self._verify_slack_signature(request):
                    logger.warning("[SLACK-COMMANDS] Invalid signature")
                    return jsonify({'error': 'Invalid signature'}), 401
                
                # Parse form data
                command = request.form.get('command', '')
                text = request.form.get('text', '').strip()
                user_id = request.form.get('user_id', '')
                user_name = request.form.get('user_name', '')
                
                logger.info(f"[SLACK-COMMANDS] Received {command} from {user_name} ({user_id}): '{text}'")
                
                # Check if user is authorized (optional)
                allowed_users = os.getenv('SLACK_ALLOWED_USER_IDS', '').split(',')
                if allowed_users and allowed_users[0] and user_id not in allowed_users:
                    logger.warning(f"[SLACK-COMMANDS] Unauthorized user {user_id}")
                    return jsonify({
                        'response_type': 'ephemeral',
                        'text': '❌ You are not authorized to use this command.'
                    })
                
                # Handle commands
                if command == '/stop-trading':
                    return self._handle_stop_trading(text, user_name)
                elif command == '/resume-trading':
                    return self._handle_resume_trading(user_name)
                else:
                    return jsonify({
                        'response_type': 'ephemeral',
                        'text': f'❓ Unknown command: {command}'
                    })
                    
            except Exception as e:
                logger.error(f"[SLACK-COMMANDS] Error processing command: {e}")
                import traceback
                logger.error(f"[SLACK-COMMANDS] Traceback: {traceback.format_exc()}")
                return jsonify({
                    'response_type': 'ephemeral',
                    'text': '❌ Internal error processing command.'
                }), 500

        @self.app.route('/api/stop', methods=['POST'])
        def api_stop_trading():
            """API endpoint to stop trading."""
            try:
                # Verify authorization token
                if not self._verify_api_token(request):
                    return jsonify({'error': 'Unauthorized'}), 401
                
                # Get reason from request body
                data = request.get_json() or {}
                reason = data.get('reason', 'Emergency stop via API')
                
                from .kill_switch import get_kill_switch
                kill_switch = get_kill_switch()
                
                success = kill_switch.activate(reason, source="api")
                
                if success:
                    logger.critical(f"[API] Emergency stop activated: {reason}")
                    return jsonify({
                        'success': True,
                        'message': 'Trading stopped',
                        'reason': reason,
                        'activated_at': kill_switch.get_status()['activated_at']
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': 'Emergency stop already active'
                    }), 409
                    
            except Exception as e:
                logger.error(f"[API] Error stopping trading: {e}")
                return jsonify({'error': 'Internal server error'}), 500

        @self.app.route('/api/resume', methods=['POST'])
        def api_resume_trading():
            """API endpoint to resume trading."""
            try:
                # Verify authorization token
                if not self._verify_api_token(request):
                    return jsonify({'error': 'Unauthorized'}), 401
                
                from .kill_switch import get_kill_switch
                kill_switch = get_kill_switch()
                
                if not kill_switch.is_active():
                    return jsonify({
                        'success': False,
                        'message': 'Trading is not currently halted'
                    }), 409
                
                status = kill_switch.get_status()
                previous_reason = status.get('reason', 'Unknown')
                
                success = kill_switch.deactivate(source="api")
                
                if success:
                    logger.info(f"[API] Trading resumed (was: {previous_reason})")
                    return jsonify({
                        'success': True,
                        'message': 'Trading resumed',
                        'previous_reason': previous_reason
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': 'Failed to resume trading'
                    }), 500
                    
            except Exception as e:
                logger.error(f"[API] Error resuming trading: {e}")
                return jsonify({'error': 'Internal server error'}), 500

        @self.app.route('/api/status', methods=['GET'])
        def api_get_status():
            """API endpoint to get kill switch status."""
            try:
                # Verify authorization token
                if not self._verify_api_token(request):
                    return jsonify({'error': 'Unauthorized'}), 401
                
                from .kill_switch import get_kill_switch
                kill_switch = get_kill_switch()
                status = kill_switch.get_status()
                
                return jsonify({
                    'success': True,
                    'kill_switch': status
                })
                
            except Exception as e:
                logger.error(f"[API] Error getting status: {e}")
                return jsonify({'error': 'Internal server error'}), 500

        @self.app.route('/health', methods=['GET'])
        def health_check():
            """Health check endpoint."""
            from .kill_switch import get_kill_switch
            kill_switch = get_kill_switch()
            status = kill_switch.get_status()
            
            return jsonify({
                'status': 'healthy', 
                'service': 'slack-webhook',
                'kill_switch': status
            })
    
    def _verify_slack_signature(self, request) -> bool:
        """Verify Slack request signature.
        
        Args:
            request: Flask request object
            
        Returns:
            True if signature is valid
        """
        signing_secret = os.getenv('SLACK_SIGNING_SECRET')
        if not signing_secret:
            logger.warning("[SLACK-COMMANDS] No SLACK_SIGNING_SECRET configured, skipping verification")
            return True  # Allow if no secret configured (dev mode)
        
        timestamp = request.headers.get('X-Slack-Request-Timestamp', '')
        signature = request.headers.get('X-Slack-Signature', '')
        
        if not timestamp or not signature:
            return False
        
        # Check timestamp (prevent replay attacks)
        try:
            request_time = int(timestamp)
            current_time = int(time.time())
            if abs(current_time - request_time) > 300:  # 5 minutes
                logger.warning("[SLACK-COMMANDS] Request timestamp too old")
                return False
        except ValueError:
            return False
        
        # Verify signature
        body = request.get_data()
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        expected_signature = 'v0=' + hmac.new(
            signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, signature)
    
    def _verify_api_token(self, request) -> bool:
        """Verify API authorization token.
        
        Args:
            request: Flask request object
            
        Returns:
            True if token is valid
        """
        expected_token = os.getenv('CONTROL_API_TOKEN')
        if not expected_token:
            logger.warning("[API] No CONTROL_API_TOKEN configured, allowing request")
            return True  # Allow if no token configured (dev mode)
        
        # Check Authorization header
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return False
        
        provided_token = auth_header[7:]  # Remove "Bearer " prefix
        return hmac.compare_digest(expected_token, provided_token)
    
    def _handle_stop_trading(self, reason_text: str, user_name: str):
        """Handle /stop-trading command.
        
        Args:
            reason_text: Reason provided by user
            user_name: Slack username
            
        Returns:
            JSON response for Slack
        """
        from .kill_switch import get_kill_switch
        
        kill_switch = get_kill_switch()
        
        # Use provided reason or default
        reason = reason_text if reason_text else f"Emergency stop by {user_name}"
        
        # Activate kill switch
        success = kill_switch.activate(reason, source="slack")
        
        if success:
            logger.critical(f"[SLACK-COMMANDS] Emergency stop activated by {user_name}: {reason}")
            
            # Send confirmation response
            return jsonify({
                'response_type': 'in_channel',  # Visible to everyone
                'text': f'🚨 *EMERGENCY STOP ACTIVATED*\n'
                       f'Reason: {reason}\n'
                       f'Activated by: {user_name}\n'
                       f'All new trading is now halted.'
            })
        else:
            return jsonify({
                'response_type': 'ephemeral',
                'text': '⚠️ Emergency stop is already active.'
            })
    
    def _handle_resume_trading(self, user_name: str):
        """Handle /resume-trading command.
        
        Args:
            user_name: Slack username
            
        Returns:
            JSON response for Slack
        """
        from .kill_switch import get_kill_switch
        
        kill_switch = get_kill_switch()
        
        if not kill_switch.is_active():
            return jsonify({
                'response_type': 'ephemeral',
                'text': '✅ Trading is not currently halted.'
            })
        
        # Get current status for logging
        status = kill_switch.get_status()
        previous_reason = status.get('reason', 'Unknown')
        
        # Deactivate kill switch
        success = kill_switch.deactivate(source="slack")
        
        if success:
            logger.info(f"[SLACK-COMMANDS] Trading resumed by {user_name} (was: {previous_reason})")
            
            return jsonify({
                'response_type': 'in_channel',  # Visible to everyone
                'text': f'✅ *TRADING RESUMED*\n'
                       f'Previous halt reason: {previous_reason}\n'
                       f'Resumed by: {user_name}\n'
                       f'Normal trading operations can continue.'
            })
        else:
            return jsonify({
                'response_type': 'ephemeral',
                'text': '❌ Failed to resume trading. Check logs.'
            })

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
