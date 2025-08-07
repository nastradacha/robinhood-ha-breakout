#!/usr/bin/env python3
"""
Ensemble LLM Decision Engine (v0.6.0)

Implements a two-model ensemble (GPT-4o-mini + DeepSeek-V2) with majority voting,
tie-breaking, and robust fallback handling for enhanced trading decision quality.

Key Features:
- Two-model ensemble voting for improved decision reliability
- Majority vote with tie-breaking by highest confidence
- Automatic fallback to single-model if one provider fails
- Configurable model selection via config.yaml
- Comprehensive error handling and logging

Ensemble Logic:
1. Query both models with identical payload
2. Collect decisions and confidences
3. Apply majority vote on {CALL, PUT, NO_TRADE}
4. Break ties by choosing higher confidence candidate
5. Set final confidence = average of winning class confidences
6. Fall back to single model if one provider fails

Author: Robinhood HA Breakout System
Version: 0.6.0
"""

import logging
from typing import Dict, List, Tuple, Optional
from collections import Counter

from .llm import LLMClient, TradeDecision, load_config

logger = logging.getLogger(__name__)


class EnsembleLLM:
    """
    Two-model ensemble LLM client with majority voting and tie-breaking.
    
    Combines decisions from multiple LLM providers to improve trading decision
    quality through consensus and reduces single-model bias.
    """
    
    def __init__(self):
        """Initialize ensemble with configured models."""
        self.config = load_config()
        self.enabled = self.config.get("ENSEMBLE_ENABLED", True)
        self.models = self.config.get("ENSEMBLE_MODELS", ["gpt-4o-mini", "deepseek-chat"])
        
        if not self.enabled:
            logger.info("[ENSEMBLE] Ensemble disabled, using single-model fallback")
            return
            
        if len(self.models) < 2:
            logger.warning(f"[ENSEMBLE] Less than 2 models configured: {self.models}, disabling ensemble")
            self.enabled = False
            return
            
        # Initialize LLM clients for each model
        self.clients = {}
        for model in self.models:
            try:
                self.clients[model] = LLMClient(model=model)
                logger.info(f"[ENSEMBLE] Initialized {model} client")
            except Exception as e:
                logger.warning(f"[ENSEMBLE] Failed to initialize {model}: {e}")
        
        if len(self.clients) < 2:
            logger.warning(f"[ENSEMBLE] Only {len(self.clients)} clients available, disabling ensemble")
            self.enabled = False
        else:
            logger.info(f"[ENSEMBLE] Ensemble enabled with {len(self.clients)} models: {list(self.clients.keys())}")
    
    def choose_trade(self, payload: Dict) -> Dict:
        """
        Make ensemble trade decision with majority voting and tie-breaking.
        
        Args:
            payload: Market data payload for LLM analysis
            
        Returns:
            Dict with keys: decision, confidence, reason
            
        Raises:
            RuntimeError: If all providers fail
        """
        if not self.enabled:
            # Fallback to single model
            logger.info("[ENSEMBLE] Ensemble disabled, using single model")
            fallback_client = LLMClient(self.config["MODEL"])
            decision = fallback_client.make_trade_decision(payload)
            return {
                "decision": decision.decision,
                "confidence": decision.confidence,
                "reason": f"Single-model decision (ensemble disabled): {decision.reason}"
            }
        
        # Collect decisions from all available models
        decisions = []
        failed_models = []
        
        for model_name, client in self.clients.items():
            try:
                logger.info(f"[ENSEMBLE] Querying {model_name}...")
                decision = client.make_trade_decision(payload)
                decisions.append({
                    "model": model_name,
                    "decision": decision.decision,
                    "confidence": decision.confidence,
                    "reason": decision.reason or f"{model_name} decision"
                })
                logger.info(f"[ENSEMBLE] {model_name}: {decision.decision} (conf: {decision.confidence:.3f})")
            except Exception as e:
                logger.warning(f"[ENSEMBLE] {model_name} failed: {e}")
                failed_models.append(model_name)
        
        # Handle failure cases
        if not decisions:
            logger.error("[ENSEMBLE] All LLM providers failed - attempting rule-based fallback")
            return self._rule_based_fallback(payload)
        
        if len(decisions) == 1:
            logger.warning(f"[ENSEMBLE] Only one model succeeded, using single decision")
            single = decisions[0]
            return {
                "decision": single["decision"],
                "confidence": single["confidence"],
                "reason": f"{single['reason']} (single model: {single['model']})"
            }
        
        # Apply ensemble voting logic
        return self._apply_ensemble_voting(decisions, failed_models)
    
    def _rule_based_fallback(self, payload: Dict) -> Dict:
        """
        Rule-based fallback when all LLM providers fail.
        
        Uses simple technical analysis rules to detect obvious breakout patterns
        without requiring LLM analysis. Conservative approach - only triggers
        on very clear signals.
        
        Args:
            payload: Market data payload
            
        Returns:
            Dict with decision, confidence, and reason
        """
        try:
            # Extract key technical indicators from payload
            breakout_analysis = payload.get('breakout_analysis', {})
            current_price = breakout_analysis.get('current_price', 0)
            resistance_levels = breakout_analysis.get('resistance_levels', [])
            support_levels = breakout_analysis.get('support_levels', [])
            volume_surge = breakout_analysis.get('volume_surge', False)
            
            # Get price movement data
            price_change_pct = breakout_analysis.get('price_change_pct', 0)
            candle_body_pct = breakout_analysis.get('candle_body_pct', 0)
            
            # Rule 1: Strong bearish breakout (PUT signal)
            if (price_change_pct < -0.5 and  # >0.5% drop
                candle_body_pct > 0.3 and     # Strong candle body
                volume_surge and              # Volume confirmation
                support_levels and            # Support level exists
                current_price < min(support_levels[:3])):  # Below recent support
                
                logger.info("[ENSEMBLE] Rule-based fallback: Strong bearish breakout detected")
                return {
                    "decision": "PUT",
                    "confidence": 0.70,  # Conservative but actionable
                    "reason": "Rule-based fallback: Strong bearish breakout with volume confirmation and support break"
                }
            
            # Rule 2: Strong bullish breakout (CALL signal)
            elif (price_change_pct > 0.5 and   # >0.5% gain
                  candle_body_pct > 0.3 and    # Strong candle body
                  volume_surge and             # Volume confirmation
                  resistance_levels and        # Resistance level exists
                  current_price > max(resistance_levels[:3])):  # Above recent resistance
                
                logger.info("[ENSEMBLE] Rule-based fallback: Strong bullish breakout detected")
                return {
                    "decision": "CALL",
                    "confidence": 0.70,  # Conservative but actionable
                    "reason": "Rule-based fallback: Strong bullish breakout with volume confirmation and resistance break"
                }
            
            # Rule 3: No clear signal - stay safe
            else:
                logger.info("[ENSEMBLE] Rule-based fallback: No clear breakout pattern")
                return {
                    "decision": "NO_TRADE",
                    "confidence": 0.0,
                    "reason": "Rule-based fallback: No clear breakout pattern detected"
                }
                
        except Exception as e:
            logger.error(f"[ENSEMBLE] Rule-based fallback failed: {e}")
            return {
                "decision": "NO_TRADE",
                "confidence": 0.0,
                "reason": f"Rule-based fallback error: {e}"
            }
    
    def _apply_ensemble_voting(self, decisions: List[Dict], failed_models: List[str]) -> Dict:
        """
        Apply majority voting with tie-breaking logic.
        
        Args:
            decisions: List of model decisions with decision, confidence, reason
            failed_models: List of models that failed (for logging)
            
        Returns:
            Final ensemble decision dict
        """
        # Count votes for each decision type
        vote_counts = Counter(d["decision"] for d in decisions)
        max_votes = max(vote_counts.values())
        winners = [decision for decision, count in vote_counts.items() if count == max_votes]
        
        logger.info(f"[ENSEMBLE] Vote counts: {dict(vote_counts)}")
        
        # Case 1: Clear majority winner
        if len(winners) == 1:
            winning_decision = winners[0]
            winning_votes = [d for d in decisions if d["decision"] == winning_decision]
            avg_confidence = sum(d["confidence"] for d in winning_votes) / len(winning_votes)
            
            reasons = [d["reason"] for d in winning_votes]
            combined_reason = f"Majority vote: {winning_decision} ({len(winning_votes)}/{len(decisions)} models). " + \
                            f"Reasons: {'; '.join(reasons)}"
            
            logger.info(f"[ENSEMBLE] Majority winner: {winning_decision} (conf: {avg_confidence:.3f})")
            
            return {
                "decision": winning_decision,
                "confidence": round(avg_confidence, 3),
                "reason": combined_reason
            }
        
        # Case 2: Tie - break by highest confidence
        logger.info(f"[ENSEMBLE] Tie between: {winners}, breaking by highest confidence")
        
        # Find the highest confidence among tied decisions
        tied_decisions = [d for d in decisions if d["decision"] in winners]
        best_decision = max(tied_decisions, key=lambda x: x["confidence"])
        
        # Get all votes for the winning decision
        winning_votes = [d for d in decisions if d["decision"] == best_decision["decision"]]
        avg_confidence = sum(d["confidence"] for d in winning_votes) / len(winning_votes)
        
        reasons = [d["reason"] for d in winning_votes]
        combined_reason = f"Tie-break winner: {best_decision['decision']} " + \
                         f"(highest conf: {best_decision['confidence']:.3f}). " + \
                         f"Reasons: {'; '.join(reasons)}"
        
        logger.info(f"[ENSEMBLE] Tie-break winner: {best_decision['decision']} " + \
                   f"(conf: {avg_confidence:.3f}, tie-break conf: {best_decision['confidence']:.3f})")
        
        if failed_models:
            combined_reason += f" (Failed models: {', '.join(failed_models)})"
        
        return {
            "decision": best_decision["decision"],
            "confidence": round(avg_confidence, 3),
            "reason": combined_reason
        }


def choose_trade(payload: Dict) -> Dict:
    """
    Convenience function for ensemble trade decision making.
    
    Args:
        payload: Market data payload for LLM analysis
        
    Returns:
        Dict with keys: decision, confidence, reason
        
    Raises:
        RuntimeError: If all providers fail
    """
    ensemble = EnsembleLLM()
    return ensemble.choose_trade(payload)


# Example usage and testing
if __name__ == "__main__":
    # Test ensemble with mock payload
    test_payload = {
        "price": 632.82,
        "trend": "BULLISH",
        "body_pct": 0.25,
        "tr_pct": 0.18,
        "room_up": 0.8,
        "room_down": 1.2,
        "vwap_deviation_pct": 0.004,
        "atm_delta": 0.497,
        "atm_oi": 10672,
        "dealer_gamma_$": -250000000.0
    }
    
    try:
        result = choose_trade(test_payload)
        print(f"Ensemble decision: {result}")
    except Exception as e:
        print(f"Ensemble test failed: {e}")
