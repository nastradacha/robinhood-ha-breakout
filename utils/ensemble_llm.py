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
            
        # Initialize LLM clients for each model (using singleton pattern)
        self.clients = {}
        for model in self.models:
            try:
                self.clients[model] = LLMClient(model=model)
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
        timeout_seconds = self.config.get("ENSEMBLE_TIMEOUT", 15)  # Increased to 15s for DeepSeek latency
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
                conf_str = f"{decision.confidence:.3f}" if decision.confidence is not None else "None"
                logger.info(f"[ENSEMBLE] {model_name}: {decision.decision} (conf: {conf_str}) [{elapsed:.1f}s] - {decision.reason or 'No reason provided'}")
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
            
            # Process results as they complete, with improved timeout handling and fail-open logic
            fast_model_threshold = 8.0  # If first model responds within 8s, consider fail-open
            first_response_time = None
            
            try:
                for future in concurrent.futures.as_completed(future_to_model, timeout=timeout_seconds):
                    model_name = future_to_model[future]
                    try:
                        result = future.result(timeout=3.0)  # Increased individual timeout to 3.0s
                        decisions.append(result)
                        
                        # Track first response time for fail-open logic
                        if first_response_time is None:
                            first_response_time = result["elapsed"]
                        
                        # Tightened fail-open logic: More conservative for trade execution
                        if (len(decisions) == 1 and 
                            result["elapsed"] <= fast_model_threshold and
                            result["decision"] != "NO_TRADE" and
                            result["confidence"] is not None and
                            result["confidence"] >= 0.70):  # Higher threshold for trade decisions
                            
                            # Wait longer (4s) to see if second model responds
                            remaining_futures = [f for f in future_to_model if f != future and not f.done()]
                            if remaining_futures:
                                logger.info(f"[ENSEMBLE] {model_name} responded quickly ({result['elapsed']:.1f}s) - waiting 4s for other models")
                                try:
                                    # Give other models 4 more seconds for better consensus
                                    for quick_future in concurrent.futures.as_completed(remaining_futures, timeout=4.0):
                                        quick_model = future_to_model[quick_future]
                                        try:
                                            quick_result = quick_future.result(timeout=1.0)
                                            decisions.append(quick_result)
                                            logger.info(f"[ENSEMBLE] {quick_model} also responded quickly ({quick_result['elapsed']:.1f}s)")
                                            
                                            # If second model disagrees on trade direction, require consensus
                                            if (quick_result["decision"] != "NO_TRADE" and 
                                                quick_result["decision"] != result["decision"]):
                                                logger.warning(f"[ENSEMBLE] Models disagree: {model_name}={result['decision']} vs {quick_model}={quick_result['decision']}, requiring full ensemble")
                                                break  # Continue to full ensemble evaluation
                                                
                                        except Exception as e:
                                            logger.warning(f"[ENSEMBLE] {quick_model} failed in quick response: {e}")
                                        break  # Only wait for one more quick response
                                except concurrent.futures.TimeoutError:
                                    logger.info(f"[ENSEMBLE] No other quick responses - using {model_name} decision")
                            
                            # Only use fast model decision if high confidence and no disagreement
                            if len(decisions) == 1:  # No second model responded or disagreed
                                conf_str = f"{result['confidence']:.3f}" if result['confidence'] is not None else "None"
                                logger.info(f"[ENSEMBLE] Fail-open: Using fast {model_name} decision ({result['elapsed']:.1f}s, conf: {conf_str})")
                                # Cancel remaining futures
                                for remaining_future in future_to_model:
                                    if remaining_future != future and not remaining_future.done():
                                        remaining_future.cancel()
                                return result
                        
                        # Early exit if first model returns NO_TRADE with high confidence
                        if (result["decision"] == "NO_TRADE" and 
                            result["confidence"] is not None and
                            result["confidence"] >= 0.80 and  # High confidence NO_TRADE
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
        
        if len(decisions) < 2:
            if len(decisions) == 1:
                MIN_CONF = 0.60  # Lowered from 0.65 to 0.60 for single-model decisions
                single = decisions[0]
                logger.warning(f"[ENSEMBLE] Only 1 model responded within {timeout_seconds}s, using single decision")
                
                # Accept single model if confidence >= 0.60 OR if it's a strong signal (>= 0.65)
                if (single["decision"] != "NO_TRADE" and 
                    single["confidence"] is not None and 
                    single["confidence"] >= MIN_CONF):
                    logger.info(f"[ENSEMBLE] Single model {single['decision']} with confidence {single['confidence']:.3f} >= {MIN_CONF} - accepting decision")
                    return {
                        "decision": single["decision"],
                        "confidence": single["confidence"],
                        "reason": f"Single model decision: {single['reason']}"
                    }
                else:
                    conf_str = f"{single['confidence']:.3f}" if single['confidence'] is not None else "None"
                    logger.info(f"[ENSEMBLE] Single model {single['decision']} with confidence {conf_str} - defaulting to NO_TRADE")
                    return {
                        "decision": "NO_TRADE",
                        "confidence": None,
                        "reason": f"Single model fallback (insufficient confidence): {single['reason']}"
                    }
        # Apply ensemble voting logic
        return self._aggregate_decisions(decisions)
    
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
                    "confidence": None,
                    "reason": "Rule-based fallback: No clear breakout pattern detected"
                }
                
        except Exception as e:
            logger.error(f"[ENSEMBLE] Rule-based fallback failed: {e}")
            return {
                "decision": "NO_TRADE",
                "confidence": None,
                "reason": f"Rule-based fallback error: {e}"
            }
    
    def _aggregate_decisions(self, decisions: List[Dict]) -> Dict:
        """
        Aggregate multiple model decisions into final ensemble decision.
        
        Enhanced ensemble logic:
        - Requires ≥1 model above MIN_CONFIDENCE threshold
        - Prefers unanimous agreement but accepts majority with high confidence
        - Falls back to NO_TRADE gracefully when no models meet threshold
        - Handles None confidence values properly
        
        Args:
            decisions: List of model decision dicts
            
        Returns:
            Final ensemble decision dict
        """
        from collections import Counter
        from utils.llm import load_config
        
        config = load_config()
        min_confidence = config.get("MIN_CONFIDENCE", 0.6)
        
        # Separate decisions by type and filter by confidence
        actionable_decisions = [
            d for d in decisions 
            if d["decision"] in ("CALL", "PUT") and d["confidence"] is not None
        ]
        
        # Filter for decisions meeting confidence threshold
        valid_votes = [
            d for d in actionable_decisions 
            if d["confidence"] >= min_confidence
        ]
        
        # Graceful fallback when no models meet confidence threshold
        if not valid_votes:
            low_conf_count = len([d for d in actionable_decisions if d["confidence"] < min_confidence])
            none_conf_count = len([d for d in decisions if d["confidence"] is None])
            
            logger.info(f"[ENSEMBLE] No models above {min_confidence:.2f} threshold: {low_conf_count} below, {none_conf_count} without confidence")
            return {
                "decision": "NO_TRADE", 
                "confidence": None, 
                "reason": f"No models meet {min_confidence:.2f} confidence threshold ({len(actionable_decisions)} actionable, 0 valid)"
            }
        
        # Count votes from valid models
        votes = [d["decision"] for d in valid_votes]
        vote_counts = Counter(votes)
        max_votes = max(vote_counts.values())
        winners = [k for k, v in vote_counts.items() if v == max_votes]

        # Handle disagreement between valid models
        if len(winners) > 1:
            logger.info(f"[ENSEMBLE] Models disagree: {dict(vote_counts)} - defaulting to NO_TRADE")
            return {
                "decision": "NO_TRADE", 
                "confidence": None, 
                "reason": f"Models disagree among {len(valid_votes)} valid votes: {dict(vote_counts)}"
            }
        
        # Unanimous or majority agreement with confidence threshold met
        winner = winners[0]
        winning_votes = [d for d in valid_votes if d["decision"] == winner]
        avg_confidence = sum(d["confidence"] for d in winning_votes) / len(winning_votes)
        
        logger.info(f"[ENSEMBLE] Agreement: {winner} from {len(winning_votes)}/{len(decisions)} models (avg conf: {avg_confidence:.3f})")
        
        return {
            "decision": winner, 
            "confidence": avg_confidence, 
            "reason": f"Ensemble {winner}: {len(winning_votes)}/{len(decisions)} models above {min_confidence:.2f} threshold"
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
