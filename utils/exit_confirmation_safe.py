#!/usr/bin/env python3
"""
Windows-Safe Interactive Exit Confirmation Workflow

Provides user-friendly interactive prompts for position exit decisions,
optimized for Windows console compatibility (no Unicode/emoji characters).

Features:
- Interactive terminal prompts for exit decisions
- Support for profit targets, stop losses, and time-based exits
- Custom premium entry for accurate fill prices
- Automatic position removal and trade logging
- Windows console compatible (ASCII only)

Usage:
    from utils.exit_confirmation_safe import SafeExitConfirmationWorkflow
    
    workflow = SafeExitConfirmationWorkflow()
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


class SafeExitConfirmationWorkflow:
    """Windows-safe interactive exit confirmation workflow for position management."""
    
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
        """Display formatted exit confirmation prompt (Windows-safe)."""
        
        symbol = position["symbol"]
        strike = position["strike"]
        option_type = position["option_type"]
        entry_price = position["entry_price"]
        quantity = position["quantity"]
        
        # Choose title based on exit reason (ASCII only)
        if exit_decision.reason == ExitReason.PROFIT_TARGET:
            title = "PROFIT TARGET REACHED"
            urgency = "[PROFIT]"
        elif exit_decision.reason == ExitReason.TRAILING_STOP:
            title = "TRAILING STOP TRIGGERED"
            urgency = "[TRAIL]"
        elif exit_decision.reason == ExitReason.STOP_LOSS:
            title = "STOP LOSS TRIGGERED"
            urgency = "[STOP]"
        elif exit_decision.reason == ExitReason.TIME_BASED:
            title = "TIME-BASED EXIT"
            urgency = "[TIME]"
        else:
            title = "EXIT SIGNAL DETECTED"
            urgency = "[EXIT]"
        
        print("\n" + "="*60)
        print(f"{urgency} {title} {urgency}")
        print("="*60)
        print(f"Position: {symbol} ${strike} {option_type}")
        print(f"Entry Price: ${entry_price:.2f}")
        print(f"Current Price: ${current_option_price:.2f}")
        print(f"Stock Price: ${current_stock_price:.2f}")
        print(f"Quantity: {quantity} contract{'s' if quantity != 1 else ''}")
        print()
        print(f"P&L: ${pnl:+.2f} ({pnl_pct:+.1f}%)")
        print()
        print(f"Reason: {exit_decision.message}")
        print()
        print("Trade: SELL")
        print(f"Expected Premium: ${current_option_price:.2f}")
        print(f"Total Value: ${current_option_price * quantity * 100:.2f}")
        print("-"*60)
        print("TIP: Away from PC? Send Slack message: 'filled 2.15' or 'cancelled'")
        print("-"*60)
        print()
    
    def _get_user_decision(self, estimated_premium: float) -> ExitConfirmationResult:
        """Get user decision through interactive prompt."""
        
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
                    print("[ERROR] Please enter a choice")
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
    
    def remove_position_from_tracking(self, position: Dict) -> bool:
        """Remove closed position from positions.csv tracking file."""
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
        """Log completed exit trade to trade history."""
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
        """Process a confirmed exit decision by submitting order, removing position and logging trade."""
        try:
            # Step 1: Submit automatic sell order through Alpaca (if available)
            order_success = self.submit_automatic_sell_order(position, exit_result)
            
            # Step 2: Remove position from tracking
            success_remove = self.remove_position_from_tracking(position)
            
            # Step 3: Log completed trade
            success_log = self.log_completed_trade(position, exit_result, exit_decision)
            
            return order_success and success_remove and success_log
            
        except Exception as e:
            self.logger.error(f"[EXIT-CONFIRM] Error processing confirmed exit: {e}")
            return False
    
    def submit_automatic_sell_order(self, position: Dict, exit_result: ExitConfirmationResult) -> bool:
        """Submit automatic sell order through Alpaca API."""
        try:
            # Check if we're using Alpaca
            from utils.llm import load_config
            config = load_config("config.yaml")
            broker = config.get("BROKER", "robinhood")
            
            if broker != "alpaca":
                print("[INFO] Manual execution required - not using Alpaca API")
                return True  # Consider success for non-Alpaca brokers
            
            # Import and initialize Alpaca options trader
            from utils.alpaca_options import create_alpaca_trader
            env = config.get("ALPACA_ENV", "paper")
            paper_mode = (env == "paper")
            alpaca_trader = create_alpaca_trader(paper=paper_mode)
            
            if not alpaca_trader:
                print("[WARNING] Alpaca API not available - manual execution required")
                return True
            
            # Build contract symbol for the position
            symbol = position["symbol"]
            strike = position["strike"]
            option_type = position["option_type"]
            expiry = position["expiry"]
            quantity = position["quantity"]
            
            # Format contract symbol (OCC format)
            from datetime import datetime
            expiry_date = datetime.strptime(expiry, "%Y-%m-%d")
            expiry_str = expiry_date.strftime("%y%m%d")
            strike_str = f"{int(strike * 1000):08d}"
            contract_symbol = f"{symbol}{expiry_str}{option_type[0]}{strike_str}"
            
            print(f"\n[AUTOMATIC EXECUTION] Submitting sell order...")
            print(f"Contract: {contract_symbol}")
            print(f"Quantity: {quantity}")
            print(f"Expected Price: ${exit_result.premium:.2f}")
            
            # Submit market sell order
            order_id = alpaca_trader.close_position(contract_symbol, quantity)
            
            if order_id:
                print(f"[SUCCESS] Sell order submitted! Order ID: {order_id}")
                print(f"[INFO] Order will execute at market price")
                self.logger.info(f"[AUTO-EXIT] Submitted sell order {order_id} for {contract_symbol}")
                return True
            else:
                print(f"[ERROR] Failed to submit sell order - manual execution required")
                print(f"[MANUAL] Please sell {quantity} contracts of {symbol} ${strike} {option_type}")
                self.logger.error(f"[AUTO-EXIT] Failed to submit sell order for {contract_symbol}")
                return False
                
        except Exception as e:
            print(f"[ERROR] Automatic execution failed: {e}")
            print(f"[MANUAL] Please execute sell order manually at your broker")
            self.logger.error(f"[AUTO-EXIT] Automatic execution error: {e}")
            return False


# Example usage and testing
if __name__ == "__main__":
    # Test the safe exit confirmation workflow
    from utils.exit_strategies import ExitDecision, ExitReason
    
    # Mock position data
    position = {
        "symbol": "SPY",
        "strike": 550.0,
        "option_type": "CALL",
        "entry_price": 2.50,
        "quantity": 1,
        "expiry": "2025-08-12"
    }
    
    # Mock exit decision
    exit_decision = ExitDecision(
        should_exit=True,
        reason=ExitReason.PROFIT_TARGET,
        current_pnl_pct=3547.3,
        message="PROFIT TARGET 15.0% REACHED! Current profit: +3547.3% - Consider taking profits!",
        urgency="high"
    )
    
    # Test workflow
    workflow = SafeExitConfirmationWorkflow()
    result = workflow.confirm_exit(position, exit_decision, 641.13, 91.18)
    
    print(f"\nResult: {result}")
