#!/usr/bin/env python3
"""
LLM Decision Agent for Hands-Free Trading

Replaces manual user prompts at key decision points (entry/exit) with LLM decisions
while maintaining all hard safety rails. Used only at existing user interaction points.

Key Features:
- Strict JSON schema enforcement with Pydantic
- Hard rails enforced BEFORE any LLM call (non-overrideable)
- Rate limiting per symbol to control API costs
- Confidence gating with configurable thresholds
- Conservative bias options for capital protection
- Full audit trail to logs and Slack

Hard Rails (Never Overrideable):
- Daily/weekly circuit breakers
- Kill switch activation
- Stop loss at -25%
- Force close at 15:45 ET
- All existing pre-LLM gates remain unchanged
"""

import time
import json
import logging
from typing import Literal, Optional, Dict, Any, List
from pydantic import BaseModel, Field, ValidationError
from datetime import datetime

logger = logging.getLogger(__name__)

# Type definitions
Action = Literal["SELL", "HOLD", "WAIT", "ABSTAIN"]
EntryAction = Literal["APPROVE", "REJECT", "NEED_USER", "ABSTAIN"]
ExitBias = Literal["conservative", "balanced", "aggressive"]


class ExitDecision(BaseModel):
    """
    Structured exit decision from LLM with validation.
    
    Fields:
        action: Primary decision (SELL/HOLD/WAIT/ABSTAIN)
        confidence: Decision confidence (0.0-1.0)
        reason: Human-readable explanation
        risk_assessment: Risk analysis summary
        tokens_used: API tokens consumed (for cost tracking)
        defer_minutes: Minutes to wait before next check (1-30)
        expected_exit_price: Estimated exit price if selling
        time_horizon_min: Expected time to completion
    """
    action: Action = Field(..., description="Exit action to take")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Decision confidence")
    reason: str = Field(..., min_length=1, description="Explanation for decision")
    risk_assessment: Optional[str] = Field(default=None, description="Risk analysis")
    tokens_used: int = Field(default=0, ge=0, description="API tokens consumed")
    defer_minutes: Optional[int] = Field(default=2, ge=1, le=30, description="Minutes to defer")
    expected_exit_price: Optional[float] = Field(default=None, description="Expected exit price")
    time_horizon_min: Optional[int] = Field(default=None, description="Time to completion")


class EntryDecision(BaseModel):
    """
    Structured entry decision from LLM with validation.
    
    Fields:
        action: Primary decision (APPROVE/REJECT/NEED_USER/ABSTAIN)
        confidence: Decision confidence (0.0-1.0)
        reason: Human-readable explanation
        risk_assessment: Risk analysis summary
        tokens_used: API tokens consumed (for cost tracking)
        execution_notes: Additional execution guidance
    """
    action: EntryAction = Field(..., description="Entry approval action")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Decision confidence")
    reason: str = Field(..., min_length=1, description="Explanation for decision")
    risk_assessment: Optional[str] = Field(default=None, description="Risk analysis")
    tokens_used: int = Field(default=0, ge=0, description="API tokens consumed")
    execution_notes: Optional[str] = Field(default=None, description="Execution guidance")


class LLMDecider:
    """
    Hands-free decision layer used ONLY at user-interaction points.
    
    Enforces all hard rails before calling any model. Provides rate-limiting
    per symbol and confidence gating. Maintains full audit trail.
    
    Design Principles:
    1. Hard rails are checked FIRST and are never overrideable
    2. Rate limiting prevents excessive API costs
    3. Confidence gating ensures quality decisions
    4. Conservative bias protects capital
    5. Full logging and Slack integration for transparency
    """
    
    def __init__(self, json_client, config: Dict, logger_instance=None, memory=None, slack_notifier=None):
        """
        Initialize LLM Decision Agent.
        
        Args:
            json_client: LLMJsonClient instance for strict JSON responses
            config: Configuration dictionary with LLM settings
            logger_instance: Optional logger instance
            memory: Optional memory system for context
            slack_notifier: Optional Slack notifier for audit trails
        """
        self.client = json_client
        self.config = config
        self.log = logger_instance or logger
        self.memory = memory
        self.slack_notifier = slack_notifier
        
        # Configuration - centralized under config['llm']
        llm_config = config.get("llm", {})
        self.min_confidence = llm_config.get("min_confidence", config.get("LLM_MIN_CONFIDENCE", 0.60))
        self.exit_bias = llm_config.get("exit_bias", config.get("LLM_EXIT_BIAS", "conservative"))
        self.rate_limit_s = llm_config.get("rate_limit_s", config.get("LLM_RATE_LIMIT_S", 30))
        self.max_api_per_scan = llm_config.get("max_api_per_scan", config.get("LLM_MAX_API_PER_SCAN", 4))
        
        # Rate limiting tracking
        self.last_call_times = {}  # symbol -> timestamp
        self.scan_api_count = 0
        self.scan_start_time = time.time()
        
        # Session-level token and cost tracking
        self.session_tokens = {"prompt": 0, "completion": 0, "total": 0}
        self.session_cost_usd = 0.0
        
        # Kill-switch behavior configuration
        self.kill_switch_behavior = llm_config.get("kill_switch_behavior", config.get("LLM_KILL_SWITCH_BEHAVIOR", "halt"))
        
        # Performance counters
        self.counters = {
            "exit_calls_total": 0,
            "exit_sell": 0,
            "exit_hold": 0,
            "exit_wait": 0,
            "exit_abstain": 0,
            "exit_below_confidence": 0,
            "entry_calls_total": 0,
            "entry_approve": 0,
            "entry_reject": 0,
            "entry_need_user": 0,
            "entry_abstain": 0,
            "entry_below_confidence": 0,
            "hard_rails_triggered": 0,
            "rate_limited": 0,
            "json_parse_failures": 0,
        }
        self.log.info(f"[LLM-DECIDER] Initialized with bias={self.exit_bias}, "
                     f"min_confidence={self.min_confidence}, rate_limit={self.rate_limit_s}s")

    def _is_rate_limited(self, symbol: str) -> bool:
        """Check if symbol is rate limited based on last call timestamp."""
        last_call = self.last_call_times.get(symbol, 0)
        return time.time() - last_call < self.rate_limit_s

    def _update_rate_limit(self, symbol: str) -> None:
        """Update rate limit timestamp for symbol."""
        self.last_call_times[symbol] = time.time()

    def reset_scan_budget(self) -> None:
        """Reset per-scan API budget counter. Call at beginning of each scan loop."""
        self.scan_api_count = 0
        self.scan_start_time = time.time()

    def _check_scan_budget(self, symbol: str) -> Optional[ExitDecision]:
        """
        Check if per-scan API budget is exceeded.
        
        Returns ExitDecision/EntryDecision if budget exceeded, None otherwise.
        """
        if self.scan_api_count >= self.max_api_per_scan:
            self.counters["rate_limited"] += 1
            return ExitDecision(
                action="WAIT",
                confidence=0.0,
                reason="BLOCKED_RATE_LIMIT_SCAN_BUDGET",
                risk_assessment="Per-scan API budget exceeded",
                defer_minutes=5
            )

    def _validate_dual_gate_safety(self, objective_trigger: bool, llm_confidence: float, action: str) -> bool:
        """
        Dual-gate safety: Both objective rule AND LLM confidence must pass.
        
        Args:
            objective_trigger: Whether objective rule (profit/stop/time) triggered
            llm_confidence: LLM decision confidence (0.0-1.0)
            action: Proposed action (SELL/HOLD/APPROVE/REJECT)
            
        Returns:
            True if both gates pass, False otherwise
        """
        # Gate 1: Objective rule must trigger for actionable decisions
        # Option A (recommended): Gate 1 only for SELL/APPROVE actions
        if action in ("SELL", "APPROVE") and not objective_trigger:
            self.log.warning(f"[DUAL-GATE] Objective rule not met for {action}")
            return False
            
        # Gate 2: LLM confidence must meet minimum threshold for all actions
        if llm_confidence < self.min_confidence:
            self.log.warning(f"[DUAL-GATE] Confidence {llm_confidence:.2f} < {self.min_confidence:.2f}")
            return False
            
        return True

    def _check_objective_exit_triggers(self, ctx: Dict[str, Any]) -> bool:
        """
        Check if objective exit rules are triggered (profit/stop/time).
        
        Args:
            ctx: Trading context with P&L and timing data
            
        Returns:
            True if objective exit conditions are met
        """
        pnl = ctx.get("pnl", {})
        pnl_pct = pnl.get("pct", 0)
        time_to_close = ctx.get("time_to_close_min", 999)
        
        # Profit target reached (15%+)
        if pnl_pct >= 15.0:
            return True
            
        # Stop loss triggered (-25%)
        if pnl_pct <= -25.0:
            return True
            
        # End-of-day force close (< 15 min to close)
        if time_to_close <= 15:
            return True
            
        return False

    def _check_objective_entry_triggers(self, order_ctx: Dict[str, Any]) -> bool:
        """
        Check if objective entry rules are triggered (liquidity/risk/greeks).
        
        Args:
            order_ctx: Order context with risk metrics and liquidity data
            
        Returns:
            True if objective triggers met, False otherwise
        """
        # Enhanced liquidity checks
        spread_bps = order_ctx.get("spread_bps", 0)
        if spread_bps > 500:  # > 5% spread
            return False
            
        # Volume and Open Interest checks
        volume = order_ctx.get("volume", 0)
        open_interest = order_ctx.get("open_interest", 0)
        
        if volume < 100:  # Minimum volume threshold
            return False
            
        if open_interest < 50:  # Minimum OI for liquidity
            return False
            
        # Greeks validation
        delta = order_ctx.get("delta")
        gamma = order_ctx.get("gamma") 
        theta = order_ctx.get("theta")
        
        # Delta should be reasonable for ATM options (0.4-0.6 range)
        if delta and (delta < 0.3 or delta > 0.7):
            return False
            
        # Theta decay shouldn't be excessive for 0DTE
        if theta and theta < -0.10:  # Excessive time decay
            return False
            
        return True

    def _check_hard_rails(self, ctx: Dict[str, Any]) -> Optional[ExitDecision]:
        """
        Check hard rails that can never be overridden by LLM.
        
        Returns ExitDecision if hard rail triggered, None otherwise.
        """
        hard_rails = ctx.get("hard_rails", {})
        
        # Kill switch or circuit breaker active
        if hard_rails.get("kill_switch") or hard_rails.get("circuit_breaker"):
            self.counters["hard_rails_triggered"] += 1
            return ExitDecision(
                action="ABSTAIN",
                confidence=1.0,
                reason="Safety rail active (kill switch or circuit breaker)"
            )
        
        # Kill switch check with configurable behavior
        if ctx.get("kill_switch_active", False):
            self.counters["hard_rails_triggered"] += 1
            if self.kill_switch_behavior == "flatten":
                return ExitDecision(
                    action="SELL",
                    confidence=1.0,
                    reason="Kill switch activated - flattening positions"
                )
            else:  # Default "halt" behavior
                return ExitDecision(
                    action="WAIT",
                    confidence=1.0,
                    reason="Kill switch activated - halting trading",
                    defer_minutes=60
                )
        
        # Force close time (15:45 ET) with early-close awareness
        current_time = ctx.get("current_time")
        market_close_time = ctx.get("market_close_time", "15:45")  # Default or early close
        
        if hard_rails.get("force_close_now") or (current_time and current_time >= market_close_time):
            self.counters["hard_rails_triggered"] += 1
            return ExitDecision(
                action="SELL",
                confidence=1.0,
                reason=f"Time >= {market_close_time} ET (force close)"
            )
        
        # Stop loss at -25%
        pnl_pct = ctx.get("pnl", {}).get("pct", 0)
        if pnl_pct <= -25.0:
            self.counters["hard_rails_triggered"] += 1
            return ExitDecision(
                action="SELL",
                confidence=1.0,
                reason=f"Stop loss triggered at {pnl_pct:.1f}% (<= -25%)"
            )
        
        return None

    def get_session_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive session statistics including counters, tokens, and costs.
        
        Returns:
            Dictionary with session performance metrics
        """
        total_decisions = (
            self.counters["exit_calls_total"] + 
            self.counters["entry_calls_total"]
        )
        
        return {
            "session_duration_minutes": (time.time() - self.scan_start_time) / 60,
            "total_api_calls": self.scan_api_count,
            "total_decisions": total_decisions,
            "counters": self.counters.copy(),
            "tokens": self.session_tokens.copy(),
            "estimated_cost_usd": self.session_cost_usd,
            "api_calls_per_scan": self.scan_api_count,
            "scan_budget_remaining": max(0, self.max_api_per_scan - self.scan_api_count)
        }

    def _log_and_audit_exit(self, symbol: str, decision: ExitDecision, ctx: Dict[str, Any], correlation_id: str) -> None:
        """Log exit decision and send Slack audit trail."""
        self.log.info(f"[EXIT-LLM] {symbol}: {decision.action} (confidence={decision.confidence:.2f}) - {decision.reason}")
        
        if self.slack_notifier:
            # Rich blocks for actionable decisions, heartbeats for others
            if decision.action in ["SELL"]:
                message = f"🤖 **LLM EXIT DECISION**\n"
                message += f"**Symbol:** {symbol}\n"
                message += f"**Action:** {decision.action}\n"
                message += f"**Confidence:** {decision.confidence:.2f}\n"
                message += f"**Reason:** {decision.reason}\n"
                message += f"**Decision ID:** {correlation_id}\n"
                if decision.risk_assessment:
                    message += f"**Risk:** {decision.risk_assessment}\n"
                self.slack_notifier.send_message(message)
            else:
                # Single-line heartbeat for non-actionable decisions
                self.slack_notifier.send_message(f"🤖 {symbol} {decision.action} ({decision.confidence:.2f}) - {decision.reason}")

    def _log_and_audit_entry(self, symbol: str, decision: EntryDecision, order_ctx: Dict[str, Any], correlation_id: str) -> None:
        """Log entry decision and send Slack audit trail."""
        self.log.info(f"[ENTRY-LLM] {symbol}: {decision.action} (confidence={decision.confidence:.2f}) - {decision.reason}")
        
        if self.slack_notifier:
            # Rich blocks for actionable decisions, heartbeats for others
            if decision.action in ["APPROVE", "REJECT"]:
                message = f"🤖 **LLM ENTRY DECISION**\n"
                message += f"**Symbol:** {symbol}\n"
                message += f"**Action:** {decision.action}\n"
                message += f"**Confidence:** {decision.confidence:.2f}\n"
                message += f"**Reason:** {decision.reason}\n"
                message += f"**Decision ID:** {correlation_id}\n"
                if decision.risk_assessment:
                    message += f"**Risk:** {decision.risk_assessment}\n"
                self.slack_notifier.send_message(message)
            else:
                # Single-line heartbeat for non-actionable decisions
                self.slack_notifier.send_message(f"🤖 {symbol} {decision.action} ({decision.confidence:.2f}) - {decision.reason}")

    def _build_exit_messages(self, ctx: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Compose structured prompt for exit decisions.
        
        Args:
            ctx: Trading context with market data, position info, etc.
            
        Returns:
            List of messages for LLM chat completion
        """
        bias = self.exit_bias.upper()
        
        system_prompt = f"""You are an options trade EXIT arbiter. OBEY HARD RULES FIRST:

1) If force_close_now==true → SELL immediately
2) If pnl.pct <= -25 → SELL immediately  
3) If kill_switch or circuit_breaker → ABSTAIN immediately

Policy bias: {bias}
- CONSERVATIVE: Protect capital, prefer SELL when momentum weakens near EOD, take profits early
- BALANCED: Standard profit/loss targets with moderate risk tolerance
- AGGRESSIVE: Hold for maximum gains, higher risk tolerance

Consider:
- Current P&L vs targets (profit_target_pct, min_profit_consider_pct)
- Time to market close (time_to_close_min)
- Market momentum (ha_trend, rsi2, vwap_rel)
- Volatility environment (vix, iv)
- Recent trade history patterns (memory)
- Option liquidity (spread_bps)

Reply ONLY with strict JSON matching the schema. No additional text."""

        schema = """{
  "action": "SELL|HOLD|WAIT|ABSTAIN",
  "confidence": 0.0-1.0,
  "reason": "string explanation",
  "defer_minutes": 1-30,
  "expected_exit_price": null|number,
  "time_horizon_min": null|number
}"""

        context_str = self.client.json_dumps(ctx)
        
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"CONTEXT:\n{context_str}\n\nSCHEMA:\n{schema}"}
        ]

    def decide_exit(self, symbol: str, ctx: Dict[str, Any]) -> ExitDecision:
        """
        Make exit decision for position using LLM with hard rail enforcement.
        
        Args:
            symbol: Trading symbol (e.g., "SPY")
            ctx: Trading context dictionary with position, market, and policy data
            
        Returns:
            ExitDecision with action, confidence, and reasoning
        """
        self.counters["exit_calls_total"] += 1
        
        # STEP 1: Check hard rails FIRST (never overrideable)
        hard_rail_decision = self._check_hard_rails(ctx)
        if hard_rail_decision:
            self.log.info(f"[EXIT-LLM] {symbol}: Hard rail triggered - {hard_rail_decision.reason}")
            return hard_rail_decision
        
        # Per-scan API budget check
        budget_check = self._check_scan_budget(symbol)
        if budget_check:
            self.counters["exit_wait"] += 1
            return budget_check

        # Rate limiting check
        if self._is_rate_limited(symbol):
            self.counters["exit_wait"] += 1
            return ExitDecision(
                action="WAIT",
                confidence=0.0,
                reason="BLOCKED_RATE_LIMIT",
                risk_assessment="Rate limited",
                defer_minutes=int(self.rate_limit_s / 60) + 1
            )

        # STEP 3: Call LLM with strict JSON enforcement
        try:
            messages = self._build_exit_messages(ctx)
            raw_response = self.client.strict_json(messages, escalate_if_low=True)
            
            # Normalize schema edge cases before validation
            try:
                if isinstance(raw_response, dict) and "defer_minutes" in raw_response:
                    dm = raw_response.get("defer_minutes")
                    if dm is None:
                        # leave as None to allow default in model
                        pass
                    else:
                        # Cast to int and clamp to [1, 30]
                        dm_int = int(dm)
                        if dm_int < 1:
                            self.log.debug(f"[LLM-NORMALIZE] defer_minutes {dm} -> 1")
                            dm_int = 1
                        elif dm_int > 30:
                            self.log.debug(f"[LLM-NORMALIZE] defer_minutes {dm} -> 30")
                            dm_int = 30
                        raw_response["defer_minutes"] = dm_int
            except Exception as _norm_e:
                # On any normalization error, fall back to safe default (2)
                self.log.debug(f"[LLM-NORMALIZE] Error normalizing defer_minutes: {_norm_e}")
                raw_response["defer_minutes"] = 2
            
            # Increment scan API counter
            self.scan_api_count += 1
            
            # Track tokens if available
            if "tokens_used" in raw_response:
                tokens = raw_response["tokens_used"]
                self.session_tokens["prompt"] += tokens.get("prompt_tokens", 0)
                self.session_tokens["completion"] += tokens.get("completion_tokens", 0)
                self.session_tokens["total"] += tokens.get("total_tokens", 0)
            
            # Parse and validate response
            decision = ExitDecision(**raw_response)
            
        except ValidationError as e:
            self.counters["json_parse_failures"] += 1
            self.log.warning(f"[EXIT-LLM] {symbol}: Invalid JSON schema - {e}")
            return ExitDecision(
                action="WAIT",
                confidence=0.0,
                reason="Invalid LLM response format",
                defer_minutes=2
            )
        except Exception as e:
            self.counters["json_parse_failures"] += 1
            self.log.error(f"[EXIT-LLM] {symbol}: LLM call failed - {e}")
            return ExitDecision(
                action="WAIT",
                confidence=0.0,
                reason=f"LLM error: {str(e)[:100]}",
                defer_minutes=5
            )
        
        # STEP 4: Dual-gate safety validation
        objective_trigger = self._check_objective_exit_triggers(ctx)
        if not self._validate_dual_gate_safety(objective_trigger, decision.confidence, decision.action):
            self.counters["exit_below_confidence"] += 1
            return ExitDecision(
                action="WAIT",
                confidence=decision.confidence,
                reason=f"BLOCKED_DUAL_GATE: objective={objective_trigger}, confidence={decision.confidence:.2f}",
                risk_assessment="Dual-gate safety check failed",
                defer_minutes=2
            )
        
        # STEP 5: Update rate limit and counters
        self._update_rate_limit(symbol)
        
        # Update action counters
        action_lower = decision.action.lower()
        counter_key = f"exit_{action_lower}"
        if counter_key in self.counters:
            self.counters[counter_key] += 1
        
        # Log decision and send Slack audit with correlation ID
        correlation_id = f"{symbol}_{int(time.time())}"
        self._log_and_audit_exit(symbol, decision, ctx, correlation_id)
        
        return decision

    def _build_entry_messages(self, ctx: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Compose structured prompt for entry approval decisions.
        
        Args:
            ctx: Order context with risk metrics, liquidity, etc.
            
        Returns:
            List of messages for LLM chat completion
        """
        system_prompt = """You are a Robinhood Review Order approval arbiter. 

Your job is to approve or reject orders that have passed all pre-LLM gates and safety checks.

HARD INVALIDATORS (return REJECT without analysis):
- position_limits_ok == false
- account_risk_ok == false  
- greeks_ok == false

APPROVAL CRITERIA:
- Narrow bid-ask spreads (low spread_bps)
- Good liquidity (high liquidity_score)
- Fair pricing vs market mid
- Reasonable slippage expectations
- Appropriate VIX environment

Use APPROVE for good setups, NEED_USER for marginal cases requiring human judgment.

Reply ONLY with strict JSON matching the schema."""

        schema = """{
  "action": "APPROVE|REJECT|NEED_USER|ABSTAIN",
  "confidence": 0.0-1.0,
  "reason": "string explanation",
  "risk_assessment": "string|null",
  "execution_notes": "string|null"
}"""

        context_str = self.client.json_dumps(ctx)
        
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"ORDER_CONTEXT:\n{context_str}\n\nSCHEMA:\n{schema}"}
        ]

    def decide_entry(self, symbol: str, order_ctx: Dict[str, Any]) -> EntryDecision:
        """
        Make entry approval decision for Robinhood Review screen.
        
        Args:
            symbol: Trading symbol
            order_ctx: Order context with risk metrics and liquidity data
            
        Returns:
            EntryDecision with approval/rejection and reasoning
        """
        # Check hard invalidators FIRST
        if not order_ctx.get("position_limits_ok", True):
            self.counters["entry_reject"] += 1
            return EntryDecision(
                action="REJECT",
                confidence=1.0,
                reason="Position limits exceeded"
            )
        
        if not order_ctx.get("account_risk_ok", True):
            self.counters["entry_reject"] += 1
            return EntryDecision(
                action="REJECT", 
                confidence=1.0,
                reason="Account risk limits exceeded"
            )
        
        if not order_ctx.get("greeks_ok", True):
            self.counters["entry_reject"] += 1
            return EntryDecision(
                action="REJECT",
                confidence=1.0,
                reason="Option Greeks outside acceptable range"
            )
        
        # Per-scan API budget check
        budget_check = self._check_scan_budget(symbol)
        if budget_check:
            self.counters["entry_abstain"] += 1
            return EntryDecision(
                action="ABSTAIN",
                confidence=0.0,
                reason="BLOCKED_RATE_LIMIT_SCAN_BUDGET"
            )

        # Rate limiting check
        if self._is_rate_limited(symbol):
            self.counters["rate_limited"] += 1
            return EntryDecision(
                action="NEED_USER",
                confidence=0.5,
                reason="Rate limited - require manual review"
            )
        
        # Call LLM for approval decision
        try:
            messages = self._build_entry_messages(order_ctx)
            raw_response = self.client.strict_json(messages, escalate_if_low=True)
            
            # Increment scan API counter
            self.scan_api_count += 1
            
            # Track tokens if available
            if "tokens_used" in raw_response:
                tokens = raw_response["tokens_used"]
                self.session_tokens["prompt"] += tokens.get("prompt_tokens", 0)
                self.session_tokens["completion"] += tokens.get("completion_tokens", 0)
                self.session_tokens["total"] += tokens.get("total_tokens", 0)
            
            decision = EntryDecision(**raw_response)
            
        except (ValidationError, Exception) as e:
            self.counters["json_parse_failures"] += 1
            self.log.warning(f"[ENTRY-LLM] {symbol}: LLM error - {e}")
            return EntryDecision(
                action="NEED_USER",
                confidence=0.0,
                reason="LLM error - require manual review"
            )
        
        # STEP 4: Dual-gate safety validation for entry decisions
        objective_trigger = self._check_objective_entry_triggers(order_ctx)
        if not self._validate_dual_gate_safety(objective_trigger, decision.confidence, decision.action):
            self.counters["entry_below_confidence"] += 1
            return EntryDecision(
                action="NEED_USER",
                confidence=decision.confidence,
                reason=f"BLOCKED_DUAL_GATE: objective={objective_trigger}, confidence={decision.confidence:.2f}",
                risk_assessment="Dual-gate safety check failed"
            )

        # Update counters and rate limit
        self._update_rate_limit(symbol)
        
        action_lower = decision.action.lower()
        if action_lower in ["approve", "need_user", "reject"]:
            self.counters[f"entry_{action_lower}"] += 1
        
        # Log decision and send Slack audit with correlation ID
        correlation_id = f"{symbol}_entry_{int(time.time())}"
        self._log_and_audit_entry(symbol, decision, order_ctx, correlation_id)
        
        return decision

    def get_session_stats(self) -> Dict[str, Any]:
        """
        Get session statistics for end-of-day reporting.
        
        Returns:
            Dictionary with decision counters and performance metrics
        """
        total_exits = sum(self.counters[k] for k in ["exit_sell", "exit_hold", "exit_wait", "exit_abstain"])
        total_entries = sum(self.counters[k] for k in ["entry_approve", "entry_need_user", "entry_reject"])
        
        return {
            "llm_decisions": {
                "exit_decisions": {
                    "total": total_exits,
                    "sell": self.counters["exit_sell"],
                    "hold": self.counters["exit_hold"], 
                    "wait": self.counters["exit_wait"],
                    "abstain": self.counters["exit_abstain"]
                },
                "entry_decisions": {
                    "total": total_entries,
                    "approve": self.counters["entry_approve"],
                    "need_user": self.counters["entry_need_user"],
                    "reject": self.counters["entry_reject"]
                },
                "quality_metrics": {
                    "below_confidence": self.counters["exit_below_confidence"],
                    "json_failures": self.counters["json_parse_failures"],
                    "rate_limited": self.counters["rate_limited"],
                    "hard_rails": self.counters["hard_rails_triggered"]
                }
            }
        }

    def _send_exit_decision_audit(self, symbol: str, decision: ExitDecision, ctx: Dict[str, Any]) -> None:
        """
        Send comprehensive Slack audit trail for exit decisions.
        
        Args:
            symbol: Trading symbol
            decision: LLM exit decision
            ctx: Trading context used for decision
        """
        if not self.slack:
            return
            
        try:
            # Extract key context for audit
            pnl = ctx.get("pnl", {})
            pnl_pct = pnl.get("pct", 0)
            pnl_dollar = pnl.get("dollar", 0)
            time_to_close = ctx.get("time_to_close_min", "N/A")
            
            # Determine message color based on decision
            color = {
                "SELL": "#FF6B6B",  # Red for sell
                "HOLD": "#4ECDC4",  # Teal for hold
                "WAIT": "#FFE66D",  # Yellow for wait
                "ABSTAIN": "#A8E6CF"  # Light green for abstain
            }.get(decision.action, "#95A5A6")
            
            # Normalize Slack messaging - use structured format for actionable events
            if decision.action in ("SELL", "HOLD"):
                # Rich block for actionable decisions
                audit_msg = f"""🤖 **LLM EXIT DECISION**
**Symbol:** {symbol}
**Action:** {decision.action}
**Confidence:** {decision.confidence:.2f}
**Reason:** {decision.reason}

**Position Context:**
• P&L: {pnl_pct:+.1f}% (${pnl_dollar:+.2f})
• Time to Close: {time_to_close} min
• Exit Bias: {self.exit_bias.upper()}

**Decision ID:** {int(time.time())}-{symbol}-EXIT"""
            else:
                # Single-line heartbeat for non-actionable decisions
                audit_msg = f"🤖 {symbol} EXIT: {decision.action} ({decision.confidence:.2f}) - {decision.reason[:50]}..."

            # Send to Slack with appropriate formatting
            if hasattr(self.slack, 'send_message'):
                self.slack.send_message(audit_msg)
            elif hasattr(self.slack, 'send_heartbeat'):
                self.slack.send_heartbeat(audit_msg)
                
        except Exception as e:
            self.log.warning(f"[LLM-AUDIT] Failed to send exit decision audit: {e}")

    def _send_entry_decision_audit(self, symbol: str, decision: 'EntryDecision', order_ctx: Dict[str, Any]) -> None:
        """
        Send comprehensive Slack audit trail for entry decisions.
        
        Args:
            symbol: Trading symbol
            decision: LLM entry decision
            order_ctx: Order context used for decision
        """
        if not self.slack:
            return
            
        try:
            # Extract key order context for audit
            strike = order_ctx.get("strike", "N/A")
            premium = order_ctx.get("premium", 0)
            quantity = order_ctx.get("quantity", 0)
            total_cost = premium * quantity * 100 if premium and quantity else 0
            spread_bps = order_ctx.get("spread_bps", "N/A")
            liquidity_score = order_ctx.get("liquidity_score", "N/A")
            
            # Determine message color based on decision
            color = {
                "APPROVE": "#2ECC71",    # Green for approve
                "REJECT": "#E74C3C",     # Red for reject  
                "NEED_USER": "#F39C12",  # Orange for need user
                "ABSTAIN": "#95A5A6"     # Gray for abstain
            }.get(decision.action, "#95A5A6")
            
            # Normalize Slack messaging - use structured format for actionable events
            if decision.action in ("APPROVE", "REJECT"):
                # Rich block for actionable decisions
                audit_msg = f"""🤖 **LLM ENTRY DECISION**
**Symbol:** {symbol}
**Action:** {decision.action}
**Confidence:** {decision.confidence:.2f}
**Reason:** {decision.reason}

**Order Context:**
• Strike: ${strike}
• Premium: ${premium:.2f}
• Quantity: {quantity}
• Total Cost: ${total_cost:.2f}
• Spread: {spread_bps} bps
• Liquidity: {liquidity_score}

**Risk Assessment:** {getattr(decision, 'risk_assessment', 'N/A')}
**Decision ID:** {int(time.time())}-{symbol}-ENTRY"""
            else:
                # Single-line heartbeat for non-actionable decisions
                audit_msg = f"🤖 {symbol} ENTRY: {decision.action} ({decision.confidence:.2f}) - {decision.reason[:50]}..."

            # Send to Slack with appropriate formatting
            if hasattr(self.slack, 'send_message'):
                self.slack.send_message(audit_msg)
            elif hasattr(self.slack, 'send_heartbeat'):
                self.slack.send_heartbeat(audit_msg)
                
        except Exception as e:
            self.log.warning(f"[LLM-AUDIT] Failed to send entry decision audit: {e}")

    def _send_session_summary_audit(self) -> None:
        """
        Send end-of-session LLM decision summary to Slack.
        """
        if not self.slack:
            return
            
        try:
            stats = self.get_session_stats()
            llm_stats = stats["llm_decisions"]
            
            exit_stats = llm_stats["exit_decisions"]
            entry_stats = llm_stats["entry_decisions"]
            quality_stats = llm_stats["quality_metrics"]
            
            summary_msg = f"""📊 **LLM DECISION SESSION SUMMARY**

**Exit Decisions:** {exit_stats['total']}
• SELL: {exit_stats['sell']} | HOLD: {exit_stats['hold']}
• WAIT: {exit_stats['wait']} | ABSTAIN: {exit_stats['abstain']}

**Entry Decisions:** {entry_stats['total']}
• APPROVE: {entry_stats['approve']} | REJECT: {entry_stats['reject']}
• NEED_USER: {entry_stats['need_user']}

**Quality Metrics:**
• Below Confidence: {quality_stats['below_confidence']}
• JSON Failures: {quality_stats['json_failures']}
• Rate Limited: {quality_stats['rate_limited']}
• Hard Rails: {quality_stats['hard_rails']}

**Config:** {self.exit_bias.upper()} bias, {self.min_confidence:.2f} min confidence"""

            if hasattr(self.slack, 'send_message'):
                self.slack.send_message(summary_msg)
            elif hasattr(self.slack, 'send_heartbeat'):
                self.slack.send_heartbeat(summary_msg)
                
        except Exception as e:
            self.log.warning(f"[LLM-AUDIT] Failed to send session summary: {e}")
