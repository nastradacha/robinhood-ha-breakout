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
from collections import Counter

from .data import fetch_market_data, calculate_heikin_ashi, analyze_breakout_pattern
from .llm import LLMClient, TradeDecision
from .data_validation import check_trading_allowed
from .staleness_monitor import check_symbol_staleness
from .symbol_state_manager import get_symbol_state_manager

logger = logging.getLogger(__name__)


class MultiSymbolScanner:
    """
    Multi-symbol breakout scanner for diversified trading opportunities.
    """

    def __init__(self, config: Dict, llm_client, slack_notifier=None, env: str = "paper", 
                 alpaca_client=None, broker: str = "robinhood", weekly_pnl_tracker=None, drawdown_circuit_breaker=None, vix_monitor=None, health_monitor=None):
        """
        Initialize multi-symbol scanner.

        Args:
            config: Trading configuration
            llm_client: LLM client for trade decisions
            slack_notifier: Slack notification client
            env: Alpaca environment - "paper" or "live" (default: "paper")
            weekly_pnl_tracker: Pre-initialized weekly P&L tracker
            drawdown_circuit_breaker: Pre-initialized circuit breaker
            vix_monitor: Pre-initialized VIX monitor
            health_monitor: Pre-initialized health monitor
        """
        self.config = config
        self.llm_client = llm_client
        self.slack_notifier = slack_notifier
        self.env = env
        
        # Use pre-initialized monitors to avoid repeated initialization
        self.weekly_pnl_tracker = weekly_pnl_tracker
        self.drawdown_circuit_breaker = drawdown_circuit_breaker
        self.vix_monitor = vix_monitor
        self.health_monitor = health_monitor

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
        # Early market hours check - skip all processing if market is closed
        from datetime import datetime
        import pytz
        
        try:
            from .market_calendar import validate_trading_time
            et_tz = pytz.timezone('US/Eastern')
            current_et = datetime.now(et_tz)
            can_trade, market_reason = validate_trading_time(current_et)
            if not can_trade:
                logger.info(f"[MULTI-SYMBOL] Pre-market: All symbols blocked (market closed) - {market_reason}")
                return []
        except Exception as e:
            # Fallback to basic weekend check if market calendar fails
            current_et = datetime.now(pytz.timezone('US/Eastern'))
            if current_et.weekday() >= 5:  # Weekend
                logger.info("[MULTI-SYMBOL] Pre-market: All symbols blocked (weekend)")
                return []
        
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
                    # Handle tuple return (opportunities, rejection_reason)
                    if isinstance(symbol_opportunities, tuple):
                        opportunities_list, rejection_reason = symbol_opportunities
                        if opportunities_list:
                            opportunities.extend(opportunities_list)
                            logger.info(
                                f"[MULTI-SYMBOL] {symbol}: Found {len(opportunities_list)} opportunities"
                            )
                        else:
                            rejection_reasons.append(f"{symbol}: {rejection_reason}")
                            logger.info(f"[MULTI-SYMBOL] {symbol}: No opportunities found")
                    elif symbol_opportunities:
                        opportunities.extend(symbol_opportunities)
                        logger.info(
                            f"[MULTI-SYMBOL] {symbol}: Found {len(symbol_opportunities)} opportunities"
                        )
                    else:
                        # Extract opportunities and rejection reason from result
                        if isinstance(symbol_opportunities, tuple):
                            opportunities_list, rejection_reason = symbol_opportunities
                        else:
                            opportunities_list, rejection_reason = symbol_opportunities, 'No opportunities found'
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
            # Check if all symbols were blocked by pre-open gate
            pre_open_blocks = sum(1 for reason in rejection_reasons if "PRE-OPEN-GATE" in reason or "Market closed" in reason or "Trading blocked" in reason)
            
            if pre_open_blocks == len(self.symbols):
                # All symbols blocked by market hours - just log once
                logger.info("[MULTI-SYMBOL] Pre-market: All symbols blocked (market closed)")
            else:
                # Create detailed summary of rejection reasons with actionable breakdown
                reason_summary = self._summarize_rejection_reasons(rejection_reasons)
                detailed_breakdown = self._create_detailed_reason_breakdown(rejection_reasons)
                
                logger.info(
                    f"[MULTI-SYMBOL] No trading opportunities found across all symbols. Reasons: {reason_summary}"
                )
                logger.info(f"[GATE-BREAKDOWN] {detailed_breakdown}")
                
                # Send Slack heartbeat with NO_TRADE reasons summary
                self._send_no_trade_heartbeat(rejection_reasons)

        return sorted_opportunities

    def _summarize_rejection_reasons(self, rejection_reasons: List[str]) -> str:
        """Summarize rejection reasons for logging and Slack alerts with concrete buckets."""
        if not rejection_reasons:
            return "Unknown reasons"
        
        # Count rejection types with concrete buckets
        reason_counts = Counter()
        
        for reason in rejection_reasons:
            if "TIME_WINDOW_CLOSED" in reason or "Trading window closed" in reason:
                reason_counts["TIME_WINDOW_CLOSED"] += 1
            elif "CIRCUIT_BREAKER" in reason or "circuit breaker" in reason.lower():
                reason_counts["CIRCUIT_BREAKER"] += 1
            elif "PAUSED_SYMBOL" in reason or "paused" in reason.lower():
                reason_counts["PAUSED_SYMBOL"] += 1
            elif "Data validation blocked" in reason or "validation" in reason.lower():
                reason_counts["DATA_VALIDATION"] += 1
            elif "Staleness check blocked" in reason or "staleness" in reason.lower():
                reason_counts["STALE_DATA"] += 1
            elif "Pre-LLM gate" in reason or "true range" in reason.lower():
                reason_counts["PRE_LLM_GATE"] += 1
            elif "LLM recommends NO_TRADE" in reason or "NO_TRADE" in reason:
                reason_counts["LLM_NO_TRADE"] += 1
            elif "401" in reason or "authorization" in reason.lower():
                reason_counts["AUTH_ERROR"] += 1
            elif "Error" in reason or "error" in reason.lower():
                reason_counts["API_ERROR"] += 1
            elif "No data available" in reason:
                reason_counts["NO_DATA"] += 1
            elif "Market closed" in reason or "PRE-OPEN-GATE" in reason:
                reason_counts["MARKET_CLOSED"] += 1
            else:
                reason_counts["OTHER"] += 1
        
        # Format summary with concrete reason names
        summary_parts = [f"{reason} {count}" for reason, count in reason_counts.items()]
        return ", ".join(summary_parts)

    def _create_detailed_reason_breakdown(self, rejection_reasons: List[str]) -> str:
        """Create detailed breakdown of rejection reasons with actionable insights."""
        if not rejection_reasons:
            return "No rejection details available"
        
        # Categorize reasons with specific details
        # Count explicit categories
        body_weak_count = 0
        tr_fail_count = 0
        momentum_fail_count = 0
        quarantined_count = 0
        validation_attention_count = 0
        validation_no_data_count = 0
        weekly_protection_count = 0
        data_staleness_count = 0
        market_closed_count = 0
        time_cutoff_count = 0
        cooldown_count = 0
        max_concurrent_count = 0
        other_reasons = []
        
        for reason in rejection_reasons:
            if "body too weak" in reason.lower() or "body_too_weak:" in reason:
                body_weak_count += 1
            elif "tr fail" in reason.lower() or "true range" in reason.lower():
                tr_fail_count += 1
            elif "insufficient momentum" in reason.lower() or "insufficient_momentum:" in reason:
                momentum_fail_count += 1
            elif "quarantined_corp_action:" in reason:
                quarantined_count += 1
            elif "validation_attention:" in reason:
                validation_attention_count += 1
            elif "validation_no_data:" in reason:
                validation_no_data_count += 1
            elif "weekly_protection:" in reason:
                weekly_protection_count += 1
            elif "data_staleness:" in reason:
                data_staleness_count += 1
            elif "market_closed:" in reason:
                market_closed_count += 1
            elif "time_cutoff:" in reason:
                time_cutoff_count += 1
            elif "cooldown:" in reason:
                cooldown_count += 1
            elif "max_concurrent_trades:" in reason:
                max_concurrent_count += 1
            else:
                # Only use "other" for truly unknown reasons
                other_reasons.append(reason)
        
        # Build explicit breakdown
        breakdown_parts = []
        if quarantined_count > 0:
            breakdown_parts.append(f"quarantined_corp_action={quarantined_count}")
        if validation_attention_count > 0:
            breakdown_parts.append(f"validation_attention={validation_attention_count}")
        if validation_no_data_count > 0:
            breakdown_parts.append(f"validation_no_data={validation_no_data_count}")
        if weekly_protection_count > 0:
            breakdown_parts.append(f"weekly_protection={weekly_protection_count}")
        if data_staleness_count > 0:
            breakdown_parts.append(f"data_staleness={data_staleness_count}")
        if body_weak_count > 0:
            breakdown_parts.append(f"body_too_weak={body_weak_count}")
        if tr_fail_count > 0:
            breakdown_parts.append(f"tr_fail={tr_fail_count}")
        if momentum_fail_count > 0:
            breakdown_parts.append(f"insufficient_momentum={momentum_fail_count}")
        if market_closed_count > 0:
            breakdown_parts.append(f"market_closed={market_closed_count}")
        if time_cutoff_count > 0:
            breakdown_parts.append(f"time_cutoff={time_cutoff_count}")
        if cooldown_count > 0:
            breakdown_parts.append(f"cooldown={cooldown_count}")
        if max_concurrent_count > 0:
            breakdown_parts.append(f"max_concurrent_trades={max_concurrent_count}")
        if other_reasons:
            breakdown_parts.append(f"other={len(other_reasons)}")
        
        return f"blocked: {', '.join(breakdown_parts)}"

    def _check_symbol_blocked(self, symbol: str, current_price: float) -> tuple[bool, str, str]:
        """
        Single source of truth for all symbol blocking decisions.
        
        Returns:
            Tuple of (is_blocked, reason, category)
        """
        # 1. Check quarantine status first
        state_manager = get_symbol_state_manager()
        if not state_manager.is_symbol_tradeable(symbol):
            symbol_info = state_manager.get_symbol_info(symbol)
            reason = symbol_info.get('reason', 'Unknown')
            return True, reason, "quarantined_corp_action"
        
        # 2. Check data validation
        try:
            data_allowed, data_reason = check_trading_allowed(symbol)
            if not data_allowed:
                if "attention" in data_reason.lower():
                    return True, data_reason, "validation_attention"
                elif "no data" in data_reason.lower():
                    return True, data_reason, "validation_no_data"
                else:
                    return True, data_reason, "validation_blocked"
        except Exception as e:
            return True, f"Data validation error: {e}", "validation_error"
        
        # 3. Check staleness
        try:
            staleness_allowed, staleness_reason = check_symbol_staleness(symbol, with_retry=True)
            if not staleness_allowed:
                return True, staleness_reason, "data_staleness"
        except Exception as e:
            return True, f"Staleness check error: {e}", "staleness_error"
        
        # 4. Check weekly protection
        try:
            if self.drawdown_circuit_breaker:
                should_disable, weekly_reason = self.drawdown_circuit_breaker.check_weekly_drawdown_limit()
                if should_disable:
                    return True, weekly_reason, "weekly_protection"
        except Exception as e:
            # Fail closed - block trading on weekly protection errors
            return True, f"Weekly protection check failed: {e}", "weekly_protection"
        
        # Symbol is not blocked
        return False, "Symbol checks passed", "allowed"

    def _scan_single_symbol(self, symbol: str) -> tuple[List[Dict], str]:
        """
        Scan a single symbol for breakout opportunities.

        Args:
            symbol: Stock symbol to scan

        Returns:
            Tuple of (opportunities list, rejection reason if no opportunities)
        """
        rejection_reason = None
        try:
            # Early market hours check - skip heavy processing if market is closed
            from datetime import datetime
            import pytz
            
            try:
                from .market_calendar import validate_trading_time
                et_tz = pytz.timezone('US/Eastern')
                current_et = datetime.now(et_tz)
                can_trade, market_reason = validate_trading_time(current_et)
                if not can_trade:
                    rejection_reason = f"Market closed: {market_reason}"
                    logger.debug(f"[PRE-OPEN-GATE] {symbol}: {market_reason}")
                    return [], rejection_reason
            except Exception as e:
                # Fallback to basic weekend check if market calendar fails
                current_et = datetime.now(pytz.timezone('US/Eastern'))
                if current_et.weekday() >= 5:  # Weekend
                    rejection_reason = "Market closed (weekend)"
                    logger.debug(f"[PRE-OPEN-GATE] {symbol}: Market closed (weekend)")
                    return [], rejection_reason
                logger.debug(f"[PRE-OPEN-GATE] {symbol}: Market calendar check failed, proceeding: {e}")

            logger.info(f"[MULTI-SYMBOL] Analyzing {symbol}...")

            # Fetch market data
            df = fetch_market_data(
                symbol=symbol,
                interval=self.config["TIMEFRAME"],
                period="5d",  # Use 5 days to get enough data for analysis
                env=self.env
            )

            if df is None or df.empty:
                rejection_reason = "No data available"
                logger.warning(f"[MULTI-SYMBOL] No data available for {symbol}")
                return [], rejection_reason

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

            # Unified blocking check - single source of truth
            is_blocked, block_reason, block_category = self._check_symbol_blocked(symbol, current_price)
            if is_blocked:
                logger.warning(f"[MULTI-SYMBOL] {symbol}: {block_category} - {block_reason}")
                return [], f"{block_category}: {block_reason}"

            # Pre-LLM hard gate: check for obvious NO_TRADE conditions
            proceed, gate_reason = self._pre_llm_hard_gate(market_data, self.config)
            if not proceed:
                rejection_reason = f"Pre-LLM gate: {gate_reason}"
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
                return [], rejection_reason

            # Check for borderline escalation before LLM call
            borderline_case = market_data.get("_borderline_body_case")
            if borderline_case:
                logger.info(f"[BORDERLINE-ESCALATE] {symbol}: Escalating borderline case to LLM (body shortfall: {borderline_case['shortfall_pct']:.1f}%)")
                # Add borderline context to market data for LLM
                market_data["_borderline_escalation"] = True
                market_data["_escalation_reason"] = f"Body {borderline_case['current_pct']:.4f}% ≥ 80% of threshold"

            # Get LLM trade decision with retry logic
            trade_decision_result = self._robust_llm_decision(market_data, symbol)
            trade_decision = {
                "decision": trade_decision_result.decision,
                "confidence": trade_decision_result.confidence,
                "reason": trade_decision_result.reason or "LLM analysis completed",
            }

            # Apply stricter confidence threshold for borderline escalations
            if borderline_case and trade_decision["decision"] != "NO_TRADE":
                min_borderline_confidence = 0.75
                if trade_decision.get("confidence", 0.0) < min_borderline_confidence:
                    rejection_reason = f"Borderline escalation: confidence {trade_decision.get('confidence', 0.0):.3f} < {min_borderline_confidence:.3f} required for borderline cases"
                    logger.info(f"[BORDERLINE-REJECT] {symbol}: {rejection_reason}")
                    return [], rejection_reason

            # Check if LLM recommends a trade
            if trade_decision["decision"] == "NO_TRADE":
                rejection_reason = f"LLM recommends NO_TRADE: {trade_decision.get('reason', 'No reason provided')}"
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
                return [], rejection_reason

            # Check confidence threshold
            confidence = trade_decision.get("confidence")
            min_confidence = self.config.get("MIN_CONFIDENCE", 0.35)

            if confidence is None or confidence < min_confidence:
                if confidence is None:
                    raw_reason = "Missing confidence score"
                else:
                    raw_reason = f"Confidence {confidence:.3f} below threshold {min_confidence:.3f}"
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
                if confidence is None:
                    rejection_reason = "Missing confidence score"
                else:
                    rejection_reason = f"Confidence {confidence:.3f} below threshold {min_confidence:.3f}"
                return [], rejection_reason

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

            # Format confidence display properly
            conf_display = f"{confidence:.3f}" if confidence is not None else "N/A"
            logger.info(
                f"[MULTI-SYMBOL] {symbol}: Found opportunity - {trade_decision['decision']} (confidence: {conf_display})"
            )
            
            # Log opportunity using deterministic serialization
            self._log_opportunity(opportunity)
            
            return [opportunity], None

        except Exception as e:
            rejection_reason = f"Error analyzing symbol: {str(e)}"
            logger.error(f"[MULTI-SYMBOL] Error analyzing {symbol}: {e}")
            return [], rejection_reason

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
                if self.vix_monitor:
                    # Use pre-initialized VIX monitor to avoid repeated initialization
                    is_spike, vix_value, vix_reason = self.vix_monitor.is_vix_spike_active()
                else:
                    # Fallback to singleton function if no pre-initialized monitor
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
                if self.drawdown_circuit_breaker:
                    # Use pre-initialized weekly circuit breaker to avoid repeated initialization
                    should_disable, weekly_reason = self.drawdown_circuit_breaker.check_weekly_drawdown_limit()
                else:
                    # Fallback to singleton function if no pre-initialized breaker
                    from .drawdown_circuit_breaker import get_drawdown_circuit_breaker
                    weekly_cb = get_drawdown_circuit_breaker(config)
                    should_disable, weekly_reason = weekly_cb.check_weekly_drawdown_limit()
                
                if should_disable:
                    return False, f"Weekly protection: {weekly_reason}"
                logger.debug(f"[WEEKLY-PROTECTION-GATE] {symbol}: {weekly_reason}")
            except Exception as e:
                logger.warning(f"[WEEKLY-PROTECTION-GATE] Weekly protection check failed for {symbol}: {e}, allowing trades (fail-safe)")
            
            # 6. Check minimum true range percentage (dynamic thresholds)
            symbol = market_data.get("symbol", "UNKNOWN")
            
            # Dynamic TR floor calculation
            min_tr_range_pct = self._calculate_dynamic_tr_floor(symbol, market_data, config)
            
            # Add sanity check to prevent "20%" accidents (treat >5 as % not fraction)
            raw_threshold = min_tr_range_pct
            if raw_threshold > 5:
                min_tr_range_pct = raw_threshold / 100.0
            min_tr_range_pct = min(max(min_tr_range_pct, 0.0), 5.0)
            
            today_tr_pct = market_data.get("today_true_range_pct", 0.0)
            
            # Gate on raw float values, round only for logging
            tr_passes_threshold = today_tr_pct >= min_tr_range_pct
            
            # Debug logging for true range values with consistent precision
            logger.info(f"[TR-DEBUG] {symbol}: TR={today_tr_pct:.4f}% (threshold: {min_tr_range_pct:.4f}%) - {'PASS' if tr_passes_threshold else 'FAIL'}")
            
            # 6a. VIX-based UVXY guardrail (skip UVXY in low-VIX regimes)
            if symbol == "UVXY":
                try:
                    vix_threshold = config.get("UVXY_VIX_THRESHOLD", 18.0)
                    current_vix = market_data.get("vix", 0.0)
                    if current_vix > 0 and current_vix < vix_threshold:
                        logger.info(f"[VIX-GUARDRAIL] {symbol}: VIX={current_vix:.2f} < {vix_threshold:.1f}, skipping UVXY in low-vol regime")
                        return False, f"VIX too low for UVXY trading: {current_vix:.2f} < {vix_threshold:.1f}"
                    elif current_vix > 0:
                        logger.info(f"[VIX-GUARDRAIL] {symbol}: VIX={current_vix:.2f} >= {vix_threshold:.1f}, UVXY trading allowed")
                except Exception as e:
                    logger.warning(f"[VIX-GUARDRAIL] VIX check failed for {symbol}: {e}, allowing trades (fail-safe)")
            
            # 6a. True range minimum check with enhanced hysteresis and momentum compensation
            hysteresis_factor = config.get('HYSTERESIS_FACTOR', 0.92)  # Increased from 0.86 to 0.92 for fewer false negatives
            hysteresis_threshold = hysteresis_factor * min_tr_range_pct
            
            # Check for strong range that can compensate for borderline momentum
            range_compensation_threshold = 1.25 * min_tr_range_pct  # 25% above threshold
            has_strong_range = today_tr_pct >= range_compensation_threshold
            
            if today_tr_pct < hysteresis_threshold:
                # Near-miss detection for quality trades close to threshold (95-98% range)
                near_miss_threshold = 0.95 * min_tr_range_pct
                if today_tr_pct >= near_miss_threshold:
                    # Check body-to-range and momentum quality
                    close_price = market_data.get("close", 0.0)
                    open_price = market_data.get("open", 0.0)
                    high_price = market_data.get("high", 0.0)
                    low_price = market_data.get("low", 0.0)
                    
                    body_to_range = abs(close_price - open_price) / max(high_price - low_price, 1e-9)
                    momentum_score = self._calculate_momentum_score(market_data)
                    
                    if body_to_range >= 0.35 and momentum_score >= 2:
                        logger.info(f"[NEAR-MISS] {symbol}: TR={today_tr_pct:.4f}% ≥ 95% of floor ({near_miss_threshold:.4f}%), good quality - scheduling 30s rescan")
                        # TODO: Implement actual reschedule mechanism
                        return False, f"NEAR_MISS_RESCHEDULE: TR={today_tr_pct:.4f}% (≥95% floor, quality OK)"
                    else:
                        logger.debug(f"[NEAR-MISS] {symbol}: TR near floor but quality insufficient (BTR={body_to_range:.3f}, momentum={momentum_score})")
                
                return False, f"True range too low ({today_tr_pct:.4f}% < {hysteresis_threshold:.4f}% hysteresis threshold, {min_tr_range_pct:.4f}% minimum)"
            elif today_tr_pct < min_tr_range_pct:
                # In hysteresis zone (90-100% of threshold) - allow to pass
                logger.info(f"[TR-HYSTERESIS] {symbol}: TR={today_tr_pct:.4f}% in hysteresis zone ({hysteresis_threshold:.4f}%-{min_tr_range_pct:.4f}%), allowing trade")
                # Continue to next gate check
            
            # 6b. Pre-LLM body percentage and momentum gates with time-of-day scaling
            pre_llm_gates = config.get("PRE_LLM_GATES", {})
            if pre_llm_gates.get("enabled", False):
                # Body percentage check with time-of-day and VIX-based scaling
                min_body_pct_config = pre_llm_gates.get("min_body_pct", {})
                if symbol in min_body_pct_config:
                    base_min_body_pct = min_body_pct_config[symbol]
                    
                    # Apply time-of-day scaling (60-70% of normal in first 90 minutes)
                    time_scaled_pct = self._apply_time_scaling_to_body_filter(base_min_body_pct, current_et)
                    
                    # Apply VIX-based scaling for low volatility adjustments
                    scaled_min_body_pct = self._apply_vix_scaling_to_body_filter(time_scaled_pct, symbol)
                    
                    current_body_pct = market_data.get("candle_body_pct", 0.0)
                    
                    # Check if body passes scaled threshold
                    body_passes = current_body_pct >= scaled_min_body_pct
                    
                    if not body_passes:
                        # Check for borderline escalation (≥90% of threshold) - widened hysteresis
                        borderline_threshold = 0.90 * scaled_min_body_pct  # Increased from 85% to 90%
                        is_borderline = current_body_pct >= borderline_threshold
                        
                        if is_borderline:
                            # Round to basis points for consistent comparison
                            current_body_bp = round(current_body_pct * 10000)  # Convert to basis points
                            threshold_bp = round(borderline_threshold * 10000)
                            
                            # Log borderline case for potential LLM escalation
                            logger.info(f"[BORDERLINE] {symbol}: Body {current_body_bp/100:.2f}bp ≥ 85% of threshold ({threshold_bp/100:.2f}bp), flagging for potential LLM escalation")
                            # Mark this as a borderline case in market_data for later escalation
                            market_data["_borderline_body_case"] = {
                                "current_pct": current_body_pct,
                                "threshold_pct": scaled_min_body_pct,
                                "shortfall_pct": ((scaled_min_body_pct - current_body_pct) / scaled_min_body_pct) * 100
                            }
                        else:
                            # Round for consistent logging
                            current_bp = round(current_body_pct * 10000)
                            threshold_bp = round(scaled_min_body_pct * 10000)
                            return False, f"Candle body too weak ({current_bp/100:.2f}bp < {threshold_bp/100:.2f}bp minimum, scaled from {round(base_min_body_pct * 10000)/100:.2f}bp)"
                
                # Momentum checks (require at least N of 3 indicators) - relaxed thresholds
                required_momentum_checks = pre_llm_gates.get("momentum_checks", 1)  # Reduced from 2 to 1
                momentum_score = 0
                
                # Check 1: Price action momentum (relaxed)
                try:
                    price = market_data.get("current_price", 0.0)
                    if price > 0:
                        # More lenient momentum check: any breakout signal counts
                        breakout_analysis = market_data.get("breakout_analysis", {})
                        candle_body_pct = breakout_analysis.get("candle_body_pct", 0.0)
                        
                        # If we have a meaningful candle body, count as momentum
                        if candle_body_pct > 0.02:  # 2% body threshold (very low)
                            momentum_score += 1
                        
                        # Alternative: check if price moved significantly
                        price_change_pct = breakout_analysis.get("price_change_pct", 0.0)
                        if abs(price_change_pct) > 0.1:  # 0.1% price movement
                            momentum_score += 1
                except:
                    pass
                
                # Check 2: Trend direction (more lenient)
                try:
                    trend_direction = market_data.get("trend_direction", "NEUTRAL")
                    # Accept any non-neutral trend OR if we have breakout signal
                    if trend_direction in ["BULLISH", "BEARISH"]:
                        momentum_score += 1
                    elif trend_direction == "NEUTRAL":
                        # Still count neutral if we have volume or volatility
                        tr_pct = market_data.get("breakout_analysis", {}).get("tr_pct", 0.0)
                        if tr_pct > 0.05:  # 5% true range indicates movement
                            momentum_score += 1
                except:
                    pass
                
                # Check 3: Volume or volatility confirmation (relaxed)
                try:
                    volume_confirmation = market_data.get("volume_confirmation", False)
                    if volume_confirmation:
                        momentum_score += 1
                    else:
                        # Alternative: check for volatility as momentum proxy
                        tr_pct = market_data.get("breakout_analysis", {}).get("tr_pct", 0.0)
                        if tr_pct > 0.08:  # 8% true range indicates momentum
                            momentum_score += 1
                except:
                    pass
                
                # Apply momentum compensation logic - strong range can compensate for borderline momentum
                if momentum_score < required_momentum_checks:
                    if has_strong_range and momentum_score >= (required_momentum_checks - 1):
                        logger.info(f"[MOMENTUM-COMPENSATION] {symbol}: TR={today_tr_pct:.4f}% (≥{range_compensation_threshold:.4f}%) compensates for momentum {momentum_score}/{required_momentum_checks}")
                        # Allow trade to proceed with strong range compensation
                    else:
                        return False, f"Insufficient momentum ({momentum_score}/{required_momentum_checks} indicators)"
            
            # 7. Check user-configured trade window (optional)
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
        # Handle explicit blocking categories first
        if "quarantined_corp_action:" in reason:
            return reason  # Already formatted
        elif "validation_attention:" in reason:
            return reason  # Already formatted
        elif "validation_no_data:" in reason:
            return reason  # Already formatted
        elif "weekly_protection:" in reason:
            return reason  # Already formatted
        elif "data_staleness:" in reason:
            return reason  # Already formatted
        
        # Handle pre-LLM gate reasons with specific categories
        if "Pre-LLM gate:" in reason:
            if "body too weak" in reason.lower():
                return f"body_too_weak: {reason}"
            elif "insufficient momentum" in reason.lower():
                return f"insufficient_momentum: {reason}"
            elif "market closed" in reason.lower():
                return f"market_closed: {reason}"
            elif "time cutoff" in reason.lower():
                return f"time_cutoff: {reason}"
            elif "volatility" in reason.lower():
                return f"low_volatility: {reason}"
            elif "trade window" in reason.lower():
                return f"trade_window: {reason}"
            elif "cooldown" in reason.lower():
                return f"cooldown: {reason}"
            elif "max concurrent" in reason.lower():
                return f"max_concurrent_trades: {reason}"
            else:
                return f"pre_llm_gate: {reason}"
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
            # Format confidence display properly for logging
            conf_display = f"{confidence:.3f}" if confidence is not None else "N/A"
            logger.debug(
                f"[MULTI-SYMBOL] Logged {symbol} decision: {decision} (confidence: {conf_display})"
            )

        except Exception as e:
            logger.error(f"[MULTI-SYMBOL] Error logging {symbol} decision: {e}")

    def _calculate_dynamic_tr_floor(self, symbol: str, market_data: Dict, config: Dict) -> float:
        """
        Calculate dynamic TR floor based on VIX and time-of-day.
        
        Args:
            symbol: Trading symbol
            market_data: Market data including VIX
            config: Configuration dictionary
            
        Returns:
            Dynamic TR floor as percentage (e.g., 0.10 for 0.10%)
        """
        # Base TR thresholds
        BASE_TR = {
            "SPY": 0.10, "QQQ": 0.15, "DIA": 0.10, "IWM": 0.15,
            "XLK": 0.18, "XLF": 0.12, "XLE": 0.20, "TLT": 0.08, "UVXY": 0.80
        }
        
        # Get base threshold
        base_tr = BASE_TR.get(symbol, 0.10)
        
        # VIX scaling - get live VIX from monitor with fallback
        current_vix = market_data.get("vix", 0.0)
        if current_vix <= 0.0 and self.vix_monitor:
            try:
                vix_data = self.vix_monitor.get_current_vix()
                if vix_data:
                    current_vix = vix_data.value
                    logger.debug(f"[DYNAMIC-TR] Retrieved live VIX from monitor: {current_vix:.2f}")
                else:
                    current_vix = 20.0
                    logger.warning("[DYNAMIC-TR] VIX monitor returned None, using fallback")
            except Exception as e:
                logger.warning(f"[DYNAMIC-TR] Failed to get live VIX: {e}, using fallback")
                current_vix = 20.0
        elif current_vix <= 0.0:
            current_vix = 20.0
            logger.warning(f"[DYNAMIC-TR] No VIX data available, using fallback: {current_vix}")
            
        # Enhanced VIX scaling for low volatility regimes
        # More aggressive reductions for index ETFs in very low VIX environments
        index_etfs = {"SPY", "QQQ", "DIA", "IWM", "XLK", "XLF", "XLE"}
        is_index_etf = symbol in index_etfs
        
        if current_vix < 12:
            # Extremely low VIX - very aggressive reduction for index ETFs
            vix_mult = 0.60 if is_index_etf else 0.80
        elif current_vix < 16:
            # Very low VIX - aggressive reduction for index ETFs
            vix_mult = 0.70 if is_index_etf else 0.85
        elif current_vix < 20:
            # Low VIX - moderate reduction for index ETFs
            vix_mult = 0.85 if is_index_etf else 0.95
        elif current_vix < 25:
            vix_mult = 1.10
        else:
            vix_mult = 1.25
            
        # Time-of-day scaling (lunch tighten 12:30-14:30 ET)
        from datetime import datetime
        import pytz
        et_tz = pytz.timezone('US/Eastern')
        now_et = datetime.now(et_tz)
        hour_decimal = now_et.hour + now_et.minute / 60.0
        lunch_mult = 1.05 if 12.5 <= hour_decimal <= 14.5 else 1.00
        
        # Special handling for UVXY with VIX-based thresholds
        if symbol == "UVXY":
            uvxy_dynamic = config.get("UVXY_DYNAMIC_TR", {})
            if uvxy_dynamic.get("enabled", False):
                vix_low = uvxy_dynamic.get("vix_low", 18.0)
                vix_high = uvxy_dynamic.get("vix_high", 25.0)
                tr_low = uvxy_dynamic.get("tr_low", 0.45)
                tr_medium = uvxy_dynamic.get("tr_medium", 0.80)
                tr_high = uvxy_dynamic.get("tr_high", 1.00)
                
                # Determine bucket and threshold
                if current_vix < vix_low:
                    dynamic_tr = tr_low
                    bucket = f"<{vix_low}"
                    bucket_midpoint = vix_low / 2  # Approximate midpoint for low bucket
                elif current_vix < vix_high:
                    dynamic_tr = tr_medium
                    bucket = f"{vix_low}-{vix_high}"
                    bucket_midpoint = (vix_low + vix_high) / 2  # True midpoint
                else:
                    dynamic_tr = tr_high
                    bucket = f">{vix_high}"
                    bucket_midpoint = vix_high + 5  # Approximate for high bucket
                    
                logger.info(f"[UVXY-THRESH] VIX={current_vix:.2f} → bucket {bucket} (mid {bucket_midpoint:.1f}) → TR floor {dynamic_tr:.3f}%")
                return dynamic_tr
        
        # Calculate final dynamic threshold
        dynamic_tr = round(base_tr * vix_mult * lunch_mult, 3)
        
        # Log dynamic calculation for debugging
        logger.debug(f"[DYNAMIC-TR] {symbol}: base={base_tr:.3f}% * VIX_mult={vix_mult:.2f} * lunch_mult={lunch_mult:.2f} = {dynamic_tr:.3f}%")
        
        return dynamic_tr

    def _calculate_momentum_score(self, market_data: Dict) -> int:
        """
        Calculate momentum score based on EMA stack, VWAP, and Heikin-Ashi.
        
        Args:
            market_data: Market data dictionary
            
        Returns:
            Momentum score (0-3, need ≥2 for quality gate)
        """
        score = 0
        indicators = []
        
        # EMA stack alignment (1 point)
        ema_9 = market_data.get("ema_9", 0.0)
        ema_21 = market_data.get("ema_21", 0.0)
        ema_bullish = ema_9 > 0 and ema_21 > 0 and ema_9 > ema_21
        if ema_bullish:
            score += 1
        indicators.append(f"EMA: {'Bullish ✅' if ema_bullish else 'Bearish ❌'}")
            
        # VWAP position (1 point)
        close_price = market_data.get("close", 0.0)
        vwap = market_data.get("vwap", 0.0)
        above_vwap = close_price > 0 and vwap > 0 and close_price > vwap
        if above_vwap:
            score += 1
        indicators.append(f"VWAP: {'Above ✅' if above_vwap else 'Below ❌'}")
            
        # Heikin-Ashi trend (1 point)
        ha_close = market_data.get("ha_close", 0.0)
        ha_open = market_data.get("ha_open", 0.0)
        ha_bullish = ha_close > 0 and ha_open > 0 and ha_close > ha_open
        if ha_bullish:
            score += 1
        indicators.append(f"HA trend: {'Bullish ✅' if ha_bullish else 'Bearish ❌'}")
        
        # Log detailed momentum breakdown
        symbol = market_data.get("symbol", "UNKNOWN")
        logger.debug(f"[MOM] {symbol}: {', '.join(indicators)} (score {score}/3)")
            
        return score

    def _apply_time_scaling_to_body_filter(self, base_min_body_pct: float, current_et) -> float:
        """
        Apply time-of-day scaling to body percentage filter.
        
        Reduces thresholds during opening period (9:30-11:00 AM ET)
        to allow more opportunities during the volatile opening period.
        
        Args:
            base_min_body_pct: Base minimum body percentage
            current_et: Current Eastern time (datetime object)
            
        Returns:
            Scaled minimum body percentage
        """
        try:
            # Ensure current_et is a datetime object and convert to time object
            if isinstance(current_et, int):
                logger.warning(f"[TIME-SCALE] Received int {current_et} instead of datetime, using current time")
                et_tz = pytz.timezone('US/Eastern')
                current_et = datetime.now(et_tz)
            elif not hasattr(current_et, 'time'):
                logger.warning(f"[TIME-SCALE] Invalid current_et type {type(current_et)}, using current time")
                et_tz = pytz.timezone('US/Eastern')
                current_et = datetime.now(et_tz)
                
            current_time = current_et.time()
            
            # Check if we're in the opening period (9:30-11:00 AM ET)
            from datetime import time as dt_time
            opening_time_obj = dt_time(9, 30)
            end_opening_obj = dt_time(11, 0)
            
            if current_time >= opening_time_obj and current_time < end_opening_obj:
                # Linear scaling from 60% at open to 100% at 11:00 AM
                # Calculate minutes since 9:30 AM ET properly
                current_minutes = current_time.hour * 60 + current_time.minute
                opening_minutes = opening_time_obj.hour * 60 + opening_time_obj.minute
                minutes_since_open = float(current_minutes - opening_minutes)
                
                # Ensure non-negative and within bounds
                minutes_since_open = max(0.0, min(90.0, minutes_since_open))
                
                scaling_factor = 0.60 + (0.40 * (minutes_since_open / 90.0))  # 60% to 100% over 90 min
                scaled_pct = base_min_body_pct * scaling_factor
                
                logger.debug(f"[TIME-SCALE] Body filter: {base_min_body_pct:.4f}% * {scaling_factor:.2f} = {scaled_pct:.4f}% (opening period)")
                return scaled_pct
            else:
                # Normal hours - no scaling
                return base_min_body_pct
                
        except Exception as e:
            logger.warning(f"[TIME-SCALE] Error applying time scaling: {e}, using base threshold")
            return base_min_body_pct

    def _apply_vix_scaling_to_body_filter(self, time_scaled_pct: float, symbol: str) -> float:
        """
        Apply VIX-based scaling to body percentage filter for low volatility adjustments.
        
        Reduces thresholds during low VIX periods to allow more trades when market
        conditions are calm but breakouts may still be valid with smaller candle bodies.
        
        VIX Scaling Logic:
        - VIX < 15: 70% of threshold (very low volatility)
        - VIX 15-20: 80% of threshold (low volatility) 
        - VIX 20-25: 90% of threshold (normal-low volatility)
        - VIX > 25: 100% of threshold (normal/high volatility)
        
        Args:
            time_scaled_pct: Time-scaled minimum body percentage
            symbol: Trading symbol for logging context
            
        Returns:
            VIX-adjusted minimum body percentage
        """
        try:
            # Import VIX monitor
            from .vix_monitor import get_vix_monitor
            
            # Get current VIX data
            vix_monitor = get_vix_monitor()
            vix_data = vix_monitor.get_current_vix()
            
            if not vix_data:
                logger.debug(f"[VIX-SCALE] {symbol}: No VIX data available, using time-scaled threshold")
                return time_scaled_pct
            
            vix_value = vix_data.value
            
            # Determine VIX-based scaling factor
            if vix_value < 15.0:
                # Very low volatility - reduce threshold by 30%
                vix_scaling_factor = 0.70
                regime = "very-low"
            elif vix_value < 20.0:
                # Low volatility - reduce threshold by 20%
                vix_scaling_factor = 0.80
                regime = "low"
            elif vix_value < 25.0:
                # Normal-low volatility - reduce threshold by 10%
                vix_scaling_factor = 0.90
                regime = "normal-low"
            else:
                # Normal/high volatility - no reduction
                vix_scaling_factor = 1.00
                regime = "normal-high"
            
            vix_scaled_pct = time_scaled_pct * vix_scaling_factor
            
            # Log VIX adjustment details
            if vix_scaling_factor < 1.0:
                logger.info(f"[VIX-SCALE] {symbol}: VIX {vix_value:.1f} ({regime}) - reducing body threshold "
                           f"{time_scaled_pct:.4f}% → {vix_scaled_pct:.4f}% ({vix_scaling_factor:.0%})")
            else:
                logger.debug(f"[VIX-SCALE] {symbol}: VIX {vix_value:.1f} ({regime}) - no threshold adjustment")
            
            return vix_scaled_pct
            
        except Exception as e:
            logger.warning(f"[VIX-SCALE] {symbol}: Error applying VIX scaling: {e}, using time-scaled threshold")
            return time_scaled_pct

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
