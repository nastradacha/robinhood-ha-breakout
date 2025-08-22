#!/usr/bin/env python3
"""
LLM JSON Client - Strict JSON Response Wrapper

Thin wrapper around existing ensemble_llm to ensure strict JSON responses
with escalation to backup models when needed. Provides temperature control
and retry logic for reliable structured outputs.

Features:
- Strict JSON parsing with validation
- Automatic escalation to backup model on parse failures
- Low temperature for consistent structured outputs
- Error handling with fallback strategies
- Integration with existing ensemble LLM infrastructure
"""

import json
import logging
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger(__name__)


class LLMJsonClient:
    """
    Wrapper for ensemble LLM client that enforces strict JSON responses.
    
    Provides reliable structured outputs by:
    1. Using low temperature for consistency
    2. Requesting JSON mode when available
    3. Escalating to backup model on failures
    4. Validating JSON structure before returning
    """
    
    def __init__(self, ensemble_client, logger_instance=None):
        """
        Initialize JSON client with ensemble LLM backend.
        
        Args:
            ensemble_client: Existing utils.ensemble_llm or LLM client
            logger_instance: Optional logger instance
        """
        self.ensemble = ensemble_client
        self.log = logger_instance or logger
        
        # Track API calls for cost monitoring
        self.call_count = 0
        self.parse_failures = 0
        self.escalations = 0

    @staticmethod
    def json_dumps(obj: Any) -> str:
        """
        Serialize object to compact JSON string.
        
        Args:
            obj: Object to serialize
            
        Returns:
            Compact JSON string
        """
        return json.dumps(obj, separators=(",", ":"), default=str)

    def strict_json(self, messages: List[Dict[str, str]], escalate_if_low: bool = True, 
                   max_tokens: int = 300) -> Dict[str, Any]:
        """
        Get strict JSON response from LLM with escalation on failures.
        
        Args:
            messages: Chat messages for LLM
            escalate_if_low: Whether to escalate to backup on parse failures
            max_tokens: Maximum tokens in response
            
        Returns:
            Parsed JSON dictionary
            
        Raises:
            ValueError: If both primary and backup fail to return valid JSON
        """
        self.call_count += 1
        
        # First attempt with primary model
        try:
            response_text, metadata = self._call_llm_json(
                messages, 
                temperature=0.1, 
                max_tokens=max_tokens,
                prefer_backup=False
            )
            
            parsed_json = self._parse_json_or_none(response_text)
            
            if parsed_json is not None:
                self.log.debug(f"[LLM-JSON] Primary model success: {len(response_text)} chars")
                return parsed_json
            
            self.parse_failures += 1
            self.log.warning(f"[LLM-JSON] Primary model returned invalid JSON: {response_text[:200]}...")
            
        except Exception as e:
            self.parse_failures += 1
            self.log.warning(f"[LLM-JSON] Primary model call failed: {e}")
        
        # Escalate to backup model if enabled
        if escalate_if_low:
            try:
                self.escalations += 1
                self.log.info("[LLM-JSON] Escalating to backup model due to JSON parse failure")
                
                response_text, metadata = self._call_llm_json(
                    messages,
                    temperature=0.1,
                    max_tokens=max_tokens, 
                    prefer_backup=True
                )
                
                parsed_json = self._parse_json_or_none(response_text)
                
                if parsed_json is not None:
                    self.log.info(f"[LLM-JSON] Backup model success: {len(response_text)} chars")
                    return parsed_json
                
                self.log.error(f"[LLM-JSON] Backup model also returned invalid JSON: {response_text[:200]}...")
                
            except Exception as e:
                self.log.error(f"[LLM-JSON] Backup model call failed: {e}")
        
        # Both attempts failed
        raise ValueError("LLM returned non-JSON response from both primary and backup models")

    def _call_llm_json(self, messages: List[Dict[str, str]], temperature: float = 0.1, 
                      max_tokens: int = 300, prefer_backup: bool = False) -> Tuple[str, Dict]:
        """
        Call ensemble LLM with JSON mode preferences.
        
        Args:
            messages: Chat messages
            temperature: Sampling temperature (low for consistency)
            max_tokens: Maximum response tokens
            prefer_backup: Whether to prefer backup model
            
        Returns:
            Tuple of (response_text, metadata)
        """
        # Check if ensemble has chat_json method
        if hasattr(self.ensemble, 'chat_json'):
            return self.ensemble.chat_json(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                prefer_backup=prefer_backup
            )
        
        # Fallback to regular chat with JSON instruction
        elif hasattr(self.ensemble, 'chat'):
            # Add JSON instruction to system message
            enhanced_messages = self._add_json_instruction(messages)
            
            response_text = self.ensemble.chat(
                enhanced_messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            # Return in expected format (text, metadata)
            return response_text, {"model": "ensemble", "prefer_backup": prefer_backup}
        
        # Fallback to make_trade_decision if available (for compatibility)
        elif hasattr(self.ensemble, 'make_trade_decision'):
            # This is a more complex fallback - construct a simple payload
            # and extract JSON from the decision
            self.log.warning("[LLM-JSON] Using make_trade_decision fallback - may not return pure JSON")
            
            # Create a minimal payload for the trade decision
            payload = {
                "messages": messages,
                "request_json": True
            }
            
            decision = self.ensemble.make_trade_decision(payload, [])
            
            # Try to extract JSON from decision attributes
            decision_dict = {
                "action": getattr(decision, 'decision', 'WAIT'),
                "confidence": getattr(decision, 'confidence', 0.5),
                "reason": getattr(decision, 'reason', 'Fallback decision')
            }
            
            return json.dumps(decision_dict), {"model": "ensemble_fallback"}
        
        else:
            raise ValueError("Ensemble client does not support required methods (chat_json, chat, or make_trade_decision)")

    def _add_json_instruction(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Add JSON formatting instruction to messages.
        
        Args:
            messages: Original chat messages
            
        Returns:
            Enhanced messages with JSON instruction
        """
        enhanced_messages = messages.copy()
        
        # Add JSON instruction to system message or create one
        json_instruction = "\n\nIMPORTANT: Respond ONLY with valid JSON. No additional text or formatting."
        
        if enhanced_messages and enhanced_messages[0]["role"] == "system":
            enhanced_messages[0]["content"] += json_instruction
        else:
            enhanced_messages.insert(0, {
                "role": "system", 
                "content": "You are a helpful assistant that responds only in valid JSON format." + json_instruction
            })
        
        return enhanced_messages

    @staticmethod
    def _parse_json_or_none(text: str) -> Optional[Dict[str, Any]]:
        """
        Attempt to parse JSON from text, returning None on failure.
        
        Args:
            text: Text to parse as JSON
            
        Returns:
            Parsed dictionary or None if parsing fails
        """
        if not text or not isinstance(text, str):
            return None
        
        # Clean up common JSON formatting issues
        text = text.strip()
        
        # Remove markdown code blocks if present
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        
        text = text.strip()
        
        try:
            parsed = json.loads(text)
            # Ensure we got a dictionary (not a list or primitive)
            return parsed if isinstance(parsed, dict) else None
        except (json.JSONDecodeError, ValueError):
            return None

    def get_stats(self) -> Dict[str, Any]:
        """
        Get client statistics for monitoring and debugging.
        
        Returns:
            Dictionary with call counts and success rates
        """
        success_rate = (self.call_count - self.parse_failures) / max(self.call_count, 1)
        escalation_rate = self.escalations / max(self.call_count, 1)
        
        return {
            "total_calls": self.call_count,
            "parse_failures": self.parse_failures,
            "escalations": self.escalations,
            "success_rate": success_rate,
            "escalation_rate": escalation_rate
        }

    def reset_stats(self) -> None:
        """Reset statistics counters."""
        self.call_count = 0
        self.parse_failures = 0
        self.escalations = 0
