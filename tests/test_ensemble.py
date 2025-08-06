#!/usr/bin/env python3
"""
Unit tests for Ensemble LLM Decision Engine (v0.6.0)

Tests the two-model ensemble voting system with majority vote, tie-breaking,
and robust failure handling scenarios.

Test Coverage:
- Majority vote scenarios (clear winners)
- Tie-breaking by highest confidence
- Single model failure handling
- All models failure handling
- Configuration validation
- Edge cases and error conditions

Author: Robinhood HA Breakout System
Version: 0.6.0
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from utils.ensemble_llm import EnsembleLLM, choose_trade
from utils.llm import TradeDecision


class TestEnsembleLLM:
    """Test suite for EnsembleLLM class."""
    
    @pytest.fixture
    def mock_config_enabled(self):
        """Mock configuration with ensemble enabled."""
        return {
            "ENSEMBLE_ENABLED": True,
            "ENSEMBLE_MODELS": ["gpt-4o-mini", "deepseek-chat"],
            "MODEL": "gpt-4o-mini"
        }
    
    @pytest.fixture
    def mock_config_disabled(self):
        """Mock configuration with ensemble disabled."""
        return {
            "ENSEMBLE_ENABLED": False,
            "ENSEMBLE_MODELS": ["gpt-4o-mini", "deepseek-chat"],
            "MODEL": "gpt-4o-mini"
        }
    
    @pytest.fixture
    def sample_payload(self):
        """Sample market data payload for testing."""
        return {
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
    
    @patch('utils.ensemble_llm.load_config')
    @patch('utils.ensemble_llm.LLMClient')
    def test_majority_win(self, mock_llm_client, mock_load_config, mock_config_enabled, sample_payload):
        """Test majority vote: GPT=CALL 0.6, DeepSeek=CALL 0.4 → CALL 0.5"""
        mock_load_config.return_value = mock_config_enabled
        
        # Mock LLM clients
        gpt_client = Mock()
        deepseek_client = Mock()
        
        # Mock decisions: both CALL with different confidences
        gpt_decision = TradeDecision(decision="CALL", confidence=0.6, reason="GPT bullish signal")
        deepseek_decision = TradeDecision(decision="CALL", confidence=0.4, reason="DeepSeek momentum")
        
        gpt_client.make_trade_decision.return_value = gpt_decision
        deepseek_client.make_trade_decision.return_value = deepseek_decision
        
        # Mock LLMClient constructor to return our mocked clients
        def mock_client_factory(model):
            if model == "gpt-4o-mini":
                return gpt_client
            elif model == "deepseek-chat":
                return deepseek_client
            
        mock_llm_client.side_effect = mock_client_factory
        
        # Test ensemble decision
        ensemble = EnsembleLLM()
        result = ensemble.choose_trade(sample_payload)
        
        # Verify majority vote result
        assert result["decision"] == "CALL"
        assert result["confidence"] == 0.5  # Average of 0.6 and 0.4
        assert "Majority vote: CALL (2/2 models)" in result["reason"]
        assert "GPT bullish signal" in result["reason"]
        assert "DeepSeek momentum" in result["reason"]
    
    @patch('utils.ensemble_llm.load_config')
    @patch('utils.ensemble_llm.LLMClient')
    def test_tie_high_conf(self, mock_llm_client, mock_load_config, mock_config_enabled, sample_payload):
        """Test tie-breaking: CALL 0.6 vs NO_TRADE 0.55 → CALL 0.6"""
        mock_load_config.return_value = mock_config_enabled
        
        # Mock LLM clients
        gpt_client = Mock()
        deepseek_client = Mock()
        
        # Mock decisions: tie between CALL and NO_TRADE, CALL has higher confidence
        gpt_decision = TradeDecision(decision="CALL", confidence=0.6, reason="GPT strong signal")
        deepseek_decision = TradeDecision(decision="NO_TRADE", confidence=0.55, reason="DeepSeek cautious")
        
        gpt_client.make_trade_decision.return_value = gpt_decision
        deepseek_client.make_trade_decision.return_value = deepseek_decision
        
        def mock_client_factory(model):
            if model == "gpt-4o-mini":
                return gpt_client
            elif model == "deepseek-chat":
                return deepseek_client
                
        mock_llm_client.side_effect = mock_client_factory
        
        # Test ensemble decision
        ensemble = EnsembleLLM()
        result = ensemble.choose_trade(sample_payload)
        
        # Verify tie-breaking result
        assert result["decision"] == "CALL"
        assert result["confidence"] == 0.6  # Average of winning class (only CALL)
        assert "Tie-break winner: CALL" in result["reason"]
        assert "highest conf: 0.6" in result["reason"]
    
    @patch('utils.ensemble_llm.load_config')
    @patch('utils.ensemble_llm.LLMClient')
    def test_provider_failure(self, mock_llm_client, mock_load_config, mock_config_enabled, sample_payload):
        """Test provider failure: DeepSeek raises; GPT ok → use GPT"""
        mock_load_config.return_value = mock_config_enabled
        
        # Mock LLM clients
        gpt_client = Mock()
        deepseek_client = Mock()
        
        # GPT succeeds, DeepSeek fails
        gpt_decision = TradeDecision(decision="PUT", confidence=0.7, reason="GPT bearish signal")
        gpt_client.make_trade_decision.return_value = gpt_decision
        deepseek_client.make_trade_decision.side_effect = Exception("DeepSeek API error")
        
        def mock_client_factory(model):
            if model == "gpt-4o-mini":
                return gpt_client
            elif model == "deepseek-chat":
                return deepseek_client
                
        mock_llm_client.side_effect = mock_client_factory
        
        # Test ensemble decision with failure
        ensemble = EnsembleLLM()
        result = ensemble.choose_trade(sample_payload)
        
        # Verify fallback to single model
        assert result["decision"] == "PUT"
        assert result["confidence"] == 0.7
        assert "single model: gpt-4o-mini" in result["reason"]
    
    @patch('utils.ensemble_llm.load_config')
    @patch('utils.ensemble_llm.LLMClient')
    def test_all_fail(self, mock_llm_client, mock_load_config, mock_config_enabled, sample_payload):
        """Test all providers fail → RuntimeError"""
        mock_load_config.return_value = mock_config_enabled
        
        # Mock LLM clients - both fail
        gpt_client = Mock()
        deepseek_client = Mock()
        
        gpt_client.make_trade_decision.side_effect = Exception("GPT API error")
        deepseek_client.make_trade_decision.side_effect = Exception("DeepSeek API error")
        
        def mock_client_factory(model):
            if model == "gpt-4o-mini":
                return gpt_client
            elif model == "deepseek-chat":
                return deepseek_client
                
        mock_llm_client.side_effect = mock_client_factory
        
        # Test ensemble decision with all failures
        ensemble = EnsembleLLM()
        
        with pytest.raises(RuntimeError, match="All LLM providers failed"):
            ensemble.choose_trade(sample_payload)
    
    @patch('utils.ensemble_llm.load_config')
    @patch('utils.ensemble_llm.LLMClient')
    def test_ensemble_disabled_fallback(self, mock_llm_client, mock_load_config, mock_config_disabled, sample_payload):
        """Test ensemble disabled → single-model fallback"""
        mock_load_config.return_value = mock_config_disabled
        
        # Mock single LLM client
        fallback_client = Mock()
        fallback_decision = TradeDecision(decision="NO_TRADE", confidence=0.3, reason="Low confidence")
        fallback_client.make_trade_decision.return_value = fallback_decision
        
        mock_llm_client.return_value = fallback_client
        
        # Test ensemble with disabled config
        ensemble = EnsembleLLM()
        result = ensemble.choose_trade(sample_payload)
        
        # Verify single-model fallback
        assert result["decision"] == "NO_TRADE"
        assert result["confidence"] == 0.3
        assert "Single-model decision (ensemble disabled)" in result["reason"]
    
    @patch('utils.ensemble_llm.load_config')
    def test_insufficient_models_config(self, mock_load_config, sample_payload):
        """Test insufficient models in config → disable ensemble"""
        mock_config = {
            "ENSEMBLE_ENABLED": True,
            "ENSEMBLE_MODELS": ["gpt-4o-mini"],  # Only one model
            "MODEL": "gpt-4o-mini"
        }
        mock_load_config.return_value = mock_config
        
        # Test ensemble initialization with insufficient models
        ensemble = EnsembleLLM()
        
        # Should disable ensemble due to insufficient models
        assert ensemble.enabled is False
    
    @patch('utils.ensemble_llm.load_config')
    @patch('utils.ensemble_llm.LLMClient')
    def test_three_way_tie_break(self, mock_llm_client, mock_load_config, sample_payload):
        """Test three-way tie scenario with extended model list"""
        # Mock config with 3 models for more complex voting
        mock_config = {
            "ENSEMBLE_ENABLED": True,
            "ENSEMBLE_MODELS": ["gpt-4o-mini", "deepseek-chat", "gpt-3.5-turbo"],
            "MODEL": "gpt-4o-mini"
        }
        mock_load_config.return_value = mock_config
        
        # Mock three different decisions
        clients = {}
        decisions = [
            ("gpt-4o-mini", TradeDecision(decision="CALL", confidence=0.8, reason="GPT strong bull")),
            ("deepseek-chat", TradeDecision(decision="PUT", confidence=0.6, reason="DeepSeek bear")),
            ("gpt-3.5-turbo", TradeDecision(decision="NO_TRADE", confidence=0.4, reason="GPT3.5 neutral"))
        ]
        
        for model, decision in decisions:
            client = Mock()
            client.make_trade_decision.return_value = decision
            clients[model] = client
        
        def mock_client_factory(model):
            return clients[model]
            
        mock_llm_client.side_effect = mock_client_factory
        
        # Test three-way tie (each decision gets 1 vote)
        ensemble = EnsembleLLM()
        result = ensemble.choose_trade(sample_payload)
        
        # Should pick CALL due to highest confidence (0.8)
        assert result["decision"] == "CALL"
        assert result["confidence"] == 0.8  # Only one CALL vote
        assert "Tie-break winner: CALL" in result["reason"]
    
    def test_convenience_function(self, sample_payload):
        """Test the convenience choose_trade function"""
        with patch('utils.ensemble_llm.EnsembleLLM') as mock_ensemble_class:
            mock_ensemble = Mock()
            mock_result = {"decision": "CALL", "confidence": 0.75, "reason": "Test result"}
            mock_ensemble.choose_trade.return_value = mock_result
            mock_ensemble_class.return_value = mock_ensemble
            
            # Test convenience function
            result = choose_trade(sample_payload)
            
            assert result == mock_result
            mock_ensemble_class.assert_called_once()
            mock_ensemble.choose_trade.assert_called_once_with(sample_payload)


class TestEnsembleIntegration:
    """Integration tests for ensemble system."""
    
    @patch('utils.ensemble_llm.load_config')
    @patch('utils.ensemble_llm.LLMClient')
    def test_real_payload_structure(self, mock_llm_client, mock_load_config):
        """Test ensemble with realistic market data payload structure"""
        mock_config = {
            "ENSEMBLE_ENABLED": True,
            "ENSEMBLE_MODELS": ["gpt-4o-mini", "deepseek-chat"],
            "MODEL": "gpt-4o-mini"
        }
        mock_load_config.return_value = mock_config
        
        # Realistic payload with all enhanced features
        realistic_payload = {
            "price": 632.82,
            "body_pct": 0.25,
            "tr_pct": 0.18,
            "trend": "BULLISH",
            "room_up": 0.8,
            "room_down": 1.2,
            "resistance": [635.50, 638.20, 641.00],
            "support": [630.10, 627.50, 625.00],
            "volume": 1250000,
            "timestamp": "2025-08-06 15:20:00",
            "today_true_range_pct": 0.18,
            "room_to_next_pivot": 1.2,
            "iv_5m": 28.5,
            "candle_body_pct": 0.25,
            "current_price": 632.82,
            "trend_direction": "BULLISH",
            "volume_confirmation": True,
            "support_levels": [630.10, 627.50, 625.00],
            "resistance_levels": [635.50, 638.20, 641.00],
            "vwap_deviation_pct": 0.004,
            "atm_delta": 0.497,
            "atm_oi": 10672,
            "dealer_gamma_$": -250000000.0
        }
        
        # Mock clients with realistic decisions
        gpt_client = Mock()
        deepseek_client = Mock()
        
        gpt_decision = TradeDecision(
            decision="CALL", 
            confidence=0.65, 
            reason="Strong bullish momentum with high OI and negative dealer gamma"
        )
        deepseek_decision = TradeDecision(
            decision="CALL", 
            confidence=0.58, 
            reason="VWAP deviation positive, ATM delta favorable for calls"
        )
        
        gpt_client.make_trade_decision.return_value = gpt_decision
        deepseek_client.make_trade_decision.return_value = deepseek_decision
        
        def mock_client_factory(model):
            if model == "gpt-4o-mini":
                return gpt_client
            elif model == "deepseek-chat":
                return deepseek_client
                
        mock_llm_client.side_effect = mock_client_factory
        
        # Test with realistic payload
        result = choose_trade(realistic_payload)
        
        # Verify realistic ensemble result
        assert result["decision"] == "CALL"
        assert abs(result["confidence"] - 0.615) < 0.01  # Average of 0.65 and 0.58
        assert "Majority vote: CALL (2/2 models)" in result["reason"]
        assert "Strong bullish momentum" in result["reason"]
        assert "VWAP deviation positive" in result["reason"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
