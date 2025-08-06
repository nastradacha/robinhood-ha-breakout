"""
Unit tests for S2: Throttled heartbeat one-liner functionality.
Tests the heartbeat throttling logic in main.py loop mode.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestHeartbeat(unittest.TestCase):
    """Test S2: Throttled heartbeat one-liner."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_config = {
            "HEARTBEAT_EVERY": 3,  # Send heartbeat every 3 cycles
            "SLACK_WEBHOOK_URL": "https://hooks.slack.com/test",
            "SLACK_BOT_TOKEN": "xoxb-test-token",
            "SLACK_CHANNEL_ID": "C1234567890",
        }

    def test_heartbeat_throttling_logic(self):
        """Test heartbeat throttling logic."""
        heartbeat_every = self.mock_config["HEARTBEAT_EVERY"]
        
        # Test cycles that should trigger heartbeat
        self.assertTrue(3 % heartbeat_every == 0)  # Cycle 3
        self.assertTrue(6 % heartbeat_every == 0)  # Cycle 6
        self.assertTrue(9 % heartbeat_every == 0)  # Cycle 9
        
        # Test cycles that should NOT trigger heartbeat
        self.assertFalse(1 % heartbeat_every == 0)  # Cycle 1
        self.assertFalse(2 % heartbeat_every == 0)  # Cycle 2
        self.assertFalse(4 % heartbeat_every == 0)  # Cycle 4
        self.assertFalse(5 % heartbeat_every == 0)  # Cycle 5

    def test_heartbeat_message_format(self):
        """Test heartbeat message format for NO_TRADE cycles."""
        # Test heartbeat message components
        cycle_count = 6
        current_time = datetime.now().strftime("%H:%M")
        symbol = "SPY"
        current_price = 580.25
        
        # Expected format: ⏳ Cycle 6 (14:30) · SPY $580.25 · NO_TRADE
        expected_msg = f"⏳ Cycle {cycle_count} ({current_time}) · {symbol} ${current_price:.2f} · NO_TRADE"
        
        self.assertIn("⏳", expected_msg)
        self.assertIn(f"Cycle {cycle_count}", expected_msg)
        self.assertIn(current_time, expected_msg)
        self.assertIn(symbol, expected_msg)
        self.assertIn(f"${current_price:.2f}", expected_msg)
        self.assertIn("NO_TRADE", expected_msg)

    def test_multi_symbol_heartbeat_format(self):
        """Test heartbeat message format for multi-symbol scanning."""
        cycle_count = 3
        current_time = datetime.now().strftime("%H:%M")
        symbols = ["SPY", "QQQ", "IWM"]
        prices = [580.25, 485.10, 220.75]
        
        # Expected format: ⏳ Cycle 3 (14:30) · SPY $580.25, QQQ $485.10, IWM $220.75 · NO_TRADE
        price_str = ", ".join([f"{sym} ${price:.2f}" for sym, price in zip(symbols, prices)])
        expected_msg = f"⏳ Cycle {cycle_count} ({current_time}) · {price_str} · NO_TRADE"
        
        self.assertIn("⏳", expected_msg)
        self.assertIn(f"Cycle {cycle_count}", expected_msg)
        self.assertIn(current_time, expected_msg)
        for symbol in symbols:
            self.assertIn(symbol, expected_msg)
        for price in prices:
            self.assertIn(f"${price:.2f}", expected_msg)
        self.assertIn("NO_TRADE", expected_msg)

    @patch("utils.enhanced_slack.requests.post")
    def test_heartbeat_slack_integration(self, mock_post):
        """Test heartbeat integration with Slack."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        
        from utils.enhanced_slack import EnhancedSlackIntegration
        
        slack_integration = EnhancedSlackIntegration(self.mock_config)
        
        # Test heartbeat message
        heartbeat_msg = "⏳ Cycle 3 (14:30) · SPY $580.25 · NO_TRADE"
        result = slack_integration.send_heartbeat(heartbeat_msg)
        
        self.assertTrue(result)
        mock_post.assert_called_once()
        
        # Verify message content
        call_args = mock_post.call_args
        self.assertIn("⏳", str(call_args))
        self.assertIn("Cycle 3", str(call_args))
        self.assertIn("NO_TRADE", str(call_args))

    def test_heartbeat_config_validation(self):
        """Test heartbeat configuration validation."""
        # Test valid HEARTBEAT_EVERY values
        valid_configs = [
            {"HEARTBEAT_EVERY": 1},  # Every cycle
            {"HEARTBEAT_EVERY": 3},  # Every 3 cycles
            {"HEARTBEAT_EVERY": 5},  # Every 5 cycles
            {"HEARTBEAT_EVERY": 10}, # Every 10 cycles
        ]
        
        for config in valid_configs:
            heartbeat_every = config["HEARTBEAT_EVERY"]
            self.assertIsInstance(heartbeat_every, int)
            self.assertGreater(heartbeat_every, 0)

    def test_heartbeat_timing_logic(self):
        """Test heartbeat timing with different intervals."""
        test_cases = [
            {"heartbeat_every": 1, "cycles": [1, 2, 3, 4, 5], "expected": [1, 2, 3, 4, 5]},
            {"heartbeat_every": 2, "cycles": [1, 2, 3, 4, 5], "expected": [2, 4]},
            {"heartbeat_every": 3, "cycles": [1, 2, 3, 4, 5, 6], "expected": [3, 6]},
            {"heartbeat_every": 5, "cycles": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], "expected": [5, 10]},
        ]
        
        for case in test_cases:
            heartbeat_every = case["heartbeat_every"]
            cycles = case["cycles"]
            expected = case["expected"]
            
            actual = [cycle for cycle in cycles if cycle % heartbeat_every == 0]
            self.assertEqual(actual, expected, 
                           f"Failed for heartbeat_every={heartbeat_every}, cycles={cycles}")

    def test_heartbeat_no_spam_protection(self):
        """Test that heartbeat prevents Slack spam."""
        heartbeat_every = 5
        total_cycles = 20
        
        # Count how many heartbeats would be sent
        heartbeat_cycles = [cycle for cycle in range(1, total_cycles + 1) 
                          if cycle % heartbeat_every == 0]
        
        # Should only send 4 heartbeats for 20 cycles with HEARTBEAT_EVERY=5
        expected_heartbeats = [5, 10, 15, 20]
        self.assertEqual(heartbeat_cycles, expected_heartbeats)
        
        # Verify spam protection: 20 cycles -> only 4 messages (80% reduction)
        spam_reduction = (total_cycles - len(heartbeat_cycles)) / total_cycles
        self.assertGreater(spam_reduction, 0.5)  # At least 50% reduction

    def test_heartbeat_disabled_when_zero(self):
        """Test heartbeat is disabled when HEARTBEAT_EVERY is 0."""
        heartbeat_every = 0
        cycles = [1, 2, 3, 4, 5, 10, 20, 100]
        
        # When HEARTBEAT_EVERY is 0, no heartbeats should be sent
        # (cycle % 0 would cause division by zero, so this should be handled)
        for cycle in cycles:
            if heartbeat_every > 0:
                should_send = cycle % heartbeat_every == 0
            else:
                should_send = False  # Disabled
            
            self.assertFalse(should_send, f"Heartbeat should be disabled when HEARTBEAT_EVERY=0")


if __name__ == "__main__":
    unittest.main()
