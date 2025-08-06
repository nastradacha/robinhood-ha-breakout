"""
Unit tests for LLM integration utilities.
"""

import pytest
import json
from unittest.mock import patch, MagicMock
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.llm import LLMClient, TradeDecision, BankrollUpdate


class TestLLMClient:
    """Test LLM client initialization and configuration."""

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_llm_client_openai_init(self):
        """Test LLM client initialization with OpenAI."""
        client = LLMClient("gpt-4o-mini")
        assert client.model == "gpt-4o-mini"
        assert client.openai_key == "test-key"

    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})
    def test_llm_client_deepseek_init(self):
        """Test LLM client initialization with DeepSeek."""
        client = LLMClient("deepseek-chat")
        assert client.model == "deepseek-chat"
        assert client.deepseek_key == "test-key"

    def test_llm_client_missing_openai_key(self):
        """Test error when OpenAI key is missing."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="OPENAI_API_KEY required"):
                LLMClient("gpt-4o-mini")

    def test_llm_client_missing_deepseek_key(self):
        """Test error when DeepSeek key is missing."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="DEEPSEEK_API_KEY required"):
                LLMClient("deepseek-chat")

    def test_get_function_schemas(self):
        """Test function schema generation."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            client = LLMClient("gpt-4o-mini")
            schemas = client._get_function_schemas()

            assert len(schemas) == 2

            # Check choose_trade function
            choose_trade = next(s for s in schemas if s["name"] == "choose_trade")
            assert "decision" in choose_trade["parameters"]["properties"]
            assert "confidence" in choose_trade["parameters"]["properties"]

            # Check update_bankroll function
            update_bankroll = next(s for s in schemas if s["name"] == "update_bankroll")
            assert "new_bankroll" in update_bankroll["parameters"]["properties"]
            assert "reason" in update_bankroll["parameters"]["properties"]

    def test_get_system_prompt(self):
        """Test system prompt generation."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            client = LLMClient("gpt-4o-mini")
            prompt = client._get_system_prompt()

            assert "options-trading assistant" in prompt.lower()
            assert "heikin-ashi" in prompt.lower()
            assert "choose_trade" in prompt
            assert "confidence" in prompt.lower()


class TestTradeDecisionMaking:
    """Test trade decision making functionality."""

    def create_sample_market_data(self):
        """Create sample market data for testing."""
        return {
            "price": 150.25,
            "body_pct": 0.85,
            "tr_pct": 1.2,
            "trend": "BULLISH",
            "room_up": 0.75,
            "room_down": 1.5,
            "resistance": [151.0, 152.5, 154.0],
            "support": [146.0, 144.5, 143.0],
            "volume": 1500000,
            "timestamp": "2023-01-01T10:30:00",
        }

    @patch("utils.llm.openai.ChatCompletion.create")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_make_trade_decision_openai_call(self, mock_openai):
        """Test trade decision with OpenAI CALL."""
        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = {
            "function_call": {
                "name": "choose_trade",
                "arguments": json.dumps(
                    {
                        "decision": "CALL",
                        "confidence": 0.75,
                        "reason": "Strong bullish breakout pattern",
                    }
                ),
            }
        }
        mock_response.usage.total_tokens = 150
        mock_openai.return_value = mock_response

        client = LLMClient("gpt-4o-mini")
        market_data = self.create_sample_market_data()

        decision = client.make_trade_decision(market_data)

        assert isinstance(decision, TradeDecision)
        assert decision.decision == "CALL"
        assert decision.confidence == 0.75
        assert decision.reason == "Strong bullish breakout pattern"
        assert decision.tokens_used == 150

        mock_openai.assert_called_once()

    @patch("utils.llm.openai.ChatCompletion.create")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_make_trade_decision_openai_put(self, mock_openai):
        """Test trade decision with OpenAI PUT."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = {
            "function_call": {
                "name": "choose_trade",
                "arguments": json.dumps({"decision": "PUT", "confidence": 0.65}),
            }
        }
        mock_response.usage.total_tokens = 120
        mock_openai.return_value = mock_response

        client = LLMClient("gpt-4o-mini")
        market_data = self.create_sample_market_data()

        decision = client.make_trade_decision(market_data)

        assert decision.decision == "PUT"
        assert decision.confidence == 0.65
        assert decision.reason is None

    @patch("utils.llm.openai.ChatCompletion.create")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_make_trade_decision_no_trade(self, mock_openai):
        """Test trade decision with NO_TRADE."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = {
            "function_call": {
                "name": "choose_trade",
                "arguments": json.dumps(
                    {
                        "decision": "NO_TRADE",
                        "confidence": 0.25,
                        "reason": "Insufficient volatility",
                    }
                ),
            }
        }
        mock_response.usage.total_tokens = 100
        mock_openai.return_value = mock_response

        client = LLMClient("gpt-4o-mini")
        market_data = self.create_sample_market_data()

        decision = client.make_trade_decision(market_data)

        assert decision.decision == "NO_TRADE"
        assert decision.confidence == 0.25
        assert decision.reason == "Insufficient volatility"

    @patch("utils.llm.requests.post")
    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})
    def test_make_trade_decision_deepseek(self, mock_post):
        """Test trade decision with DeepSeek."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "function_call": {
                            "name": "choose_trade",
                            "arguments": json.dumps(
                                {"decision": "CALL", "confidence": 0.80}
                            ),
                        }
                    }
                }
            ],
            "usage": {"total_tokens": 140},
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        client = LLMClient("deepseek-chat")
        market_data = self.create_sample_market_data()

        decision = client.make_trade_decision(market_data)

        assert decision.decision == "CALL"
        assert decision.confidence == 0.80
        assert decision.tokens_used == 140

        mock_post.assert_called_once()

    @patch("utils.llm.openai.ChatCompletion.create")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_make_trade_decision_with_win_history(self, mock_openai):
        """Test trade decision with win history."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = {
            "function_call": {
                "name": "choose_trade",
                "arguments": json.dumps({"decision": "CALL", "confidence": 0.70}),
            }
        }
        mock_response.usage.total_tokens = 160
        mock_openai.return_value = mock_response

        client = LLMClient("gpt-4o-mini")
        market_data = self.create_sample_market_data()
        win_history = [True, False, True, True, False]  # 60% win rate

        decision = client.make_trade_decision(market_data, win_history)

        # Check that win rate context was included in the call
        call_args = mock_openai.call_args[1]
        messages = call_args["messages"]
        user_message = next(m for m in messages if m["role"] == "user")
        assert "Recent win rate: 0.60" in user_message["content"]

    @patch("utils.llm.openai.ChatCompletion.create")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_make_trade_decision_api_error(self, mock_openai):
        """Test trade decision with API error."""
        mock_openai.side_effect = Exception("API Error")

        client = LLMClient("gpt-4o-mini")
        market_data = self.create_sample_market_data()

        decision = client.make_trade_decision(market_data)

        assert decision.decision == "NO_TRADE"
        assert decision.confidence == 0.0
        assert "API error" in decision.reason
        assert decision.tokens_used == 0

    @patch("utils.llm.openai.ChatCompletion.create")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_make_trade_decision_no_function_call(self, mock_openai):
        """Test trade decision when no function call is returned."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = {"content": "Some text response"}
        mock_response.usage.total_tokens = 50
        mock_openai.return_value = mock_response

        client = LLMClient("gpt-4o-mini")
        market_data = self.create_sample_market_data()

        decision = client.make_trade_decision(market_data)

        assert decision.decision == "NO_TRADE"
        assert decision.confidence == 0.0
        assert "did not provide valid function call" in decision.reason


class TestBankrollUpdateSuggestion:
    """Test bankroll update suggestion functionality."""

    @patch("utils.llm.openai.ChatCompletion.create")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_suggest_bankroll_update_significant_change(self, mock_openai):
        """Test bankroll update suggestion for significant change."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = {
            "function_call": {
                "name": "update_bankroll",
                "arguments": json.dumps(
                    {
                        "new_bankroll": 45.0,
                        "reason": "Successful trade increased bankroll by 12.5%",
                    }
                ),
            }
        }
        mock_response.usage.total_tokens = 80
        mock_openai.return_value = mock_response

        client = LLMClient("gpt-4o-mini")

        update = client.suggest_bankroll_update(
            current_bankroll=40.0,
            realized_pnl=5.0,
            trade_details={"symbol": "SPY", "direction": "CALL"},
        )

        assert isinstance(update, BankrollUpdate)
        assert update.new_bankroll == 45.0
        assert "Successful trade" in update.reason
        assert update.tokens_used == 80

    @patch("utils.llm.openai.ChatCompletion.create")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_suggest_bankroll_update_small_change(self, mock_openai):
        """Test bankroll update suggestion for small change (should return None)."""
        client = LLMClient("gpt-4o-mini")

        # Small change (2% - below 5% threshold)
        update = client.suggest_bankroll_update(
            current_bankroll=40.0,
            realized_pnl=0.8,  # 2% change
            trade_details={"symbol": "SPY", "direction": "CALL"},
        )

        assert update is None
        # OpenAI should not be called for small changes
        mock_openai.assert_not_called()

    @patch("utils.llm.openai.ChatCompletion.create")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_suggest_bankroll_update_no_function_call(self, mock_openai):
        """Test bankroll update when no function call is returned."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = {"content": "Some text response"}
        mock_response.usage.total_tokens = 50
        mock_openai.return_value = mock_response

        client = LLMClient("gpt-4o-mini")

        update = client.suggest_bankroll_update(
            current_bankroll=40.0,
            realized_pnl=5.0,
            trade_details={"symbol": "SPY", "direction": "CALL"},
        )

        assert update is None


class TestSimilarTradeSuggestion:
    """Test similar trade suggestion functionality."""

    @patch("utils.llm.openai.ChatCompletion.create")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_suggest_similar_trade_openai(self, mock_openai):
        """Test similar trade suggestion with OpenAI."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            "Consider QQQ CALL options with similar delta and expiry. Current QQQ showing bullish momentum with good volume."
        )
        mock_openai.return_value = mock_response

        client = LLMClient("gpt-4o-mini")

        completed_trade = {
            "symbol": "SPY",
            "direction": "CALL",
            "strike": 450.0,
            "confidence": 0.75,
        }

        market_data = {"price": 450.25, "trend": "BULLISH", "volume": 1500000}

        suggestion = client.suggest_similar_trade(completed_trade, market_data)

        assert suggestion is not None
        assert "QQQ CALL" in suggestion
        assert "bullish momentum" in suggestion
        mock_openai.assert_called_once()

    @patch("utils.llm.requests.post")
    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})
    def test_suggest_similar_trade_deepseek(self, mock_post):
        """Test similar trade suggestion with DeepSeek."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "No similar opportunities identified at this time."
                    }
                }
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        client = LLMClient("deepseek-chat")

        completed_trade = {"symbol": "SPY", "direction": "PUT"}
        market_data = {"price": 450.25, "trend": "BEARISH"}

        suggestion = client.suggest_similar_trade(completed_trade, market_data)

        assert suggestion == "No similar opportunities identified at this time."
        mock_post.assert_called_once()

    @patch("utils.llm.openai.ChatCompletion.create")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_suggest_similar_trade_api_error(self, mock_openai):
        """Test similar trade suggestion with API error."""
        mock_openai.side_effect = Exception("API Error")

        client = LLMClient("gpt-4o-mini")

        completed_trade = {"symbol": "SPY", "direction": "CALL"}
        market_data = {"price": 450.25}

        suggestion = client.suggest_similar_trade(completed_trade, market_data)

        assert suggestion is None


if __name__ == "__main__":
    pytest.main([__file__])
