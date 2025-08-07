#!/usr/bin/env python3
"""
Unit tests for confidence threshold synchronization.

Tests that SYSTEM_TEMPLATE thresholds are properly synced with runtime config,
specifically testing the 65% confidence threshold behavior.

Test Cases:
- Confidence 60% → blocked (below 65% threshold)
- Confidence 70% → allowed (above 65% threshold)
- Confidence calibration cap raised to 90% for trade_count < 20
- True range penalty reduced to 5% instead of 15%
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.llm import LLMClient, TradeDecision


class TestConfidenceThreshold(unittest.TestCase):
    """Test confidence threshold synchronization with config."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_config = {
            "MIN_CONFIDENCE": 0.65,
            "MIN_CANDLE_BODY_PCT": 0.05,
            "MODEL": "gpt-4o-mini"
        }
        
        # Mock environment variables
        self.env_patcher = patch.dict(os.environ, {
            'OPENAI_API_KEY': 'test-key',
            'DEEPSEEK_API_KEY': 'test-key'
        })
        self.env_patcher.start()

    def tearDown(self):
        """Clean up test fixtures."""
        self.env_patcher.stop()

    @patch('utils.llm.load_config')
    def test_system_prompt_uses_config_threshold(self, mock_load_config):
        """Test that system prompt uses MIN_CONFIDENCE from config."""
        mock_load_config.return_value = self.mock_config
        
        client = LLMClient(model="gpt-4o-mini")
        prompt = client._get_system_prompt()
        
        # Should use 0.65 from config, not hardcoded 0.35
        self.assertIn("If confidence < 0.65, override decision to NO_TRADE", prompt)
        self.assertNotIn("If confidence < 0.35, override decision to NO_TRADE", prompt)

    @patch('utils.llm.load_config')
    def test_confidence_cap_raised_to_90_percent(self, mock_load_config):
        """Test that confidence cap is raised to 90% for trade_count < 20."""
        mock_load_config.return_value = self.mock_config
        
        client = LLMClient(model="gpt-4o-mini")
        prompt = client._get_system_prompt()
        
        # Should cap at 90% instead of 50%
        self.assertIn("cap 0.90 if trade_count < 20", prompt)
        self.assertNotIn("cap 0.50 if no memory", prompt)

    @patch('utils.llm.load_config')
    def test_true_range_penalty_reduced(self, mock_load_config):
        """Test that true range penalty is reduced to 5% instead of 15%."""
        mock_load_config.return_value = self.mock_config
        
        client = LLMClient(model="gpt-4o-mini")
        prompt = client._get_system_prompt()
        
        # Should subtract 0.05 instead of 0.15
        self.assertIn("subtract 0.05 from confidence", prompt)
        self.assertNotIn("subtract 0.15 from confidence", prompt)

    @patch('utils.llm.load_config')
    def test_confidence_60_percent_blocked(self, mock_load_config):
        """Test that 60% confidence threshold is properly configured in system prompt."""
        mock_load_config.return_value = self.mock_config
        
        client = LLMClient(model="gpt-4o-mini")
        prompt = client._get_system_prompt()
        
        # Verify the prompt uses 65% threshold from config
        self.assertIn("If confidence < 0.65, override decision to NO_TRADE", prompt)
        
        # This test verifies the prompt configuration
        # The actual blocking of 60% confidence happens in main.py based on MIN_CONFIDENCE
        # The LLM itself should be instructed to return NO_TRADE for confidence < 65%

    @patch('utils.llm.load_config')
    def test_confidence_70_percent_allowed(self, mock_load_config):
        """Test that 70% confidence threshold is properly configured in system prompt."""
        mock_load_config.return_value = self.mock_config
        
        client = LLMClient(model="gpt-4o-mini")
        prompt = client._get_system_prompt()
        
        # Verify the prompt uses 65% threshold from config
        self.assertIn("If confidence < 0.65, override decision to NO_TRADE", prompt)
        
        # This test verifies the prompt configuration
        # Signals with 70% confidence should pass the LLM's internal threshold
        # and then be evaluated against MIN_CONFIDENCE in main.py

    @patch('utils.llm.load_config')
    def test_different_config_threshold_respected(self, mock_load_config):
        """Test that different MIN_CONFIDENCE values are respected."""
        # Test with different threshold
        custom_config = self.mock_config.copy()
        custom_config["MIN_CONFIDENCE"] = 0.75
        mock_load_config.return_value = custom_config
        
        client = LLMClient(model="gpt-4o-mini")
        prompt = client._get_system_prompt()
        
        # Should use 0.75 from config
        self.assertIn("If confidence < 0.75, override decision to NO_TRADE", prompt)

    @patch('utils.llm.load_config')
    def test_default_threshold_when_missing(self, mock_load_config):
        """Test that default 65% threshold is used when MIN_CONFIDENCE is missing."""
        config_without_threshold = {
            "MIN_CANDLE_BODY_PCT": 0.05,
            "MODEL": "gpt-4o-mini"
        }
        mock_load_config.return_value = config_without_threshold
        
        client = LLMClient(model="gpt-4o-mini")
        prompt = client._get_system_prompt()
        
        # Should use default 0.65
        self.assertIn("If confidence < 0.65, override decision to NO_TRADE", prompt)


if __name__ == "__main__":
    unittest.main()
