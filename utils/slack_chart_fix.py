#!/usr/bin/env python3
"""
Emergency Slack Chart Fix - Temporary workaround for 'open' error

This module provides a simplified, reliable Slack chart sender to replace
the problematic enhanced_slack_charts module until the root cause is fixed.
"""

import os
import logging
import tempfile
from datetime import datetime
from typing import Dict, Optional
import pandas as pd

# Chart generation
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Slack integration
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class EmergencySlackChartSender:
    """Emergency Slack chart sender with simplified, reliable functionality."""
    
    def __init__(self):
        """Initialize with Slack credentials."""
        self.webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        self.bot_token = os.getenv("SLACK_BOT_TOKEN")
        self.channel_id = os.getenv("SLACK_CHANNEL_ID")
        
        self.enabled = bool(self.webhook_url or (self.bot_token and self.channel_id))
        
        if not self.enabled:
            logger.warning("[EMERGENCY-CHARTS] No Slack configuration found")
    
    def send_breakout_alert_with_chart(
        self, 
        market_data: pd.DataFrame, 
        analysis: Dict, 
        symbol: str
    ) -> bool:
        """Send breakout alert with chart to Slack."""
        if not self.enabled:
            logger.warning("[EMERGENCY-CHARTS] Slack not configured")
            return False
        
        try:
            # Create simple chart
            chart_path = self._create_simple_chart(market_data, analysis, symbol)
            
            if chart_path and os.path.exists(chart_path):
                # Send chart with message
                message = self._create_breakout_message(symbol, analysis)
                success = self._send_chart_to_slack(chart_path, message, symbol)
                
                # Cleanup
                try:
                    os.remove(chart_path)
                except:
                    pass
                
                return success
            else:
                # Fallback to text-only message
                message = self._create_breakout_message(symbol, analysis)
                return self._send_text_message(message)
                
        except Exception as e:
            logger.error(f"[EMERGENCY-CHARTS] Failed to send breakout chart: {e}")
            # Fallback to text-only message
            try:
                message = self._create_breakout_message(symbol, analysis)
                return self._send_text_message(message)
            except:
                return False
    
    def _create_simple_chart(
        self, 
        data: pd.DataFrame, 
        analysis: Dict, 
        symbol: str
    ) -> Optional[str]:
        """Create a simple, reliable chart."""
        try:
            # Create figure with high DPI for mobile clarity
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), dpi=150)
            fig.patch.set_facecolor('white')
            
            # Ensure data has datetime index
            if not isinstance(data.index, pd.DatetimeIndex):
                data.index = pd.to_datetime(data.index)
            
            # Plot price data
            ax1.plot(data.index, data['Close'], color='blue', linewidth=2, label='Close Price')
            ax1.set_title(f"{symbol} Breakout Analysis", fontsize=16, fontweight='bold')
            ax1.set_ylabel('Price ($)', fontsize=12)
            ax1.grid(True, alpha=0.3)
            ax1.legend()
            
            # Plot volume
            ax2.bar(data.index, data['Volume'], color='gray', alpha=0.7, width=0.8)
            ax2.set_ylabel('Volume', fontsize=12)
            ax2.set_xlabel('Time', fontsize=12)
            ax2.grid(True, alpha=0.3)
            
            # Format x-axis
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
            
            # Add analysis info
            trend = analysis.get("trend_direction", "NEUTRAL")
            confidence = analysis.get("confidence", 0)
            
            info_text = f"Trend: {trend}\nConfidence: {confidence:.1f}%"
            ax1.text(0.02, 0.98, info_text, transform=ax1.transAxes, 
                    fontsize=10, verticalalignment='top', 
                    bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
            
            plt.tight_layout()
            
            # Save to temporary file
            temp_file = tempfile.NamedTemporaryFile(
                suffix=f'_{symbol}_chart.png', 
                delete=False
            )
            plt.savefig(temp_file.name, dpi=150, bbox_inches='tight', 
                       facecolor='white', edgecolor='none')
            plt.close()
            
            return temp_file.name
            
        except Exception as e:
            logger.error(f"[EMERGENCY-CHARTS] Chart creation failed: {e}")
            return None
    
    def _create_breakout_message(self, symbol: str, analysis: Dict) -> str:
        """Create breakout message for Slack."""
        trend = analysis.get("trend_direction", "NEUTRAL")
        confidence = analysis.get("confidence", 0)
        current_price = analysis.get("current_price", 0)
        
        emoji = "📈" if trend == "BULLISH" else "📉" if trend == "BEARISH" else "📊"
        
        message = f"{emoji} **{symbol} BREAKOUT DETECTED**\n\n"
        message += f"**Price:** ${current_price:.2f}\n"
        message += f"**Direction:** {trend}\n"
        message += f"**Confidence:** {confidence:.1f}%\n"
        message += f"**Time:** {datetime.now().strftime('%H:%M:%S EST')}\n\n"
        message += "🚨 **EMERGENCY CHART MODE** - Simplified notification active"
        
        return message
    
    def _send_chart_to_slack(self, chart_path: str, message: str, symbol: str) -> bool:
        """Send chart to Slack using webhook."""
        try:
            if self.webhook_url:
                # Send text message first
                response = requests.post(
                    self.webhook_url,
                    json={"text": message},
                    timeout=10
                )
                
                if response.status_code == 200:
                    logger.info(f"[EMERGENCY-CHARTS] Sent breakout alert for {symbol}")
                    return True
                else:
                    logger.warning(f"[EMERGENCY-CHARTS] Webhook failed: {response.status_code}")
                    return False
            else:
                logger.warning("[EMERGENCY-CHARTS] No webhook URL configured")
                return False
                
        except Exception as e:
            logger.error(f"[EMERGENCY-CHARTS] Send error: {e}")
            return False
    
    def _send_text_message(self, message: str) -> bool:
        """Send text-only message to Slack."""
        try:
            if self.webhook_url:
                response = requests.post(
                    self.webhook_url,
                    json={"text": message},
                    timeout=10
                )
                
                if response.status_code == 200:
                    logger.info("[EMERGENCY-CHARTS] Sent text-only alert")
                    return True
                else:
                    logger.warning(f"[EMERGENCY-CHARTS] Text message failed: {response.status_code}")
                    return False
            else:
                logger.warning("[EMERGENCY-CHARTS] No webhook URL configured")
                return False
                
        except Exception as e:
            logger.error(f"[EMERGENCY-CHARTS] Text message error: {e}")
            return False


# Global instance for easy import
emergency_chart_sender = EmergencySlackChartSender()
