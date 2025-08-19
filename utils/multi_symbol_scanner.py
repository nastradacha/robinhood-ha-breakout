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
from typing import Dict, List
from datetime import datetime
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from .data import fetch_market_data, calculate_heikin_ashi, analyze_breakout_pattern
from .llm import LLMClient, TradeDecision
from .data_validation import check_trading_allowed

logger = logging.getLogger(__name__)


class MultiSymbolScanner:
    """
    Multi-symbol breakout scanner for diversified trading opportunities.
    """

    def __init__(self, config: Dict, llm_client, slack_notifier=None, env: str = "paper"):
        """
        Initialize multi-symbol scanner.

        Args:
            config: Trading configuration
            llm_client: LLM client for trade decisions
            slack_notifier: Slack notification client
            env: Alpaca environment - "paper" or "live" (default: "paper")
        """
        self.config = config
        self.llm_client = llm_client
        self.slack_notifier = slack_notifier
        self.env = env

        # Multi-symbol configuration
        self.symbols = config.get("SYMBOLS", ["SPY"])
        self.multi_config = config.get("multi_symbol", {})
        self.enabled = self.multi_config.get("enabled", False)
        self.max_concurrent_trades = self.multi_config.get("max_concurrent_trades", 1)
        self.allocation_method = self.multi_config.get("symbol_allocation", "equal")
        self.priority_order = self.multi_config.get("priority_order", self.symbols)

        logger.info(f"[MULTI-SYMBOL] Initialized scanner for symbols: {self.symbols}")
        logger.info(f"[MULTI-SYMBOL] Multi-symbol enabled: {self.enabled}")
        logger.info(
            f"[MULTI-SYMBOL] Max concurrent trades: {self.max_concurrent_trades}"
        )

    def scan_all_symbols(self) -> List[Dict]:
        """
        Scan all configured symbols for breakout opportunities.

        Returns:
            List of trade opportunities sorted by priority/confidence
        """
        if not self.enabled:
            # Fallback to single symbol mode
            default_symbol = self.config.get("SYMBOL", "SPY")
            logger.info(
                f"[MULTI-SYMBOL] Multi-symbol disabled, scanning {default_symbol} only"
            )
            return self._scan_single_symbol(default_symbol)

        logger.info(f"[MULTI-SYMBOL] Starting scan of {len(self.symbols)} symbols...")

        opportunities = []
        rejection_reasons = []  # Track why symbols were rejected

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
                        logger.info(
                            f"[MULTI-SYMBOL] {symbol}: Found {len(symbol_opportunities)} opportunities"
                        )
                    else:
                        # Try to get rejection reason from the scan result
                        rejection_reason = getattr(future, '_rejection_reason', 'No opportunities')
                        rejection_reasons.append(f"{symbol}: {rejection_reason}")
                        logger.info(f"[MULTI-SYMBOL] {symbol}: No opportunities found")
                except Exception as e:
                    rejection_reasons.append(f"{symbol}: Error - {str(e)}")
                    logger.error(f"[MULTI-SYMBOL] Error scanning {symbol}: {e}")

        # Sort opportunities by priority and confidence
        sorted_opportunities = self._prioritize_opportunities(opportunities)

        if sorted_opportunities:
            logger.info(
                f"[MULTI-SYMBOL] Total opportunities found: {len(sorted_opportunities)}"
            )
            self._send_multi_symbol_alert(sorted_opportunities)
        else:
            # Create summary of rejection reasons
            reason_summary = self._summarize_rejection_reasons(rejection_reasons)
            logger.info(
                f"[MULTI-SYMBOL] No trading opportunities found across all symbols. Reasons: {reason_summary}"
            )
            # Send Slack heartbeat with NO_TRADE reasons summary
            self._send_no_trade_heartbeat(rejection_reasons)

        return sorted_opportunities

    def _summarize_rejection_reasons(self, rejection_reasons: List[str]) -> str:
        """Summarize rejection reasons for logging and Slack alerts."""
        if not rejection_reasons:
            return "Unknown reasons"
        
        # Count rejection types
        reason_counts = {}
        for reason in rejection_reasons:
            if "True range too low" in reason:
                reason_counts["TR below threshold"] = reason_counts.get("TR below threshold", 0) + 1
            elif "401" in reason or "authorization" in reason.lower():
                reason_counts["Options auth error"] = reason_counts.get("Options auth error", 0) + 1
            elif "Error" in reason:
                reason_counts["API errors"] = reason_counts.get("API errors", 0) + 1
            else:
                reason_counts["Other"] = reason_counts.get("Other", 0) + 1
        
        # Format summary
        summary_parts = []
        for reason_type, count in reason_counts.items():
            summary_parts.append(f"{count} {reason_type}")
        
        return "; ".join(summary_parts)

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
                interval=self.config["TIMEFRAME"],
                period="5d",  # Use 5 days to get enough data for analysis
                env=self.env
            )

            if df is None or df.empty:
                logger.warning(f"[MULTI-SYMBOL] No data available for {symbol}")
                return []

            # Calculate Heikin-Ashi candles
            ha_df = calculate_heikin_ashi(df)

            # Analyze breakout pattern
            lookback_bars = self.config.get("LOOKBACK_BARS", 20)
            breakout_analysis = analyze_breakout_pattern(ha_df, lookback_bars)

            # Get current price
            current_price = float(df["Close"].iloc[-1])

            # Prepare standardized market data for LLM
            market_data = self._prepare_market_data(
                symbol, df, ha_df, breakout_analysis
            )

            # Data quality validation gate
            data_allowed, data_reason = check_trading_allowed(symbol)
            if not data_allowed:
                logger.warning(f"[MULTI-SYMBOL] {symbol}: Data validation blocked trade - {data_reason}")
                return []
            else:
                logger.info(f"[MULTI-SYMBOL] {symbol}: Data quality check passed - {data_reason}")

            # Pre-LLM hard gate: check for obvious NO_TRADE conditions
            proceed, gate_reason = self._pre_llm_hard_gate(market_data, self.config)
            if not proceed:
                logger.info(f"[MULTI-SYMBOL] {symbol}: Pre-LLM gate blocked trade - {gate_reason}")
                
                # Log decision for analytics with unified format
                formatted_reason = self._format_no_trade_reason(symbol, f"Pre-LLM gate: {gate_reason}")
                self._log_signal_event(
                    symbol,
                    "NO_TRADE",
                    0.0,
                    formatted_reason,
                    market_data.get("current_price", 0.0),
                )
                self._log_symbol_decision(
                    symbol,
                    "NO_TRADE",
                    0.0,
                    formatted_reason,
                    market_data.get("current_price", 0.0),
                )
                return []

            # Get LLM trade decision with retry logic
            trade_decision_result = self._robust_llm_decision(market_data, symbol)
            trade_decision = {
                "decision": trade_decision_result.decision,
                "confidence": trade_decision_result.confidence,
                "reason": trade_decision_result.reason or "LLM analysis completed",
            }

            # Check if LLM recommends a trade
            if trade_decision["decision"] == "NO_TRADE":
                logger.info(f"[MULTI-SYMBOL] {symbol}: LLM recommends NO_TRADE")

                # Log individual symbol decision for analytics with unified format
                raw_reason = trade_decision.get("reason", "LLM analysis completed")
                formatted_reason = self._format_no_trade_reason(symbol, raw_reason)
                self._log_signal_event(
                    symbol,
                    "NO_TRADE",
                    trade_decision.get("confidence", 0.0),
                    formatted_reason,
                    market_data.get("current_price", 0.0),
                )
                self._log_symbol_decision(
                    symbol,
                    "NO_TRADE",
                    trade_decision.get("confidence", 0.0),
                    formatted_reason,
                    market_data.get("current_price", 0.0),
                )
                return []

            # Check confidence threshold
            confidence = trade_decision.get("confidence", 0.0)
            min_confidence = self.config.get("MIN_CONFIDENCE", 0.35)

            if confidence < min_confidence:
                logger.info(
                    f"[MULTI-SYMBOL] {symbol}: Confidence {confidence:.2f} below threshold {min_confidence}"
                )

                # Log individual symbol decision for analytics with unified format
                raw_reason = f"Confidence {confidence:.2f} below threshold {min_confidence}"
                formatted_reason = self._format_no_trade_reason(symbol, raw_reason)
                self._log_signal_event(
                    symbol,
                    "NO_TRADE",
                    confidence,
                    formatted_reason,
                    market_data.get("current_price", 0.0),
                )
                self._log_symbol_decision(
                    symbol,
                    "NO_TRADE",
                    confidence,
                    formatted_reason,
                    market_data.get("current_price", 0.0),
                )
                return []

            # Apply consecutive-loss throttle (stricter requirements after losses)
            throttle_proceed, throttle_reason = self._apply_consecutive_loss_throttle(market_data, confidence)
            if not throttle_proceed:
                logger.info(f"[MULTI-SYMBOL] {symbol}: Consecutive loss throttle blocked - {throttle_reason}")
                
                # Log decision for analytics with unified format
                raw_reason = f"Consecutive loss throttle: {throttle_reason}"
                formatted_reason = self._format_no_trade_reason(symbol, raw_reason)
                self._log_signal_event(
                    symbol,
                    "NO_TRADE",
                    confidence,
                    formatted_reason,
                    market_data.get("current_price", 0.0),
                )
                self._log_symbol_decision(
                    symbol,
                    "NO_TRADE",
                    confidence,
                    formatted_reason,
                    market_data.get("current_price", 0.0),
                )
                return []

            # Apply rapid flip protection (prevent churning from opposite signals)
            flip_proceed, flip_reason = self._recent_signal_guard(symbol, trade_decision["decision"], market_data)
            if not flip_proceed:
                logger.info(f"[MULTI-SYMBOL] {symbol}: Rapid flip guard blocked - {flip_reason}")
                
                # Log decision for analytics
                self._log_signal_event(
                    symbol,
                    "NO_TRADE",
                    confidence,
                    f"Rapid flip guard: {flip_reason}",
                    market_data.get("current_price", 0.0),
                )
                self._log_symbol_decision(
                    symbol,
                    "NO_TRADE",
                    confidence,
                    f"Rapid flip guard: {flip_reason}",
                    market_data.get("current_price", 0.0),
                )
                return []

            # Map decision to strict option side
            try:
                option_side = self._map_decision_to_side(trade_decision["decision"])
            except ValueError as e:
                logger.error(f"[MULTI-SYMBOL] {symbol}: Invalid decision mapping - {e}")
                # Log as NO_TRADE and return empty
                formatted_reason = self._format_no_trade_reason(symbol, f"Invalid decision: {trade_decision['decision']}")
                self._log_symbol_decision(
                    symbol,
                    "NO_TRADE",
                    confidence,
                    formatted_reason,
                    current_price,
                )
                return []
            
            # Get expiry policy early (before execution layer)
            expiry_policy, expiry_date = self._get_expiry_policy_early()
            
            # Create opportunity record with strict option-side mapping and expiry policy
            opportunity = {
                "symbol": symbol,
                "current_price": current_price,
                "decision": trade_decision["decision"],
                "option_side": option_side,  # Strict CALL/PUT mapping
                "expiry_policy": expiry_policy,  # 0DTE or WEEKLY
                "expiry_date": expiry_date,  # YYYY-MM-DD format
                "confidence": confidence,
                "reason": trade_decision.get("reason", ""),
                "breakout_analysis": breakout_analysis,
                "timestamp": datetime.now(),
                "priority_score": self._calculate_priority_score(
                    symbol, confidence, breakout_analysis
                ),
            }

            logger.info(
                f"[MULTI-SYMBOL] {symbol}: Found opportunity - {trade_decision['decision']} (confidence: {confidence:.2f})"
            )
            
            # Log opportunity using deterministic serialization
            self._log_opportunity(opportunity)
            
            return [opportunity]

        except Exception as e:
            logger.error(f"[MULTI-SYMBOL] Error analyzing {symbol}: {e}")
            return []

    def _prepare_market_data(
        self,
        symbol: str,
        df: pd.DataFrame,
        ha_df: pd.DataFrame,
        breakout_analysis: Dict,
    ) -> Dict:
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
            current_price = float(df["Close"].iloc[-1])

            # Use more context (10 vs 5 candles) for better LLM analysis
            ha_records = (
                ha_df.to_dict("records")[-10:]
                if len(ha_df) > 10
                else ha_df.to_dict("records")
            )

            # Standardized structure that matches single-symbol mode
            market_data = {
                "symbol": symbol,  # Always include symbol for consistency
                "current_price": current_price,
                "breakout_analysis": breakout_analysis,
                "ha_df": ha_records,
                "timeframe": self.config.get("TIMEFRAME", "5m"),
                "lookback_bars": self.config.get("LOOKBACK_BARS", 20),
                "analysis_timestamp": datetime.now().isoformat(),  # Add timestamp for freshness
                # Additional fields for LLM validation compatibility
                "today_true_range_pct": breakout_analysis.get(
                    "true_range_pct", 0.0
                ),
                "room_to_next_pivot": breakout_analysis.get("room_to_next_pivot", 0.0),
                "iv_5m": breakout_analysis.get("iv_5m", 30.0),
                "candle_body_pct": breakout_analysis.get("candle_body_pct", 0.0),
                "trend_direction": breakout_analysis.get("trend_direction", "NEUTRAL"),
                "vwap_deviation_pct": breakout_analysis.get("vwap_deviation_pct", 0.0),
                "volume_confirmation": breakout_analysis.get(
                    "volume_confirmation", False
                ),
                "support_levels": breakout_analysis.get("support_levels", []),
                "resistance_levels": breakout_analysis.get("resistance_levels", []),
            }

            logger.debug(
                f"[MULTI-SYMBOL] {symbol}: Prepared standardized market data with {len(ha_records)} candles"
            )
            return market_data

        except Exception as e:
            logger.error(
                f"[MULTI-SYMBOL] Error preparing market data for {symbol}: {e}"
            )
            # Return minimal safe structure
            return {
                "symbol": symbol,
                "current_price": 0.0,
                "breakout_analysis": {},
                "ha_df": [],
                "timeframe": "5m",
                "lookback_bars": 20,
                "analysis_timestamp": datetime.now().isoformat(),
                "today_true_range_pct": 0.0,
                "room_to_next_pivot": 0.0,
                "iv_5m": 30.0,
                "candle_body_pct": 0.0,
                "trend_direction": "NEUTRAL",
                "volume_confirmation": False,
                "support_levels": [],
                "resistance_levels": [],
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
                    delay = min(2**attempt, 5)  # Exponential backoff, max 5 seconds
                    logger.info(
                        f"[MULTI-SYMBOL] {symbol}: Retry attempt {attempt}, waiting {delay}s..."
                    )
                    time.sleep(delay)

                # Create fresh LLM client instance for context isolation
                # This prevents previous symbol analysis from influencing current decision
                symbol_llm = LLMClient(self.config.get("MODEL", "gpt-4o-mini"))

                # Get enhanced context for better LLM learning (if bankroll manager available)
                enhanced_context = None
                win_history = []
                if hasattr(self, "bankroll_manager") and self.bankroll_manager:
                    try:
                        enhanced_context = (
                            self.bankroll_manager.get_enhanced_llm_context()
                        )
                        win_history = enhanced_context.get("win_history", [])
                    except Exception as e:
                        logger.warning(
                            f"[MULTI-SYMBOL] Could not get enhanced context: {e}"
                        )
                        # Fallback to basic win history
                        win_history = (
                            self.bankroll_manager.get_win_history()
                            if self.bankroll_manager
                            else []
                        )

                # Check if ensemble is enabled (v0.6.0)
                from utils.llm import load_config
                config = load_config()
                if config.get("ENSEMBLE_ENABLED", True):
                    logger.debug(f"[MULTI-SYMBOL] {symbol}: Using ensemble decision making")
                    from utils.ensemble_llm import choose_trade
                    from utils.llm import TradeDecision
                    ensemble_result = choose_trade(market_data)
                    # Convert ensemble result to TradeDecision format
                    result = TradeDecision(
                        decision=ensemble_result["decision"],
                        confidence=ensemble_result["confidence"],
                        reason=ensemble_result["reason"]
                    )
                else:
                    logger.debug(f"[MULTI-SYMBOL] {symbol}: Using single-model decision making")
                    result = symbol_llm.make_trade_decision(
                        market_data, win_history, enhanced_context
                    )

                # Add small delay after successful call to prevent rate limiting
                time.sleep(0.5)  # 500ms delay between LLM calls

                logger.debug(
                    f"[MULTI-SYMBOL] {symbol}: LLM decision successful on attempt {attempt + 1}"
                )
                return result

            except Exception as e:
                last_error = e
                error_msg = str(e).lower()

                # Check for rate limiting errors
                if any(
                    term in error_msg
                    for term in ["rate limit", "quota", "too many requests"]
                ):
                    if attempt < retries:
                        wait_time = min(
                            10 * (attempt + 1), 30
                        )  # Progressive wait for rate limits
                        logger.warning(
                            f"[MULTI-SYMBOL] {symbol}: Rate limit hit, waiting {wait_time}s before retry"
                        )
                        time.sleep(wait_time)
                        continue

                # Log the error
                if attempt < retries:
                    logger.warning(
                        f"[MULTI-SYMBOL] {symbol}: LLM attempt {attempt + 1} failed, retrying: {e}"
                    )
                else:
                    logger.error(
                        f"[MULTI-SYMBOL] {symbol}: All LLM attempts failed: {e}"
                    )

        # All attempts failed, return safe default
        logger.error(f"[MULTI-SYMBOL] {symbol}: Returning NO_TRADE due to LLM failures")
        
        # Format error reason for transparency (as requested)
        error_detail = str(last_error) if last_error else 'Unknown error'
        transparent_reason = f"LLM_ERROR: {error_detail} (after {retries + 1} attempts)"
        
        return TradeDecision(
            decision="NO_TRADE",
            confidence=0.0,
            reason=transparent_reason,
            tokens_used=0,
        )

    def _calculate_priority_score(
        self, symbol: str, confidence: float, breakout_analysis: Dict
    ) -> float:
        """
        Calculate deterministic priority score for opportunity ranking.
        
        Uses a weighted formula to blend multiple technical factors into a normalized 0-1 score:
        
        score = clamp(
           0.50 * confidence                           # 50% - LLM confidence (primary factor)
         + 0.20 * norm_abs(vwap_deviation_pct, 1.0)   # 20% - Price momentum strength
         + 0.15 * norm(room_to_next_pivot, 1.0)       # 15% - Room to move
         + 0.10 * (trend in STRONG_* ? 1 : 0)         # 10% - Strong trend confirmation
         + 0.05 * (volume_confirmation ? 1 : 0), 0, 1) # 5% - Volume support
        
        This ensures deterministic ranking where same inputs always produce same output.

        Args:
            symbol: Stock symbol
            confidence: LLM confidence score (0-1)
            breakout_analysis: Technical analysis results

        Returns:
            Priority score (0-1, higher = better)
        """
        try:
            # Extract technical factors with safe defaults
            vwap_deviation_pct = breakout_analysis.get("vwap_deviation_pct", 0.0)
            room_to_next_pivot = breakout_analysis.get("room_to_next_pivot", 0.0)
            trend_direction = breakout_analysis.get("trend_direction", "NEUTRAL")
            volume_confirmation = breakout_analysis.get("volume_confirmation", False)
            
            # Normalize and weight each component
            confidence_component = 0.50 * max(0.0, min(1.0, confidence))  # Clamp confidence to 0-1
            
            # VWAP deviation: normalize absolute value, cap at 1.0%
            vwap_component = 0.20 * min(1.0, abs(vwap_deviation_pct))
            
            # Room to pivot: normalize, cap at 1.0 (100% room)
            room_component = 0.15 * min(1.0, max(0.0, room_to_next_pivot))
            
            # Strong trend: binary 0 or 1
            strong_trend = 1.0 if trend_direction in ["STRONG_BULLISH", "STRONG_BEARISH"] else 0.0
            trend_component = 0.10 * strong_trend
            
            # Volume confirmation: binary 0 or 1
            volume_component = 0.05 * (1.0 if volume_confirmation else 0.0)
            
            # Calculate final score
            score = confidence_component + vwap_component + room_component + trend_component + volume_component
            
            # Ensure score is in [0, 1] range
            final_score = max(0.0, min(1.0, score))
            
            # Log detailed breakdown for debugging
            logger.debug(
                f"[PRIORITY] {symbol}: conf={confidence:.3f}({confidence_component:.3f}) "
                f"vwap={vwap_deviation_pct:.3f}({vwap_component:.3f}) "
                f"room={room_to_next_pivot:.3f}({room_component:.3f}) "
                f"trend={trend_direction}({trend_component:.3f}) "
                f"vol={volume_confirmation}({volume_component:.3f}) "
                f"→ {final_score:.3f}"
            )
            
            return final_score

        except Exception as e:
            logger.error(
                f"[MULTI-SYMBOL] Error calculating priority score for {symbol}: {e}"
            )
            # Fallback to confidence-only scoring (normalized)
            return max(0.0, min(1.0, confidence))

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
        batch_enabled = self.config.get("llm_batch_analysis", True)
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
            symbol = data.get("symbol", f"SYMBOL_{i}")
            current_price = data.get("current_price", 0)
            breakout_analysis = data.get("breakout_analysis", {})

            prompt += f"Symbol {i}: {symbol}\n"
            prompt += f"Current Price: ${current_price:.2f}\n"
            prompt += f"Breakout Analysis: {breakout_analysis}\n"
            prompt += (
                f"Technical Data: {len(data.get('ha_df', []))} candles available\n\n"
            )

        prompt += "For each symbol, provide a trading decision (CALL/PUT/NO_TRADE), confidence (0-1), and reasoning. "
        prompt += (
            "Consider each symbol independently and rank them by opportunity quality."
        )

        return prompt

    def _pre_llm_hard_gate(self, market_data: Dict, config: Dict) -> tuple[bool, str]:
        """
        Pre-LLM hard gate: enforce hard rules before calling LLM.
        
        Blocks known bad contexts: market closed, after time cutoff, 
        too-low volatility range, VIX spikes, or user-configured "no trade" windows.
        
        Args:
            market_data: Market data dictionary
            config: Trading configuration
            
        Returns:
            tuple[bool, str]: (proceed, reason) - proceed=False blocks LLM call
        """
        from datetime import datetime, time as dt_time
        import pytz
        
        try:
            # Get current time in ET (market timezone)
            et_tz = pytz.timezone('US/Eastern')
            current_et = datetime.now(et_tz)
            current_time = current_et.time()
            
            # 1. Check VIX spike detection (US-FA-001)
            try:
                from .vix_monitor import check_vix_spike
                is_spike, vix_value, vix_reason = check_vix_spike()
                if is_spike:
                    return False, f"VIX spike blocking trades: {vix_reason}"
                logger.debug(f"[VIX-GATE] {vix_reason}")
            except Exception as e:
                logger.warning(f"[VIX-GATE] VIX check failed: {e}, allowing trades (fail-safe)")
            
            # 2. Check market hours validation (US-FA-003)
            try:
                from .market_calendar import validate_trading_time
                can_trade, market_reason = validate_trading_time(current_et)
                if not can_trade:
                    return False, f"Market hours validation: {market_reason}"
                logger.debug(f"[MARKET-GATE] {market_reason}")
            except Exception as e:
                logger.warning(f"[MARKET-GATE] Market hours check failed: {e}, falling back to basic validation")
                
                # Fallback to basic market hours validation
                # Check if after entry cutoff time (15:15 ET)
                entry_cutoff = dt_time(15, 15)  # 3:15 PM ET
                if current_time >= entry_cutoff:
                    return False, f"After entry cutoff time (current: {current_time.strftime('%H:%M')}, cutoff: 15:15 ET)"
                
                # Check if market is closed (basic weekday check)
                if current_et.weekday() >= 5:  # Saturday=5, Sunday=6
                    return False, f"Market closed (weekend: {current_et.strftime('%A')})"
                
                # Check if before market open (9:30 AM ET)
                market_open = dt_time(9, 30)
                if current_time < market_open:
                    return False, f"Before market open (current: {current_time.strftime('%H:%M')}, open: 09:30 ET)"
            
            # 3. Check earnings calendar blocking (US-FA-002)
            symbol = market_data.get("symbol", "UNKNOWN")
            try:
                from .earnings_calendar import validate_earnings_blocking
                can_trade, earnings_reason = validate_earnings_blocking(symbol, current_et.astimezone(pytz.UTC))
                if not can_trade:
                    return False, f"Earnings blocking: {earnings_reason}"
                logger.debug(f"[EARNINGS-GATE] {symbol}: {earnings_reason}")
            except Exception as e:
                logger.warning(f"[EARNINGS-GATE] Earnings check failed for {symbol}: {e}, allowing trades (fail-safe)")
            
            # 4. Check daily drawdown circuit breaker (US-FA-004)
            try:
                from .drawdown_circuit_breaker import check_circuit_breaker
                should_block, circuit_reason = check_circuit_breaker(config)
                if should_block:
                    return False, f"Circuit breaker: {circuit_reason}"
                logger.debug(f"[CIRCUIT-BREAKER-GATE] {symbol}: {circuit_reason}")
            except Exception as e:
                logger.warning(f"[CIRCUIT-BREAKER-GATE] Circuit breaker check failed for {symbol}: {e}, allowing trades (fail-safe)")
            
            # 5. Check weekly drawdown protection (US-FA-005)
            try:
                from .weekly_drawdown_circuit_breaker import get_weekly_circuit_breaker
                weekly_cb = get_weekly_circuit_breaker(config)
                should_disable, weekly_reason = weekly_cb.check_weekly_drawdown_limit()
                if should_disable:
                    return False, f"Weekly protection: {weekly_reason}"
                logger.debug(f"[WEEKLY-PROTECTION-GATE] {symbol}: {weekly_reason}")
            except Exception as e:
                logger.warning(f"[WEEKLY-PROTECTION-GATE] Weekly protection check failed for {symbol}: {e}, allowing trades (fail-safe)")
            
            # 6. Check minimum true range percentage (per-symbol thresholds)
            symbol = market_data.get("symbol", "UNKNOWN")
            by_symbol = config.get("MIN_TR_RANGE_PCT_BY_SYMBOL", {})
            min_tr_range_pct = float(by_symbol.get(symbol, config.get("MIN_TR_RANGE_PCT", 1.0)))
            
            # Add sanity check to prevent "20%" accidents (treat >5 as % not fraction)
            raw_threshold = min_tr_range_pct
            if raw_threshold > 5:
                min_tr_range_pct = raw_threshold / 100.0
            min_tr_range_pct = min(max(min_tr_range_pct, 0.0), 5.0)
            
            today_tr_pct = market_data.get("today_true_range_pct", 0.0)
            
            # Debug logging for true range values with higher precision
            logger.info(f"[TR-DEBUG] {symbol}: TR={today_tr_pct:.4f}% (threshold: {min_tr_range_pct:.4f}%) [raw: {today_tr_pct:.6f} vs {min_tr_range_pct:.6f}]")
            
            if today_tr_pct < min_tr_range_pct:
                return False, f"True range too low ({today_tr_pct:.4f}% < {min_tr_range_pct:.4f}% minimum)"
            
            # 5. Check user-configured trade window (optional)
            trade_window = config.get("TRADE_WINDOW")
            if trade_window and isinstance(trade_window, list) and len(trade_window) == 2:
                try:
                    start_time = dt_time.fromisoformat(trade_window[0])
                    end_time = dt_time.fromisoformat(trade_window[1])
                    
                    if not (start_time <= current_time <= end_time):
                        return False, f"Outside trade window ({trade_window[0]}-{trade_window[1]}, current: {current_time.strftime('%H:%M')})"
                except (ValueError, TypeError):
                    logger.warning(f"Invalid TRADE_WINDOW format: {trade_window}")
            
            # All checks passed
            return True, "All pre-LLM checks passed"
            
        except Exception as e:
            logger.warning(f"Pre-LLM gate error: {e}")
            # On error, allow LLM call (fail-open for robustness)
            return True, f"Gate check error (allowing trade): {e}"

    def _apply_consecutive_loss_throttle(self, market_data: Dict, decision_conf: float) -> tuple[bool, str]:
        """
        Apply consecutive-loss throttle: stricter requirements after losses.
        
        If last two trades were losses, require:
        - Higher candle body percentage (20% vs normal 10%)
        - Higher confidence threshold (+5% boost)
        
        Args:
            market_data: Market data dictionary with candle_body_pct
            decision_conf: LLM decision confidence
            
        Returns:
            tuple[bool, str]: (proceed, reason)
        """
        try:
            # Get recent trade outcomes from bankroll
            from .bankroll import BankrollManager
            
            # Use same broker/env as scanner
            bankroll = BankrollManager(
                start_capital=1000.0,  # Dummy value, we're just reading history
                broker=getattr(self, 'broker', 'robinhood'),
                env=getattr(self, 'env', 'paper')
            )
            
            recent_outcomes = bankroll.get_recent_outcomes(n=2)
            
            # If insufficient history, allow trade (fail-open)
            if len(recent_outcomes) < 2:
                return True, "Insufficient trade history for throttle"
            
            # Check if last two trades were losses
            last_two_losses = all(outcome == False for outcome in recent_outcomes)
            
            if last_two_losses:
                # Apply stricter requirements after consecutive losses
                candle_body_pct = market_data.get("candle_body_pct", 0.0)
                min_confidence = self.config.get("MIN_CONFIDENCE", 0.65)
                
                # Require higher candle body (20% vs normal 5-10%)
                required_candle_body = 0.20  # 20%
                if candle_body_pct < required_candle_body:
                    return False, f"After 2 losses: candle body {candle_body_pct:.1%} < {required_candle_body:.1%} required"
                
                # Require higher confidence (+5% boost)
                required_confidence = min_confidence + 0.05  # +5%
                if decision_conf < required_confidence:
                    return False, f"After 2 losses: confidence {decision_conf:.1%} < {required_confidence:.1%} required"
                
                return True, f"Consecutive loss throttle passed (candle: {candle_body_pct:.1%}, conf: {decision_conf:.1%})"
            
            else:
                # Normal requirements after a win
                candle_body_pct = market_data.get("candle_body_pct", 0.0)
                min_candle_body = self.config.get("MIN_CANDLE_BODY_PCT", 0.05)
                
                # Allow relaxed candle body requirement (10% vs config 5%)
                relaxed_candle_body = max(min_candle_body, 0.10)  # At least 10%
                if candle_body_pct < relaxed_candle_body:
                    return False, f"Normal mode: candle body {candle_body_pct:.1%} < {relaxed_candle_body:.1%} required"
                
                return True, f"Normal throttle passed (recent win, candle: {candle_body_pct:.1%})"
                
        except Exception as e:
            logger.warning(f"Consecutive loss throttle error: {e}")
            # Fail-open: allow trade on errors
            return True, f"Throttle check error (allowing trade): {e}"

    def _recent_signal_guard(self, symbol: str, new_decision: str, market_data: Dict, window_min: int = 5) -> tuple[bool, str]:
        """
        Rapid flip protection: suppress opposite trade signals within X minutes.
        
        Prevents churning by blocking opposite signals unless strong reversal detected.
        
        Args:
            symbol: Stock symbol
            new_decision: New trade decision (CALL, PUT, NO_TRADE)
            market_data: Market data with trend and deviation info
            window_min: Cooldown window in minutes (default: 5)
            
        Returns:
            tuple[bool, str]: (proceed, reason)
        """
        try:
            import json
            from pathlib import Path
            from datetime import datetime, timedelta
            
            # Skip guard for NO_TRADE decisions
            if new_decision == "NO_TRADE":
                return True, "NO_TRADE decisions not subject to rapid flip guard"
            
            # Load recent signal log
            cache_dir = Path(".cache")
            log_file = cache_dir / f"signal_log_{symbol}.json"
            
            if not log_file.exists():
                return True, "No signal history for rapid flip check"
            
            try:
                with open(log_file, 'r') as f:
                    signal_log = json.load(f)
            except Exception as e:
                logger.warning(f"Error reading signal log for {symbol}: {e}")
                return True, "Signal log read error (allowing trade)"
            
            if not signal_log:
                return True, "Empty signal history"
            
            # Find most recent trade signal (CALL or PUT, not NO_TRADE)
            recent_trade_signal = None
            current_time = datetime.now()
            
            for entry in reversed(signal_log):
                if entry.get("decision") in ["CALL", "PUT"]:
                    try:
                        entry_time = datetime.fromisoformat(entry["timestamp"])
                        time_diff = current_time - entry_time
                        
                        # Check if within cooldown window
                        if time_diff <= timedelta(minutes=window_min):
                            recent_trade_signal = entry
                            break
                        else:
                            # Outside window, no need to check further
                            break
                    except Exception as e:
                        logger.warning(f"Error parsing timestamp in signal log: {e}")
                        continue
            
            if not recent_trade_signal:
                return True, f"No recent trade signals within {window_min} minutes"
            
            # Check if new decision is opposite to recent signal
            recent_decision = recent_trade_signal["decision"]
            is_opposite = (recent_decision == "CALL" and new_decision == "PUT") or \
                         (recent_decision == "PUT" and new_decision == "CALL")
            
            if not is_opposite:
                return True, f"Same direction as recent {recent_decision} signal"
            
            # Opposite signal detected - check for strong reversal criteria
            trend_direction = market_data.get("trend_direction", "NEUTRAL")
            vwap_deviation_pct = market_data.get("vwap_deviation_pct", 0.0)
            
            # Define strong reversal criteria
            strong_trend = trend_direction in ["STRONG_BULLISH", "STRONG_BEARISH"]
            strong_deviation = abs(vwap_deviation_pct) > 0.2  # > 0.2% VWAP deviation
            
            if strong_trend and strong_deviation:
                return True, f"Strong reversal detected: {trend_direction}, VWAP dev: {vwap_deviation_pct:.1%}"
            
            # Block weak opposite signal
            time_since = current_time - datetime.fromisoformat(recent_trade_signal["timestamp"])
            minutes_ago = int(time_since.total_seconds() / 60)
            
            return False, f"Rapid flip blocked: {recent_decision} {minutes_ago}m ago, weak {new_decision} signal (trend: {trend_direction}, VWAP: {vwap_deviation_pct:.1%})"
            
        except Exception as e:
            logger.warning(f"Rapid flip guard error for {symbol}: {e}")
            # Fail-open: allow trade on errors
            return True, f"Rapid flip guard error (allowing trade): {e}"

    def _parse_batch_results(
        self, batch_result, symbols_data: List[Dict]
    ) -> List[Dict]:
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
            logger.warning(
                "[MULTI-SYMBOL] Batch result parsing not fully implemented, using individual analysis"
            )
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
            symbol = data.get("symbol", "UNKNOWN")
            try:
                # Use the existing robust LLM decision method
                decision = self._robust_llm_decision(data, symbol)
                results.append(
                    {
                        "symbol": symbol,
                        "decision": decision.decision,
                        "confidence": decision.confidence,
                        "reason": decision.reason,
                        "tokens_used": decision.tokens_used,
                    }
                )
            except Exception as e:
                logger.error(
                    f"[MULTI-SYMBOL] Error in individual analysis for {symbol}: {e}"
                )
                results.append(
                    {
                        "symbol": symbol,
                        "decision": "NO_TRADE",
                        "confidence": 0.0,
                        "reason": f"Analysis error: {str(e)}",
                        "tokens_used": 0,
                    }
                )
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
            if "priority_score" not in opp or not isinstance(
                opp["priority_score"], (int, float)
            ):
                logger.warning(
                    f"[MULTI-SYMBOL] Missing or invalid priority_score for {opp.get('symbol', 'unknown')}, setting to 0"
                )
                opp["priority_score"] = 0.0

        # Sort by priority score (highest first) with safe key access
        try:
            sorted_opps = sorted(
                opportunities,
                key=lambda x: float(x.get("priority_score", 0.0)),
                reverse=True,
            )
        except (TypeError, ValueError) as e:
            logger.error(f"[MULTI-SYMBOL] Error sorting opportunities: {e}")
            # Fallback: sort by confidence if priority_score fails
            sorted_opps = sorted(
                opportunities,
                key=lambda x: float(x.get("confidence", 0.0)),
                reverse=True,
            )

        # Apply max concurrent trades limit
        if len(sorted_opps) > self.max_concurrent_trades:
            logger.info(
                f"[MULTI-SYMBOL] Limiting to top {self.max_concurrent_trades} opportunities"
            )
            sorted_opps = sorted_opps[: self.max_concurrent_trades]

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
                    symbol=opp["symbol"],
                    decision=opp["decision"],
                    analysis=opp["breakout_analysis"],
                    market_data=market_data,
                    confidence=opp["confidence"],
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
                "🎯 *MULTI-SYMBOL BREAKOUT ALERT*",
                f"Found {len(opportunities)} trading opportunities:",
                "",
            ]

            for i, opp in enumerate(opportunities, 1):
                summary_lines.extend(
                    [
                        f"*{i}. {opp['symbol']}* - {opp['decision']}",
                        f"   • Price: ${opp['current_price']:.2f}",
                        f"   • Confidence: {opp['confidence']:.1%}",
                        f"   • Priority: {opp['priority_score']:.1f}",
                        f"   • Reason: {opp['reason'][:100]}...",
                        "",
                    ]
                )

            summary_lines.extend(
                [
                    "📊 *Trading Priority:*",
                    f"Recommended order: {' → '.join([opp['symbol'] for opp in opportunities])}",
                    "",
                    "⚠️ *Risk Management:*",
                    f"Max concurrent trades: {self.max_concurrent_trades}",
                    "Review each opportunity carefully before trading.",
                ]
            )

            message = "\n".join(summary_lines)

            # Send via Slack webhook (fallback method)
            if hasattr(self.slack_notifier, "send_message"):
                self.slack_notifier.send_message(message)
            else:
                logger.warning(
                    "[MULTI-SYMBOL] Slack notifier doesn't support multi-symbol alerts"
                )

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
                "total_trades": 0,
                "win_rate": 0.0,
                "avg_pnl": 0.0,
                "last_trade": None,
            }

        return performance

    def _map_decision_to_side(self, decision: str) -> str:
        """
        Map LLM trade decision to strict option side.
        
        Args:
            decision: LLM decision string
            
        Returns:
            Strict option side: "CALL" or "PUT"
            
        Raises:
            ValueError: If decision cannot be mapped to valid option side
        """
        decision_upper = decision.upper().strip()
        
        # Direct mapping
        if decision_upper == "CALL" or decision_upper == "BUY_CALL":
            return "CALL"
        elif decision_upper == "PUT" or decision_upper == "BUY_PUT":
            return "PUT"
        
        # Fuzzy matching for robustness
        if "CALL" in decision_upper:
            return "CALL"
        elif "PUT" in decision_upper:
            return "PUT"
        
        # Invalid decision
        raise ValueError(f"Cannot map decision '{decision}' to valid option side (CALL/PUT)")

    def _get_expiry_policy_early(self) -> tuple[str, str]:
        """
        Get expiry policy early in the scanning process.
        
        Returns:
            Tuple of (policy, expiry_date) where policy is '0DTE' or 'WEEKLY'
        """
        try:
            # Try to use Alpaca client if available
            if hasattr(self, 'alpaca_trader') and self.alpaca_trader:
                return self.alpaca_trader.get_expiry_policy()
            
            # Fallback: implement same logic as AlpacaOptionsTrader
            from datetime import datetime, timedelta
            import pytz
            
            # Get current ET time
            et_tz = pytz.timezone('US/Eastern')
            now_et = datetime.now(et_tz)
            hour = now_et.hour
            minute = now_et.minute
            
            # Use 0DTE between 10:00-15:15 ET
            if 10 <= hour < 15 or (hour == 15 and minute <= 15):
                # Today's date for 0DTE
                today = now_et.date()
                return "0DTE", today.strftime("%Y-%m-%d")
            else:
                # Find nearest weekly Friday
                today = now_et.date()
                days_until_friday = (4 - today.weekday()) % 7
                if days_until_friday == 0:  # Today is Friday
                    days_until_friday = 7  # Next Friday
                
                next_friday = today + timedelta(days=days_until_friday)
                return "WEEKLY", next_friday.strftime("%Y-%m-%d")
                
        except Exception as e:
            logger.warning(f"Error determining expiry policy early: {e}")
            # Fallback to weekly
            from datetime import datetime, timedelta
            today = datetime.now().date()
            days_until_friday = (4 - today.weekday()) % 7
            if days_until_friday == 0:
                days_until_friday = 7
            next_friday = today + timedelta(days=days_until_friday)
            return "WEEKLY", next_friday.strftime("%Y-%m-%d")

    def _serialize_opportunity(self, opportunity: Dict) -> Dict:
        """
        Create deterministic serialization of opportunity record.
        
        Ensures consistent field order and format for logging, CSV export,
        and audit trails. Only includes fields relevant for serialization.
        
        Args:
            opportunity: Raw opportunity dictionary
            
        Returns:
            Serialized opportunity with fixed field order
        """
        # Fixed field order for deterministic serialization
        serialized = {
            "timestamp": opportunity.get("timestamp", datetime.now()).isoformat(),
            "symbol": opportunity.get("symbol", ""),
            "decision": opportunity.get("decision", ""),
            "confidence": float(opportunity.get("confidence", 0.0)),
            "current_price": float(opportunity.get("current_price", 0.0)),
            "option_side": opportunity.get("option_side", ""),
            "expiry_policy": opportunity.get("expiry_policy", ""),
            "expiry_date": opportunity.get("expiry_date", ""),
            "reason": opportunity.get("reason", ""),
            "priority_score": float(opportunity.get("priority_score", 0.0)),
        }
        
        return serialized

    def _log_opportunity(self, opportunity: Dict):
        """
        Log opportunity using deterministic serialization for audits and analytics.
        
        Args:
            opportunity: Raw opportunity dictionary
        """
        try:
            # Serialize opportunity with fixed field order
            serialized = self._serialize_opportunity(opportunity)
            
            # Log structured opportunity for analytics
            logger.info(f"[OPPORTUNITY] {serialized}")
            
            # Optional: Write to CSV for audit trail (if needed)
            # This could be extended to write to trade_history CSV
            
        except Exception as e:
            logger.warning(f"Error logging opportunity: {e}")
            # Fail silently - logging should not break trading

    def _format_no_trade_reason(self, symbol: str, reason: str) -> str:
        """
        Format NO_TRADE reason for unified machine-readable format.
        
        Args:
            symbol: Stock symbol
            reason: Raw reason string
            
        Returns:
            Formatted reason string with machine-readable prefix
        """
        # Extract machine-readable reason code
        if "Pre-LLM gate:" in reason:
            if "market closed" in reason.lower():
                return f"MARKET_CLOSED: {reason}"
            elif "time cutoff" in reason.lower():
                return f"TIME_CUTOFF: {reason}"
            elif "volatility" in reason.lower():
                return f"LOW_VOLATILITY: {reason}"
            elif "trade window" in reason.lower():
                return f"TRADE_WINDOW: {reason}"
            else:
                return f"PRE_LLM_GATE: {reason}"
        elif "LLM_ERROR:" in reason:
            return reason  # Already formatted
        elif "Confidence" in reason and "below threshold" in reason:
            return f"LOW_CONF: {reason}"
        elif "Consecutive loss throttle:" in reason:
            return f"LOSS_THROTTLE: {reason}"
        elif "Rapid flip guard:" in reason:
            return f"FLIP_GUARD: {reason}"
        else:
            return f"OTHER: {reason}"

    def _log_signal_event(self, symbol: str, decision: str, confidence: float, reason: str, price: float):
        """
        Log trading signal event for rapid flip protection and analytics.
        
        Args:
            symbol: Stock symbol
            decision: Trade decision (CALL, PUT, NO_TRADE)
            confidence: LLM confidence score
            reason: Decision reason
            price: Current stock price
        """
        try:
            import json
            import os
            from pathlib import Path
            
            # Create .cache directory if it doesn't exist
            cache_dir = Path(".cache")
            cache_dir.mkdir(exist_ok=True)
            
            # Signal log file per symbol
            log_file = cache_dir / f"signal_log_{symbol}.json"
            
            # Load existing log
            signal_log = []
            if log_file.exists():
                try:
                    with open(log_file, 'r') as f:
                        signal_log = json.load(f)
                except Exception as e:
                    logger.warning(f"Error loading signal log for {symbol}: {e}")
                    signal_log = []
            
            # Add new decision
            signal_entry = {
                "timestamp": datetime.now().isoformat(),
                "decision": decision,
                "confidence": confidence,
                "reason": reason,
                "price": price,
                "scanner_env": getattr(self, 'env', 'unknown')
            }
            
            signal_log.append(signal_entry)
            
            # Keep only last 50 entries for memory efficiency
            if len(signal_log) > 50:
                signal_log = signal_log[-50:]
            
            # Save updated log
            with open(log_file, 'w') as f:
                json.dump(signal_log, f, indent=2)
                
        except Exception as e:
            logger.warning(f"Error logging signal for {symbol}: {e}")
            # Fail silently - logging should not break trading

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
                "timestamp": [current_time],
                "Open": [opportunity["current_price"]],
                "High": [opportunity["current_price"]],
                "Low": [opportunity["current_price"]],
                "Close": [opportunity["current_price"]],
                "Volume": [1000],  # Placeholder volume
            }

            df = pd.DataFrame(data)
            df.set_index("timestamp", inplace=True)

            return df

        except Exception as e:
            logger.warning(
                f"[MULTI-SYMBOL] Failed to create market data for chart: {e}"
            )
            # Return empty DataFrame as fallback
            return pd.DataFrame()

    def _log_symbol_decision(
        self,
        symbol: str,
        decision: str,
        confidence: float,
        reason: str,
        current_price: float,
    ):
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
                "timestamp": datetime.now().isoformat(),
                "symbol": symbol,
                "decision": decision,
                "confidence": confidence,
                "reason": reason,
                "current_price": current_price,
                "strike": "",
                "direction": "",
                "quantity": "",
                "premium": "",
                "total_cost": "",
                "llm_tokens": 0,
            }

            # Resolve broker/env-scoped trade history path robustly
            log_file = self.config.get("TRADE_LOG_FILE")
            if not log_file:
                try:
                    from utils.llm import load_config  # type: ignore
                    cfg = load_config("config.yaml")

                    # Prefer TRADE_LOG_FILE if set by config/loader
                    log_file = cfg.get("TRADE_LOG_FILE")
                    if not log_file:
                        broker = cfg.get("BROKER", "robinhood")
                        env = cfg.get("ALPACA_ENV", "paper") if broker == "alpaca" else "live"
                        from utils.scoped_files import get_scoped_paths  # type: ignore
                        log_file = get_scoped_paths(broker, env)["trade_history"]
                except Exception:
                    # Computed scoped fallback (legacy-safe)
                    try:
                        from utils.scoped_files import get_scoped_paths  # type: ignore
                        log_file = get_scoped_paths("robinhood", "live")["trade_history"]
                    except Exception:
                        # Last resort legacy path
                        log_file = "logs/trade_history_robinhood_live.csv"

            log_trade_decision(log_file, trade_data)
            logger.debug(
                f"[MULTI-SYMBOL] Logged {symbol} decision: {decision} (confidence: {confidence:.2f})"
            )

        except Exception as e:
            logger.error(f"[MULTI-SYMBOL] Error logging {symbol} decision: {e}")

    def _send_no_trade_heartbeat(self, rejection_reasons: List[str] = None):
        """
        Send Slack heartbeat when no trading opportunities are found.
        
        Args:
            rejection_reasons: List of rejection reasons for context
        """
        try:
            if self.slack_notifier:
                message = "🔄 Multi-symbol scan complete - No trading opportunities found"
                self.slack_notifier.send_heartbeat(message)
                logger.debug("[MULTI-SYMBOL] Sent no-trade heartbeat to Slack")
            else:
                logger.debug("[MULTI-SYMBOL] No Slack notifier available for heartbeat")
        except Exception as e:
            logger.error(f"[MULTI-SYMBOL] Error sending no-trade heartbeat: {e}")
