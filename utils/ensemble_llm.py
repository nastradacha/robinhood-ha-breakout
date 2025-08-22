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
import concurrent.futures
import time

from .llm import LLMClient, TradeDecision, load_config

logger = logging.getLogger(__name__)


class EnsembleLLM:
    """
    Two-model ensemble LLM client with majority voting and tie-breaking.
    
    Combines decisions from multiple LLM providers to improve trading decision
    quality through consensus and reduces single-model bias.
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize ensemble with configured models."""
        if self._initialized:
            return
            
        self.config = load_config()
        self.enabled = self.config.get("ENSEMBLE_ENABLED", True)
        self.models = self.config.get("ENSEMBLE_MODELS", ["gpt-4o-mini", "deepseek-chat"])
        
        if not self.enabled:
            logger.info("[ENSEMBLE] Ensemble disabled, using single-model fallback")
            self._initialized = True
            return
            
        if len(self.models) < 2:
            logger.warning(f"[ENSEMBLE] Less than 2 models configured: {self.models}, disabling ensemble")
            self.enabled = False
            self._initialized = True
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
            
        self._initialized = True
    
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
        
        # Collect decisions from all available models in parallel with timeout
        decisions = []
        failed_models = []
        timeout_seconds = self.config.get("ENSEMBLE_TIMEOUT", 6)  # 6s total timeout
        early_exit_confidence = self.config.get("ENSEMBLE_EARLY_EXIT_CONFIDENCE", 0.7)
        
        def query_model(model_name, client):
            """Query a single model and return result."""
            try:
                logger.info(f"[ENSEMBLE] Querying {model_name}...")
                start_time = time.time()
                decision = client.make_trade_decision(payload)
                elapsed = time.time() - start_time
                
                result = {
                    "model": model_name,
                    "decision": decision.decision,
                    "confidence": decision.confidence,
                    "reason": decision.reason or f"{model_name} decision",
                    "elapsed": elapsed
                }
                logger.info(f"[ENSEMBLE] {model_name}: {decision.decision} (conf: {decision.confidence:.3f}) [{elapsed:.1f}s] - {decision.reason or 'No reason provided'}")
                return result
            except Exception as e:
                logger.warning(f"[ENSEMBLE] {model_name} failed: {e}")
                raise e
        
        # Execute models in parallel with timeout
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(self.clients)) as executor:
            # Submit all tasks
            future_to_model = {
                executor.submit(query_model, model_name, client): model_name 
                for model_name, client in self.clients.items()
            }
            
            # Process results as they complete, with improved timeout handling
            try:
                for future in concurrent.futures.as_completed(future_to_model, timeout=timeout_seconds):
                    model_name = future_to_model[future]
                    try:
                        result = future.result(timeout=1.0)  # Individual result timeout
                        decisions.append(result)
                        
                        # Early exit if first model returns NO_TRADE with high confidence
                        if (result["decision"] == "NO_TRADE" and 
                            result["confidence"] >= early_exit_confidence and 
                            len(decisions) == 1):
                            logger.info(f"[ENSEMBLE] Early exit: {model_name} NO_TRADE with {result['confidence']:.3f} confidence")
                            # Cancel remaining futures
                            for remaining_future in future_to_model:
                                if remaining_future != future:
                                    remaining_future.cancel()
                            break
                            
                    except Exception as e:
                        logger.warning(f"[ENSEMBLE] {model_name} failed: {e}")
                        failed_models.append(model_name)
                        
            except concurrent.futures.TimeoutError:
                logger.warning(f"[ENSEMBLE] Timeout after {timeout_seconds}s, using available results")
                # Cancel remaining futures on timeout and wait for cancellation
                for future in future_to_model:
                    if not future.done():
                        future.cancel()
                        model_name = future_to_model[future]
                        failed_models.append(model_name)
                        logger.warning(f"[ENSEMBLE] Cancelled {model_name} due to timeout")
                        
                # Wait briefly for cancellations to complete
                time.sleep(0.1)
        
        # Handle failure cases
        if not decisions:
            logger.error("[ENSEMBLE] All LLM providers failed")
            raise RuntimeError("All LLM providers failed")
        
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
        # Filter out ABSTAIN votes - they don't participate in voting
        voting_decisions = [d for d in decisions if d["decision"] != "ABSTAIN"]
        abstain_count = len(decisions) - len(voting_decisions)
        
        if abstain_count > 0:
            logger.info(f"[ENSEMBLE] {abstain_count} models abstained from voting")
        
        # If all models abstained, default to NO_TRADE
        if not voting_decisions:
            logger.warning("[ENSEMBLE] All models abstained - defaulting to NO_TRADE")
            return {
                "decision": "NO_TRADE",
                "confidence": 0.0,
                "reason": "All models abstained from voting due to parse failures"
            }
        
        # New ensemble veto policy: Only block if BOTH models say NO_TRADE
        votes = [d["decision"] for d in voting_decisions if d["decision"] in {"CALL", "PUT", "NO_TRADE"}]
        vote_counts = Counter(votes)
        
        logger.info(f"[ENSEMBLE] Vote counts: {dict(vote_counts)} (abstained: {abstain_count})")
        
        # Case 1: No valid votes - defer to rules
        if len(votes) == 0:
            logger.info("[ENSEMBLE] No valid votes - deferring to rules")
            return {
                "decision": "NO_TRADE",
                "confidence": 0.0,
                "reason": "No valid ensemble votes - deferred to rules"
            }
        
        # Case 2: Both models say NO_TRADE - block trade
        if len(votes) >= 2 and all(v == "NO_TRADE" for v in votes):
            no_trade_votes = [d for d in voting_decisions if d["decision"] == "NO_TRADE"]
            avg_confidence = sum(d["confidence"] for d in no_trade_votes) / len(no_trade_votes)
            reasons = [d["reason"] for d in no_trade_votes]
            
            logger.info(f"[ENSEMBLE] Both models agree: NO_TRADE (conf: {avg_confidence:.3f})")
            
            return {
                "decision": "NO_TRADE",
                "confidence": round(avg_confidence, 3),
                "reason": f"Unanimous NO_TRADE ({len(no_trade_votes)}/{len(voting_decisions)} models). Reasons: {'; '.join(reasons)}"
            }
        
        # Case 3: Mixed votes (TRADE + NO_TRADE) - defer to rules but allow trade
        if "NO_TRADE" in votes and any(v in {"CALL", "PUT"} for v in votes):
            trade_votes = [d for d in voting_decisions if d["decision"] in {"CALL", "PUT"}]
            if trade_votes:
                best_trade = max(trade_votes, key=lambda x: x["confidence"])
                logger.info(f"[ENSEMBLE] Mixed votes - deferring to trade signal: {best_trade['decision']}")
                
                return {
                    "decision": best_trade["decision"],
                    "confidence": round(best_trade["confidence"], 3),
                    "reason": f"Mixed ensemble votes - trade signal wins: {best_trade['reason']}"
                }
        
        # Case 4: Clear majority winner (all CALL or all PUT)
        if len(set(votes)) == 1:
            winning_decision = votes[0]
            winning_votes = [d for d in voting_decisions if d["decision"] == winning_decision]
            avg_confidence = sum(d["confidence"] for d in winning_votes) / len(winning_votes)
            
            reasons = [d["reason"] for d in winning_votes]
            combined_reason = f"Majority vote: {winning_decision} ({len(winning_votes)}/{len(voting_decisions)} models). " + \
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
        tied_decisions = [d for d in voting_decisions if d["decision"] in winners]
        best_decision = max(tied_decisions, key=lambda x: x["confidence"])
        
        # Get all votes for the winning decision
        winning_votes = [d for d in voting_decisions if d["decision"] == best_decision["decision"]]
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
