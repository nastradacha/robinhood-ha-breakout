#!/usr/bin/env python3
"""
Multi-Symbol Scanner Module

Handles scanning and analysis of multiple symbols (SPY, QQQ, IWM) simultaneously
for breakout opportunities. Provides prioritization and signal aggregation.

Features:
- Concurrent analysis of multiple symbols
- Signal prioritization and ranking
- Risk allocation across symbols
- Consolidated Slack notifications
- Performance tracking per symbol
"""

import logging
import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from .data import fetch_market_data, calculate_heikin_ashi, analyze_breakout_pattern
from .llm import LLMClient, TradeDecision
from .enhanced_slack import EnhancedSlackIntegration

logger = logging.getLogger(__name__)

class MultiSymbolScanner:
    """
    Multi-symbol breakout scanner for diversified trading opportunities.
    """
    
    def __init__(self, config: Dict, llm_client, slack_notifier=None):
        """
        Initialize multi-symbol scanner.
        
        Args:
            config: Trading configuration
            llm_client: LLM client for trade decisions
            slack_notifier: Slack notification client
        """
        self.config = config
        self.llm_client = llm_client
        self.slack_notifier = slack_notifier
        
        # Multi-symbol configuration
        self.symbols = config.get('SYMBOLS', ['SPY'])
        self.multi_config = config.get('multi_symbol', {})
        self.enabled = self.multi_config.get('enabled', False)
        self.max_concurrent_trades = self.multi_config.get('max_concurrent_trades', 1)
        self.allocation_method = self.multi_config.get('symbol_allocation', 'equal')
        self.priority_order = self.multi_config.get('priority_order', self.symbols)
        
        logger.info(f"[MULTI-SYMBOL] Initialized scanner for symbols: {self.symbols}")
        logger.info(f"[MULTI-SYMBOL] Multi-symbol enabled: {self.enabled}")
        logger.info(f"[MULTI-SYMBOL] Max concurrent trades: {self.max_concurrent_trades}")
    
    def scan_all_symbols(self) -> List[Dict]:
        """
        Scan all configured symbols for breakout opportunities.
        
        Returns:
            List of trade opportunities sorted by priority/confidence
        """
        if not self.enabled:
            # Fallback to single symbol mode
            default_symbol = self.config.get('SYMBOL', 'SPY')
            logger.info(f"[MULTI-SYMBOL] Multi-symbol disabled, scanning {default_symbol} only")
            return self._scan_single_symbol(default_symbol)
        
        logger.info(f"[MULTI-SYMBOL] Starting scan of {len(self.symbols)} symbols...")
        
        opportunities = []
        
        # Use ThreadPoolExecutor for concurrent symbol analysis
        with ThreadPoolExecutor(max_workers=len(self.symbols)) as executor:
            # Submit all symbol scans
            future_to_symbol = {
                executor.submit(self._scan_single_symbol, symbol): symbol 
                for symbol in self.symbols
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    symbol_opportunities = future.result()
                    if symbol_opportunities:
                        opportunities.extend(symbol_opportunities)
                        logger.info(f"[MULTI-SYMBOL] {symbol}: Found {len(symbol_opportunities)} opportunities")
                    else:
                        logger.info(f"[MULTI-SYMBOL] {symbol}: No opportunities found")
                except Exception as e:
                    logger.error(f"[MULTI-SYMBOL] Error scanning {symbol}: {e}")
        
        # Sort opportunities by priority and confidence
        sorted_opportunities = self._prioritize_opportunities(opportunities)
        
        if sorted_opportunities:
            logger.info(f"[MULTI-SYMBOL] Total opportunities found: {len(sorted_opportunities)}")
            self._send_multi_symbol_alert(sorted_opportunities)
        else:
            logger.info("[MULTI-SYMBOL] No trading opportunities found across all symbols")
        
        return sorted_opportunities
    
    def _scan_single_symbol(self, symbol: str) -> List[Dict]:
        """
        Scan a single symbol for breakout opportunities.
        
        Args:
            symbol: Stock symbol to scan
            
        Returns:
            List of opportunities for this symbol
        """
        try:
            logger.info(f"[MULTI-SYMBOL] Analyzing {symbol}...")
            
            # Fetch market data
            df = fetch_market_data(
                symbol=symbol,
                interval=self.config['TIMEFRAME'],
                period="5d"  # Use 5 days to get enough data for analysis
            )
            
            if df is None or df.empty:
                logger.warning(f"[MULTI-SYMBOL] No data available for {symbol}")
                return []
            
            # Calculate Heikin-Ashi candles
            ha_df = calculate_heikin_ashi(df)
            
            # Analyze breakout pattern
            lookback_bars = self.config.get('LOOKBACK_BARS', 20)
            breakout_analysis = analyze_breakout_pattern(ha_df, lookback_bars)
            
            # Always proceed to LLM analysis - let LLM decide based on all market conditions
            # The old has_breakout check was incorrect and blocking all trades
            
            # Get current price
            current_price = float(df['Close'].iloc[-1])
            
            # Prepare standardized market data for LLM
            market_data = self._prepare_market_data(symbol, df, ha_df, breakout_analysis)
            
            # Get LLM trade decision with retry logic
            trade_decision_result = self._robust_llm_decision(market_data, symbol)
            trade_decision = {
                'decision': trade_decision_result.decision,
                'confidence': trade_decision_result.confidence,
                'reason': trade_decision_result.reason or 'LLM analysis completed'
            }
            
            # Check if LLM recommends a trade
            if trade_decision['decision'] == 'NO_TRADE':
                logger.info(f"[MULTI-SYMBOL] {symbol}: LLM recommends NO_TRADE")
                
                # Log individual symbol decision for analytics
                self._log_symbol_decision(symbol, 'NO_TRADE', trade_decision.get('confidence', 0.0), 
                                        trade_decision.get('reason', 'LLM analysis completed'), current_price)
                return []
            
            # Check confidence threshold
            confidence = trade_decision.get('confidence', 0.0)
            min_confidence = self.config.get('MIN_CONFIDENCE', 0.35)
            
            if confidence < min_confidence:
                logger.info(f"[MULTI-SYMBOL] {symbol}: Confidence {confidence:.2f} below threshold {min_confidence}")
                
                # Log individual symbol decision for analytics
                self._log_symbol_decision(symbol, 'NO_TRADE', confidence, 
                                        f'Confidence {confidence:.2f} below threshold {min_confidence}', current_price)
                return []
            
            # Create opportunity record
            opportunity = {
                'symbol': symbol,
                'current_price': current_price,
                'decision': trade_decision['decision'],
                'confidence': confidence,
                'reason': trade_decision.get('reason', ''),
                'breakout_analysis': breakout_analysis,
                'timestamp': datetime.now(),
                'priority_score': self._calculate_priority_score(symbol, confidence, breakout_analysis)
            }
            
            logger.info(f"[MULTI-SYMBOL] {symbol}: Found opportunity - {trade_decision['decision']} (confidence: {confidence:.2f})")
            return [opportunity]
            
        except Exception as e:
            logger.error(f"[MULTI-SYMBOL] Error analyzing {symbol}: {e}")
            return []
    
    def _prepare_market_data(self, symbol: str, df: pd.DataFrame, ha_df: pd.DataFrame, breakout_analysis: Dict) -> Dict:
        """
        Ensure consistent market data structure for both single and multi-symbol modes.
        
        Args:
            symbol: Stock symbol
            df: Original price data
            ha_df: Heikin-Ashi data
            breakout_analysis: Technical analysis results
            
        Returns:
            Standardized market data dictionary
        """
        try:
            current_price = float(df['Close'].iloc[-1])
            
            # Use more context (10 vs 5 candles) for better LLM analysis
            ha_records = ha_df.to_dict('records')[-10:] if len(ha_df) > 10 else ha_df.to_dict('records')
            
            # Standardized structure that matches single-symbol mode
            market_data = {
                'symbol': symbol,  # Always include symbol for consistency
                'current_price': current_price,
                'breakout_analysis': breakout_analysis,
                'ha_df': ha_records,
                'timeframe': self.config.get('TIMEFRAME', '5m'),
                'lookback_bars': self.config.get('LOOKBACK_BARS', 20),
                'analysis_timestamp': datetime.now().isoformat(),  # Add timestamp for freshness
                
                # Additional fields for LLM validation compatibility
                'today_true_range_pct': breakout_analysis.get('today_true_range_pct', 0.0),
                'room_to_next_pivot': breakout_analysis.get('room_to_next_pivot', 0.0),
                'iv_5m': breakout_analysis.get('iv_5m', 30.0),
                'candle_body_pct': breakout_analysis.get('candle_body_pct', 0.0),
                'trend_direction': breakout_analysis.get('trend_direction', 'NEUTRAL'),
                'volume_confirmation': breakout_analysis.get('volume_confirmation', False),
                'support_levels': breakout_analysis.get('support_levels', []),
                'resistance_levels': breakout_analysis.get('resistance_levels', [])
            }
            
            logger.debug(f"[MULTI-SYMBOL] {symbol}: Prepared standardized market data with {len(ha_records)} candles")
            return market_data
            
        except Exception as e:
            logger.error(f"[MULTI-SYMBOL] Error preparing market data for {symbol}: {e}")
            # Return minimal safe structure
            return {
                'symbol': symbol,
                'current_price': 0.0,
                'breakout_analysis': {},
                'ha_df': [],
                'timeframe': '5m',
                'lookback_bars': 20,
                'analysis_timestamp': datetime.now().isoformat(),
                'today_true_range_pct': 0.0,
                'room_to_next_pivot': 0.0,
                'iv_5m': 30.0,
                'candle_body_pct': 0.0,
                'trend_direction': 'NEUTRAL',
                'volume_confirmation': False,
                'support_levels': [],
                'resistance_levels': []
            }
    
    def _robust_llm_decision(self, market_data: Dict, symbol: str, retries: int = 2):
        """
        Make LLM decision with retry logic and rate limiting protection.
        
        Args:
            market_data: Market analysis data
            symbol: Stock symbol being analyzed
            retries: Number of retry attempts
            
        Returns:
            TradeDecision object
        """
        last_error = None
        for attempt in range(retries + 1):
            try:
                # Add delay to prevent rate limiting (except first attempt)
                if attempt > 0:
                    delay = min(2 ** attempt, 5)  # Exponential backoff, max 5 seconds
                    logger.info(f"[MULTI-SYMBOL] {symbol}: Retry attempt {attempt}, waiting {delay}s...")
                    time.sleep(delay)
                
                # Create fresh LLM client instance for context isolation
                # This prevents previous symbol analysis from influencing current decision
                symbol_llm = LLMClient(self.config.get('MODEL', 'gpt-4o-mini'))
                
                # Get enhanced context for better LLM learning (if bankroll manager available)
                enhanced_context = None
                win_history = []
                if hasattr(self, 'bankroll_manager') and self.bankroll_manager:
                    try:
                        enhanced_context = self.bankroll_manager.get_enhanced_llm_context()
                        win_history = enhanced_context.get('win_history', [])
                    except Exception as e:
                        logger.warning(f"[MULTI-SYMBOL] Could not get enhanced context: {e}")
                        # Fallback to basic win history
                        win_history = self.bankroll_manager.get_win_history() if self.bankroll_manager else []
                
                result = symbol_llm.make_trade_decision(market_data, win_history, enhanced_context)
                
                # Add small delay after successful call to prevent rate limiting
                time.sleep(0.5)  # 500ms delay between LLM calls
                
                logger.debug(f"[MULTI-SYMBOL] {symbol}: LLM decision successful on attempt {attempt + 1}")
                return result
                
            except Exception as e:
                last_error = e
                error_msg = str(e).lower()
                
                # Check for rate limiting errors
                if any(term in error_msg for term in ['rate limit', 'quota', 'too many requests']):
                    if attempt < retries:
                        wait_time = min(10 * (attempt + 1), 30)  # Progressive wait for rate limits
                        logger.warning(f"[MULTI-SYMBOL] {symbol}: Rate limit hit, waiting {wait_time}s before retry")
                        time.sleep(wait_time)
                        continue
                
                # Log the error
                if attempt < retries:
                    logger.warning(f"[MULTI-SYMBOL] {symbol}: LLM attempt {attempt + 1} failed, retrying: {e}")
                else:
                    logger.error(f"[MULTI-SYMBOL] {symbol}: All LLM attempts failed: {e}")
        
        # All attempts failed, return safe default
        logger.error(f"[MULTI-SYMBOL] {symbol}: Returning NO_TRADE due to LLM failures")
        return TradeDecision(
            decision="NO_TRADE",
            confidence=0.0,
            reason=f"LLM error after {retries + 1} attempts: {str(last_error) if last_error else 'Unknown error'}",
            tokens_used=0
        )
    
    def _calculate_priority_score(self, symbol: str, confidence: float, breakout_analysis: Dict) -> float:
        """
        Calculate priority score for opportunity ranking.
        
        Args:
            symbol: Stock symbol
            confidence: LLM confidence score
            breakout_analysis: Technical analysis results
            
        Returns:
            Priority score (higher = better)
        """
        try:
            # Base score from confidence
            score = confidence * 100
            
            # Technical strength bonus
            candle_body_pct = breakout_analysis.get('candle_body_pct', 0.0)
            if isinstance(candle_body_pct, (int, float)):
                score += candle_body_pct * 10  # Up to 10 points for strong candles
            
            # Volume confirmation bonus
            if breakout_analysis.get('volume_confirmation', False):
                score += 5
            
            # Trend alignment bonus
            trend = breakout_analysis.get('trend_direction', 'NEUTRAL')
            if trend in ['BULLISH', 'BEARISH']:  # Clear trend direction
                score += 3
            
            # Room to move bonus
            room_to_move = breakout_analysis.get('room_to_next_pivot', 0.0)
            if isinstance(room_to_move, (int, float)) and room_to_move > 2.0:
                score += min(room_to_move, 10)  # Up to 10 points for room to move
            
            return max(score, 0.0)  # Ensure non-negative
            
        except Exception as e:
            logger.error(f"[MULTI-SYMBOL] Error calculating priority score for {symbol}: {e}")
            return confidence * 100  # Fallback to confidence-only scoring
    
    def _should_use_batch_analysis(self, opportunities_count: int) -> bool:
        """
        Determine if batch analysis should be used based on number of opportunities.
        
        Args:
            opportunities_count: Number of potential opportunities to analyze
            
        Returns:
            True if batch analysis should be used
        """
        # Use batch analysis for 2+ symbols to reduce API calls
        # But only if enabled in config (default: True for cost savings)
        batch_enabled = self.config.get('llm_batch_analysis', True)
        return batch_enabled and opportunities_count >= 2
    
    def _create_batch_analysis_prompt(self, symbols_data: List[Dict]) -> str:
        """
        Create a single LLM prompt to analyze multiple symbols simultaneously.
        
        Args:
            symbols_data: List of market data for each symbol
            
        Returns:
            Formatted batch analysis prompt
        """
        prompt = "Analyze the following symbols simultaneously and provide trading decisions for each:\n\n"
        
        for i, data in enumerate(symbols_data, 1):
            symbol = data.get('symbol', f'SYMBOL_{i}')
            current_price = data.get('current_price', 0)
            breakout_analysis = data.get('breakout_analysis', {})
            
            prompt += f"Symbol {i}: {symbol}\n"
            prompt += f"Current Price: ${current_price:.2f}\n"
            prompt += f"Breakout Analysis: {breakout_analysis}\n"
            prompt += f"Technical Data: {len(data.get('ha_df', []))} candles available\n\n"
        
        prompt += "For each symbol, provide a trading decision (CALL/PUT/NO_TRADE), confidence (0-1), and reasoning. "
        prompt += "Consider each symbol independently and rank them by opportunity quality."
        
        return prompt
    
    def _parse_batch_results(self, batch_result, symbols_data: List[Dict]) -> List[Dict]:
        """
        Parse batch LLM results and convert to individual symbol decisions.
        
        Args:
            batch_result: LLM batch analysis result
            symbols_data: Original symbol data for reference
            
        Returns:
            List of individual trade decisions
        """
        try:
            # For now, fall back to individual analysis if batch parsing fails
            # This is a safety mechanism - batch analysis is an optimization
            logger.warning("[MULTI-SYMBOL] Batch result parsing not fully implemented, using individual analysis")
            return self._individual_analysis(symbols_data)
            
        except Exception as e:
            logger.error(f"[MULTI-SYMBOL] Error parsing batch results: {e}")
            return self._individual_analysis(symbols_data)
    
    def _individual_analysis(self, symbols_data: List[Dict]) -> List[Dict]:
        """
        Fallback to individual symbol analysis.
        
        Args:
            symbols_data: List of market data for each symbol
            
        Returns:
            List of individual trade decisions
        """
        results = []
        for data in symbols_data:
            symbol = data.get('symbol', 'UNKNOWN')
            try:
                # Use the existing robust LLM decision method
                decision = self._robust_llm_decision(data, symbol)
                results.append({
                    'symbol': symbol,
                    'decision': decision.decision,
                    'confidence': decision.confidence,
                    'reason': decision.reason,
                    'tokens_used': decision.tokens_used
                })
            except Exception as e:
                logger.error(f"[MULTI-SYMBOL] Error in individual analysis for {symbol}: {e}")
                results.append({
                    'symbol': symbol,
                    'decision': 'NO_TRADE',
                    'confidence': 0.0,
                    'reason': f'Analysis error: {str(e)}',
                    'tokens_used': 0
                })
        return results
    
    def _prioritize_opportunities(self, opportunities: List[Dict]) -> List[Dict]:
        """
        Sort opportunities by priority score and apply allocation rules.
        
        Args:
            opportunities: List of trading opportunities
            
        Returns:
            Sorted and filtered opportunities
        """
        if not opportunities:
            return []
        
        # Ensure all opportunities have valid priority_score
        for opp in opportunities:
            if 'priority_score' not in opp or not isinstance(opp['priority_score'], (int, float)):
                logger.warning(f"[MULTI-SYMBOL] Missing or invalid priority_score for {opp.get('symbol', 'unknown')}, setting to 0")
                opp['priority_score'] = 0.0
        
        # Sort by priority score (highest first) with safe key access
        try:
            sorted_opps = sorted(opportunities, key=lambda x: float(x.get('priority_score', 0.0)), reverse=True)
        except (TypeError, ValueError) as e:
            logger.error(f"[MULTI-SYMBOL] Error sorting opportunities: {e}")
            # Fallback: sort by confidence if priority_score fails
            sorted_opps = sorted(opportunities, key=lambda x: float(x.get('confidence', 0.0)), reverse=True)
        
        # Apply max concurrent trades limit
        if len(sorted_opps) > self.max_concurrent_trades:
            logger.info(f"[MULTI-SYMBOL] Limiting to top {self.max_concurrent_trades} opportunities")
            sorted_opps = sorted_opps[:self.max_concurrent_trades]
        
        return sorted_opps
    
    def _send_multi_symbol_alert(self, opportunities: List[Dict]):
        """
        Send consolidated Slack alert for multiple opportunities.
        
        Args:
            opportunities: List of trading opportunities
        """
        if not self.slack_notifier:
            return
        
        try:
            if len(opportunities) == 1:
                # Single opportunity - use enhanced breakout alert with chart
                opp = opportunities[0]
                # For enhanced Slack integration, we need market data DataFrame
                # Create a simple DataFrame from the breakout analysis for chart generation
                market_data = self._create_market_data_for_chart(opp)
                
                self.slack_notifier.send_breakout_alert_with_chart(
                    symbol=opp['symbol'],
                    decision=opp['decision'],
                    analysis=opp['breakout_analysis'],
                    market_data=market_data,
                    confidence=opp['confidence']
                )
            else:
                # Multiple opportunities - send summary alert
                self._send_multi_opportunity_alert(opportunities)
                
        except Exception as e:
            logger.error(f"[MULTI-SYMBOL] Error sending Slack alert: {e}")
    
    def _send_multi_opportunity_alert(self, opportunities: List[Dict]):
        """
        Send Slack alert for multiple simultaneous opportunities.
        
        Args:
            opportunities: List of trading opportunities
        """
        try:
            # Create summary message
            summary_lines = [
                f"🎯 *MULTI-SYMBOL BREAKOUT ALERT*",
                f"Found {len(opportunities)} trading opportunities:",
                ""
            ]
            
            for i, opp in enumerate(opportunities, 1):
                summary_lines.extend([
                    f"*{i}. {opp['symbol']}* - {opp['decision']}",
                    f"   • Price: ${opp['current_price']:.2f}",
                    f"   • Confidence: {opp['confidence']:.1%}",
                    f"   • Priority: {opp['priority_score']:.1f}",
                    f"   • Reason: {opp['reason'][:100]}...",
                    ""
                ])
            
            summary_lines.extend([
                f"📊 *Trading Priority:*",
                f"Recommended order: {' → '.join([opp['symbol'] for opp in opportunities])}",
                "",
                f"⚠️ *Risk Management:*",
                f"Max concurrent trades: {self.max_concurrent_trades}",
                f"Review each opportunity carefully before trading."
            ])
            
            message = "\n".join(summary_lines)
            
            # Send via Slack webhook (fallback method)
            if hasattr(self.slack_notifier, 'send_message'):
                self.slack_notifier.send_message(message)
            else:
                logger.warning("[MULTI-SYMBOL] Slack notifier doesn't support multi-symbol alerts")
                
        except Exception as e:
            logger.error(f"[MULTI-SYMBOL] Error sending multi-opportunity alert: {e}")
    
    def get_symbol_performance(self) -> Dict[str, Dict]:
        """
        Get performance statistics for each symbol.
        
        Returns:
            Dictionary of performance metrics per symbol
        """
        # This would integrate with the analytics dashboard
        # to provide per-symbol performance tracking
        performance = {}
        
        for symbol in self.symbols:
            performance[symbol] = {
                'total_trades': 0,
                'win_rate': 0.0,
                'avg_pnl': 0.0,
                'last_trade': None
            }
        
        return performance
    
    def _create_market_data_for_chart(self, opportunity: Dict) -> pd.DataFrame:
        """
        Create a simple market data DataFrame for chart generation.
        
        Args:
            opportunity: Trading opportunity with breakout analysis
            
        Returns:
            DataFrame with basic market data for charting
        """
        try:
            # Create a minimal DataFrame with current price data
            # This is a simplified version for chart generation
            current_time = datetime.now()
            
            data = {
                'timestamp': [current_time],
                'Open': [opportunity['current_price']],
                'High': [opportunity['current_price']],
                'Low': [opportunity['current_price']],
                'Close': [opportunity['current_price']],
                'Volume': [1000]  # Placeholder volume
            }
            
            df = pd.DataFrame(data)
            df.set_index('timestamp', inplace=True)
            
            return df
            
        except Exception as e:
            logger.warning(f"[MULTI-SYMBOL] Failed to create market data for chart: {e}")
            # Return empty DataFrame as fallback
            return pd.DataFrame()
    
    def _log_symbol_decision(self, symbol: str, decision: str, confidence: float, reason: str, current_price: float):
        """
        Log individual symbol decision for analytics and debugging.
        
        Args:
            symbol: Stock symbol
            decision: Trade decision (CALL, PUT, NO_TRADE)
            confidence: LLM confidence score
            reason: Decision reasoning
            current_price: Current stock price
        """
        try:
            from .logging_utils import log_trade_decision
            
            trade_data = {
                'timestamp': datetime.now().isoformat(),
                'symbol': symbol,
                'decision': decision,
                'confidence': confidence,
                'reason': reason,
                'current_price': current_price,
                'strike': '',
                'direction': '',
                'quantity': '',
                'premium': '',
                'total_cost': '',
                'llm_tokens': 0
            }
            
            log_trade_decision(self.config.get('TRADE_LOG_FILE', 'logs/trade_log.csv'), trade_data)
            logger.debug(f"[MULTI-SYMBOL] Logged {symbol} decision: {decision} (confidence: {confidence:.2f})")
            
        except Exception as e:
            logger.error(f"[MULTI-SYMBOL] Error logging {symbol} decision: {e}")
