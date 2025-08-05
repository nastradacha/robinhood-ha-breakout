#!/usr/bin/env python3
"""
Unit tests for Slack trade confirmation functionality.

Tests the handle_confirmation_message method in EnhancedSlackIntegration
to ensure proper parsing and handling of trade confirmation messages.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.enhanced_slack import EnhancedSlackIntegration


class TestSlackConfirmation:
    """Test cases for Slack trade confirmation functionality."""
    
    @pytest.fixture
    def enhanced_slack(self):
        """Create EnhancedSlackIntegration instance for testing."""
        with patch('utils.enhanced_slack.SlackNotifier'), \
             patch('utils.enhanced_slack.SlackChartGenerator'), \
             patch('utils.enhanced_slack.EnhancedSlackNotifier'):
            slack = EnhancedSlackIntegration()
            return slack
    
    @pytest.fixture
    def mock_trade_confirmation_manager(self):
        """Create mock TradeConfirmationManager."""
        manager = Mock()
        manager.record_trade_outcome = Mock()
        return manager
    
    def test_handle_submitted_message(self, enhanced_slack, mock_trade_confirmation_manager):
        """Test handling of 'submitted' confirmation message."""
        # Setup
        enhanced_slack.set_trade_confirmation_manager(mock_trade_confirmation_manager)
        event = {
            'text': 'submitted',
            'channel': 'C1234567890',
            'user': 'U1234567890'
        }
        
        # Mock the ephemeral reply method
        enhanced_slack._send_ephemeral_reply = Mock()
        
        # Execute
        result = enhanced_slack.handle_confirmation_message(event)
        
        # Assert
        assert result is True
        mock_trade_confirmation_manager.record_trade_outcome.assert_called_once_with('SUBMITTED', None)
        enhanced_slack._send_ephemeral_reply.assert_called_once_with(
            'C1234567890', 'U1234567890', '✅ Trade recorded (SUBMITTED @ estimated price)'
        )
    
    def test_handle_filled_with_price_message(self, enhanced_slack, mock_trade_confirmation_manager):
        """Test handling of 'filled $1.27' confirmation message."""
        # Setup
        enhanced_slack.set_trade_confirmation_manager(mock_trade_confirmation_manager)
        event = {
            'text': 'filled $1.27',
            'channel': 'C1234567890',
            'user': 'U1234567890'
        }
        
        # Mock the ephemeral reply method
        enhanced_slack._send_ephemeral_reply = Mock()
        
        # Execute
        result = enhanced_slack.handle_confirmation_message(event)
        
        # Assert
        assert result is True
        mock_trade_confirmation_manager.record_trade_outcome.assert_called_once_with('SUBMITTED', 1.27)
        enhanced_slack._send_ephemeral_reply.assert_called_once_with(
            'C1234567890', 'U1234567890', '✅ Trade recorded (SUBMITTED @ $1.27)'
        )
    
    def test_handle_filled_without_dollar_sign(self, enhanced_slack, mock_trade_confirmation_manager):
        """Test handling of 'filled 0.85' confirmation message."""
        # Setup
        enhanced_slack.set_trade_confirmation_manager(mock_trade_confirmation_manager)
        event = {
            'text': 'filled 0.85',
            'channel': 'C1234567890',
            'user': 'U1234567890'
        }
        
        # Mock the ephemeral reply method
        enhanced_slack._send_ephemeral_reply = Mock()
        
        # Execute
        result = enhanced_slack.handle_confirmation_message(event)
        
        # Assert
        assert result is True
        mock_trade_confirmation_manager.record_trade_outcome.assert_called_once_with('SUBMITTED', 0.85)
        enhanced_slack._send_ephemeral_reply.assert_called_once_with(
            'C1234567890', 'U1234567890', '✅ Trade recorded (SUBMITTED @ $0.85)'
        )
    
    def test_handle_cancelled_message(self, enhanced_slack, mock_trade_confirmation_manager):
        """Test handling of 'cancelled' confirmation message."""
        # Setup
        enhanced_slack.set_trade_confirmation_manager(mock_trade_confirmation_manager)
        event = {
            'text': 'cancelled',
            'channel': 'C1234567890',
            'user': 'U1234567890'
        }
        
        # Mock the ephemeral reply method
        enhanced_slack._send_ephemeral_reply = Mock()
        
        # Execute
        result = enhanced_slack.handle_confirmation_message(event)
        
        # Assert
        assert result is True
        mock_trade_confirmation_manager.record_trade_outcome.assert_called_once_with('CANCELLED', None)
        enhanced_slack._send_ephemeral_reply.assert_called_once_with(
            'C1234567890', 'U1234567890', '❌ Trade recorded (CANCELLED)'
        )
    
    def test_handle_non_confirmation_message(self, enhanced_slack, mock_trade_confirmation_manager):
        """Test handling of non-confirmation message."""
        # Setup
        enhanced_slack.set_trade_confirmation_manager(mock_trade_confirmation_manager)
        event = {
            'text': 'hello world',
            'channel': 'C1234567890',
            'user': 'U1234567890'
        }
        
        # Execute
        result = enhanced_slack.handle_confirmation_message(event)
        
        # Assert
        assert result is False
        mock_trade_confirmation_manager.record_trade_outcome.assert_not_called()
    
    def test_handle_message_without_trade_manager(self, enhanced_slack):
        """Test handling message when no trade confirmation manager is set."""
        # Setup - no trade confirmation manager set
        event = {
            'text': 'submitted',
            'channel': 'C1234567890',
            'user': 'U1234567890'
        }
        
        # Execute
        result = enhanced_slack.handle_confirmation_message(event)
        
        # Assert
        assert result is False
    
    def test_handle_malformed_event(self, enhanced_slack, mock_trade_confirmation_manager):
        """Test handling of malformed event data."""
        # Setup
        enhanced_slack.set_trade_confirmation_manager(mock_trade_confirmation_manager)
        event = {
            'text': '',  # Empty text
            'channel': 'C1234567890'
            # Missing user field
        }
        
        # Execute
        result = enhanced_slack.handle_confirmation_message(event)
        
        # Assert
        assert result is False
        mock_trade_confirmation_manager.record_trade_outcome.assert_not_called()
    
    def test_case_insensitive_matching(self, enhanced_slack, mock_trade_confirmation_manager):
        """Test that message matching is case-insensitive."""
        # Setup
        enhanced_slack.set_trade_confirmation_manager(mock_trade_confirmation_manager)
        event = {
            'text': 'SUBMITTED',  # Uppercase
            'channel': 'C1234567890',
            'user': 'U1234567890'
        }
        
        # Mock the ephemeral reply method
        enhanced_slack._send_ephemeral_reply = Mock()
        
        # Execute
        result = enhanced_slack.handle_confirmation_message(event)
        
        # Assert
        assert result is True
        mock_trade_confirmation_manager.record_trade_outcome.assert_called_once_with('SUBMITTED', None)
    
    def test_filled_price_parsing_edge_cases(self, enhanced_slack, mock_trade_confirmation_manager):
        """Test edge cases in filled price parsing."""
        # Setup
        enhanced_slack.set_trade_confirmation_manager(mock_trade_confirmation_manager)
        enhanced_slack._send_ephemeral_reply = Mock()
        
        test_cases = [
            ('filled $12.34', 12.34),
            ('filled 0.01', 0.01),
            ('filled $999.99', 999.99),
            ('filled 5', 5.0),
        ]
        
        for text, expected_price in test_cases:
            event = {
                'text': text,
                'channel': 'C1234567890',
                'user': 'U1234567890'
            }
            
            # Execute
            result = enhanced_slack.handle_confirmation_message(event)
            
            # Assert
            assert result is True
            mock_trade_confirmation_manager.record_trade_outcome.assert_called_with('SUBMITTED', expected_price)
            
            # Reset mock for next iteration
            mock_trade_confirmation_manager.reset_mock()
    
    def test_invalid_filled_price_format(self, enhanced_slack, mock_trade_confirmation_manager):
        """Test handling of invalid filled price formats."""
        # Setup
        enhanced_slack.set_trade_confirmation_manager(mock_trade_confirmation_manager)
        event = {
            'text': 'filled abc',  # Invalid price format
            'channel': 'C1234567890',
            'user': 'U1234567890'
        }
        
        # Execute
        result = enhanced_slack.handle_confirmation_message(event)
        
        # Assert
        assert result is False
        mock_trade_confirmation_manager.record_trade_outcome.assert_not_called()


if __name__ == '__main__':
    pytest.main([__file__])
