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
from .llm import LLMClient
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
            
            if not breakout_analysis.get('has_breakout', False):
                logger.info(f"[MULTI-SYMBOL] {symbol}: No breakout pattern detected")
                return []
            
            # Get current price
            current_price = float(df['Close'].iloc[-1])
            
            # Prepare market data for LLM
            market_data = {
                'symbol': symbol,
                'current_price': current_price,
                'breakout_analysis': breakout_analysis,
                'ha_df': ha_df.to_dict('records')[-5:] if len(ha_df) > 5 else ha_df.to_dict('records'),
                'timeframe': self.config.get('TIMEFRAME', '5m'),
                'lookback_bars': self.config.get('LOOKBACK_BARS', 20)
            }
            
            # Get LLM trade decision
            trade_decision_result = self.llm_client.make_trade_decision(market_data)
            trade_decision = {
                'decision': trade_decision_result.decision,
                'confidence': trade_decision_result.confidence,
                'reason': trade_decision_result.reason or 'LLM analysis completed'
            }
            
            # Check if LLM recommends a trade
            if trade_decision['decision'] == 'NO_TRADE':
                logger.info(f"[MULTI-SYMBOL] {symbol}: LLM recommends NO_TRADE")
                return []
            
            # Check confidence threshold
            confidence = trade_decision.get('confidence', 0.0)
            min_confidence = self.config.get('MIN_CONFIDENCE', 0.35)
            
            if confidence < min_confidence:
                logger.info(f"[MULTI-SYMBOL] {symbol}: Confidence {confidence:.2f} below threshold {min_confidence}")
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
    
    def _calculate_priority_score(self, symbol: str, confidence: float, breakout_analysis: Dict) -> float:
        """
        Calculate priority score for ranking opportunities.
        
        Args:
            symbol: Stock symbol
            confidence: LLM confidence score
            breakout_analysis: Technical analysis results
            
        Returns:
            Priority score (higher = better)
        """
        try:
            # Ensure confidence is a valid number
            if not isinstance(confidence, (int, float)):
                confidence = 0.0
            
            score = float(confidence) * 100  # Base score from confidence
            
            # Add symbol priority bonus
            if symbol in self.priority_order:
                priority_bonus = (len(self.priority_order) - self.priority_order.index(symbol)) * 5
                score += priority_bonus
            
            # Add technical strength bonus
            breakout_strength = breakout_analysis.get('breakout_strength', 0.0)
            if isinstance(breakout_strength, (int, float)):
                score += float(breakout_strength) * 10
            
            # Add volume confirmation bonus
            volume_ratio = breakout_analysis.get('volume_ratio', 1.0)
            if isinstance(volume_ratio, (int, float)) and float(volume_ratio) > 1.5:
                score += 5
            
            return float(score)
        except Exception as e:
            logger.warning(f"[MULTI-SYMBOL] Error calculating priority score for {symbol}: {e}")
            return 0.0
    
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
                # Single opportunity - use standard breakout alert
                opp = opportunities[0]
                self.slack_notifier.send_breakout_alert(
                    symbol=opp['symbol'],
                    decision=opp['decision'],
                    confidence=opp['confidence'],
                    current_price=opp['current_price'],
                    reason=opp['reason'],
                    breakout_analysis=opp['breakout_analysis']
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
