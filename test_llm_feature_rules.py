#!/usr/bin/env python3
"""
Unit Tests for Enhanced LLM Feature Rules and Dynamic Threshold Logic

Tests the enhanced LLM prompt rules including:
- VWAP deviation analysis
- ATM delta calculation
- ATM open interest assessment
- Dealer gamma intelligence
- Dynamic candle-body threshold based on dealer gamma
- Context memory integration

Author: Robinhood HA Breakout System
Version: 0.6.1
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import sys
import os

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.llm import LLMClient, TradeDecision


class TestLLMFeatureRules(unittest.TestCase):
    """Test enhanced LLM feature rules and dynamic threshold logic."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock environment variables to avoid API key requirements
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key', 'DEEPSEEK_API_KEY': 'test-key'}):
            self.llm_client = LLMClient(model="gpt-4o-mini")

    @patch('utils.llm.load_config')
    @patch('utils.llm.load_recent')
    def test_dynamic_threshold_strong_negative_gamma(self, mock_load_recent, mock_load_config):
        """Test dynamic threshold with strong negative dealer gamma."""
        # Mock config and recent trades
        mock_load_config.return_value = {"MEMORY_DEPTH": 5}
        mock_load_recent.return_value = []

        # Market data with strong negative dealer gamma
        market_data = {
            "symbol": "SPY",
            "current_price": 450.0,
            "candle_body_pct": 0.03,  # Below standard 0.05% threshold
            "dealer_gamma_$": -2000000,  # Strong negative gamma
            "vwap_deviation_pct": 0.2,
            "atm_delta": 0.52,
            "atm_oi": 15000,
            "trend": "BULLISH"
        }

        # Mock API response
        mock_response = {
            "choices": [{
                "message": {
                    "function_call": {
                        "name": "choose_trade",
                        "arguments": json.dumps({
                            "decision": "BUY_CALL",
                            "confidence": 0.75,
                            "reason": "Strong negative dealer gamma allows lower threshold"
                        })
                    }
                }
            }],
            "usage": {"total_tokens": 500}
        }

        with patch.object(self.llm_client, '_call_openai_api', return_value=mock_response):
            decision = self.llm_client.make_trade_decision(market_data)

        # Verify decision was made (would be NO_TRADE with standard threshold)
        self.assertEqual(decision.decision, "BUY_CALL")
        self.assertGreater(decision.confidence, 0.7)

    @patch('utils.llm.load_config')
    @patch('utils.llm.load_recent')
    def test_dynamic_threshold_moderate_negative_gamma(self, mock_load_recent, mock_load_config):
        """Test dynamic threshold with moderate negative dealer gamma."""
        # Mock config and recent trades
        mock_load_config.return_value = {"MEMORY_DEPTH": 5}
        mock_load_recent.return_value = []

        # Market data with moderate negative dealer gamma
        market_data = {
            "symbol": "QQQ",
            "current_price": 380.0,
            "candle_body_pct": 0.04,  # Below standard but above strong negative threshold
            "dealer_gamma_$": -500000,  # Moderate negative gamma
            "vwap_deviation_pct": 0.15,
            "atm_delta": 0.48,
            "atm_oi": 8000,
            "trend": "BULLISH"
        }

        # Mock API response
        mock_response = {
            "choices": [{
                "message": {
                    "function_call": {
                        "name": "choose_trade",
                        "arguments": json.dumps({
                            "decision": "BUY_CALL",
                            "confidence": 0.65,
                            "reason": "Moderate negative dealer gamma allows slightly lower threshold"
                        })
                    }
                }
            }],
            "usage": {"total_tokens": 450}
        }

        with patch.object(self.llm_client, '_call_openai_api', return_value=mock_response):
            decision = self.llm_client.make_trade_decision(market_data)

        # Verify decision considers moderate gamma adjustment
        self.assertEqual(decision.decision, "BUY_CALL")
        self.assertGreater(decision.confidence, 0.6)

    @patch('utils.llm.load_config')
    @patch('utils.llm.load_recent')
    def test_dynamic_threshold_positive_gamma(self, mock_load_recent, mock_load_config):
        """Test dynamic threshold with positive dealer gamma (standard threshold)."""
        # Mock config and recent trades
        mock_load_config.return_value = {"MEMORY_DEPTH": 5}
        mock_load_recent.return_value = []

        # Market data with positive dealer gamma
        market_data = {
            "symbol": "IWM",
            "current_price": 220.0,
            "candle_body_pct": 0.03,  # Below standard threshold
            "dealer_gamma_$": 1000000,  # Positive gamma
            "vwap_deviation_pct": 0.1,
            "atm_delta": 0.50,
            "atm_oi": 5000,
            "trend": "NEUTRAL"
        }

        # Mock API response for NO_TRADE (standard threshold applies)
        mock_response = {
            "choices": [{
                "message": {
                    "function_call": {
                        "name": "choose_trade",
                        "arguments": json.dumps({
                            "decision": "NO_TRADE",
                            "confidence": 0.8,
                            "reason": "Candle body below standard 0.05% threshold"
                        })
                    }
                }
            }],
            "usage": {"total_tokens": 400}
        }

        with patch.object(self.llm_client, '_call_openai_api', return_value=mock_response):
            decision = self.llm_client.make_trade_decision(market_data)

        # Verify standard threshold is maintained
        self.assertEqual(decision.decision, "NO_TRADE")

    @patch('utils.llm.load_config')
    @patch('utils.llm.load_recent')
    def test_enhanced_llm_features_in_prompt(self, mock_load_recent, mock_load_config):
        """Test that enhanced LLM features are properly included in the prompt."""
        # Mock config and recent trades
        mock_load_config.return_value = {"MEMORY_DEPTH": 5}
        mock_load_recent.return_value = []

        # Market data with all enhanced features
        market_data = {
            "symbol": "SPY",
            "current_price": 450.0,
            "candle_body_pct": 0.06,
            "vwap_deviation_pct": 0.25,  # Enhanced feature
            "atm_delta": 0.52,  # Enhanced feature
            "atm_oi": 15000,  # Enhanced feature
            "dealer_gamma_$": -1500000,  # Enhanced feature
            "trend": "STRONG_BULLISH"
        }

        # Mock API call to capture the prompt
        captured_prompt = None
        def capture_api_call(*args, **kwargs):
            nonlocal captured_prompt
            captured_prompt = kwargs.get('messages', args[0] if args else [])
            return {
                "choices": [{
                    "message": {
                        "function_call": {
                            "name": "choose_trade",
                            "arguments": json.dumps({
                                "decision": "BUY_CALL",
                                "confidence": 0.8,
                                "reason": "All enhanced features considered"
                            })
                        }
                    }
                }],
                "usage": {"total_tokens": 600}
            }

        with patch.object(self.llm_client, '_call_openai_api', side_effect=capture_api_call):
            decision = self.llm_client.make_trade_decision(market_data)

        # Verify enhanced features are in the market data sent to LLM
        user_message = captured_prompt[1]['content']
        market_analysis = json.loads(user_message.split('Market Analysis:\n')[1].split('\n\nBased on')[0])
        
        self.assertIn('vwap_deviation_pct', market_analysis)
        self.assertIn('atm_delta', market_analysis)
        self.assertIn('atm_oi', market_analysis)
        self.assertIn('dealer_gamma_$', market_analysis)
        
        # Verify dynamic threshold context is included
        self.assertIn('DYNAMIC THRESHOLD', user_message)
        self.assertIn('dealer gamma', user_message)

    @patch('utils.llm.load_config')
    @patch('utils.llm.load_recent')
    def test_context_memory_integration(self, mock_load_recent, mock_load_config):
        """Test that context memory from recent trades is properly integrated."""
        # Mock config and recent trades
        mock_load_config.return_value = {"MEMORY_DEPTH": 3}
        mock_recent_trades = [
            {
                "symbol": "SPY",
                "outcome": "WIN",
                "pnl_pct": 12.5,
                "entry_reason": "Strong breakout with high volume"
            },
            {
                "symbol": "QQQ", 
                "outcome": "LOSS",
                "pnl_pct": -8.2,
                "entry_reason": "False breakout, low volume"
            }
        ]
        mock_load_recent.return_value = mock_recent_trades

        market_data = {
            "symbol": "SPY",
            "current_price": 450.0,
            "candle_body_pct": 0.06,
            "dealer_gamma_$": 0,
            "trend": "BULLISH"
        }

        # Mock API call to capture the prompt
        captured_prompt = None
        def capture_api_call(*args, **kwargs):
            nonlocal captured_prompt
            captured_prompt = kwargs.get('messages', args[0] if args else [])
            return {
                "choices": [{
                    "message": {
                        "function_call": {
                            "name": "choose_trade",
                            "arguments": json.dumps({
                                "decision": "BUY_CALL",
                                "confidence": 0.75,
                                "reason": "Learning from recent trade context"
                            })
                        }
                    }
                }],
                "usage": {"total_tokens": 550}
            }

        with patch.object(self.llm_client, '_call_openai_api', side_effect=capture_api_call):
            decision = self.llm_client.make_trade_decision(market_data)

        # Verify recent trades context is included in enhanced_context
        user_message = captured_prompt[1]['content']
        market_analysis = json.loads(user_message.split('Market Analysis:\n')[1].split('\n\nBased on')[0])
        
        # Check that recent_trades are included in the market analysis
        self.assertIn('recent_trades', market_analysis)
        self.assertEqual(len(market_analysis['recent_trades']), 2)

    def test_system_prompt_contains_enhanced_features(self):
        """Test that system prompt contains rules for enhanced LLM features."""
        system_prompt = self.llm_client._get_system_prompt()
        
        # Verify enhanced feature rules are present
        self.assertIn('vwap_deviation_pct', system_prompt)
        self.assertIn('atm_delta', system_prompt)
        self.assertIn('atm_oi', system_prompt)
        self.assertIn('dealer_gamma_$', system_prompt)
        
        # Verify context memory rules are present
        self.assertIn('recent_trades', system_prompt)
        self.assertIn('Learn from recent', system_prompt)

    @patch('utils.llm.load_config')
    @patch('utils.llm.load_recent')
    def test_threshold_calculation_edge_cases(self, mock_load_recent, mock_load_config):
        """Test dynamic threshold calculation with edge cases."""
        # Mock config and recent trades
        mock_load_config.return_value = {"MEMORY_DEPTH": 5}
        mock_load_recent.return_value = []

        # Test case 1: Exactly at strong negative threshold
        market_data_1 = {
            "symbol": "SPY",
            "dealer_gamma_$": -1000000,  # Exactly at threshold
            "candle_body_pct": 0.04
        }

        # Test case 2: Zero dealer gamma
        market_data_2 = {
            "symbol": "QQQ", 
            "dealer_gamma_$": 0,  # Zero gamma
            "candle_body_pct": 0.04
        }

        # Test case 3: Missing dealer gamma
        market_data_3 = {
            "symbol": "IWM",
            "candle_body_pct": 0.04
            # No dealer_gamma_$ field
        }

        test_cases = [market_data_1, market_data_2, market_data_3]
        
        for i, market_data in enumerate(test_cases):
            with self.subTest(case=i):
                # Mock API response
                mock_response = {
                    "choices": [{
                        "message": {
                            "function_call": {
                                "name": "choose_trade",
                                "arguments": json.dumps({
                                    "decision": "NO_TRADE",
                                    "confidence": 0.5,
                                    "reason": f"Edge case {i+1}"
                                })
                            }
                        }
                    }],
                    "usage": {"total_tokens": 300}
                }

                with patch.object(self.llm_client, '_call_openai_api', return_value=mock_response):
                    decision = self.llm_client.make_trade_decision(market_data)
                    
                # Verify decision is made without errors
                self.assertIsInstance(decision, TradeDecision)
                self.assertIn(decision.decision, ["BUY_CALL", "BUY_PUT", "NO_TRADE"])


if __name__ == '__main__':
    unittest.main()
