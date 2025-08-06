"""
Slack Integration Module

Provides comprehensive Slack notification capabilities for the Robinhood HA Breakout
trading system. Enables real-time mobile alerts for trade signals, system status,
and trading outcomes with rich formatting and emoji support.

Key Features:
- Real-time trade signal notifications
- Rich message formatting with blocks and attachments
- System status and heartbeat messages
- Error and warning alerts
- Trading outcome summaries
- Mobile-friendly notifications

Notification Types:
- Trade Signals: Immediate alerts when LLM detects opportunities
- System Status: Startup, shutdown, and health check messages
- Heartbeat: Periodic "no trade" status during quiet periods
- Trade Outcomes: Results after manual confirmation
- Errors: System errors and recovery notifications
- Portfolio Updates: P&L and bankroll changes

Message Formatting:
- Color-coded messages (green=profit, red=loss, blue=info)
- Emoji indicators for quick visual recognition
- Structured blocks for complex information
- Fallback text for accessibility
- Timestamp and context information

Safety Features:
- Graceful degradation if Slack is unavailable
- Timeout protection for webhook calls
- Error logging without system interruption
- Optional notifications (system works without Slack)

Configuration:
- SLACK_WEBHOOK_URL: Incoming webhook for notifications
- SLACK_BOT_TOKEN: Bot token for two-way communication (optional)
- SLACK_CHANNEL_ID: Target channel for bot messages (optional)

Usage:
    # Initialize notifier
    notifier = SlackNotifier(webhook_url=os.getenv('SLACK_WEBHOOK_URL'))

    # Send trade signal
    notifier.send_trade_signal({
        'decision': 'BUY_CALL',
        'symbol': 'SPY',
        'strike': 635.0,
        'confidence': 0.85,
        'reason': 'Strong bullish breakout pattern'
    })

    # Send heartbeat during quiet periods
    notifier.send_heartbeat('Market scanning - no signals detected')

Author: Robinhood HA Breakout System
Version: 2.0.0
License: MIT
"""

import os
import logging
import requests
from typing import Dict, Optional, Any
from datetime import datetime


class SlackNotifier:
    """Handles Slack webhook notifications for trading system events."""

    def __init__(self, webhook_url: Optional[str] = None):
        """Initialize Slack notifier with webhook URL."""
        self.webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
        self.logger = logging.getLogger(__name__)

        if not self.webhook_url:
            self.logger.warning(
                "No Slack webhook URL configured - notifications disabled"
            )
            self.enabled = False
        else:
            self.enabled = True
            self.logger.info("Slack notifications enabled")

    def _send_message(self, payload: Dict[str, Any]) -> bool:
        """Send message to Slack webhook."""
        if not self.enabled:
            return False

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                self.logger.debug("Slack notification sent successfully")
                return True
            else:
                self.logger.error(
                    f"Slack notification failed: {response.status_code} - {response.text}"
                )
                return False

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to send Slack notification: {e}")
            return False

    def send_heartbeat(self, message: str) -> bool:
        """Send a lightweight heartbeat message for NO_TRADE cycles in loop mode.

        Args:
            message: Simple status message (e.g., "⏳ 09:35 · No breakout (body 0.07%)")

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            return False

        payload = {
            "text": message,
            "username": "Trading Bot",
            "icon_emoji": ":chart_with_upwards_trend:",
        }

        return self._send_message(payload)

    def send_profit_alert(
        self,
        symbol: str,
        strike: float,
        option_type: str,
        pnl_pct: float,
        profit_level: int,
    ) -> bool:
        """Send profit target alert for position monitoring.

        Args:
            symbol: Stock symbol (e.g., 'SPY')
            strike: Option strike price
            option_type: 'CALL' or 'PUT'
            pnl_pct: Current P&L percentage
            profit_level: Profit level reached (5%, 10%, etc.)

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            return False

        payload = {
            "attachments": [
                {
                    "color": "#36a64f",  # Green for profit
                    "title": f"[PROFIT] TARGET HIT! (+{profit_level}%)",
                    "text": f"Position: {symbol} ${strike} {option_type}",
                    "fields": [
                        {"title": "P&L", "value": f"{pnl_pct:+.1f}%", "short": True},
                        {"title": "Target", "value": f"{profit_level}%", "short": True},
                        {
                            "title": "Time",
                            "value": datetime.now().strftime("%H:%M:%S ET"),
                            "short": True,
                        },
                        {
                            "title": "Action",
                            "value": "Consider taking profits!",
                            "short": False,
                        },
                    ],
                }
            ]
        }

        return self._send_message(payload)

    def send_stop_loss_alert(
        self, symbol: str, strike: float, option_type: str, loss_pct: float
    ) -> bool:
        """Send stop loss alert for position monitoring.

        Args:
            symbol: Stock symbol (e.g., 'SPY')
            strike: Option strike price
            option_type: 'CALL' or 'PUT'
            loss_pct: Current loss percentage (positive number)

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            return False

        payload = {
            "attachments": [
                {
                    "color": "#ff0000",  # Red for loss
                    "title": f"[STOP LOSS] TRIGGERED! (-{loss_pct:.1f}%)",
                    "text": f"Position: {symbol} ${strike} {option_type}",
                    "fields": [
                        {"title": "Loss", "value": f"-{loss_pct:.1f}%", "short": True},
                        {"title": "Threshold", "value": "25%", "short": True},
                        {
                            "title": "Time",
                            "value": datetime.now().strftime("%H:%M:%S ET"),
                            "short": True,
                        },
                        {
                            "title": "Action",
                            "value": "CONSIDER CLOSING POSITION!",
                            "short": False,
                        },
                    ],
                }
            ]
        }

        return self._send_message(payload)

    def send_end_of_day_warning(self, minutes_to_close: int) -> bool:
        """Send end-of-day warning to close positions.

        Args:
            minutes_to_close: Minutes until market close

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            return False

        payload = {
            "attachments": [
                {
                    "color": "#ff9500",  # Orange for warning
                    "title": "[EOD] END OF DAY WARNING!",
                    "text": f"Market closes in {minutes_to_close} minutes.",
                    "fields": [
                        {
                            "title": "Time to Close",
                            "value": f"{minutes_to_close} minutes",
                            "short": True,
                        },
                        {
                            "title": "Target Close Time",
                            "value": "3:45 PM ET",
                            "short": True,
                        },
                        {
                            "title": "Action",
                            "value": "Consider closing all positions to avoid overnight risk!",
                            "short": False,
                        },
                    ],
                }
            ]
        }

        return self._send_message(payload)

    def send_startup_notification(self, dry_run: bool = False) -> bool:
        """Send notification when system starts."""
        mode = "DRY RUN" if dry_run else "LIVE TRADING"
        color = (
            "#36a64f" if dry_run else "#ff9500"
        )  # Green for dry run, orange for live

        payload = {
            "attachments": [
                {
                    "color": color,
                    "title": f"🚀 Robinhood HA Breakout - {mode} Started",
                    "text": f"System initialized in {'analysis-only' if dry_run else 'live trading'} mode",
                    "fields": [
                        {"title": "Mode", "value": mode, "short": True},
                        {
                            "title": "Time",
                            "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "short": True,
                        },
                    ],
                    "footer": "Robinhood HA Breakout",
                    "ts": int(datetime.now().timestamp()),
                }
            ]
        }

        return self._send_message(payload)

    def send_market_analysis(self, analysis: Dict[str, Any]) -> bool:
        """Send market analysis results."""
        trend = analysis.get("trend", "UNKNOWN")
        price = analysis.get("current_price", 0)
        body_pct = analysis.get("body_percentage", 0)

        # Color based on trend
        color_map = {
            "BULLISH": "#36a64f",  # Green
            "BEARISH": "#d50000",  # Red
            "NEUTRAL": "#ffc107",  # Yellow
        }
        color = color_map.get(trend, "#6c757d")  # Default gray

        payload = {
            "attachments": [
                {
                    "color": color,
                    "title": "📊 Market Analysis - SPY",
                    "fields": [
                        {"title": "Trend", "value": f"{trend}", "short": True},
                        {
                            "title": "Current Price",
                            "value": f"${price:.2f}",
                            "short": True,
                        },
                        {
                            "title": "Candle Body %",
                            "value": f"{body_pct:.2f}%",
                            "short": True,
                        },
                        {
                            "title": "Support Levels",
                            "value": str(analysis.get("support_count", 0)),
                            "short": True,
                        },
                        {
                            "title": "Resistance Levels",
                            "value": str(analysis.get("resistance_count", 0)),
                            "short": True,
                        },
                    ],
                    "footer": "Heikin-Ashi Analysis",
                    "ts": int(datetime.now().timestamp()),
                }
            ]
        }

        return self._send_message(payload)

    def send_trade_decision(
        self,
        decision: str,
        confidence: float,
        reason: str,
        bankroll: float,
        position_size: float = 0,
    ) -> bool:
        """Send LLM trade decision notification."""
        # Color based on decision
        color_map = {
            "CALL": "#36a64f",  # Green for bullish
            "PUT": "#d50000",  # Red for bearish
            "NO_TRADE": "#6c757d",  # Gray for no trade
        }
        color = color_map.get(decision, "#6c757d")

        # Emoji based on decision
        emoji_map = {"CALL": "📈", "PUT": "📉", "NO_TRADE": "⏸️"}
        emoji = emoji_map.get(decision, "❓")

        # Ensure confidence is a float for formatting
        if isinstance(confidence, str):
            try:
                confidence = float(confidence)
            except (ValueError, TypeError):
                confidence = 0.0
        elif confidence is None:
            confidence = 0.0

        # Ensure bankroll is a float for formatting
        if isinstance(bankroll, str):
            try:
                bankroll = float(bankroll)
            except (ValueError, TypeError):
                bankroll = 0.0
        elif bankroll is None:
            bankroll = 0.0

        # Ensure position_size is a float for formatting
        if isinstance(position_size, str):
            try:
                position_size = float(position_size)
            except (ValueError, TypeError):
                position_size = 0.0
        elif position_size is None:
            position_size = 0.0

        fields = [
            {"title": "Decision", "value": f"{emoji} {decision}", "short": True},
            {"title": "Confidence", "value": f"{confidence:.1f}%", "short": True},
            {"title": "Current Bankroll", "value": f"${bankroll:.2f}", "short": True},
        ]

        # Add position size if trade is recommended
        if decision in ["CALL", "PUT"] and position_size > 0:
            fields.append(
                {
                    "title": "Position Size",
                    "value": f"${position_size:.2f}",
                    "short": True,
                }
            )

        payload = {
            "attachments": [
                {
                    "color": color,
                    "title": "🤖 LLM Trade Decision",
                    "text": f"*Reasoning:* {reason}",
                    "fields": fields,
                    "footer": "OpenAI GPT-4o-mini",
                    "ts": int(datetime.now().timestamp()),
                }
            ]
        }

        return self._send_message(payload)

    def send_browser_status(self, status: str, message: str = "") -> bool:
        """Send browser automation status updates."""
        status_colors = {
            "login_success": "#36a64f",
            "login_failed": "#d50000",
            "mfa_required": "#ffc107",
            "navigation_success": "#36a64f",
            "navigation_failed": "#d50000",
            "order_ready": "#ff9500",
            "error": "#d50000",
        }

        status_emojis = {
            "login_success": "✅",
            "login_failed": "❌",
            "mfa_required": "🔐",
            "navigation_success": "🧭",
            "navigation_failed": "❌",
            "order_ready": "⚠️",
            "error": "🚨",
        }

        color = status_colors.get(status, "#6c757d")
        emoji = status_emojis.get(status, "📱")

        payload = {
            "attachments": [
                {
                    "color": color,
                    "title": f"{emoji} Browser Status Update",
                    "text": message or f"Status: {status.replace('_', ' ').title()}",
                    "footer": "Selenium Automation",
                    "ts": int(datetime.now().timestamp()),
                }
            ]
        }

        return self._send_message(payload)

    def send_order_ready_alert(
        self, trade_type: str, strike: str, expiry: str, position_size: float, **kwargs
    ) -> bool:
        """Send critical alert when order is ready for review with comprehensive trade details."""
        # Extract additional trade details from kwargs
        action = kwargs.get("action", "OPEN")  # OPEN or CLOSE
        confidence = kwargs.get("confidence", 0.0)
        reason = kwargs.get("reason", "No reason provided")
        current_price = kwargs.get("current_price", 0.0)
        premium = kwargs.get("premium", 0.0)
        quantity = kwargs.get("quantity", 1)
        total_cost = kwargs.get("total_cost", position_size)
        bankroll = kwargs.get("bankroll", 0.0)
        trend = kwargs.get("trend", "UNKNOWN")
        candle_body_pct = kwargs.get("candle_body_pct", 0.0)

        # Determine action-specific messaging
        if action == "CLOSE":
            action_emoji = "🔄"
            action_text = "CLOSING POSITION"
            action_color = "#ff6b35"  # Orange-red for close
            entry_premium = kwargs.get("entry_premium", 0.0)
            contracts_held = kwargs.get("contracts_held", quantity)
        else:
            action_emoji = "📈" if trade_type == "CALL" else "📉"
            action_text = "OPENING POSITION"
            action_color = "#ff9500"  # Orange for open

        # Build comprehensive field list
        fields = [
            {
                "title": "🎯 Action",
                "value": f"{action_emoji} {action_text}",
                "short": True,
            },
            {"title": "📊 Direction", "value": f"{trade_type}", "short": True},
            {"title": "💰 Strike Price", "value": f"{strike}", "short": True},
            {"title": "📅 Expiry", "value": f"{expiry}", "short": True},
            {
                "title": "📦 Quantity",
                "value": f"{quantity} contract{'s' if quantity != 1 else ''}",
                "short": True,
            },
            {"title": "💵 Premium/Contract", "value": f"${premium:.2f}", "short": True},
            {"title": "💸 Total Cost", "value": f"${total_cost:.2f}", "short": True},
            {"title": "🎯 Confidence", "value": f"{confidence:.1%}", "short": True},
            {"title": "📈 SPY Price", "value": f"${current_price:.2f}", "short": True},
            {"title": "📊 Trend", "value": f"{trend}", "short": True},
            {
                "title": "🕯️ Candle Body",
                "value": f"{candle_body_pct:.2f}%",
                "short": True,
            },
            {"title": "💼 Bankroll", "value": f"${bankroll:.2f}", "short": True},
        ]

        # Add position-specific fields for CLOSE trades
        if action == "CLOSE":
            entry_premium = kwargs.get("entry_premium", 0.0)
            entry_cost = entry_premium * quantity
            potential_pnl = total_cost - entry_cost
            pnl_pct = (potential_pnl / entry_cost * 100) if entry_cost > 0 else 0

            fields.extend(
                [
                    {
                        "title": "🔢 Entry Premium",
                        "value": f"${entry_premium:.2f}",
                        "short": True,
                    },
                    {
                        "title": "📊 Est. P/L",
                        "value": f"${potential_pnl:.2f} ({pnl_pct:+.1f}%)",
                        "short": True,
                    },
                ]
            )

        # Create the main alert payload
        payload = {
            "text": f"🚨 *{action_text} READY FOR REVIEW* 🚨",
            "attachments": [
                {
                    "color": action_color,
                    "title": f"⚠️ Manual Review Required - {action_text}",
                    "text": f"*LLM Reasoning:* {reason}\n\n*Your trade is pre-filled and waiting for final approval in Robinhood*",
                    "fields": fields,
                    "footer": "⚠️ CRITICAL: Review all details and submit manually - DO NOT leave unattended",
                    "ts": int(datetime.now().timestamp()),
                },
                {
                    "color": "#36a64f",  # Green for instructions
                    "title": "📋 Next Steps",
                    "text": "1. ✅ Review all trade details above\n2. 🌐 Check the browser for order review screen\n3. 🤔 Verify the trade aligns with your strategy\n4. 📱 Submit manually if approved, or cancel if not\n5. 💰 Enter actual fill price when prompted",
                    "footer": "Trading Instructions",
                    "ts": int(datetime.now().timestamp()),
                },
            ],
        }

        return self._send_message(payload)

    def send_error_alert(self, error_type: str, error_message: str) -> bool:
        """Send error notifications."""
        payload = {
            "attachments": [
                {
                    "color": "#d50000",  # Red for errors
                    "title": f"🚨 System Error: {error_type}",
                    "text": f"```{error_message}```",
                    "footer": "Error Alert",
                    "ts": int(datetime.now().timestamp()),
                }
            ]
        }

        return self._send_message(payload)

    def send_completion_summary(self, session_summary: Dict[str, Any]) -> bool:
        """Send session completion summary."""
        total_trades = session_summary.get("trades_analyzed", 0)
        decisions_made = session_summary.get("decisions_made", 0)
        final_bankroll = session_summary.get("final_bankroll", 0)

        payload = {
            "attachments": [
                {
                    "color": "#36a64f",
                    "title": "✅ Session Complete",
                    "fields": [
                        {
                            "title": "Trades Analyzed",
                            "value": str(total_trades),
                            "short": True,
                        },
                        {
                            "title": "Decisions Made",
                            "value": str(decisions_made),
                            "short": True,
                        },
                        {
                            "title": "Final Bankroll",
                            "value": f"${final_bankroll:.2f}",
                            "short": True,
                        },
                        {
                            "title": "Duration",
                            "value": session_summary.get("duration", "N/A"),
                            "short": True,
                        },
                    ],
                    "footer": "Session Summary",
                    "ts": int(datetime.now().timestamp()),
                }
            ]
        }

        return self._send_message(payload)


def create_slack_notifier() -> SlackNotifier:
    """Factory function to create a SlackNotifier instance."""
    return SlackNotifier()


# Test function for webhook validation
def test_slack_webhook(webhook_url: str) -> bool:
    """Test if Slack webhook is working."""
    notifier = SlackNotifier(webhook_url)
    return notifier._send_message(
        {
            "text": "🧪 Test notification from Robinhood HA Breakout system",
            "attachments": [
                {
                    "color": "#36a64f",
                    "title": "✅ Webhook Test Successful",
                    "text": "Your Slack integration is working correctly!",
                    "footer": "Configuration Test",
                    "ts": int(datetime.now().timestamp()),
                }
            ],
        }
    )


if __name__ == "__main__":
    # Test the Slack integration
    import sys
    from dotenv import load_dotenv

    load_dotenv()

    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("❌ No SLACK_WEBHOOK_URL found in environment")
        sys.exit(1)

    print("🧪 Testing Slack webhook...")
    if test_slack_webhook(webhook_url):
        print("✅ Slack webhook test successful!")
    else:
        print("❌ Slack webhook test failed!")
        sys.exit(1)
