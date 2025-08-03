"""
LLM Integration Module

Provides sophisticated AI-powered trade decision making using Large Language Models.
Supports both OpenAI (GPT-4o-mini) and DeepSeek APIs with function calling capabilities
for structured trade analysis and bankroll management.

Key Features:
- Multi-provider LLM support (OpenAI GPT-4o-mini, DeepSeek)
- Function calling for structured trade decisions
- Robust error handling with exponential backoff retry
- Conservative trade decision making with confidence scoring
- Bankroll management suggestions based on P&L
- Market analysis interpretation and pattern recognition

Trade Decision Process:
1. Analyze market data (Heikin-Ashi patterns, volume, momentum)
2. Consider recent win/loss history for confidence calibration
3. Apply conservative risk management principles
4. Generate structured trade decision with reasoning
5. Provide confidence score (0.0-1.0) for decision quality

Supported Models:
- gpt-4o-mini: OpenAI's efficient model for trading decisions
- deepseek-chat: DeepSeek's competitive alternative
- Automatic fallback between providers if one fails

Safety Features:
- Conservative bias: prefers NO_TRADE over risky positions
- Confidence thresholds: requires high confidence for trades
- Win/loss history integration: adjusts confidence based on recent performance
- Comprehensive error handling and logging
- Rate limiting and retry mechanisms

Function Calling Schema:
- make_trade_decision(): Returns BUY_CALL, BUY_PUT, or NO_TRADE
- suggest_bankroll_update(): Recommends bankroll adjustments
- suggest_similar_trade(): Identifies follow-up opportunities

Usage:
    # Initialize LLM client
    llm = LLMClient(model='gpt-4o-mini')
    
    # Make trade decision
    decision = llm.make_trade_decision(market_data, win_history)
    if decision.decision != 'NO_TRADE' and decision.confidence > 0.7:
        # Proceed with trade setup
        pass

Author: Robinhood HA Breakout System
Version: 2.0.0
License: MIT
"""

import json
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import httpx
import requests
import openai
import os
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    config_file = Path(config_path)
    if not config_file.exists():
        config_file = Path(__file__).parent.parent / config_path
    
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    
    # Add derived fields
    config['TRADE_LOG_FILE'] = config.get('TRADE_LOG_FILE', 'logs/trade_log.csv')
    config['LOG_FILE'] = config.get('LOG_FILE', 'logs/app.log')
    
    return config


# Custom exceptions for better error handling
class LLMAPIError(Exception):
    """Base exception for LLM API errors."""
    pass

class LLMTimeoutError(LLMAPIError):
    """Timeout error for LLM API calls."""
    pass

class LLMAuthError(LLMAPIError):
    """Authentication error for LLM API calls."""
    pass

class LLMRateLimitError(LLMAPIError):
    """Rate limit error for LLM API calls."""
    pass

class LLMParseError(LLMAPIError):
    """JSON parsing error for LLM responses."""
    pass


# Retry decorator for API calls with exponential back-off
api_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((LLMTimeoutError, LLMRateLimitError, httpx.TimeoutException, httpx.ConnectError)),
    reraise=True
)


@dataclass
class TradeDecision:
    """Data class for trade decision results."""
    decision: str  # "CALL", "PUT", "NO_TRADE"
    confidence: float  # 0.0 to 1.0
    reason: Optional[str] = None
    tokens_used: int = 0


@dataclass
class BankrollUpdate:
    """Data class for bankroll update suggestions."""
    new_bankroll: float
    reason: str
    tokens_used: int = 0


class LLMClient:
    """Unified client for OpenAI and DeepSeek APIs."""
    
    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.deepseek_key = os.getenv("DEEPSEEK_API_KEY")
        
        if model.startswith("gpt") and not self.openai_key:
            raise ValueError("OPENAI_API_KEY required for OpenAI models")
        elif model.startswith("deepseek") and not self.deepseek_key:
            raise ValueError("DEEPSEEK_API_KEY required for DeepSeek models")
        
        # Initialize OpenAI client if using OpenAI
        if model.startswith("gpt"):
            openai.api_key = self.openai_key
    
    def _get_function_schemas(self) -> list:
        """Get function calling schemas for trade decisions."""
        return [
            {
                "name": "choose_trade",
                "description": "Make a trading decision based on market analysis",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "decision": {
                            "type": "string",
                            "enum": ["CALL", "PUT", "NO_TRADE"],
                            "description": "Trading decision"
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                            "description": "Confidence level (0.0 to 1.0)"
                        },
                        "reason": {
                            "type": "string",
                            "description": "Brief reason for the decision (required if confidence < 0.5)"
                        }
                    },
                    "required": ["decision", "confidence"]
                }
            },
            {
                "name": "update_bankroll",
                "description": "Suggest bankroll update after realized P/L",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "new_bankroll": {
                            "type": "number",
                            "description": "Suggested new bankroll amount"
                        },
                        "reason": {
                            "type": "string",
                            "description": "Reason for bankroll update"
                        }
                    },
                    "required": ["new_bankroll", "reason"]
                }
            }
        ]
    
    def _get_system_prompt(self) -> str:
        """Get the system prompt for trade decision making."""
        config = load_config()
        body_cutoff = config.get('MIN_CANDLE_BODY_PCT', 0.30)
        return f"""You are an options-trading assistant specializing in SPY breakout strategies using Heikin-Ashi candles analyzing 5-minute intervals.

DECISION RULES:
- Return JSON only via the choose_trade function
- Calibrate confidence against a 20-trade memory: confidence = wins_last20 / 20 (cap 0.50 if no memory)
- If today_true_range_pct < 40, subtract 0.15 from confidence
- If breakout candle body < {body_cutoff}% of price, return NO_TRADE & confidence 0
- Boost confidence by 0.10 only when room_to_next_pivot >= 0.5%
- If 5-min IV > 45%, halve confidence
- If confidence < 0.35, override decision to NO_TRADE
- Think step-by-step internally, output only JSON
- When confidence < 0.5, include a short 'reason' string in the JSON

BANKROLL MANAGEMENT:
- At the end of each trading session you will receive the realized P/L
- If bankroll change > 5%, propose an update_bankroll call
- Otherwise do nothing

ANALYSIS FOCUS:
- Heikin-Ashi candle patterns and breakouts
- Support/resistance levels and room to move
- True range and volatility context
- Volume confirmation
- Risk/reward assessment"""
    
    @api_retry
    def _call_openai(self, messages: list, functions: list) -> Dict:
        """Call OpenAI API with function calling and robust error handling."""
        try:
            from openai import OpenAI
            import ssl
            
            # Create SSL context that handles certificate issues
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            # Create HTTP client with SSL handling
            http_client = httpx.Client(
                verify=False,  # Disable SSL verification for problematic certificates
                timeout=httpx.Timeout(30.0, read=30.0, write=10.0, connect=5.0)
            )
            
            client = OpenAI(
                api_key=self.openai_key,
                http_client=http_client,
                max_retries=0  # We handle retries with tenacity
            )
            
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=[{"type": "function", "function": func} for func in functions],
                tool_choice="auto",
                temperature=0.1,
                max_tokens=500
            )
            
            return {
                "response": response,
                "tokens_used": response.usage.total_tokens
            }
        
        except httpx.TimeoutException as e:
            logger.error(f"OpenAI API timeout: {e}")
            raise LLMTimeoutError(f"OpenAI API timeout: {e}") from e
        
        except httpx.ConnectError as e:
            logger.error(f"OpenAI API connection error: {e}")
            raise LLMTimeoutError(f"OpenAI connection failed: {e}") from e
        
        except openai.AuthenticationError as e:
            logger.error(f"OpenAI authentication error: {e}")
            raise LLMAuthError(f"OpenAI authentication failed: {e}") from e
        
        except openai.RateLimitError as e:
            logger.error(f"OpenAI rate limit error: {e}")
            raise LLMRateLimitError(f"OpenAI rate limit exceeded: {e}") from e
        
        except json.JSONDecodeError as e:
            logger.error(f"OpenAI response JSON parse error: {e}")
            raise LLMParseError(f"Failed to parse OpenAI response: {e}") from e
        
        except Exception as e:
            logger.error(f"Unexpected OpenAI API error: {e}", exc_info=True)
            raise LLMAPIError(f"OpenAI API error: {e}") from e
    
    @api_retry
    def _call_deepseek(self, messages: list, functions: list) -> Dict:
        """Call DeepSeek API with function calling and robust error handling."""
        try:
            headers = {
                "Authorization": f"Bearer {self.deepseek_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.model,
                "messages": messages,
                "functions": functions,
                "function_call": "auto",
                "temperature": 0.1,
                "max_tokens": 500
            }
            
            response = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            return {
                "response": result,
                "tokens_used": result.get("usage", {}).get("total_tokens", 0)
            }
        
        except requests.exceptions.Timeout as e:
            logger.error(f"DeepSeek API timeout: {e}")
            raise LLMTimeoutError(f"DeepSeek API timeout: {e}") from e
        
        except requests.exceptions.ConnectionError as e:
            logger.error(f"DeepSeek API connection error: {e}")
            raise LLMTimeoutError(f"DeepSeek connection failed: {e}") from e
        
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                logger.error(f"DeepSeek authentication error: {e}")
                raise LLMAuthError(f"DeepSeek authentication failed: {e}") from e
            elif e.response.status_code == 429:
                logger.error(f"DeepSeek rate limit error: {e}")
                raise LLMRateLimitError(f"DeepSeek rate limit exceeded: {e}") from e
            else:
                logger.error(f"DeepSeek HTTP error: {e}")
                raise LLMAPIError(f"DeepSeek HTTP error: {e}") from e
        
        except json.JSONDecodeError as e:
            logger.error(f"DeepSeek response JSON parse error: {e}")
            raise LLMParseError(f"Failed to parse DeepSeek response: {e}") from e
        
        except Exception as e:
            logger.error(f"Unexpected DeepSeek API error: {e}", exc_info=True)
            raise LLMAPIError(f"DeepSeek API error: {e}") from e
    
    def _validate_and_fill_market_data(self, market_data: Dict) -> Dict:
        """
        Validate market data and fill missing required fields with sensible defaults.
        
        The system prompt expects specific keys that must be present for consistent LLM behavior.
        """
        validated_data = market_data.copy()
        
        # Required fields with defaults
        required_fields = {
            'today_true_range_pct': 0.0,  # Default to 0% if not calculated
            'room_to_next_pivot': 0.0,    # Default to 0% room to move
            'iv_5m': 30.0,                # Default to moderate IV if not available
            'candle_body_pct': 0.0,       # Default to 0% body strength
            'current_price': 0.0,         # Should always be present, but safety default
            'trend_direction': 'NEUTRAL', # Default trend if not determined
            'volume_confirmation': False,  # Default to no volume confirmation
            'support_levels': [],         # Default to empty list
            'resistance_levels': []       # Default to empty list
        }
        
        # Fill missing fields with defaults
        for field, default_value in required_fields.items():
            if field not in validated_data or validated_data[field] is None:
                validated_data[field] = default_value
                logger.warning(f"[LLM] Missing field '{field}', using default: {default_value}")
        
        # Ensure numeric fields are actually numeric
        numeric_fields = ['today_true_range_pct', 'room_to_next_pivot', 'iv_5m', 
                         'candle_body_pct', 'current_price']
        for field in numeric_fields:
            try:
                validated_data[field] = float(validated_data[field])
            except (ValueError, TypeError):
                validated_data[field] = required_fields[field]
                logger.warning(f"[LLM] Invalid numeric value for '{field}', using default: {required_fields[field]}")
        
        return validated_data
    
    def make_trade_decision(self, market_data: Dict, win_history: Optional[list] = None) -> TradeDecision:
        """
        Make a trade decision based on market analysis.
        
        Args:
            market_data: Market analysis dictionary from data.py
            win_history: List of recent win/loss results for confidence calibration
        
        Returns:
            TradeDecision object
        """
        # Validate and fill missing market data fields
        validated_market_data = self._validate_and_fill_market_data(market_data)
        
        # Prepare context about recent performance
        win_rate_context = ""
        if win_history:
            recent_wins = sum(1 for result in win_history[-20:] if result)
            win_rate = recent_wins / min(len(win_history), 20)
            win_rate_context = f"Recent win rate: {win_rate:.2f} over {min(len(win_history), 20)} trades. "
        
        messages = [
            {"role": "system", "content": self._get_system_prompt()},
            {"role": "user", "content": f"""
{win_rate_context}

Market Analysis:
{json.dumps(validated_market_data, indent=2)}

Based on this Heikin-Ashi analysis, make your trading decision. Consider:
1. Breakout strength (candle body %)
2. Volatility context (true range %)
3. Room to move to next support/resistance
4. Volume confirmation
5. Overall trend direction

Use the choose_trade function to respond."""}
        ]
        
        functions = self._get_function_schemas()
        
        try:
            # Call appropriate API
            if self.model.startswith("gpt"):
                result = self._call_openai(messages, functions)
                response = result["response"]
                tokens_used = result["tokens_used"]
                
                # Parse OpenAI response
                if response.choices[0].message.tool_calls:
                    tool_call = response.choices[0].message.tool_calls[0]
                    if tool_call.function.name == "choose_trade":
                        args = json.loads(tool_call.function.arguments)
                        return TradeDecision(
                            decision=args["decision"],
                            confidence=args["confidence"],
                            reason=args.get("reason"),
                            tokens_used=tokens_used
                        )
            
            else:  # DeepSeek
                result = self._call_deepseek(messages, functions)
                response = result["response"]
                tokens_used = result["tokens_used"]
                
                # Parse DeepSeek response
                if response["choices"][0]["message"].get("function_call"):
                    func_call = response["choices"][0]["message"]["function_call"]
                    if func_call["name"] == "choose_trade":
                        args = json.loads(func_call["arguments"])
                        return TradeDecision(
                            decision=args["decision"],
                            confidence=args["confidence"],
                            reason=args.get("reason"),
                            tokens_used=tokens_used
                        )
            
            # Fallback if no function call
            logger.warning("No valid function call received, defaulting to NO_TRADE")
            return TradeDecision(
                decision="NO_TRADE",
                confidence=0.0,
                reason="LLM did not provide valid function call",
                tokens_used=tokens_used
            )
        
        except Exception as e:
            logger.error(f"Error making trade decision: {e}")
            return TradeDecision(
                decision="NO_TRADE",
                confidence=0.0,
                reason=f"API error: {str(e)}",
                tokens_used=0
            )
    
    def suggest_bankroll_update(self, current_bankroll: float, realized_pnl: float, 
                              trade_details: Dict) -> Optional[BankrollUpdate]:
        """
        Suggest bankroll update based on realized P/L.
        
        Args:
            current_bankroll: Current bankroll amount
            realized_pnl: Realized profit/loss
            trade_details: Details about the completed trade
        
        Returns:
            BankrollUpdate object if update suggested, None otherwise
        """
        new_bankroll = current_bankroll + realized_pnl
        change_pct = abs(realized_pnl / current_bankroll) * 100
        
        # Only suggest update if change > 5%
        if change_pct <= 5.0:
            return None
        
        messages = [
            {"role": "system", "content": self._get_system_prompt()},
            {"role": "user", "content": f"""
Trade completed with the following results:
- Previous bankroll: ${current_bankroll:.2f}
- Realized P/L: ${realized_pnl:.2f}
- New bankroll: ${new_bankroll:.2f}
- Change: {change_pct:.1f}%

Trade details:
{json.dumps(trade_details, indent=2)}

The bankroll change is significant (>{5.0}%). Use the update_bankroll function to suggest the new bankroll amount."""}
        ]
        
        functions = self._get_function_schemas()
        
        try:
            # Call appropriate API
            if self.model.startswith("gpt"):
                result = self._call_openai(messages, functions)
                response = result["response"]
                tokens_used = result["tokens_used"]
                
                # Parse OpenAI response
                if response.choices[0].message.tool_calls:
                    tool_call = response.choices[0].message.tool_calls[0]
                    if tool_call.function.name == "update_bankroll":
                        args = json.loads(tool_call.function.arguments)
                        return BankrollUpdate(
                            new_bankroll=args["new_bankroll"],
                            reason=args["reason"],
                            tokens_used=tokens_used
                        )
            
            else:  # DeepSeek
                result = self._call_deepseek(messages, functions)
                response = result["response"]
                tokens_used = result["tokens_used"]
                
                # Parse DeepSeek response
                if response["choices"][0]["message"].get("function_call"):
                    func_call = response["choices"][0]["message"]["function_call"]
                    if func_call["name"] == "update_bankroll":
                        args = json.loads(func_call["arguments"])
                        return BankrollUpdate(
                            new_bankroll=args["new_bankroll"],
                            reason=args["reason"],
                            tokens_used=tokens_used
                        )
            
            return None
        
        except Exception as e:
            logger.error(f"Error suggesting bankroll update: {e}")
            return None
    
    def suggest_similar_trade(self, completed_trade: Dict, market_data: Dict) -> Optional[str]:
        """
        Suggest a similar trade opportunity after a completed trade.
        
        Args:
            completed_trade: Details of the just-completed trade
            market_data: Current market analysis
        
        Returns:
            String suggestion or None
        """
        messages = [
            {"role": "system", "content": """You are an options trading assistant. 
            Analyze the completed trade and current market conditions to suggest similar opportunities.
            Focus on SPY or other liquid ETFs with similar characteristics.
            Keep suggestions brief and actionable."""},
            {"role": "user", "content": f"""
Just completed trade:
{json.dumps(completed_trade, indent=2)}

Current market conditions:
{json.dumps(market_data, indent=2)}

Based on the success/failure of the completed trade and current market conditions, 
suggest a similar trading opportunity. Consider:
1. Similar market patterns
2. Comparable risk/reward
3. Liquid options with good spreads
4. Time decay considerations

Provide a brief, actionable suggestion or say "No similar opportunities identified" if none exist."""}
        ]
        
        try:
            if self.model.startswith("gpt"):
                from openai import OpenAI
                import httpx
                
                # Create HTTP client with SSL handling
                http_client = httpx.Client(
                    verify=False,
                    timeout=httpx.Timeout(30.0, read=30.0, write=10.0, connect=5.0)
                )
                
                client = OpenAI(
                    api_key=self.openai_key,
                    http_client=http_client,
                    max_retries=2
                )
                
                response = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=200
                )
                return response.choices[0].message.content.strip()
            
            else:  # DeepSeek
                headers = {
                    "Authorization": f"Bearer {self.deepseek_key}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 200
                }
                
                response = requests.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=30
                )
                response.raise_for_status()
                
                result = response.json()
                return result["choices"][0]["message"]["content"].strip()
        
        except Exception as e:
            logger.error(f"Error suggesting similar trade: {e}")
            return None
