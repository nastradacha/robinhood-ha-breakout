#!/usr/bin/env python3
"""
Enhanced Slack Chart Integration - High-Quality Chart Images for Mobile Trading

Generates professional, high-clarity trading charts optimized for Slack delivery
and mobile viewing. Focuses on visual clarity, professional presentation, and
reliable image upload to Slack channels.

Key Improvements:
- Higher DPI (200) for crystal-clear mobile viewing
- Enhanced color schemes with better contrast
- Larger fonts and thicker lines for readability
- Professional styling with clear labels and legends
- Reliable Slack image upload with fallback options
- Optimized file sizes for fast mobile loading

Usage:
    from utils.enhanced_slack_charts import EnhancedSlackChartSender
    
    chart_sender = EnhancedSlackChartSender()
    chart_sender.send_breakout_chart_to_slack(market_data, analysis, "SPY")
"""

import os
import logging
import tempfile
from datetime import datetime
from typing import Dict, Optional, List
import pandas as pd
import numpy as np

# Chart generation with enhanced quality
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import seaborn as sns

# Slack integration
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class EnhancedSlackChartSender:
    """
    High-quality chart generation and Slack delivery system.
    
    Creates professional trading charts with enhanced visual clarity
    and sends them directly to Slack channels as image attachments.
    """
    
    def __init__(self):
        """Initialize enhanced chart sender with high-quality settings."""
        # Slack configuration
        self.webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        self.bot_token = os.getenv("SLACK_BOT_TOKEN")
        self.channel_id = os.getenv("SLACK_CHANNEL_ID")
        
        self.enabled = bool(self.webhook_url or self.bot_token)
        
        # Create temporary directory for charts
        self.chart_dir = tempfile.mkdtemp(prefix="trading_charts_")
        
        # Enhanced chart configuration for maximum clarity
        self.setup_chart_styling()
        
        logger.info(f"[ENHANCED-CHARTS] Initialized (enabled: {self.enabled})")
    
    def setup_chart_styling(self):
        """Setup professional chart styling for maximum clarity."""
        # Use professional dark theme
        plt.style.use("dark_background")
        
        # Enhanced configuration for mobile clarity
        self.chart_config = {
            "figsize": (16, 12),  # Large size for detail
            "dpi": 200,  # High DPI for crisp images
            "facecolor": "#0d1117",  # GitHub dark background
            "edgecolor": "#f0f6fc",  # Light text
            "title_size": 20,  # Large, readable titles
            "label_size": 16,  # Large axis labels
            "tick_size": 14,  # Large tick labels
            "legend_size": 14,  # Large legend
            "line_width": 3.0,  # Thick lines for visibility
            "marker_size": 10,  # Large markers
            "grid_alpha": 0.3,  # Subtle grid
            "text_color": "#f0f6fc",  # Light text color
        }
        
        # Professional color palette
        self.colors = {
            "bullish": "#00d4aa",  # Bright green
            "bearish": "#f85149",  # Bright red
            "neutral": "#7c3aed",  # Purple
            "volume": "#6e7681",  # Gray
            "sma": "#ffa657",  # Orange
            "support": "#1f6feb",  # Blue
            "resistance": "#da3633",  # Red
            "current": "#f0f6fc",  # White
        }
    
    def send_breakout_chart_to_slack(
        self, 
        market_data: pd.DataFrame, 
        analysis: Dict, 
        symbol: str = "SPY",
        message_text: str = None
    ) -> bool:
        """
        Generate and send high-quality breakout chart to Slack.
        
        Args:
            market_data: Historical OHLCV data
            analysis: Breakout analysis results
            symbol: Stock symbol
            message_text: Optional message to accompany chart
            
        Returns:
            True if chart was sent successfully, False otherwise
        """
        if not self.enabled:
            logger.warning("[ENHANCED-CHARTS] Slack not configured - chart not sent")
            return False
            
        try:
            # Generate high-quality chart
            chart_path = self.create_professional_breakout_chart(
                market_data, analysis, symbol
            )
            
            # Create professional message
            if not message_text:
                message_text = self._create_breakout_message(symbol, analysis)
            
            # Send to Slack with image
            success = self._send_chart_to_slack(chart_path, message_text, symbol)
            
            # Cleanup
            if os.path.exists(chart_path):
                os.remove(chart_path)
                
            return success
            
        except Exception as e:
            logger.error(f"[ENHANCED-CHARTS] Failed to send breakout chart: {e}")
            return False
    
    def create_professional_breakout_chart(
        self, 
        market_data: pd.DataFrame, 
        analysis: Dict, 
        symbol: str
    ) -> str:
        """
        Create professional-quality breakout chart with enhanced clarity.
        
        Args:
            market_data: Historical OHLCV data
            analysis: Breakout analysis results
            symbol: Stock symbol
            
        Returns:
            Path to generated chart file
        """
        # Prepare data (last 50 bars for mobile viewing)
        data = market_data.tail(50).copy()
        
        # Create figure with enhanced settings
        fig, (ax1, ax2) = plt.subplots(
            2, 1, 
            figsize=self.chart_config["figsize"],
            facecolor=self.chart_config["facecolor"],
            gridspec_kw={'height_ratios': [3, 1], 'hspace': 0.3}
        )
        
        # Main price chart
        self._plot_enhanced_price_action(ax1, data, analysis, symbol)
        
        # Volume chart
        self._plot_enhanced_volume(ax2, data)
        
        # Professional formatting
        self._format_chart_professionally(fig, ax1, ax2, symbol, analysis)
        
        # Save with high quality
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        chart_path = os.path.join(
            self.chart_dir, 
            f"{symbol}_enhanced_breakout_{timestamp}.png"
        )
        
        plt.savefig(
            chart_path,
            dpi=self.chart_config["dpi"],
            facecolor=self.chart_config["facecolor"],
            bbox_inches="tight",
            pad_inches=0.4,
            format='png',
        )
        plt.close()
        
        logger.info(f"[ENHANCED-CHARTS] Created chart: {chart_path}")
        return chart_path
    
    def _plot_enhanced_price_action(
        self, 
        ax, 
        data: pd.DataFrame, 
        analysis: Dict, 
        symbol: str
    ):
        """Plot enhanced price action with clear visual elements."""
        # Calculate Heikin-Ashi for smoother visualization
        ha_data = self._calculate_heikin_ashi(data)
        
        # Plot Heikin-Ashi candles with enhanced visibility
        for i, (idx, row) in enumerate(ha_data.iterrows()):
            color = self.colors["bullish"] if row["HA_Close"] >= row["HA_Open"] else self.colors["bearish"]
            
            # Thick candle bodies for mobile visibility
            body_height = abs(row["HA_Close"] - row["HA_Open"])
            body_bottom = min(row["HA_Open"], row["HA_Close"])
            
            # Candle body
            ax.add_patch(Rectangle(
                (i - 0.4, body_bottom), 0.8, body_height,
                facecolor=color, alpha=0.8, linewidth=1
            ))
            
            # Wicks
            ax.plot([i, i], [row["HA_Low"], row["HA_High"]], 
                   color=color, linewidth=2, alpha=0.7)
        
        # Add moving averages with enhanced visibility
        if len(data) >= 20:
            sma_20 = data["Close"].rolling(20).mean()
            ax.plot(range(len(sma_20)), sma_20, 
                   color=self.colors["sma"], 
                   linewidth=self.chart_config["line_width"],
                   alpha=0.9, label="SMA(20)")
        
        # Highlight current price and trend
        current_price = analysis.get("current_price", data["Close"].iloc[-1])
        trend = analysis.get("trend_direction", "NEUTRAL")
        
        # Current price line
        ax.axhline(y=current_price, color=self.colors["current"], 
                  linewidth=2, linestyle="--", alpha=0.8)
        
        # Trend annotation with enhanced visibility
        if trend == "BULLISH":
            ax.annotate(
                f"BULLISH BREAKOUT\n${current_price:.2f}",
                xy=(len(data) * 0.7, current_price),
                xytext=(10, 30),
                textcoords="offset points",
                fontsize=self.chart_config["label_size"],
                color=self.colors["bullish"],
                weight="bold",
                bbox=dict(boxstyle="round,pad=0.3", facecolor=self.colors["bullish"], alpha=0.2),
                arrowprops=dict(arrowstyle="->", color=self.colors["bullish"], lw=2)
            )
        elif trend == "BEARISH":
            ax.annotate(
                f"BEARISH SIGNAL\n${current_price:.2f}",
                xy=(len(data) * 0.7, current_price),
                xytext=(10, -40),
                textcoords="offset points",
                fontsize=self.chart_config["label_size"],
                color=self.colors["bearish"],
                weight="bold",
                bbox=dict(boxstyle="round,pad=0.3", facecolor=self.colors["bearish"], alpha=0.2),
                arrowprops=dict(arrowstyle="->", color=self.colors["bearish"], lw=2)
            )
        
        # Add support/resistance levels if available
        if "support_level" in analysis:
            ax.axhline(y=analysis["support_level"], 
                      color=self.colors["support"], 
                      linewidth=2, linestyle=":", alpha=0.7,
                      label=f"Support ${analysis['support_level']:.2f}")
        
        if "resistance_level" in analysis:
            ax.axhline(y=analysis["resistance_level"], 
                      color=self.colors["resistance"], 
                      linewidth=2, linestyle=":", alpha=0.7,
                      label=f"Resistance ${analysis['resistance_level']:.2f}")
    
    def _plot_enhanced_volume(self, ax, data: pd.DataFrame):
        """Plot enhanced volume chart with clear visualization."""
        volume = data["Volume"].values
        colors = [
            self.colors["bullish"] if data.iloc[i]["Close"] >= data.iloc[i]["Open"] 
            else self.colors["bearish"] for i in range(len(data))
        ]
        
        # Volume bars with enhanced visibility
        bars = ax.bar(range(len(volume)), volume, color=colors, alpha=0.7, width=0.8)
        
        # Volume moving average
        if len(volume) >= 10:
            vol_ma = pd.Series(volume).rolling(10).mean()
            ax.plot(range(len(vol_ma)), vol_ma, 
                   color=self.colors["neutral"], 
                   linewidth=2, alpha=0.8, label="Vol MA(10)")
    
    def _calculate_heikin_ashi(self, data: pd.DataFrame) -> pd.DataFrame:
        """Calculate Heikin-Ashi values for smoother visualization."""
        ha_data = data.copy()
        
        # Initialize first values
        ha_data.loc[ha_data.index[0], "HA_Close"] = (
            data["Open"].iloc[0] + data["High"].iloc[0] + 
            data["Low"].iloc[0] + data["Close"].iloc[0]
        ) / 4
        ha_data.loc[ha_data.index[0], "HA_Open"] = (
            data["Open"].iloc[0] + data["Close"].iloc[0]
        ) / 2
        
        # Calculate remaining values
        for i in range(1, len(data)):
            ha_data.loc[ha_data.index[i], "HA_Close"] = (
                data["Open"].iloc[i] + data["High"].iloc[i] + 
                data["Low"].iloc[i] + data["Close"].iloc[i]
            ) / 4
            
            ha_data.loc[ha_data.index[i], "HA_Open"] = (
                ha_data["HA_Open"].iloc[i-1] + ha_data["HA_Close"].iloc[i-1]
            ) / 2
            
            ha_data.loc[ha_data.index[i], "HA_High"] = max(
                data["High"].iloc[i], 
                ha_data["HA_Open"].iloc[i], 
                ha_data["HA_Close"].iloc[i]
            )
            
            ha_data.loc[ha_data.index[i], "HA_Low"] = min(
                data["Low"].iloc[i], 
                ha_data["HA_Open"].iloc[i], 
                ha_data["HA_Close"].iloc[i]
            )
        
        return ha_data
    
    def _format_chart_professionally(
        self, 
        fig, 
        ax1, 
        ax2, 
        symbol: str, 
        analysis: Dict
    ):
        """Apply professional formatting to the chart."""
        # Main chart formatting
        ax1.set_title(
            f"{symbol} - Breakout Analysis ({datetime.now().strftime('%Y-%m-%d %H:%M')})",
            fontsize=self.chart_config["title_size"],
            color=self.chart_config["text_color"],
            weight="bold",
            pad=20
        )
        
        ax1.set_ylabel("Price ($)", 
                      fontsize=self.chart_config["label_size"],
                      color=self.chart_config["text_color"])
        
        ax1.grid(True, alpha=self.chart_config["grid_alpha"])
        ax1.legend(loc="upper left", fontsize=self.chart_config["legend_size"])
        
        # Volume chart formatting
        ax2.set_ylabel("Volume", 
                      fontsize=self.chart_config["label_size"],
                      color=self.chart_config["text_color"])
        ax2.set_xlabel("Time", 
                      fontsize=self.chart_config["label_size"],
                      color=self.chart_config["text_color"])
        
        ax2.grid(True, alpha=self.chart_config["grid_alpha"])
        
        # Enhanced tick formatting
        for ax in [ax1, ax2]:
            ax.tick_params(
                labelsize=self.chart_config["tick_size"],
                colors=self.chart_config["text_color"]
            )
        
        # Add analysis summary box
        analysis_text = self._create_analysis_summary(analysis)
        ax1.text(
            0.02, 0.98, analysis_text,
            transform=ax1.transAxes,
            fontsize=12,
            verticalalignment='top',
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#1c2128", alpha=0.8),
            color=self.chart_config["text_color"]
        )
    
    def _create_analysis_summary(self, analysis: Dict) -> str:
        """Create analysis summary text for chart."""
        confidence = analysis.get("confidence", 0)
        trend = analysis.get("trend_direction", "NEUTRAL")
        
        summary = f"Confidence: {confidence:.1f}%\n"
        summary += f"Trend: {trend}\n"
        
        if "breakout_strength" in analysis:
            summary += f"Strength: {analysis['breakout_strength']:.2f}\n"
        
        return summary
    
    def _create_breakout_message(self, symbol: str, analysis: Dict) -> str:
        """Create professional breakout message for Slack."""
        trend = analysis.get("trend_direction", "NEUTRAL")
        confidence = analysis.get("confidence", 0)
        current_price = analysis.get("current_price", 0)
        
        emoji = "📈" if trend == "BULLISH" else "📉" if trend == "BEARISH" else "📊"
        
        message = f"{emoji} **{symbol} BREAKOUT ANALYSIS**\n\n"
        message += f"**Current Price:** ${current_price:.2f}\n"
        message += f"**Trend:** {trend}\n"
        message += f"**Confidence:** {confidence:.1f}%\n"
        message += f"**Time:** {datetime.now().strftime('%H:%M:%S EST')}\n\n"
        message += "📊 **Professional chart analysis attached above**"
        
        return message
    
    def _send_chart_to_slack(
        self, 
        chart_path: str, 
        message_text: str, 
        symbol: str
    ) -> bool:
        """Send chart image to Slack with message."""
        try:
            # Try bot token upload first (best quality)
            if self.bot_token and self.channel_id:
                return self._upload_with_bot_token(chart_path, message_text, symbol)
            
            # Fallback to webhook (text only)
            elif self.webhook_url:
                return self._send_webhook_message(message_text)
            
            else:
                logger.warning("[ENHANCED-CHARTS] No Slack configuration available")
                return False
                
        except Exception as e:
            logger.error(f"[ENHANCED-CHARTS] Failed to send to Slack: {e}")
            return False
    
    def _upload_with_bot_token(
        self, 
        chart_path: str, 
        message_text: str, 
        symbol: str
    ) -> bool:
        """Upload chart using new Slack file upload API."""
        try:
            # Step 1: Get upload URL
            upload_response = requests.post(
                "https://slack.com/api/files.getUploadURLExternal",
                headers={"Authorization": f"Bearer {self.bot_token}"},
                data={
                    "filename": f"{symbol}_chart_{datetime.now().strftime('%H%M%S')}.png",
                    "length": os.path.getsize(chart_path)
                },
                timeout=10
            )
            
            if upload_response.status_code != 200:
                logger.warning(f"[ENHANCED-CHARTS] Failed to get upload URL: {upload_response.status_code}")
                return False
                
            upload_data = upload_response.json()
            if not upload_data.get("ok"):
                logger.warning(f"[ENHANCED-CHARTS] Upload URL error: {upload_data.get('error')}")
                return False
            
            upload_url = upload_data["upload_url"]
            file_id = upload_data["file_id"]
            
            # Step 2: Upload file to the URL
            with open(chart_path, "rb") as file:
                upload_file_response = requests.post(
                    upload_url,
                    files={"file": file},
                    timeout=30
                )
            
            if upload_file_response.status_code != 200:
                logger.warning(f"[ENHANCED-CHARTS] File upload failed: {upload_file_response.status_code}")
                return False
            
            # Step 3: Complete the upload and share to channel
            complete_response = requests.post(
                "https://slack.com/api/files.completeUploadExternal",
                headers={"Authorization": f"Bearer {self.bot_token}"},
                json={
                    "files": [{
                        "id": file_id,
                        "title": f"{symbol} Breakout Analysis Chart"
                    }],
                    "channel_id": self.channel_id,
                    "initial_comment": message_text
                },
                timeout=10
            )
            
            if complete_response.status_code == 200:
                result = complete_response.json()
                if result.get("ok"):
                    logger.info("[ENHANCED-CHARTS] Chart uploaded successfully to Slack")
                    return True
                else:
                    logger.warning(f"[ENHANCED-CHARTS] Complete upload failed: {result.get('error')}")
                    return False
            else:
                logger.warning(f"[ENHANCED-CHARTS] Complete upload failed: {complete_response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"[ENHANCED-CHARTS] New API upload error: {e}")
            return False
    
    def _send_webhook_message(self, message_text: str) -> bool:
        """Send message via webhook (fallback, text only)."""
        try:
            response = requests.post(
                self.webhook_url,
                json={"text": message_text},
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info("[ENHANCED-CHARTS] Webhook message sent (no chart)")
                return True
            else:
                logger.warning(f"[ENHANCED-CHARTS] Webhook failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"[ENHANCED-CHARTS] Webhook error: {e}")
            return False


# Example usage and testing
if __name__ == "__main__":
    # Test enhanced chart generation
    print("Testing Enhanced Slack Chart System...")
    
    chart_sender = EnhancedSlackChartSender()
    
    if chart_sender.enabled:
        print("✅ Slack configuration detected")
        print("📊 Enhanced chart system ready for high-quality image delivery")
    else:
        print("❌ Slack not configured - set SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN")
