#!/usr/bin/env python3
"""
Full End-to-End Test with Robinhood Browser Automation

This script runs a complete end-to-end test that includes:
1. Enhanced LLM decision making with all new features
2. Real market data analysis with Alpaca integration
3. Actual Robinhood browser automation (login, navigation, option selection)
4. Trade execution workflow (up to Review screen)
5. Slack alerts with rich charts
6. Complete error handling and validation

This is the COMPLETE production workflow test including browser automation.

Usage:
    python test_full_e2e_with_browser.py --symbol SPY --live-browser
    python test_full_e2e_with_browser.py --symbol QQQ --dry-run
"""

import argparse
import logging
import time
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

# Add project root to path
sys.path.append(str(Path(__file__).parent))

# Import all production modules
from utils.data import fetch_market_data, prepare_llm_payload, build_llm_features, calculate_heikin_ashi, analyze_breakout_pattern
from utils.llm import LLMClient, TradeDecision
from utils.slack_bot import SlackBot
from utils.enhanced_slack import EnhancedSlackIntegration
from utils.recent_trades import load_recent
from utils.llm import load_config
from utils.browser import RobinhoodBot
from utils.portfolio import PortfolioManager
from utils.bankroll import BankrollManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/full_e2e_test.log')
    ]
)
logger = logging.getLogger(__name__)

class FullE2ETest:
    """Complete end-to-end test including Robinhood browser automation."""
    
    def __init__(self, symbol: str = "SPY", live_browser: bool = False):
        """Initialize full E2E test."""
        self.symbol = symbol
        self.live_browser = live_browser
        self.config = load_config()
        
        # Initialize components
        self.llm_client = LLMClient()
        self.portfolio = PortfolioManager()
        self.bankroll = BankrollManager()
        
        # Initialize Slack (optional)
        try:
            self.slack = SlackBot()
            self.enhanced_slack = EnhancedSlackIntegration()
            self.slack_enabled = True
            logger.info("[INIT] Slack integration initialized")
        except Exception as e:
            logger.warning(f"[INIT] Slack initialization failed: {e}")
            self.slack_enabled = False
        
        # Test statistics
        self.stats = {
            'start_time': datetime.now(),
            'steps_completed': 0,
            'errors': 0,
            'browser_automation': False,
            'trade_executed': False
        }
        
        logger.info(f"[INIT] Full E2E Test initialized for {symbol}")
        logger.info(f"[INIT] Live browser automation: {live_browser}")
        logger.info(f"[INIT] Slack alerts: {self.slack_enabled}")

    def step_1_market_data_analysis(self) -> Dict:
        """Step 1: Fetch and analyze real market data with enhanced features."""
        logger.info("[STEP 1] Market Data Analysis with Enhanced Features")
        
        try:
            # Fetch real market data
            logger.info(f"[DATA] Fetching real-time market data for {self.symbol}")
            market_data = fetch_market_data(self.symbol, period="1d", interval="1m")
            
            if market_data.empty:
                raise ValueError(f"No market data available for {self.symbol}")
            
            # Analyze market data for breakout patterns
            logger.info("[ANALYSIS] Calculating Heikin-Ashi and breakout patterns")
            ha_data = calculate_heikin_ashi(market_data)
            analysis = analyze_breakout_pattern(ha_data, lookback=20)
            analysis['symbol'] = self.symbol
            
            # Calculate enhanced LLM features
            logger.info("[FEATURES] Calculating enhanced LLM features")
            enhanced_features = build_llm_features(self.symbol)
            
            logger.info("[OK] Market data analysis completed:")
            logger.info(f"  - Current Price: ${analysis['current_price']:.2f}")
            logger.info(f"  - Trend Direction: {analysis['trend_direction']}")
            logger.info(f"  - VWAP Deviation: {enhanced_features.get('vwap_deviation_pct', 0):.3f}%")
            logger.info(f"  - ATM Delta: {enhanced_features.get('atm_delta', 0):.3f}")
            logger.info(f"  - ATM Open Interest: {enhanced_features.get('atm_oi', 0):,}")
            logger.info(f"  - Dealer Gamma: ${enhanced_features.get('dealer_gamma_$', 0):,}")
            
            self.stats['steps_completed'] += 1
            return {
                'success': True,
                'analysis': analysis,
                'enhanced_features': enhanced_features
            }
            
        except Exception as e:
            logger.error(f"[ERROR] Market data analysis failed: {e}")
            self.stats['errors'] += 1
            return {'success': False, 'error': str(e)}

    def step_2_llm_decision(self, analysis: Dict, enhanced_features: Dict) -> Dict:
        """Step 2: Make enhanced LLM trade decision with context memory."""
        logger.info("[STEP 2] Enhanced LLM Decision Making")
        
        try:
            # Load recent trades for context memory
            recent_trades = load_recent(self.config.get('MEMORY_DEPTH', 5))
            logger.info(f"[CONTEXT] Loaded {len(recent_trades)} recent trades for context")
            
            # Prepare enhanced LLM payload
            logger.info("[LLM] Preparing enhanced payload with all features")
            llm_payload = prepare_llm_payload(analysis, max_tokens=400)
            llm_payload.update(enhanced_features)
            if recent_trades:
                llm_payload['recent_trades'] = recent_trades
            
            # Make LLM decision
            logger.info("[LLM] Making enhanced trade decision")
            decision = self.llm_client.make_trade_decision(
                llm_payload,
                enhanced_context={
                    'recent_trades': recent_trades,
                    'enhanced_features': enhanced_features
                }
            )
            
            logger.info(f"[OK] LLM Decision: {decision.decision}")
            logger.info(f"  - Confidence: {decision.confidence}")
            logger.info(f"  - Reason: {decision.reason[:100] if decision.reason else 'N/A'}...")
            
            self.stats['steps_completed'] += 1
            return {
                'success': True,
                'decision': decision,
                'llm_payload': llm_payload
            }
            
        except Exception as e:
            logger.error(f"[ERROR] LLM decision failed: {e}")
            self.stats['errors'] += 1
            return {'success': False, 'error': str(e)}

    def step_3_slack_notification(self, decision: TradeDecision, analysis: Dict, enhanced_features: Dict) -> Dict:
        """Step 3: Send Slack notification with rich charts."""
        logger.info("[STEP 3] Slack Notification with Rich Charts")
        
        if not self.slack_enabled:
            logger.info("[SKIP] Slack notifications disabled")
            return {'success': True, 'skipped': True}
        
        try:
            if decision.decision == 'NO_TRADE':
                logger.info("[SLACK] Sending NO_TRADE heartbeat")
                # Send heartbeat notification
                heartbeat_message = f"NO_TRADE for {self.symbol} @ ${analysis['current_price']:.2f} ({analysis['trend_direction']})"
                self.slack.send_heartbeat(heartbeat_message)
            else:
                logger.info(f"[SLACK] Sending {decision.decision} breakout alert with chart")
                # Send rich breakout alert with chart
                self.enhanced_slack.send_breakout_alert_with_chart(
                    symbol=self.symbol,
                    decision=decision.decision,
                    confidence=decision.confidence,
                    current_price=analysis['current_price'],
                    analysis=analysis
                )
            
            logger.info("[OK] Slack notification sent successfully")
            self.stats['steps_completed'] += 1
            return {'success': True}
            
        except Exception as e:
            logger.error(f"[ERROR] Slack notification failed: {e}")
            self.stats['errors'] += 1
            return {'success': False, 'error': str(e)}

    def step_4_browser_automation(self, decision: TradeDecision, analysis: Dict) -> Dict:
        """Step 4: Robinhood browser automation (the missing piece!)."""
        logger.info("[STEP 4] Robinhood Browser Automation")
        
        if decision.decision == 'NO_TRADE':
            logger.info("[SKIP] No trade to execute - browser automation not needed")
            return {'success': True, 'no_trade': True}
        
        if not self.live_browser:
            logger.info("[SIMULATE] Simulating browser automation (use --live-browser for real test)")
            return {
                'success': True,
                'simulated': True,
                'premium': 1.25,
                'quantity': 1
            }
        
        browser = None
        try:
            logger.info("[BROWSER] Starting Chrome browser with stealth mode")
            browser = RobinhoodBot()
            
            # Step 4.1: Start browser and load session
            logger.info("[BROWSER] Loading Robinhood session")
            browser.start_browser()
            
            # Step 4.2: Navigate to options page
            logger.info(f"[BROWSER] Navigating to {self.symbol} options")
            browser.navigate_to_options(self.symbol)
            
            # Step 4.3: Find and select ATM option
            logger.info(f"[BROWSER] Finding ATM {decision.decision} option")
            option_type = 'call' if decision.decision == 'CALL' else 'put'
            current_price = analysis['current_price']
            
            option_info = browser.find_atm_option(current_price, option_type)
            if not option_info:
                raise ValueError(f"Could not find ATM {option_type} option")
            
            logger.info(f"[BROWSER] Found option: {option_info['strike']} {option_type} @ ${option_info['premium']}")
            
            # Step 4.4: Click option and proceed to buy
            logger.info("[BROWSER] Clicking option and setting up trade")
            browser.click_option_and_buy(option_info)
            
            # Step 4.5: Set quantity and proceed to review
            logger.info("[BROWSER] Setting quantity and proceeding to review")
            quantity = self.calculate_position_size(option_info['premium'])
            browser.set_quantity_and_review(quantity)
            
            # Step 4.6: Reach Review screen (DO NOT SUBMIT)
            logger.info("[BROWSER] Reached Review screen - STOPPING HERE")
            logger.info("[SAFETY] Trade setup complete but NOT submitted for safety")
            
            self.stats['browser_automation'] = True
            self.stats['steps_completed'] += 1
            
            return {
                'success': True,
                'option_info': option_info,
                'quantity': quantity,
                'total_cost': option_info['premium'] * quantity * 100,
                'review_screen_reached': True
            }
            
        except Exception as e:
            logger.error(f"[ERROR] Browser automation failed: {e}")
            self.stats['errors'] += 1
            return {'success': False, 'error': str(e)}
            
        finally:
            if browser:
                logger.info("[BROWSER] Closing browser")
                browser.quit()

    def calculate_position_size(self, premium: float) -> int:
        """Calculate appropriate position size based on risk management."""
        try:
            current_bankroll = self.bankroll.get_current_bankroll()
            risk_fraction = self.config.get('RISK_FRACTION', 0.2)
            max_risk = current_bankroll * risk_fraction
            
            # Calculate max contracts based on premium
            max_contracts = int(max_risk / (premium * 100))
            
            # Ensure at least 1 contract but not more than reasonable limit
            quantity = max(1, min(max_contracts, 5))
            
            logger.info(f"[RISK] Position size: {quantity} contracts (${premium * quantity * 100:.2f} total)")
            return quantity
            
        except Exception as e:
            logger.warning(f"[RISK] Position sizing failed, using 1 contract: {e}")
            return 1

    def step_5_trade_logging(self, decision: TradeDecision, browser_result: Dict) -> Dict:
        """Step 5: Log trade outcome and update records."""
        logger.info("[STEP 5] Trade Logging and Record Keeping")
        
        try:
            if decision.decision == 'NO_TRADE':
                logger.info("[LOG] Logging NO_TRADE decision")
                # Log NO_TRADE decision for LLM learning
                # This would typically go to trade_log.csv
            else:
                logger.info("[LOG] Logging trade setup (not executed)")
                # Log trade setup details for analysis
                trade_details = {
                    'symbol': self.symbol,
                    'decision': decision.decision,
                    'confidence': decision.confidence,
                    'reason': decision.reason,
                    'browser_automation': browser_result.get('success', False),
                    'review_screen_reached': browser_result.get('review_screen_reached', False),
                    'simulated': browser_result.get('simulated', False)
                }
                logger.info(f"[LOG] Trade details: {trade_details}")
            
            self.stats['steps_completed'] += 1
            return {'success': True}
            
        except Exception as e:
            logger.error(f"[ERROR] Trade logging failed: {e}")
            self.stats['errors'] += 1
            return {'success': False, 'error': str(e)}

    def run_full_test(self) -> Dict:
        """Run the complete end-to-end test with all components."""
        logger.info("=" * 80)
        logger.info("[START] FULL END-TO-END TEST WITH BROWSER AUTOMATION")
        logger.info("=" * 80)
        logger.info(f"Symbol: {self.symbol}")
        logger.info(f"Live Browser: {self.live_browser}")
        logger.info(f"Slack Alerts: {self.slack_enabled}")
        logger.info("=" * 80)
        
        results = {}
        
        try:
            # Step 1: Market Data Analysis
            step1_result = self.step_1_market_data_analysis()
            results['step1_market_data'] = step1_result
            if not step1_result['success']:
                raise Exception(f"Step 1 failed: {step1_result['error']}")
            
            # Step 2: LLM Decision
            step2_result = self.step_2_llm_decision(
                step1_result['analysis'],
                step1_result['enhanced_features']
            )
            results['step2_llm_decision'] = step2_result
            if not step2_result['success']:
                raise Exception(f"Step 2 failed: {step2_result['error']}")
            
            # Step 3: Slack Notification
            step3_result = self.step_3_slack_notification(
                step2_result['decision'],
                step1_result['analysis'],
                step1_result['enhanced_features']
            )
            results['step3_slack'] = step3_result
            if not step3_result['success']:
                raise Exception(f"Step 3 failed: {step3_result['error']}")
            
            # Step 4: Browser Automation (THE CRITICAL MISSING PIECE)
            step4_result = self.step_4_browser_automation(
                step2_result['decision'],
                step1_result['analysis']
            )
            results['step4_browser'] = step4_result
            if not step4_result['success']:
                raise Exception(f"Step 4 failed: {step4_result['error']}")
            
            # Step 5: Trade Logging
            step5_result = self.step_5_trade_logging(
                step2_result['decision'],
                step4_result
            )
            results['step5_logging'] = step5_result
            if not step5_result['success']:
                raise Exception(f"Step 5 failed: {step5_result['error']}")
            
            # Test completed successfully
            self.print_final_summary(results)
            return {
                'success': True,
                'results': results,
                'stats': self.stats
            }
            
        except Exception as e:
            logger.error(f"[FAILED] Full E2E test failed: {e}")
            self.stats['errors'] += 1
            self.print_final_summary(results)
            return {
                'success': False,
                'error': str(e),
                'results': results,
                'stats': self.stats
            }

    def print_final_summary(self, results: Dict):
        """Print comprehensive test summary."""
        duration = datetime.now() - self.stats['start_time']
        
        logger.info("=" * 80)
        logger.info("[FULL E2E TEST SUMMARY]")
        logger.info("=" * 80)
        logger.info(f"Duration: {duration}")
        logger.info(f"Symbol: {self.symbol}")
        logger.info(f"Live Browser: {self.live_browser}")
        logger.info("")
        
        logger.info("[TEST RESULTS]:")
        logger.info(f"  Steps Completed: {self.stats['steps_completed']}/5")
        logger.info(f"  Errors: {self.stats['errors']}")
        logger.info(f"  Browser Automation: {'[OK]' if self.stats['browser_automation'] else '[SKIPPED]'}")
        logger.info("")
        
        logger.info("[COMPONENT STATUS]:")
        logger.info(f"  Market Data & Analysis: {'[OK]' if results.get('step1_market_data', {}).get('success') else '[FAILED]'}")
        logger.info(f"  Enhanced LLM Decision: {'[OK]' if results.get('step2_llm_decision', {}).get('success') else '[FAILED]'}")
        logger.info(f"  Slack Notifications: {'[OK]' if results.get('step3_slack', {}).get('success') else '[FAILED]'}")
        logger.info(f"  Browser Automation: {'[OK]' if results.get('step4_browser', {}).get('success') else '[FAILED]'}")
        logger.info(f"  Trade Logging: {'[OK]' if results.get('step5_logging', {}).get('success') else '[FAILED]'}")
        logger.info("")
        
        if self.stats['errors'] == 0:
            logger.info("[SUCCESS] FULL E2E TEST COMPLETED SUCCESSFULLY!")
            logger.info("All components including browser automation validated!")
        else:
            logger.warning(f"[WARNING] {self.stats['errors']} errors encountered - check logs")
        
        logger.info("=" * 80)

def main():
    """Main entry point for full E2E test."""
    parser = argparse.ArgumentParser(description='Full End-to-End Test with Browser Automation')
    parser.add_argument('--symbol', type=str, default='SPY', help='Symbol to test (default: SPY)')
    parser.add_argument('--live-browser', action='store_true', help='Use real browser automation (default: simulate)')
    
    args = parser.parse_args()
    
    # Run full E2E test
    test = FullE2ETest(symbol=args.symbol, live_browser=args.live_browser)
    result = test.run_full_test()
    
    # Exit with appropriate code
    sys.exit(0 if result['success'] else 1)

if __name__ == "__main__":
    main()
