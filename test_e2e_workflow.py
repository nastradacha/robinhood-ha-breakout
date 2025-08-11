#!/usr/bin/env python3
"""
End-to-End Test: Slack Notification and Robinhood Trade Selection

This test simulates the complete trading workflow:
1. Market data analysis with enhanced LLM features
2. LLM decision making with context memory
3. Slack notification with rich charts
4. Robinhood browser automation for trade execution
5. Trade confirmation and logging

Usage:
    python test_e2e_workflow.py [--symbol SPY] [--force-trade] [--dry-run]

Options:
    --symbol: Symbol to test (default: SPY)
    --force-trade: Force a CALL trade decision for testing
    --dry-run: Skip actual Robinhood execution, test everything else
"""

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.data import fetch_market_data, analyze_breakout_pattern, build_llm_features
from utils.llm import LLMClient
from utils.enhanced_slack import EnhancedSlackIntegration
from utils.browser import RobinhoodBot
from utils.portfolio import PortfolioManager
from utils.bankroll import BankrollManager
from utils.trade_confirmation import TradeConfirmationManager
# Load config directly since utils.config doesn't exist
import yaml

def load_config():
    with open('config.yaml', 'r') as f:
        return yaml.safe_load(f)
import logging

# Configure centralized logging
from utils.logging_utils import setup_logging
setup_logging(log_level="INFO", log_file="logs/test_e2e_workflow.log")
logger = logging.getLogger(__name__)


class E2ETestWorkflow:
    """End-to-end test workflow for the enhanced trading system."""
    
    def __init__(self, symbol: str = "SPY", force_trade: bool = False, dry_run: bool = False):
        self.symbol = symbol
        self.force_trade = force_trade
        self.dry_run = dry_run
        self.config = load_config()
        
        # Initialize components in correct order
        self.portfolio = PortfolioManager()
        self.bankroll = BankrollManager()
        self.llm_client = LLMClient()
        self.slack = EnhancedSlackIntegration()
        self.confirmation_manager = TradeConfirmationManager(
            portfolio_manager=self.portfolio,
            bankroll_manager=self.bankroll
        )
        
        if not dry_run:
            self.browser = RobinhoodBot()
        
        logger.info(f"[E2E-TEST] Initialized for {symbol} (force_trade={force_trade}, dry_run={dry_run})")

    def step_1_market_analysis(self) -> Dict[str, Any]:
        """Step 1: Fetch market data and perform enhanced analysis."""
        logger.info("[E2E-TEST] Step 1: Market Data Analysis with Enhanced Features")
        
        try:
            # Fetch market data
            market_data = fetch_market_data(self.symbol)
            logger.info(f"[E2E-TEST] ✓ Fetched {len(market_data)} bars for {self.symbol}")
            
            # Analyze breakout pattern
            analysis = analyze_breakout_pattern(market_data, self.symbol)
            logger.info(f"[E2E-TEST] ✓ Breakout analysis completed")
            
            # Build enhanced LLM features (new functionality)
            enhanced_features = build_llm_features(market_data, self.symbol)
            logger.info(f"[E2E-TEST] ✓ Enhanced LLM features calculated:")
            logger.info(f"    - VWAP Deviation: {enhanced_features.get('vwap_deviation_pct', 'N/A')}%")
            logger.info(f"    - ATM Delta: {enhanced_features.get('atm_delta', 'N/A')}")
            logger.info(f"    - ATM Open Interest: {enhanced_features.get('atm_oi', 'N/A')}")
            logger.info(f"    - Dealer Gamma: ${enhanced_features.get('dealer_gamma_$', 'N/A')}")
            
            # Combine analysis with enhanced features
            analysis.update(enhanced_features)
            
            return {
                'market_data': market_data,
                'analysis': analysis,
                'enhanced_features': enhanced_features
            }
            
        except Exception as e:
            logger.error(f"[E2E-TEST] ✗ Market analysis failed: {e}")
            raise

    def step_2_llm_decision(self, market_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Step 2: LLM decision making with enhanced context and recent trade memory."""
        logger.info("[E2E-TEST] Step 2: LLM Decision with Enhanced Context Memory")
        
        try:
            market_data = market_analysis['market_data']
            analysis = market_analysis['analysis']
            
            # Load win history for context
            win_history = self.bankroll.get_win_history(depth=10) if hasattr(self.bankroll, 'get_win_history') else []
            
            # Enhanced context with new features
            enhanced_context = {
                'symbol': self.symbol,
                'enhanced_features': market_analysis['enhanced_features'],
                'test_mode': True
            }
            
            if self.force_trade:
                # Force a CALL decision for testing
                logger.info("[E2E-TEST] ⚠️ Forcing CALL trade decision for testing")
                decision = {
                    'action': 'CALL',
                    'confidence': 0.75,
                    'reasoning': 'Forced trade for end-to-end testing - enhanced features integrated',
                    'quantity': 1
                }
            else:
                # Real LLM decision with enhanced features and context memory
                decision = self.llm_client.make_trade_decision(
                    market_data=market_data,
                    win_history=win_history,
                    enhanced_context=enhanced_context
                )
            
            logger.info(f"[E2E-TEST] ✓ LLM Decision: {decision['action']} (confidence: {decision.get('confidence', 'N/A')})")
            logger.info(f"[E2E-TEST] ✓ Reasoning: {decision.get('reasoning', 'N/A')[:100]}...")
            
            return decision
            
        except Exception as e:
            logger.error(f"[E2E-TEST] ✗ LLM decision failed: {e}")
            raise

    def step_3_slack_notification(self, market_analysis: Dict[str, Any], decision: Dict[str, Any]) -> bool:
        """Step 3: Send rich Slack notification with charts and analysis."""
        logger.info("[E2E-TEST] Step 3: Enhanced Slack Notification with Charts")
        
        try:
            if decision['action'] == 'NO_TRADE':
                # Send heartbeat notification
                success = self.slack.send_heartbeat(
                    symbols=[self.symbol],
                    no_trade_count=1,
                    enhanced_features=market_analysis['enhanced_features']
                )
                logger.info("[E2E-TEST] ✓ Sent NO_TRADE heartbeat notification")
            else:
                # Send breakout alert with chart
                success = self.slack.send_breakout_alert_with_chart(
                    symbol=self.symbol,
                    trade_type=decision['action'],
                    confidence=decision.get('confidence', 0.5),
                    reasoning=decision.get('reasoning', ''),
                    market_data=market_analysis['market_data'],
                    enhanced_features=market_analysis['enhanced_features']
                )
                logger.info(f"[E2E-TEST] ✓ Sent {decision['action']} breakout alert with chart")
            
            return success
            
        except Exception as e:
            logger.error(f"[E2E-TEST] ✗ Slack notification failed: {e}")
            return False

    def step_4_robinhood_execution(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """Step 4: Robinhood browser automation for trade execution."""
        logger.info("[E2E-TEST] Step 4: Robinhood Trade Execution")
        
        if self.dry_run:
            logger.info("[E2E-TEST] ⚠️ DRY RUN: Skipping actual Robinhood execution")
            return {
                'success': True,
                'premium': 1.25,  # Mock premium
                'quantity': decision.get('quantity', 1),
                'dry_run': True
            }
        
        if decision['action'] == 'NO_TRADE':
            logger.info("[E2E-TEST] ✓ No trade to execute")
            return {'success': True, 'no_trade': True}
        
        try:
            # Check portfolio constraints
            positions = self.portfolio.load_positions()
            trade_action = self.portfolio.determine_trade_action(
                self.symbol, decision['action'], positions
            )
            
            if trade_action != 'OPEN':
                logger.info(f"[E2E-TEST] ✓ Portfolio constraint: {trade_action}")
                return {'success': True, 'constraint': trade_action}
            
            # Start browser and navigate to options
            logger.info("[E2E-TEST] Starting Chrome browser...")
            self.browser.start_browser()
            
            # Navigate to symbol
            logger.info(f"[E2E-TEST] Navigating to {self.symbol} options...")
            self.browser.navigate_to_symbol(self.symbol)
            
            # Find and select ATM option
            logger.info("[E2E-TEST] Finding ATM option...")
            option_found = self.browser.find_atm_option(decision['action'])
            
            if not option_found:
                raise Exception("Could not find suitable ATM option")
            
            # Set quantity
            quantity = decision.get('quantity', 1)
            logger.info(f"[E2E-TEST] Setting quantity to {quantity}...")
            self.browser.set_quantity(quantity)
            
            # Get premium and proceed to review
            logger.info("[E2E-TEST] Proceeding to review screen...")
            premium = self.browser.get_option_premium()
            review_success = self.browser.click_review_order()
            
            if not review_success:
                raise Exception("Could not reach review screen")
            
            logger.info(f"[E2E-TEST] ✓ Reached review screen - Premium: ${premium}")
            logger.info("[E2E-TEST] ⚠️ STOPPING at review screen for safety")
            
            return {
                'success': True,
                'premium': premium,
                'quantity': quantity,
                'review_reached': True
            }
            
        except Exception as e:
            logger.error(f"[E2E-TEST] ✗ Robinhood execution failed: {e}")
            return {'success': False, 'error': str(e)}
        
        finally:
            if hasattr(self, 'browser'):
                try:
                    self.browser.cleanup()
                except:
                    pass

    def step_5_trade_confirmation(self, decision: Dict[str, Any], execution_result: Dict[str, Any]) -> bool:
        """Step 5: Trade confirmation workflow and logging."""
        logger.info("[E2E-TEST] Step 5: Trade Confirmation and Logging")
        
        try:
            if decision['action'] == 'NO_TRADE' or execution_result.get('no_trade'):
                # Log NO_TRADE decision
                self.confirmation_manager.log_trade_decision(
                    symbol=self.symbol,
                    action='NO_TRADE',
                    reasoning=decision.get('reasoning', 'E2E test - no trade'),
                    confidence=decision.get('confidence', 0.0)
                )
                logger.info("[E2E-TEST] ✓ Logged NO_TRADE decision")
                return True
            
            if not execution_result.get('success'):
                logger.error("[E2E-TEST] ✗ Cannot confirm failed execution")
                return False
            
            if execution_result.get('dry_run'):
                logger.info("[E2E-TEST] ✓ DRY RUN: Simulated trade confirmation")
                return True
            
            # Real trade confirmation (stopped at review screen)
            logger.info("[E2E-TEST] Trade reached review screen - manual confirmation required")
            logger.info("[E2E-TEST] In production, user would confirm via:")
            logger.info("[E2E-TEST]   1. Interactive prompt (S/C)")
            logger.info("[E2E-TEST]   2. Slack confirmation message")
            
            # For testing, simulate a cancel
            logger.info("[E2E-TEST] Simulating CANCEL for safety...")
            
            # Log the test trade
            self.confirmation_manager.log_trade_decision(
                symbol=self.symbol,
                action=decision['action'],
                reasoning=f"E2E test - {decision.get('reasoning', '')}",
                confidence=decision.get('confidence', 0.0),
                premium=execution_result.get('premium', 0.0),
                quantity=execution_result.get('quantity', 1)
            )
            
            logger.info("[E2E-TEST] ✓ Trade logged for testing")
            return True
            
        except Exception as e:
            logger.error(f"[E2E-TEST] ✗ Trade confirmation failed: {e}")
            return False

    def run_full_workflow(self) -> bool:
        """Run the complete end-to-end test workflow."""
        logger.info("=" * 60)
        logger.info("[E2E-TEST] Starting Full Workflow Test")
        logger.info("=" * 60)
        
        start_time = datetime.now(timezone.utc)
        
        try:
            # Step 1: Market Analysis with Enhanced Features
            market_analysis = self.step_1_market_analysis()
            
            # Step 2: LLM Decision with Context Memory
            decision = self.step_2_llm_decision(market_analysis)
            
            # Step 3: Enhanced Slack Notification
            slack_success = self.step_3_slack_notification(market_analysis, decision)
            
            # Step 4: Robinhood Execution
            execution_result = self.step_4_robinhood_execution(decision)
            
            # Step 5: Trade Confirmation
            confirmation_success = self.step_5_trade_confirmation(decision, execution_result)
            
            # Summary
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            
            logger.info("=" * 60)
            logger.info("[E2E-TEST] Workflow Summary")
            logger.info("=" * 60)
            logger.info(f"Symbol: {self.symbol}")
            logger.info(f"Duration: {duration:.1f} seconds")
            logger.info(f"LLM Decision: {decision['action']} (confidence: {decision.get('confidence', 'N/A')})")
            logger.info(f"Slack Notification: {'✓' if slack_success else '✗'}")
            logger.info(f"Robinhood Execution: {'✓' if execution_result.get('success') else '✗'}")
            logger.info(f"Trade Confirmation: {'✓' if confirmation_success else '✗'}")
            
            overall_success = all([
                slack_success,
                execution_result.get('success', False),
                confirmation_success
            ])
            
            if overall_success:
                logger.info("[E2E-TEST] 🎉 FULL WORKFLOW TEST PASSED")
            else:
                logger.error("[E2E-TEST] ❌ WORKFLOW TEST FAILED")
            
            return overall_success
            
        except Exception as e:
            logger.error(f"[E2E-TEST] ❌ Workflow failed with exception: {e}")
            return False


def main():
    """Main entry point for end-to-end test."""
    parser = argparse.ArgumentParser(description="End-to-End Trading Workflow Test")
    parser.add_argument("--symbol", default="SPY", help="Symbol to test (default: SPY)")
    parser.add_argument("--force-trade", action="store_true", help="Force a CALL trade decision")
    parser.add_argument("--dry-run", action="store_true", help="Skip Robinhood execution")
    
    args = parser.parse_args()
    
    # Run the test
    workflow = E2ETestWorkflow(
        symbol=args.symbol,
        force_trade=args.force_trade,
        dry_run=args.dry_run
    )
    
    success = workflow.run_full_workflow()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
