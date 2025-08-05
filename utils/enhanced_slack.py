#!/usr/bin/env python3
"""
Enhanced Slack Integration for Professional Trading Alerts

Combines the existing SlackNotifier with rich chart generation for
mobile-optimized trading decision support. Provides institutional-grade
market analysis directly to your phone.

Key Features:
- Professional trading charts with technical analysis
- Rich message formatting with market context
- Mobile-optimized visualizations
- Automatic chart upload and sharing
- Comprehensive position monitoring alerts
- Breakout signal notifications with visual confirmation

Usage:
    from utils.enhanced_slack import EnhancedSlackIntegration
    
    slack = EnhancedSlackIntegration()
    slack.send_breakout_alert_with_chart(symbol, decision, analysis, market_data, confidence)
"""

import os
import logging
from typing import Dict, Optional
import pandas as pd
from datetime import datetime

try:
    from .slack import SlackNotifier
    from .slack_charts import SlackChartGenerator, EnhancedSlackNotifier
except ImportError:
    # Handle standalone execution
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from utils.slack import SlackNotifier
    from utils.slack_charts import SlackChartGenerator, EnhancedSlackNotifier

logger = logging.getLogger(__name__)

class EnhancedSlackIntegration:
    """
    Unified enhanced Slack integration combining charts and notifications.
    
    Provides a single interface for all Slack communications with rich
    chart integration and professional mobile-friendly formatting.
    """
    
    def __init__(self):
        """Initialize enhanced Slack integration."""
        # Initialize components
        self.basic_notifier = SlackNotifier()
        self.chart_generator = SlackChartGenerator()
        self.enhanced_notifier = EnhancedSlackNotifier()
        
        # Configuration
        self.enabled = self.basic_notifier.enabled
        self.charts_enabled = self.enabled and os.getenv('SLACK_BOT_TOKEN')
        
        logger.info(f"[ENHANCED-SLACK] Initialized (enabled: {self.enabled}, charts: {self.charts_enabled})")
    
    def send_breakout_alert_with_chart(self, symbol: str, decision: str, analysis: Dict, 
                                     market_data: pd.DataFrame, confidence: float):
        """
        Send comprehensive breakout alert with professional chart.
        
        Args:
            symbol: Stock symbol (e.g., 'SPY')
            decision: Trading decision ('CALL', 'PUT', 'NO_TRADE')
            analysis: Market analysis results
            market_data: Historical market data
            confidence: LLM confidence score
        """
        if not self.enabled:
            logger.debug("[ENHANCED-SLACK] Slack not enabled, skipping alert")
            return
        
        try:
            if self.charts_enabled and decision in ['CALL', 'PUT']:
                # Send rich alert with chart
                self.enhanced_notifier.send_breakout_alert_with_chart(
                    symbol, decision, analysis, market_data, confidence
                )
                logger.info(f"[ENHANCED-SLACK] Sent breakout alert with chart for {symbol} {decision}")
            else:
                # Fallback to enhanced text alert
                self._send_enhanced_text_alert(symbol, decision, analysis, confidence)
                logger.info(f"[ENHANCED-SLACK] Sent enhanced text alert for {symbol} {decision}")
                
        except Exception as e:
            logger.error(f"[ENHANCED-SLACK] Failed to send breakout alert: {e}")
            # Fallback to basic notification
            self._send_basic_fallback_alert(symbol, decision, analysis, confidence)
    
    def send_position_alert_with_chart(self, position: Dict, current_price: float, 
                                     pnl_pct: float, alert_type: str, exit_decision: Dict = None):
        """
        Send position monitoring alert with P&L visualization.
        
        Args:
            position: Position details
            current_price: Current stock price
            pnl_pct: Current P&L percentage
            alert_type: Type of alert (profit_target, stop_loss, trailing_stop, etc.)
            exit_decision: Exit strategy decision data
        """
        if not self.enabled:
            return
        
        try:
            if self.charts_enabled:
                # Send rich alert with P&L chart
                self.enhanced_notifier.send_position_alert_with_chart(
                    position, current_price, pnl_pct, alert_type, exit_decision
                )
                logger.info(f"[ENHANCED-SLACK] Sent position alert with chart for {position['symbol']}")
            else:
                # Fallback to enhanced text alert
                self._send_enhanced_position_text(position, current_price, pnl_pct, alert_type)
                logger.info(f"[ENHANCED-SLACK] Sent enhanced position text for {position['symbol']}")
                
        except Exception as e:
            logger.error(f"[ENHANCED-SLACK] Failed to send position alert: {e}")
            # Fallback to basic notification
            self._send_basic_position_fallback(position, current_price, pnl_pct, alert_type)
    
    def send_market_summary_with_chart(self, symbol: str, analysis: Dict, market_data: pd.DataFrame):
        """
        Send daily market summary with comprehensive analysis chart.
        
        Args:
            symbol: Stock symbol
            analysis: Market analysis results
            market_data: Historical market data
        """
        if not self.enabled:
            return
        
        try:
            if self.charts_enabled:
                # Generate comprehensive market summary chart
                chart_path = self.chart_generator.create_breakout_chart(market_data, analysis, symbol)
                
                # Create market summary message
                message = self._create_market_summary_message(symbol, analysis)
                
                # Send with chart
                self.enhanced_notifier._send_message_with_image(message, chart_path)
                logger.info(f"[ENHANCED-SLACK] Sent market summary with chart for {symbol}")
            else:
                # Text-only market summary
                self._send_text_market_summary(symbol, analysis)
                
        except Exception as e:
            logger.error(f"[ENHANCED-SLACK] Failed to send market summary: {e}")
    
    def send_heartbeat_with_context(self, message: str, analysis: Dict = None):
        """
        Send enhanced heartbeat with market context.
        
        Args:
            message: Heartbeat message
            analysis: Optional market analysis for context
        """
        if not self.enabled:
            return
        
        try:
            if analysis:
                # Enhanced heartbeat with market context
                enhanced_message = f"{message}\n" \
                                 f"📊 Market: {analysis.get('trend_direction', 'N/A')} trend\n" \
                                 f"💰 Price: ${analysis.get('current_price', 0):.2f}\n" \
                                 f"📈 Strength: {analysis.get('breakout_strength', 0):.1f}"
            else:
                enhanced_message = message
            
            self.basic_notifier.send_heartbeat(enhanced_message)
            logger.debug(f"[ENHANCED-SLACK] Sent enhanced heartbeat")
            
        except Exception as e:
            logger.error(f"[ENHANCED-SLACK] Failed to send heartbeat: {e}")
    
    def _send_enhanced_text_alert(self, symbol: str, decision: str, analysis: Dict, confidence: float):
        """Send enhanced text-only breakout alert."""
        trend_emoji = "📈" if analysis.get('trend_direction') == 'BULLISH' else "📉" if analysis.get('trend_direction') == 'BEARISH' else "➡️"
        decision_emoji = "🚀" if decision == 'CALL' else "🔻" if decision == 'PUT' else "⏸️"
        
        message = f"""{decision_emoji} **{symbol} {decision} SIGNAL** {trend_emoji}
        
**Market Analysis:**
• Price: ${analysis.get('current_price', 0):.2f}
• Confidence: {confidence:.1%}
• Trend: {analysis.get('trend_direction', 'N/A')}
• Strength: {analysis.get('breakout_strength', 0):.1f}
• Body: {analysis.get('candle_body_pct', 0):.2f}%
• Volume: {analysis.get('volume_ratio', 0):.1f}x

**Key Levels:**
• Resistance: ${analysis.get('nearest_resistance', 0):.2f}
• Support: ${analysis.get('nearest_support', 0):.2f}

*Professional analysis powered by real-time data*"""
        
        self.basic_notifier.send_trade_decision(symbol, decision, confidence, message)
    
    def _send_enhanced_position_text(self, position: Dict, current_price: float, 
                                   pnl_pct: float, alert_type: str):
        """Send enhanced text-only position alert."""
        pnl_emoji = "💰" if pnl_pct > 0 else "🛑" if pnl_pct < -10 else "📊"
        
        message = f"""{pnl_emoji} **{position['symbol']} POSITION ALERT**

**Position Details:**
• Contract: ${position['strike']} {position['option_type']}
• Entry: ${position['entry_price']:.2f}
• Current: ${current_price:.2f}
• P&L: {pnl_pct:+.1f}%

**Alert Type:** {alert_type.replace('_', ' ').title()}

*Real-time monitoring with advanced exit strategies*"""
        
        self.basic_notifier.send_heartbeat(message)
    
    def _create_market_summary_message(self, symbol: str, analysis: Dict) -> Dict:
        """Create rich market summary message."""
        trend_emoji = "📈" if analysis.get('trend_direction') == 'BULLISH' else "📉" if analysis.get('trend_direction') == 'BEARISH' else "➡️"
        
        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"📊 {symbol} Daily Market Summary"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Current Price:* ${analysis.get('current_price', 0):.2f}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Trend:* {trend_emoji} {analysis.get('trend_direction', 'N/A')}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Breakout Strength:* {analysis.get('breakout_strength', 0):.1f}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Volume Activity:* {analysis.get('volume_ratio', 0):.1f}x average"
                        }
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Key Technical Levels:*\n" \
                               f"• Resistance: ${analysis.get('nearest_resistance', 0):.2f}\n" \
                               f"• Support: ${analysis.get('nearest_support', 0):.2f}\n" \
                               f"• True Range: {analysis.get('true_range_pct', 0):.2f}%"
                    }
                }
            ]
        }
    
    def _send_text_market_summary(self, symbol: str, analysis: Dict):
        """Send text-only market summary."""
        trend_emoji = "📈" if analysis.get('trend_direction') == 'BULLISH' else "📉" if analysis.get('trend_direction') == 'BEARISH' else "➡️"
        
        message = f"""📊 **{symbol} MARKET SUMMARY** {trend_emoji}

**Current Status:**
• Price: ${analysis.get('current_price', 0):.2f}
• Trend: {analysis.get('trend_direction', 'N/A')}
• Strength: {analysis.get('breakout_strength', 0):.1f}
• Volume: {analysis.get('volume_ratio', 0):.1f}x

**Key Levels:**
• Resistance: ${analysis.get('nearest_resistance', 0):.2f}
• Support: ${analysis.get('nearest_support', 0):.2f}

*Professional market analysis*"""
        
        self.basic_notifier.send_heartbeat(message)
    
    def _send_basic_fallback_alert(self, symbol: str, decision: str, analysis: Dict, confidence: float):
        """Fallback to basic Slack notification."""
        try:
            self.basic_notifier.send_trade_decision(symbol, decision, confidence, 
                                                  f"Market analysis: {analysis.get('trend_direction', 'N/A')} trend")
        except Exception as e:
            logger.error(f"[ENHANCED-SLACK] Even basic fallback failed: {e}")
    
    def _send_basic_position_fallback(self, position: Dict, current_price: float, 
                                    pnl_pct: float, alert_type: str):
        """Fallback to basic position notification."""
        try:
            message = f"{position['symbol']} {alert_type}: P&L {pnl_pct:+.1f}%"
            self.basic_notifier.send_heartbeat(message)
        except Exception as e:
            logger.error(f"[ENHANCED-SLACK] Even basic position fallback failed: {e}")
    
    # Delegate other methods to basic notifier for compatibility
    def send_browser_status(self, status: str, message: str):
        """Delegate browser status to basic notifier."""
        return self.basic_notifier.send_browser_status(status, message)
    
    def send_trade_decision(self, symbol: str = None, decision: str = None, confidence: float = None, 
                           reason: str = "", bankroll: float = None, position_size: float = None, **kwargs):
        """Enhanced trade decision notification with additional context."""
        # Handle both old and new calling patterns
        if symbol is None and 'decision' in kwargs:
            decision = kwargs.get('decision')
            confidence = kwargs.get('confidence', 0.0)
            reason = kwargs.get('reason', '')
            bankroll = kwargs.get('bankroll')
            position_size = kwargs.get('position_size')
            symbol = 'SPY'  # Default symbol
        
        # Ensure confidence is a float (convert from string if needed)
        if isinstance(confidence, str):
            try:
                confidence = float(confidence)
            except (ValueError, TypeError):
                confidence = 0.0
        elif confidence is None:
            confidence = 0.0
        
        # Create enhanced message with additional context
        if bankroll is not None and position_size is not None:
            enhanced_reason = f"{reason}\n\nBankroll: ${bankroll:.2f}\nPosition Size: ${position_size:.2f}"
        else:
            enhanced_reason = reason
        
        return self.basic_notifier.send_trade_decision(symbol, decision, confidence, enhanced_reason)
    
    def send_heartbeat(self, message: str):
        """Delegate basic heartbeat to basic notifier."""
        self.basic_notifier.send_heartbeat(message)
    
    def send_startup_notification(self, dry_run: bool = False):
        """Send system startup notification."""
        mode = "DRY RUN" if dry_run else "LIVE TRADING"
        emoji = "🧪" if dry_run else "🚀"
        
        message = f"{emoji} **ROBINHOOD HA BREAKOUT STARTED**\n\n" \
                 f"**Mode:** {mode}\n" \
                 f"**Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n" \
                 f"**Status:** System initialized and ready\n\n" \
                 f"*Conservative ATM options trading system active*"
        
        self.send_heartbeat(message)
    
    def send_error_alert(self, title: str, error_message: str):
        """Send error alert notification."""
        message = f"❌ **{title.upper()}**\n\n" \
                 f"**Error:** {error_message}\n" \
                 f"**Time:** {datetime.now().strftime('%H:%M:%S')}\n\n" \
                 f"*System may require attention*"
        
        self.send_heartbeat(message)
    
    def send_completion_summary(self, summary: dict):
        """Send session completion summary."""
        message = f"✅ **SESSION COMPLETE**\n\n" \
                 f"**Duration:** {summary.get('duration', 'N/A')}\n" \
                 f"**Scans:** {summary.get('scans', 0)}\n" \
                 f"**Trades:** {summary.get('trades', 0)}\n" \
                 f"**Status:** {summary.get('status', 'Completed')}\n\n" \
                 f"*Trading session ended*"
        
        self.send_heartbeat(message)
    
    def send_message(self, message: str):
        """Send generic message via Slack."""
        self.send_heartbeat(message)
    
    def send_market_analysis(self, analysis: dict):
        """Send market analysis summary."""
        symbol = analysis.get('symbol', 'N/A')
        trend = analysis.get('trend_direction', 'N/A')
        price = analysis.get('current_price', 0)
        
        message = f"📊 **{symbol} MARKET ANALYSIS**\n\n" \
                 f"**Price:** ${price:.2f}\n" \
                 f"**Trend:** {trend}\n" \
                 f"**Analysis:** Market conditions evaluated\n\n" \
                 f"*Automated market analysis complete*"
        
        self.send_heartbeat(message)

# Example usage and testing
if __name__ == "__main__":
    # Test enhanced Slack integration
    enhanced_slack = EnhancedSlackIntegration()
    
    print("=== TESTING ENHANCED SLACK INTEGRATION ===")
    print(f"Basic notifications enabled: {enhanced_slack.enabled}")
    print(f"Chart integration enabled: {enhanced_slack.charts_enabled}")
    
    # Test sample data
    import pandas as pd
    import numpy as np
    
    dates = pd.date_range(start='2025-01-01', periods=50, freq='5min')
    sample_data = pd.DataFrame({
        'Open': np.random.randn(50).cumsum() + 630,
        'High': np.random.randn(50).cumsum() + 632,
        'Low': np.random.randn(50).cumsum() + 628,
        'Close': np.random.randn(50).cumsum() + 630,
        'Volume': np.random.randint(1000000, 5000000, 50)
    }, index=dates)
    
    sample_analysis = {
        'current_price': 630.50,
        'trend_direction': 'BULLISH',
        'breakout_strength': 7.2,
        'candle_body_pct': 0.15,
        'volume_ratio': 1.8,
        'resistance_levels': [632.0, 635.0, 638.0],
        'support_levels': [628.0, 625.0, 622.0],
        'nearest_resistance': 632.0,
        'nearest_support': 628.0
    }
    
    # Test enhanced heartbeat
    enhanced_slack.send_heartbeat_with_context("🔄 System active", sample_analysis)
    
    print("Enhanced Slack integration ready for professional trading alerts!")
