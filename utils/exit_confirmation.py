#!/usr/bin/env python3
"""
Interactive Exit Confirmation Workflow

Provides user-friendly interactive prompts for position exit decisions,
similar to the entry confirmation workflow but optimized for profit-taking
and risk management scenarios.

Features:
- Interactive terminal prompts for exit decisions
- Support for profit targets, stop losses, and time-based exits
- Custom premium entry for accurate fill prices
- Slack integration for remote confirmation
- Position logging and portfolio updates
- Multi-broker support (Robinhood/Alpaca)

Usage:
    from utils.exit_confirmation import ExitConfirmationWorkflow
    
    workflow = ExitConfirmationWorkflow()
    result = workflow.confirm_exit(position, exit_decision, current_price)
"""

import logging
import sys
import csv
import os
from datetime import datetime
from typing import Dict, Optional, Tuple, Any
from dataclasses import dataclass

from utils.exit_strategies import ExitDecision, ExitReason

logger = logging.getLogger(__name__)


@dataclass
class ExitConfirmationResult:
    """Result of exit confirmation workflow."""
    
    action: str  # "submit", "cancel", "custom_price"
    premium: Optional[float] = None
    confirmed: bool = False
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class ExitConfirmationWorkflow:
    """Interactive exit confirmation workflow for position management."""
    
    def __init__(self):
        """Initialize exit confirmation workflow."""
        self.logger = logging.getLogger(__name__)
        
        # Import Slack integration if available
        try:
            from utils.enhanced_slack import EnhancedSlackIntegration
            self.slack = EnhancedSlackIntegration()
        except ImportError:
            self.slack = None
            self.logger.warning("[EXIT-CONFIRM] Slack integration not available")
    
    def confirm_exit(
        self, 
        position: Dict, 
        exit_decision: ExitDecision, 
        current_stock_price: float,
        current_option_price: float
    ) -> ExitConfirmationResult:
        """
        Present interactive exit confirmation prompt to user.
        
        Args:
            position: Position data (symbol, strike, entry_price, etc.)
            exit_decision: Exit strategy decision with reasoning
            current_stock_price: Current underlying stock price
            current_option_price: Current estimated option price
            
        Returns:
            ExitConfirmationResult with user decision
        """
        symbol = position["symbol"]
        strike = position["strike"]
        option_type = position["option_type"]
        entry_price = position["entry_price"]
        quantity = position["quantity"]
        
        # Calculate P&L
        current_value = current_option_price * quantity * 100
        entry_value = entry_price * quantity * 100
        pnl = current_value - entry_value
        pnl_pct = (pnl / entry_value) * 100
        
        # Display exit prompt
        self._display_exit_prompt(
            position, exit_decision, current_stock_price, 
            current_option_price, pnl, pnl_pct
        )
        
        # Get user decision
        return self._get_user_decision(current_option_price)
    
    def _display_exit_prompt(
        self, 
        position: Dict, 
        exit_decision: ExitDecision,
        current_stock_price: float,
        current_option_price: float,
        pnl: float,
        pnl_pct: float
    ) -> None:
        """Display formatted exit confirmation prompt."""
        
        symbol = position["symbol"]
        strike = position["strike"]
        option_type = position["option_type"]
        entry_price = position["entry_price"]
        quantity = position["quantity"]
        
        # Choose emoji and title based on exit reason (Windows-safe)
        if exit_decision.reason == ExitReason.PROFIT_TARGET:
            emoji = "[PROFIT]"
            title = "PROFIT TARGET REACHED"
            urgency_color = "[+]"
        elif exit_decision.reason == ExitReason.TRAILING_STOP:
            emoji = "[TRAIL]"
            title = "TRAILING STOP TRIGGERED"
            urgency_color = "[!]"
        elif exit_decision.reason == ExitReason.STOP_LOSS:
            emoji = "[STOP]"
            title = "STOP LOSS TRIGGERED"
            urgency_color = "[!]"
        elif exit_decision.reason == ExitReason.TIME_BASED:
            emoji = "[TIME]"
            title = "TIME-BASED EXIT"
            urgency_color = "[!]"
        else:
            emoji = "[EXIT]"
            title = "EXIT SIGNAL DETECTED"
            urgency_color = "[!]"
        
        print("\n" + "="*60)
        print(f"{emoji} {title} {emoji}")
        print("="*60)
        print(f"Position: {symbol} ${strike} {option_type}")
        print(f"Entry Price: ${entry_price:.2f}")
        print(f"Current Price: ${current_option_price:.2f}")
        print(f"Stock Price: ${current_stock_price:.2f}")
        print(f"Quantity: {quantity} contract{'s' if quantity != 1 else ''}")
        print()
        print(f"P&L: ${pnl:+.2f} ({pnl_pct:+.1f}%)")
        print()
        print(f"{urgency_color} Reason: {exit_decision.message}")
        print()
        print("Trade: SELL")
        print(f"Expected Premium: ${current_option_price:.2f}")
        print(f"Total Value: ${current_option_price * quantity * 100:.2f}")
        print("-"*60)
        print("TIP: Away from PC? Send Slack message: 'filled 2.15' or 'cancelled'")
        print("-"*60)
        print()
    
    def _get_user_decision(self, estimated_premium: float, config: Dict = None) -> ExitConfirmationResult:
        """Get user decision through interactive prompt or LLM in unattended mode."""
        
        # Check if unattended mode is enabled and exit decisions are automated
        if config and config.get("UNATTENDED") and "exit" in config.get("LLM_DECISIONS", []):
            return self._get_llm_decision(estimated_premium, config)
        
        # Original interactive prompt
        while True:
            print("Options:")
            print(f"  [S] Submit at expected price (${estimated_premium:.2f})")
            print("  [C] Cancel exit (keep position open)")
            print("  [P] Submit at different price (enter custom premium)")
            print("  [0.XX] Enter premium directly (e.g., 2.15)")
            print()
            
            try:
                decision = input("Your choice: ").lower().strip()
                
                if not decision:
                    print("❌ Please enter a choice")
                    continue
                
                # Direct premium entry (e.g., "2.15")
                try:
                    premium = float(decision)
                    if 0.01 <= premium <= 50.0:  # Reasonable bounds
                        print(f"[OK] Submitting SELL order at ${premium:.2f}")
                        return ExitConfirmationResult(
                            action="custom_price",
                            premium=premium,
                            confirmed=True
                        )
                    else:
                        print("[ERROR] Premium must be between $0.01 and $50.00")
                        continue
                except ValueError:
                    pass  # Not a number, check other options
                
                # Standard options
                if decision == 's':
                    print(f"[OK] Submitting SELL order at ${estimated_premium:.2f}")
                    return ExitConfirmationResult(
                        action="submit",
                        premium=estimated_premium,
                        confirmed=True
                    )
                
                elif decision == 'c':
                    print("[CANCEL] Exit cancelled - keeping position open")
                    return ExitConfirmationResult(
                        action="cancel",
                        confirmed=False
                    )
                
                elif decision == 'p':
                    # Custom premium entry
                    while True:
                        try:
                            custom_premium = input("Enter sell price: $").strip()
                            premium = float(custom_premium)
                            if 0.01 <= premium <= 50.0:
                                print(f"[OK] Submitting SELL order at ${premium:.2f}")
                                return ExitConfirmationResult(
                                    action="custom_price",
                                    premium=premium,
                                    confirmed=True
                                )
                            else:
                                print("[ERROR] Premium must be between $0.01 and $50.00")
                        except ValueError:
                            print("[ERROR] Please enter a valid number")
                        except KeyboardInterrupt:
                            print("\n[CANCEL] Cancelled")
                            return ExitConfirmationResult(
                                action="cancel",
                                confirmed=False
                            )
                
                else:
                    print("[ERROR] Invalid choice. Please enter S, C, P, or a premium amount")
                    continue
                    
            except KeyboardInterrupt:
                print("\n[CANCEL] Exit cancelled")
                return ExitConfirmationResult(
                    action="cancel",
                    confirmed=False
                )
            except Exception as e:
                self.logger.error(f"[EXIT-CONFIRM] Error in user input: {e}")
                print("[ERROR] Error processing input, please try again")
                continue

    def _get_llm_decision(self, estimated_premium: float, config: Dict) -> ExitConfirmationResult:
        """Get exit decision from LLM in unattended mode."""
        try:
            from utils.llm_decider import LLMDecider
            from utils.llm_json_client import LLMJsonClient
            from utils.llm import LLMClient
            
            # Initialize LLM components
            ensemble_client = LLMClient(config)
            json_client = LLMJsonClient(ensemble_client, self.logger)
            decider = LLMDecider(json_client, config, self.logger)
            
            # Build context for LLM decision
            ctx = self._build_exit_context(estimated_premium, config)
            
            # Get LLM decision
            llm_decision = decider.decide_exit("POSITION", ctx)
            
            # Convert LLM decision to ExitConfirmationResult
            if llm_decision.action == "SELL":
                premium = llm_decision.expected_exit_price or estimated_premium
                self.logger.info(f"[EXIT-LLM] Auto-approving exit at ${premium:.2f} (confidence: {llm_decision.confidence:.2f})")
                return ExitConfirmationResult(
                    action="submit",
                    premium=premium,
                    confirmed=True
                )
            elif llm_decision.action == "HOLD":
                self.logger.info(f"[EXIT-LLM] Auto-rejecting exit (confidence: {llm_decision.confidence:.2f}) - {llm_decision.reason}")
                return ExitConfirmationResult(
                    action="cancel",
                    confirmed=False
                )
            else:  # WAIT or ABSTAIN
                self.logger.info(f"[EXIT-LLM] LLM deferred decision - falling back to manual prompt")
                # Fall back to manual decision
                return self._get_manual_decision(estimated_premium)
                
        except Exception as e:
            self.logger.error(f"[EXIT-LLM] Error getting LLM decision: {e}")
            self.logger.info("[EXIT-LLM] Falling back to manual decision due to error")
            return self._get_manual_decision(estimated_premium)

    def _build_exit_context(self, estimated_premium: float, config: Dict) -> Dict:
        """Build context dictionary for LLM exit decision."""
        from datetime import datetime
        import pytz
        
        # Get current time in ET
        et_tz = pytz.timezone('US/Eastern')
        now_et = datetime.now(et_tz)
        
        # Calculate minutes to market close (4:00 PM ET)
        market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        if now_et > market_close:
            # After hours - set to next day
            market_close = market_close.replace(day=market_close.day + 1)
        
        minutes_to_close = max(0, (market_close - now_et).total_seconds() / 60)
        
        # Build context
        ctx = {
            "symbol": "POSITION",
            "timestamp": now_et.isoformat(),
            "time_to_close_min": minutes_to_close,
            "hard_rails": {
                "force_close_now": minutes_to_close <= 15,  # Force close at 3:45 PM
                "kill_switch": False,  # Would be checked by caller
                "circuit_breaker": False,  # Would be checked by caller
            },
            "pnl": {
                "pct": 0.0,  # Would be calculated by caller
                "velocity_pct_4m": 0.0,  # Would need historical data
            },
            "price": {
                "last": estimated_premium,
                "vwap_rel": 0.0,  # Would need market data
                "spread_bps": 50,  # Estimate
                "iv": 0.3,  # Estimate
            },
            "trend": {
                "ha_trend": "BULLISH",  # Would need market analysis
                "rsi2": 50,  # Would need technical analysis
                "vix": 20.0,  # Would need VIX data
            },
            "policy": {
                "profit_target_pct": 15.0,
                "min_profit_consider_pct": 5.0,
                "stop_loss_pct": -25.0
            },
            "memory": []  # Would include recent trade history
        }
        
        return ctx

    def _get_manual_decision(self, estimated_premium: float) -> ExitConfirmationResult:
        """Get manual decision through interactive prompt (original logic)."""
        while True:
            print("Options:")
            print(f"  [S] Submit at expected price (${estimated_premium:.2f})")
            print("  [C] Cancel exit (keep position open)")
            print("  [P] Submit at different price (enter custom premium)")
            print("  [0.XX] Enter premium directly (e.g., 2.15)")
            print()
            
            try:
                decision = input("Your choice: ").lower().strip()
                
                if not decision:
                    print("❌ Please enter a choice")
                    continue
                
                # Direct premium entry (e.g., "2.15")
                try:
                    premium = float(decision)
                    if 0.01 <= premium <= 50.0:  # Reasonable bounds
                        print(f"[OK] Submitting SELL order at ${premium:.2f}")
                        return ExitConfirmationResult(
                            action="custom_price",
                            premium=premium,
                            confirmed=True
                        )
                    else:
                        print("[ERROR] Premium must be between $0.01 and $50.00")
                        continue
                except ValueError:
                    pass  # Not a number, check other options
                
                # Standard options
                if decision == 's':
                    print(f"[OK] Submitting SELL order at ${estimated_premium:.2f}")
                    return ExitConfirmationResult(
                        action="submit",
                        premium=estimated_premium,
                        confirmed=True
                    )
                
                elif decision == 'c':
                    print("[CANCEL] Exit cancelled - keeping position open")
                    return ExitConfirmationResult(
                        action="cancel",
                        confirmed=False
                    )
                
                elif decision == 'p':
                    # Custom premium entry
                    while True:
                        try:
                            custom_premium = input("Enter sell price: $").strip()
                            premium = float(custom_premium)
                            if 0.01 <= premium <= 50.0:
                                print(f"[OK] Submitting SELL order at ${premium:.2f}")
                                return ExitConfirmationResult(
                                    action="custom_price",
                                    premium=premium,
                                    confirmed=True
                                )
                            else:
                                print("[ERROR] Premium must be between $0.01 and $50.00")
                        except ValueError:
                            print("[ERROR] Please enter a valid number")
                        except KeyboardInterrupt:
                            print("\n[CANCEL] Cancelled")
                            return ExitConfirmationResult(
                                action="cancel",
                                confirmed=False
                            )
                
                else:
                    print("[ERROR] Invalid choice. Please enter S, C, P, or a premium amount")
                    continue
                    
            except KeyboardInterrupt:
                print("\n[CANCEL] Exit cancelled")
                return ExitConfirmationResult(
                    action="cancel",
                    confirmed=False
                )
            except Exception as e:
                self.logger.error(f"[EXIT-CONFIRM] Error in user input: {e}")
                print("[ERROR] Error processing input, please try again")
                continue
    
    def send_slack_notification(
        self, 
        position: Dict, 
        exit_decision: ExitDecision,
        result: ExitConfirmationResult
    ) -> None:
        """Send Slack notification about exit decision."""
        
        if not self.slack or not self.slack.enabled:
            return
        
        symbol = position["symbol"]
        strike = position["strike"]
        option_type = position["option_type"]
        
        if result.confirmed:
            if result.action == "submit":
                message = f"🎯 EXIT CONFIRMED: {symbol} ${strike} {option_type} @ ${result.premium:.2f}"
            elif result.action == "custom_price":
                message = f"🎯 EXIT CONFIRMED: {symbol} ${strike} {option_type} @ ${result.premium:.2f} (custom)"
            else:
                message = f"🎯 EXIT CONFIRMED: {symbol} ${strike} {option_type}"
        else:
            message = f"❌ EXIT CANCELLED: {symbol} ${strike} {option_type} - position remains open"
        
        try:
            # Use basic message sending - enhanced features optional
            if hasattr(self.slack, 'send_message'):
                self.slack.send_message(message)
            else:
                self.logger.warning("[EXIT-CONFIRM] Slack send_message not available")
        except Exception as e:
            self.logger.error(f"[EXIT-CONFIRM] Slack notification failed: {e}")
    
    def remove_position_from_tracking(self, position: Dict) -> bool:
        """
        Remove closed position from positions.csv tracking file.
        
        Args:
            position: Position data to remove
            
        Returns:
            True if successfully removed, False otherwise
        """
        try:
            # Get positions file path (use scoped files if available)
            try:
                from utils.llm import load_config
                from utils.scoped_files import get_scoped_paths
                
                config = load_config("config.yaml")
                broker = config.get("BROKER", "robinhood")
                env = config.get("ALPACA_ENV", "paper") if broker == "alpaca" else "live"
                positions_file = get_scoped_paths(broker, env)["positions"]
            except Exception:
                # Fallback to default positions file
                positions_file = "positions.csv"
            
            if not os.path.exists(positions_file):
                self.logger.warning(f"[EXIT-CONFIRM] Positions file not found: {positions_file}")
                return False
            
            # Read current positions
            remaining_positions = []
            position_found = False
            
            with open(positions_file, 'r', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Check if this is the position to remove
                    if (row.get('symbol') == position['symbol'] and
                        float(row.get('strike', 0)) == float(position['strike']) and
                        row.get('side') == position['option_type']):
                        position_found = True
                        self.logger.info(f"[EXIT-CONFIRM] Removing position: {position['symbol']} ${position['strike']} {position['option_type']}")
                    else:
                        remaining_positions.append(row)
            
            if not position_found:
                self.logger.warning(f"[EXIT-CONFIRM] Position not found in tracking file")
                return False
            
            # Write back remaining positions
            with open(positions_file, 'w', newline='') as f:
                if remaining_positions:
                    fieldnames = remaining_positions[0].keys()
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(remaining_positions)
                else:
                    # Write empty file with header only
                    writer = csv.writer(f)
                    writer.writerow(['entry_time', 'symbol', 'expiry', 'strike', 'side', 'contracts', 'entry_premium'])
            
            self.logger.info(f"[EXIT-CONFIRM] Position removed from tracking file")
            return True
            
        except Exception as e:
            self.logger.error(f"[EXIT-CONFIRM] Error removing position from tracking: {e}")
            return False
    
    def log_completed_trade(
        self, 
        position: Dict, 
        exit_result: ExitConfirmationResult,
        exit_decision: ExitDecision
    ) -> bool:
        """
        Log completed exit trade to trade history.
        
        Args:
            position: Position data
            exit_result: Exit confirmation result with premium
            exit_decision: Exit strategy decision
            
        Returns:
            True if successfully logged, False otherwise
        """
        try:
            # Get trade log file path (use scoped files if available)
            try:
                from utils.llm import load_config
                from utils.scoped_files import get_scoped_paths
                
                config = load_config("config.yaml")
                broker = config.get("BROKER", "robinhood")
                env = config.get("ALPACA_ENV", "paper") if broker == "alpaca" else "live"
                trade_log_file = get_scoped_paths(broker, env)["trade_history"]
            except Exception:
                # Fallback to default trade log file
                trade_log_file = "logs/trade_log.csv"
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(trade_log_file), exist_ok=True)
            
            # Prepare trade log entry
            symbol = position["symbol"]
            strike = position["strike"]
            option_type = position["option_type"]
            entry_price = position["entry_price"]
            exit_price = exit_result.premium
            quantity = position["quantity"]
            
            # Calculate P&L
            entry_value = entry_price * quantity * 100
            exit_value = exit_price * quantity * 100
            pnl = exit_value - entry_value
            pnl_pct = (pnl / entry_value) * 100
            
            trade_entry = {
                'timestamp': datetime.now().isoformat(),
                'action': 'SELL',
                'symbol': symbol,
                'strike': strike,
                'option_type': option_type,
                'expiry': position.get('expiry', ''),
                'quantity': quantity,
                'premium': exit_price,
                'total_cost': exit_value,
                'entry_price': entry_price,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'exit_reason': exit_decision.reason.value,
                'broker': 'manual_execution',
                'notes': f"Interactive exit: {exit_result.action}"
            }
            
            # Check if file exists and has header
            file_exists = os.path.exists(trade_log_file)
            
            with open(trade_log_file, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=trade_entry.keys())
                
                # Write header if file is new
                if not file_exists:
                    writer.writeheader()
                
                writer.writerow(trade_entry)
            
            self.logger.info(f"[EXIT-CONFIRM] Trade logged: {symbol} ${strike} {option_type} SELL @ ${exit_price:.2f} (P&L: ${pnl:+.2f})")
            return True
            
        except Exception as e:
            self.logger.error(f"[EXIT-CONFIRM] Error logging completed trade: {e}")
            return False
    
    def process_confirmed_exit(
        self, 
        position: Dict, 
        exit_result: ExitConfirmationResult,
        exit_decision: ExitDecision
    ) -> bool:
        """
        Process confirmed exit by removing position and logging trade.
        
        Args:
            position: Position data
            exit_result: Exit confirmation result
            exit_decision: Exit strategy decision
            
        Returns:
            True if all operations successful, False otherwise
        """
        success = True
        
        # Remove position from tracking
        if not self.remove_position_from_tracking(position):
            success = False
        
        # Log completed trade
        if not self.log_completed_trade(position, exit_result, exit_decision):
            success = False
        
        # Send Slack notification about position closure
        if success:
            try:
                self.send_slack_notification(position, exit_decision, exit_result)
            except Exception as e:
                self.logger.error(f"[EXIT-CONFIRM] Slack notification failed: {e}")
        
        return success


# Example usage and testing
if __name__ == "__main__":
    # Test the exit confirmation workflow
    from utils.exit_strategies import ExitDecision, ExitReason
    
    # Mock position data
    position = {
        "symbol": "IWM",
        "strike": 223.0,
        "option_type": "CALL",
        "entry_price": 0.86,
        "quantity": 2,
        "expiry": "2025-08-12"
    }
    
    # Mock exit decision
    exit_decision = ExitDecision(
        should_exit=True,
        reason=ExitReason.PROFIT_TARGET,
        current_pnl_pct=141.3,
        message="🎯 PROFIT TARGET 15.0% REACHED! Current profit: +141.3% - Consider taking profits!",
        urgency="high"
    )
    
    # Test workflow
    workflow = ExitConfirmationWorkflow()
    result = workflow.confirm_exit(position, exit_decision, 225.05, 2.09)
    
    print(f"\nResult: {result}")
