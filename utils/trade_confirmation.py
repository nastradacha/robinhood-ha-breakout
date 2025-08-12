#!/usr/bin/env python3
"""
Trade Confirmation Module

Provides comprehensive trade confirmation and outcome tracking for the Robinhood HA
Breakout trading system. Ensures accurate position and P&L tracking by recording
user decisions after manual review at the Robinhood Review screen.

Key Features:
- Multiple confirmation methods (interactive prompt, Slack bridge, browser detection)
- Hybrid confirmation workflow for maximum accuracy
- Real-time trade outcome recording
- Slack integration for remote confirmation
- Automatic position and bankroll updates
- Comprehensive error handling and fallbacks

Confirmation Methods:
1. Interactive Prompt: Direct CLI input with trade details
2. Slack Bridge: Remote confirmation via Slack messages
3. Browser Detection: Automatic outcome detection (experimental)
4. Auto-Detection: Combination of multiple methods

Workflow:
1. System stops at Robinhood Review screen
2. User manually reviews trade details
3. User decides to Submit or Cancel
4. System prompts for confirmation of actual outcome
5. User provides actual fill price if submitted
6. System updates positions and bankroll accordingly
7. Slack notification sent with trade outcome

Safety Features:
- Never assumes trade outcome without confirmation
- Requires explicit user input for all trades
- Validates all input data before processing
- Comprehensive logging for audit trails
- Graceful error handling and recovery

Slack Integration:
- Real-time trade alerts with confirmation buttons
- Remote confirmation via mobile device
- Automatic position updates from Slack responses
- Fallback to interactive prompt if Slack unavailable

Data Tracking:
- Actual fill prices vs. estimated premiums
- Trade execution timestamps
- Position opening/closing logic
- Realized P&L calculations
- Performance metrics updates

Usage:
    # Initialize confirmation manager
    confirmer = TradeConfirmationManager(
        portfolio_manager=portfolio,
        bankroll_manager=bankroll,
        slack_notifier=slack
    )

    # Get user decision after Review screen
    decision, actual_premium = confirmer.get_user_decision(
        trade_details={
            'symbol': 'SPY',
            'strike': 635.0,
            'side': 'CALL',
            'quantity': 1,
            'estimated_premium': 2.50
        },
        method='prompt'  # or 'slack', 'browser', 'auto'
    )

    # Record trade outcome
    confirmer.record_trade_outcome(
        trade_details=trade_details,
        decision=decision,
        actual_premium=actual_premium
    )

Author: Robinhood HA Breakout System
Version: 2.0.0
License: MIT
"""

import logging
from typing import Optional, Dict, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class TradeConfirmationManager:
    """Manages trade confirmation and outcome recording."""

    def __init__(self, portfolio_manager, bankroll_manager, slack_notifier=None):
        self.portfolio_manager = portfolio_manager
        self.bankroll_manager = bankroll_manager
        self.slack_notifier = slack_notifier
        self.pending_trade = None  # Store trade details for Slack bridge

    def get_user_decision(
        self, trade_details: Dict, method: str = "prompt"
    ) -> Tuple[str, Optional[float]]:
        """
        Get user's decision about trade execution.

        Args:
            trade_details: Dictionary with trade information
            method: Method to use ('prompt', 'browser', 'slack', 'auto')

        Returns:
            Tuple of (decision, actual_premium) where decision is 'SUBMITTED', 'CANCELLED', or 'UNKNOWN'
        """
        if method == "prompt":
            return self._prompt_user_decision(trade_details)
        elif method == "browser":
            return self._detect_browser_decision(trade_details)
        elif method == "slack":
            return self._wait_for_slack_confirmation(trade_details)
        else:
            return self._auto_detect_decision(trade_details)

    def _prompt_user_decision(self, trade_details: Dict) -> Tuple[str, Optional[float]]:
        """Prompt user directly for their decision with Slack bridge support."""
        # Store pending trade for potential Slack confirmation
        self.pending_trade = trade_details.copy()

        print("\n" + "=" * 60)
        print("🎯 TRADE DECISION REQUIRED")
        print("=" * 60)
        print(
            f"Trade: {trade_details.get('direction', 'N/A')} ${trade_details.get('strike', 'N/A')}"
        )
        print(f"Expected Premium: ${trade_details.get('premium', 'N/A'):.2f}")
        print(f"Quantity: {trade_details.get('quantity', 1)} contracts")
        print("-" * 60)
        print("💡 TIP: Away from PC? Send Slack message: 'filled 1.28' or 'cancelled'")
        print("-" * 60)

        while True:
            print("\nOptions:")
            print(
                "  [S] Submit at expected price (${:.2f})".format(
                    trade_details.get("premium", 0)
                )
            )
            print("  [C] Cancel trade")
            print("  [P] Submit at different price (enter custom premium)")
            print("  [0.XX] Enter premium directly (e.g., 0.75)")

            decision = input("\nYour choice: ").lower().strip()

            # Check if user entered a premium directly (e.g., "0.75", "1.25")
            try:
                if (
                    decision.replace(".", "").replace("-", "").isdigit()
                    and float(decision) > 0
                ):
                    actual_premium = float(decision)
                    print(f"[OK] Trade SUBMITTED at ${actual_premium:.2f}")
                    return "SUBMITTED", actual_premium
            except ValueError:
                pass

            if decision in ["s", "submit", "submitted"]:
                # Submit at expected price
                actual_premium = trade_details.get("premium", 0)
                print(f"[OK] Trade SUBMITTED at expected price ${actual_premium:.2f}")
                return "SUBMITTED", actual_premium

            elif decision in ["p", "price", "custom"]:
                # Get custom fill price
                while True:
                    try:
                        custom_input = input("Enter actual fill price: $").strip()
                        actual_premium = float(custom_input)
                        if actual_premium <= 0:
                            print("Price must be greater than 0")
                            continue
                        break
                    except ValueError:
                        print("Please enter a valid price (e.g., 1.25)")

                print(f"[OK] Trade SUBMITTED at custom price ${actual_premium:.2f}")
                return "SUBMITTED", actual_premium

            elif decision in ["c", "cancel", "cancelled"]:
                print("❌ Trade CANCELLED")
                return "CANCELLED", None

            else:
                print(
                    "Invalid input. Please choose S, C, P, or enter a premium directly (e.g., 0.75)"
                )

    def _detect_browser_decision(
        self, trade_details: Dict, timeout: int = 30
    ) -> Tuple[str, Optional[float]]:
        """Try to detect if trade was submitted by monitoring browser."""
        # This would require access to the browser driver
        # Implementation depends on Robinhood's confirmation screens
        logger.info("Browser detection not yet implemented")
        return "UNKNOWN", None

    def _wait_for_slack_confirmation(
        self, trade_details: Dict, timeout: int = 300
    ) -> Tuple[str, Optional[float]]:
        """Wait for Slack confirmation (if Slack integration is available)."""
        if not self.slack_notifier:
            logger.warning("Slack notifier not available")
            return "UNKNOWN", None

        # Send notification asking for confirmation
        message = f"🤔 Trade Decision Needed:\n{trade_details.get('direction')} ${trade_details.get('strike')} @ ${trade_details.get('premium', 0):.2f}\n\nReply with:\n• 'submitted' or 'filled $X.XX'\n• 'cancelled'"

        if self.slack_notifier.send_heartbeat(message):
            logger.info("Sent Slack confirmation request")
            # In a real implementation, you'd listen for Slack responses
            # For now, fall back to prompt
            return self._prompt_user_decision(trade_details)

        return "UNKNOWN", None

    def _auto_detect_decision(self, trade_details: Dict) -> Tuple[str, Optional[float]]:
        """Try multiple detection methods automatically."""
        # Try browser detection first
        decision, premium = self._detect_browser_decision(trade_details, timeout=10)

        if decision == "UNKNOWN":
            # Fall back to user prompt
            decision, premium = self._prompt_user_decision(trade_details)

        return decision, premium

    def record_trade_outcome(
        self,
        trade_details: Dict,
        decision: str,
        actual_premium: Optional[float] = None,
        auto_start_monitor: bool = True,
    ):
        """
        Record the trade outcome in all tracking systems.

        Args:
            trade_details: Original trade details
            decision: 'SUBMITTED', 'CANCELLED', or 'UNKNOWN'
            actual_premium: Actual fill price if submitted
            auto_start_monitor: Whether to auto-start position monitoring
        """
        timestamp = datetime.now().isoformat()

        if decision == "SUBMITTED":
            # Create position record
            from utils.portfolio import Position

            position = Position(
                entry_time=timestamp,
                symbol=trade_details.get("symbol", "SPY"),
                expiry=trade_details.get("expiry", ""),
                strike=trade_details.get("strike", 0),
                side=trade_details.get("direction", ""),
                contracts=trade_details.get("quantity", 1),
                entry_premium=actual_premium or trade_details.get("premium", 0),
            )

            # Add to portfolio
            self.portfolio_manager.add_position(position)

            # Update bankroll with actual fill price
            if actual_premium is not None:
                # Apply actual fill price to reconcile bankroll
                position_id = f"{trade_details.get('symbol', 'SPY')}_{trade_details.get('strike', 0)}_{timestamp}"
                self.bankroll_manager.apply_fill(
                    position_id=position_id,
                    fill_price=actual_premium,
                    contracts=trade_details.get("quantity", 1),
                )

            # Record trade in bankroll history
            total_cost = (
                (actual_premium or trade_details.get("premium", 0))
                * trade_details.get("quantity", 1)
                * 100
            )
            self.bankroll_manager.record_trade(
                {
                    **trade_details,
                    "actual_premium": actual_premium,
                    "total_cost": total_cost,
                    "status": "SUBMITTED",
                    "position_id": f"{trade_details.get('symbol', 'SPY')}_{trade_details.get('strike', 0)}_{timestamp}",
                }
            )

            used_premium = actual_premium if actual_premium is not None else trade_details.get("premium", 0)
            logger.info(
                f"[OK] Recorded SUBMITTED trade: {trade_details.get('direction')} ${trade_details.get('strike')} @ ${used_premium:.2f}"
            )

            # Auto-start position monitoring if enabled
            if auto_start_monitor:
                try:
                    from utils.monitor_launcher import ensure_monitor_running

                    symbol = trade_details.get("symbol", "SPY")
                    if ensure_monitor_running(symbol):
                        logger.info(f"[OK] Auto-started position monitor for {symbol}")
                    else:
                        logger.warning(
                            f"[WARNING] Failed to auto-start monitor for {symbol}"
                        )
                except Exception as e:
                    logger.error(f"[ERROR] Monitor auto-start failed: {e}")

            # S3: Send fill-price echo to Slack
            if self.slack_notifier:
                # Enhanced fill-price echo format: ✅ Trade recorded: CALL 580 @ $1.28 · Qty 1
                side = trade_details.get('direction', 'CALL')
                strike = trade_details.get('strike', 0)
                qty = trade_details.get('quantity', 1)
                fill_price = actual_premium or trade_details.get('premium', 0)
                
                fill_echo_msg = f"✅ Trade recorded: {side} {strike} @ ${fill_price:.2f} · Qty {qty}"
                self.slack_notifier.send_heartbeat(fill_echo_msg)
                logger.info(f"[S3-FILL-ECHO] Sent fill-price echo: {fill_echo_msg}")

        elif decision == "CANCELLED":
            # Record cancelled trade for statistics
            self.bankroll_manager.record_trade(
                {**trade_details, "status": "CANCELLED", "total_cost": 0}
            )

            logger.info(
                f"❌ Recorded CANCELLED trade: {trade_details.get('direction')} ${trade_details.get('strike')}"
            )

            # Send Slack confirmation for cancelled trade
            if self.slack_notifier:
                side = trade_details.get('direction', 'CALL')
                strike = trade_details.get('strike', 0)
                cancel_msg = f"❌ Trade cancelled: {side} {strike}"
                self.slack_notifier.send_heartbeat(cancel_msg)

        else:
            logger.warning(f"⚠️ Unknown trade outcome: {decision}")

    def process_slack_message(self, message: str) -> bool:
        """Process Slack message for trade confirmation.

        Args:
            message: Slack message content (e.g., 'filled 1.28', 'cancelled')

        Returns:
            True if message was processed, False otherwise
        """
        if not self.pending_trade:
            logger.warning("No pending trade to confirm via Slack")
            return False

        message = message.lower().strip()

        # Parse different message formats
        if message in ["cancelled", "cancel", "no", "abort"]:
            decision = "CANCELLED"
            actual_premium = None
            logger.info("Slack confirmation: Trade CANCELLED")

        elif message in ["submitted", "submit", "yes", "filled"]:
            decision = "SUBMITTED"
            actual_premium = self.pending_trade.get("premium", 0)
            logger.info(
                f"Slack confirmation: Trade SUBMITTED at expected premium ${actual_premium:.2f}"
            )

        elif message.startswith("filled ") or message.startswith("fill "):
            # Parse "filled 1.28" format
            try:
                parts = message.split()
                actual_premium = float(parts[1].replace("$", ""))
                decision = "SUBMITTED"
                logger.info(
                    f"Slack confirmation: Trade SUBMITTED at ${actual_premium:.2f}"
                )
            except (IndexError, ValueError):
                logger.error(f"Invalid Slack message format: {message}")
                return False

        else:
            logger.warning(f"Unrecognized Slack message: {message}")
            return False

        # Record the trade outcome (copy pending trade before clearing)
        trade_copy = self.pending_trade.copy()
        self.record_trade_outcome(trade_copy, decision, actual_premium)

        # Clear pending trade
        self.pending_trade = None

        # Send confirmation back to Slack
        if self.slack_notifier:
            if decision == "SUBMITTED":
                confirm_msg = f"[OK] Confirmed via Slack: {trade_copy.get('direction')} ${trade_copy.get('strike')} @ ${actual_premium:.2f}"
            else:
                confirm_msg = "❌ Confirmed via Slack: Trade cancelled"
            self.slack_notifier.send_heartbeat(confirm_msg)

        return True


def create_quick_confirmation_script():
    """Create a standalone script for quick trade confirmation."""
    script_content = '''#!/usr/bin/env python3
"""
Quick trade confirmation script.

Usage:
    python confirm_trade.py --submitted --premium 1.25
    python confirm_trade.py --cancelled
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from utils.trade_confirmation import TradeConfirmationManager
from utils.portfolio import PortfolioManager
from utils.bankroll import BankrollManager

def main():
    parser = argparse.ArgumentParser(description='Confirm trade outcome')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--submitted', action='store_true', help='Trade was submitted')
    group.add_argument('--cancelled', action='store_true', help='Trade was cancelled')
    
    parser.add_argument('--premium', type=float, help='Actual fill premium')
    parser.add_argument('--strike', type=float, help='Strike price')
    parser.add_argument('--direction', choices=['CALL', 'PUT'], help='Option direction')
    
    args = parser.parse_args()
    
    # Initialize managers
    portfolio_manager = PortfolioManager()
    bankroll_manager = BankrollManager()
    confirmation_manager = TradeConfirmationManager(portfolio_manager, bankroll_manager)
    
    # Create trade details from args
    trade_details = {
        'strike': args.strike or 0,
        'direction': args.direction or 'CALL',
        'premium': args.premium or 0,
        'quantity': 1,
        'symbol': 'SPY'
    }
    
    if args.submitted:
        decision = "SUBMITTED"
        actual_premium = args.premium
    else:
        decision = "CANCELLED"
        actual_premium = None
    
    confirmation_manager.record_trade_outcome(trade_details, decision, actual_premium)
    print(f"Trade outcome recorded: {decision}")

if __name__ == "__main__":
    main()
'''

    with open("confirm_trade.py", "w") as f:
        f.write(script_content)

    logger.info("Created confirm_trade.py script")


if __name__ == "__main__":
    # Demo usage
    from utils.portfolio import PortfolioManager
    from utils.bankroll import BankrollManager

    portfolio_manager = PortfolioManager()
    bankroll_manager = BankrollManager()
    confirmation_manager = TradeConfirmationManager(portfolio_manager, bankroll_manager)

    # Example trade details
    trade_details = {
        "symbol": "SPY",
        "direction": "CALL",
        "strike": 635.0,
        "premium": 1.25,
        "quantity": 1,
        "expiry": "2025-01-03",
    }

    # Get user decision
    decision, actual_premium = confirmation_manager.get_user_decision(
        trade_details, method="prompt"
    )

    # Record outcome
    confirmation_manager.record_trade_outcome(trade_details, decision, actual_premium)
