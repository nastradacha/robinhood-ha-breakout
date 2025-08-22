#!/usr/bin/env python3
"""
LLM Decision Agent Acceptance Tests

Fast-running tests to validate unattended mode functionality:
1. Dry-run mode with no prompts
2. Confidence gating blocks low-confidence decisions
3. Monitor exit rails trigger automatic exits
4. Dual-gate safety validation
5. Slack audit trail generation
"""

import pytest
import logging
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.llm_decider import LLMDecider, ExitDecision, EntryDecision
from utils.llm_json_client import LLMJsonClient


class TestLLMAcceptance:
    """Acceptance tests for LLM Decision Agent unattended mode."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.mock_ensemble = Mock()
        self.mock_logger = Mock()
        self.mock_slack = Mock()
        
        # Mock LLM client
        self.mock_json_client = Mock(spec=LLMJsonClient)
        
        # Test configuration
        self.config = {
            "llm": {
                "min_confidence": 0.60,
                "exit_bias": "conservative",
                "rate_limit_s": 1,  # Fast for testing
                "max_api_per_scan": 4
            }
        }
        
        # Initialize LLM decider
        self.llm_decider = LLMDecider(
            self.mock_json_client,
            self.config,
            self.mock_logger,
            slack_notifier=self.mock_slack
        )

    def test_dry_run_no_prompts(self):
        """Test: Dry-run mode should generate decisions without user prompts."""
        # Mock high-confidence exit decision
        self.mock_json_client.strict_json.return_value = {
            "action": "SELL",
            "confidence": 0.85,
            "reason": "Profit target reached at 15.2%",
            "risk_assessment": "Low risk exit"
        }
        
        # Test context with profit trigger
        exit_ctx = {
            "pnl": {"pct": 15.2, "dollar": 152.0},
            "time_to_close_min": 45,
            "hard_rails": {}
        }
        
        # Execute exit decision
        decision = self.llm_decider.decide_exit("SPY", exit_ctx)
        
        # Validate decision
        assert decision.action == "SELL"
        assert decision.confidence == 0.85
        assert "Profit target reached" in decision.reason
        
        # Verify no user interaction required
        assert self.mock_json_client.strict_json.called
        
        # Verify Slack audit trail
        self.mock_slack.send_message.assert_called_once()

    def test_confidence_gate_blocks_low_confidence(self):
        """Test: Low confidence decisions should be blocked and logged."""
        # Mock low-confidence decision
        self.mock_json_client.strict_json.return_value = {
            "action": "SELL",
            "confidence": 0.45,  # Below 0.60 threshold
            "reason": "Uncertain market conditions",
            "risk_assessment": "High uncertainty"
        }
        
        # Test context with profit trigger
        exit_ctx = {
            "pnl": {"pct": 16.0, "dollar": 160.0},
            "time_to_close_min": 30,
            "hard_rails": {}
        }
        
        # Execute exit decision
        decision = self.llm_decider.decide_exit("SPY", exit_ctx)
        
        # Should be blocked due to low confidence
        assert decision.action == "WAIT"
        assert "BLOCKED_DUAL_GATE" in decision.reason
        assert decision.confidence == 0.45
        
        # Verify counter increment
        assert self.llm_decider.counters["exit_below_confidence"] == 1

    def test_monitor_exit_rails_auto_sell(self):
        """Test: Monitor should auto-exit on profit/stop/EOD without prompts."""
        # Mock confident exit decision
        self.mock_json_client.strict_json.return_value = {
            "action": "SELL",
            "confidence": 0.90,
            "reason": "End-of-day force close triggered",
            "risk_assessment": "Time-based exit"
        }
        
        # Test context with EOD trigger
        exit_ctx = {
            "pnl": {"pct": 8.5, "dollar": 85.0},
            "time_to_close_min": 10,  # < 15 min trigger
            "hard_rails": {}
        }
        
        # Execute exit decision
        decision = self.llm_decider.decide_exit("SPY", exit_ctx)
        
        # Should auto-sell due to EOD + high confidence
        assert decision.action == "SELL"
        assert decision.confidence == 0.90
        
        # Verify objective trigger worked
        objective_trigger = self.llm_decider._check_objective_exit_triggers(exit_ctx)
        assert objective_trigger is True

    def test_hard_rails_override_llm(self):
        """Test: Hard rails should always override LLM decisions."""
        # Test context with kill switch active
        exit_ctx = {
            "pnl": {"pct": 5.0, "dollar": 50.0},
            "time_to_close_min": 60,
            "hard_rails": {"kill_switch": True}
        }
        
        # Execute exit decision (LLM should not be called)
        decision = self.llm_decider.decide_exit("SPY", exit_ctx)
        
        # Should abstain due to kill switch
        assert decision.action == "ABSTAIN"
        assert "kill switch" in decision.reason.lower()
        assert decision.confidence == 1.0
        
        # LLM should not have been called
        self.mock_json_client.strict_json.assert_not_called()

    def test_entry_dual_gate_validation(self):
        """Test: Entry decisions require both objective rules and confidence."""
        # Mock high-confidence entry decision
        self.mock_json_client.strict_json.return_value = {
            "action": "APPROVE",
            "confidence": 0.80,
            "reason": "Good liquidity and fair pricing",
            "risk_assessment": "Low risk entry"
        }
        
        # Test context with good objective conditions
        entry_ctx = {
            "position_limits_ok": True,
            "account_risk_ok": True,
            "greeks_ok": True,
            "spread_bps": 25,  # Good spread
            "liquidity_score": 0.8,  # Good liquidity
            "volume": 200,  # Sufficient volume
            "open_interest": 100,  # Sufficient OI
            "delta": 0.5,  # Good delta for ATM
            "theta": -0.05  # Reasonable theta decay
        }
        
        # Execute entry decision
        decision = self.llm_decider.decide_entry("SPY", entry_ctx)
        
        # Should approve with both gates passing
        assert decision.action == "APPROVE"
        assert decision.confidence == 0.80
        
        # Verify objective trigger
        objective_trigger = self.llm_decider._check_objective_entry_triggers(entry_ctx)
        assert objective_trigger is True

    def test_entry_blocked_poor_liquidity(self):
        """Test: Entry should be blocked with poor liquidity despite high confidence."""
        # Mock high-confidence decision
        self.mock_json_client.strict_json.return_value = {
            "action": "APPROVE",
            "confidence": 0.85,
            "reason": "Strong signal detected",
            "risk_assessment": "Good setup"
        }
        
        # Test context with poor liquidity
        entry_ctx = {
            "position_limits_ok": True,
            "account_risk_ok": True,
            "greeks_ok": True,
            "spread_bps": 100,  # Wide spread
            "liquidity_score": 0.3  # Poor liquidity
        }
        
        # Execute entry decision
        decision = self.llm_decider.decide_entry("SPY", entry_ctx)
        
        # Should be blocked due to poor objective conditions
        assert decision.action == "NEED_USER"
        assert "BLOCKED_DUAL_GATE" in decision.reason
        assert "objective=False" in decision.reason

    def test_rate_limiting_enforcement(self):
        """Test: Rate limiting should prevent excessive API calls."""
        # First call should succeed
        self.mock_json_client.strict_json.return_value = {
            "action": "HOLD",
            "confidence": 0.70,
            "reason": "Market conditions stable"
        }
        
        exit_ctx = {
            "pnl": {"pct": 5.0, "dollar": 50.0},
            "time_to_close_min": 60,
            "hard_rails": {}
        }
        
        # First call
        decision1 = self.llm_decider.decide_exit("SPY", exit_ctx)
        assert decision1.action == "HOLD"
        
        # Second call immediately (should be rate limited)
        decision2 = self.llm_decider.decide_exit("SPY", exit_ctx)
        assert decision2.action == "WAIT"
        assert "Rate limited" in decision2.reason

    def test_slack_audit_trail_structure(self):
        """Test: Slack notifications should have consistent structure."""
        # Mock decision
        self.mock_json_client.strict_json.return_value = {
            "action": "SELL",
            "confidence": 0.75,
            "reason": "Profit target achieved",
            "risk_assessment": "Low risk exit"
        }
        
        exit_ctx = {
            "pnl": {"pct": 15.5, "dollar": 155.0},
            "time_to_close_min": 30,
            "hard_rails": {}
        }
        
        # Execute decision
        decision = self.llm_decider.decide_exit("SPY", exit_ctx)
        
        # Verify Slack was called
        self.mock_slack.send_message.assert_called_once()
        
        # Check message structure
        call_args = self.mock_slack.send_message.call_args[0][0]
        assert "🤖 **LLM EXIT DECISION**" in call_args
        assert "**Symbol:** SPY" in call_args

    def test_rate_limiting_enforcement(self):
        """Test: Rate limiting should prevent excessive API calls."""
        # First call should succeed
        self.mock_json_client.strict_json.return_value = {
            "action": "HOLD",
            "confidence": 0.70,
            "reason": "Market conditions stable"
        }
        
        exit_ctx = {
            "pnl": {"pct": 5.0, "dollar": 50.0},
            "time_to_close_min": 60,
            "hard_rails": {}
        }
        
        # First call
        decision1 = self.llm_decider.decide_exit("SPY", exit_ctx)
        assert decision1.action == "HOLD"
        
        # Second call immediately (should be rate limited)
        decision2 = self.llm_decider.decide_exit("SPY", exit_ctx)
        assert decision2.action == "WAIT"
        assert "BLOCKED_RATE_LIMIT" in decision2.reason

    def test_slack_audit_trail_structure(self):
        """Test: Slack notifications should have consistent structure."""
        # Mock decision
        self.mock_json_client.strict_json.return_value = {
            "action": "SELL",
            "confidence": 0.75,
            "reason": "Profit target achieved",
            "risk_assessment": "Low risk exit"
        }
        
        exit_ctx = {
            "pnl": {"pct": 15.5, "dollar": 155.0},
            "time_to_close_min": 30,
            "hard_rails": {}
        }
        
        # Execute decision
        decision = self.llm_decider.decide_exit("SPY", exit_ctx)
        
        # Verify Slack was called
        self.mock_slack.send_message.assert_called_once()
        
        # Check message structure
        call_args = self.mock_slack.send_message.call_args[0][0]
        assert "🤖 **LLM EXIT DECISION**" in call_args
        assert "**Symbol:** SPY" in call_args
        assert "**Action:** SELL" in call_args
        assert "**Confidence:** 0.75" in call_args
        assert "**Decision ID:**" in call_args

def run_acceptance_tests():
    """Run all acceptance tests and report results."""
    pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "-x"  # Stop on first failure
    ])


if __name__ == "__main__":
    run_acceptance_tests()
