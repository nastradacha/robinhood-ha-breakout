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
        """Setup professional chart styling for maximum clarity and mobile optimization."""
        # Use professional dark theme optimized for mobile
        plt.style.use("dark_background")
        
        # Ultra-high quality configuration for crystal-clear mobile viewing
        self.chart_config = {
            "figsize": (20, 14),  # Larger canvas for more detail
            "dpi": 300,  # Ultra-high DPI for razor-sharp images
            "facecolor": "#0d1117",  # GitHub dark background
            "edgecolor": "#f0f6fc",  # Light text
            "title_size": 24,  # Extra large, bold titles
            "subtitle_size": 18,  # Subtitle for additional context
            "label_size": 18,  # Large axis labels
            "tick_size": 16,  # Large tick labels
            "legend_size": 16,  # Large legend
            "annotation_size": 14,  # Clear annotations
            "line_width": 4.0,  # Extra thick lines for mobile visibility
            "marker_size": 12,  # Large markers
            "grid_alpha": 0.25,  # Subtle but visible grid
            "text_color": "#f0f6fc",  # High-contrast light text
            "spine_width": 2.0,  # Thicker chart borders
            "candle_width": 0.8,  # Wider candles for clarity
        }
        
        # Enhanced professional color palette with better contrast
        self.colors = {
            "bullish": "#00ff88",  # Brighter green for better visibility
            "bearish": "#ff4757",  # Brighter red for better visibility
            "neutral": "#a55eea",  # Enhanced purple
            "volume": "#8395a7",  # Improved gray contrast
            "sma": "#ffa502",  # Enhanced orange
            "ema": "#ff6b6b",  # EMA line color
            "support": "#3742fa",  # Brighter blue
            "resistance": "#ff3838",  # Brighter red
            "current": "#ffffff",  # Pure white for maximum contrast
            "breakout": "#ffd700",  # Gold for breakout highlights
            "background": "#0d1117",  # Consistent background
            "grid": "#30363d",  # Grid color
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
        Create ultra-high-quality breakout chart with enhanced clarity and mobile optimization.
        
        Args:
            market_data: Historical OHLCV data
            analysis: Breakout analysis results
            symbol: Stock symbol
            
        Returns:
            Path to generated chart file
        """
        # Prepare data (last 60 bars for better context)
        data = market_data.tail(60).copy()
        
        # Create figure with ultra-high quality settings
        fig, (ax1, ax2) = plt.subplots(
            2, 1, 
            figsize=self.chart_config["figsize"],
            facecolor=self.chart_config["facecolor"],
            gridspec_kw={'height_ratios': [4, 1], 'hspace': 0.35}
        )
        
        # Set consistent background
        ax1.set_facecolor(self.colors["background"])
        ax2.set_facecolor(self.colors["background"])
        
        # Main price chart with enhanced elements
        self._plot_enhanced_price_action(ax1, data, analysis, symbol)
        
        # Volume chart with improved styling
        self._plot_enhanced_volume(ax2, data)
        
        # Professional formatting with enhanced labels
        self._format_chart_professionally(fig, ax1, ax2, symbol, analysis)
        
        # Add comprehensive chart annotations
        self._add_chart_annotations(ax1, analysis, symbol)
        
        # Save with ultra-high quality settings
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        chart_path = os.path.join(
            self.chart_dir, 
            f"{symbol}_ultra_hq_breakout_{timestamp}.png"
        )
        
        plt.savefig(
            chart_path,
            dpi=self.chart_config["dpi"],
            facecolor=self.chart_config["facecolor"],
            bbox_inches="tight",
            pad_inches=0.5,  # More padding for mobile
            format='png',
            optimize=True,  # Optimize file size
            quality=95,  # High quality compression
        )
        plt.close()
        
        logger.info(f"[ENHANCED-CHARTS] Created ultra-HQ chart: {chart_path}")
        return chart_path
    
    def _plot_enhanced_price_action(
        self, 
        ax, 
        data: pd.DataFrame, 
        analysis: Dict, 
        symbol: str
    ):
        """Plot ultra-enhanced price action with crystal-clear visual elements."""
        # Calculate Heikin-Ashi for smoother visualization
        ha_data = self._calculate_heikin_ashi(data)
        
        # Plot enhanced Heikin-Ashi candles with maximum mobile visibility
        for i, (idx, row) in enumerate(ha_data.iterrows()):
            is_bullish = row["HA_Close"] >= row["HA_Open"]
            color = self.colors["bullish"] if is_bullish else self.colors["bearish"]
            
            # Enhanced candle bodies with better proportions
            body_height = abs(row["HA_Close"] - row["HA_Open"])
            body_bottom = min(row["HA_Open"], row["HA_Close"])
            
            # Ultra-wide candle bodies for mobile clarity
            candle_width = self.chart_config["candle_width"]
            ax.add_patch(Rectangle(
                (i - candle_width/2, body_bottom), candle_width, body_height,
                facecolor=color, alpha=0.9, linewidth=2, edgecolor=color
            ))
            
            # Thicker, more visible wicks
            ax.plot([i, i], [row["HA_Low"], row["HA_High"]], 
                   color=color, linewidth=3, alpha=0.8, solid_capstyle='round')
        
        # Add multiple moving averages for better analysis
        if len(data) >= 20:
            sma_20 = data["Close"].rolling(20).mean()
            ax.plot(range(len(sma_20)), sma_20, 
                   color=self.colors["sma"], 
                   linewidth=self.chart_config["line_width"],
                   alpha=0.9, label="SMA(20)", linestyle='-')
        
        if len(data) >= 50:
            sma_50 = data["Close"].rolling(50).mean()
            ax.plot(range(len(sma_50)), sma_50, 
                   color=self.colors["ema"], 
                   linewidth=self.chart_config["line_width"] - 1,
                   alpha=0.8, label="SMA(50)", linestyle='--')
        
        # Enhanced current price visualization
        current_price = analysis.get("current_price", data["Close"].iloc[-1])
        trend = analysis.get("trend_direction", "NEUTRAL")
        
        # Prominent current price line with glow effect
        ax.axhline(y=current_price, color=self.colors["current"], 
                  linewidth=4, linestyle="-", alpha=1.0, zorder=10)
        ax.axhline(y=current_price, color=self.colors["current"], 
                  linewidth=8, linestyle="-", alpha=0.3, zorder=9)  # Glow effect
        
        # Enhanced trend annotations with better positioning
        if trend == "BULLISH":
            ax.annotate(
                f"🚀 BULLISH BREAKOUT\n${current_price:.2f}",
                xy=(len(data) * 0.75, current_price),
                xytext=(15, 40),
                textcoords="offset points",
                fontsize=self.chart_config["annotation_size"],
                color=self.colors["bullish"],
                weight="bold",
                bbox=dict(boxstyle="round,pad=0.5", facecolor=self.colors["bullish"], 
                         alpha=0.25, edgecolor=self.colors["bullish"], linewidth=2),
                arrowprops=dict(arrowstyle="->", color=self.colors["bullish"], 
                               lw=3, alpha=0.9)
            )
        elif trend == "BEARISH":
            ax.annotate(
                f"📉 BEARISH SIGNAL\n${current_price:.2f}",
                xy=(len(data) * 0.75, current_price),
                xytext=(15, -50),
                textcoords="offset points",
                fontsize=self.chart_config["annotation_size"],
                color=self.colors["bearish"],
                weight="bold",
                bbox=dict(boxstyle="round,pad=0.5", facecolor=self.colors["bearish"], 
                         alpha=0.25, edgecolor=self.colors["bearish"], linewidth=2),
                arrowprops=dict(arrowstyle="->", color=self.colors["bearish"], 
                               lw=3, alpha=0.9)
            )
        
        # Enhanced support/resistance levels with labels
        if "support_level" in analysis and analysis["support_level"]:
            support_price = analysis["support_level"]
            ax.axhline(y=support_price, 
                      color=self.colors["support"], 
                      linewidth=3, linestyle=":", alpha=0.8, zorder=5)
            ax.text(len(data) * 0.02, support_price, f"Support: ${support_price:.2f}",
                   color=self.colors["support"], fontsize=self.chart_config["annotation_size"],
                   weight="bold", verticalalignment='bottom')
        
        if "resistance_level" in analysis and analysis["resistance_level"]:
            resistance_price = analysis["resistance_level"]
            ax.axhline(y=resistance_price, 
                      color=self.colors["resistance"], 
                      linewidth=3, linestyle=":", alpha=0.8, zorder=5)
            ax.text(len(data) * 0.02, resistance_price, f"Resistance: ${resistance_price:.2f}",
                   color=self.colors["resistance"], fontsize=self.chart_config["annotation_size"],
                   weight="bold", verticalalignment='top')
    
    def _plot_enhanced_volume(self, ax, data: pd.DataFrame):
        """Plot ultra-enhanced volume chart with crystal-clear visualization."""
        volume = data["Volume"].values
        
        # Enhanced color coding for volume bars
        colors = [
            self.colors["bullish"] if data.iloc[i]["Close"] >= data.iloc[i]["Open"] 
            else self.colors["bearish"] for i in range(len(data))
        ]
        
        # Ultra-enhanced volume bars with better visibility
        bars = ax.bar(range(len(volume)), volume, color=colors, alpha=0.8, width=0.9, 
                     edgecolor='none', linewidth=0)
        
        # Highlight high volume bars
        avg_volume = np.mean(volume)
        for i, (bar, vol) in enumerate(zip(bars, volume)):
            if vol > avg_volume * 1.5:  # High volume threshold
                bar.set_alpha(1.0)
                bar.set_edgecolor(colors[i])
                bar.set_linewidth(2)
        
        # Enhanced volume moving average
        if len(volume) >= 10:
            vol_ma = pd.Series(volume).rolling(10).mean()
            ax.plot(range(len(vol_ma)), vol_ma, 
                   color=self.colors["neutral"], 
                   linewidth=3, alpha=0.9, label="Vol MA(10)", linestyle='-')
        
        # Add volume statistics annotation
        current_vol = volume[-1]
        avg_vol_text = f"Avg: {avg_volume/1000000:.1f}M" if avg_volume > 1000000 else f"Avg: {avg_volume/1000:.0f}K"
        current_vol_text = f"Current: {current_vol/1000000:.1f}M" if current_vol > 1000000 else f"Current: {current_vol/1000:.0f}K"
        
        ax.text(0.02, 0.95, f"{current_vol_text}\n{avg_vol_text}", 
               transform=ax.transAxes, fontsize=self.chart_config["annotation_size"],
               color=self.colors["current"], weight="bold", 
               verticalalignment='top', 
               bbox=dict(boxstyle="round,pad=0.3", facecolor=self.colors["background"], 
                        alpha=0.8, edgecolor=self.colors["current"], linewidth=1))
    
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
    
    def _add_chart_annotations(self, ax, analysis: Dict, symbol: str):
        """Add comprehensive chart annotations for enhanced clarity."""
        # Add timestamp watermark
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S EST')
        ax.text(0.98, 0.02, f"Generated: {timestamp}", 
               transform=ax.transAxes, fontsize=10,
               color=self.colors["volume"], alpha=0.7,
               horizontalalignment='right', verticalalignment='bottom')
        
        # Add confidence meter visualization
        confidence = analysis.get("confidence", 0)
        if confidence > 0:
            # Create confidence bar in top-right corner
            conf_color = (self.colors["bullish"] if confidence >= 65 
                         else self.colors["neutral"] if confidence >= 50 
                         else self.colors["bearish"])
            
            ax.text(0.98, 0.98, f"🎯 Confidence\n{confidence:.1f}%", 
                   transform=ax.transAxes, fontsize=self.chart_config["annotation_size"],
                   color=conf_color, weight="bold",
                   horizontalalignment='right', verticalalignment='top',
                   bbox=dict(boxstyle="round,pad=0.4", facecolor=conf_color, 
                            alpha=0.15, edgecolor=conf_color, linewidth=2))
        
        # Add volatility indicator
        if "atr_percentage" in analysis:
            atr_pct = analysis["atr_percentage"]
            volatility_emoji = "🔥" if atr_pct > 2.0 else "📊" if atr_pct > 1.0 else "😴"
            ax.text(0.02, 0.02, f"{volatility_emoji} ATR: {atr_pct:.2f}%", 
                   transform=ax.transAxes, fontsize=self.chart_config["annotation_size"],
                   color=self.colors["current"], weight="bold",
                   verticalalignment='bottom',
                   bbox=dict(boxstyle="round,pad=0.3", facecolor=self.colors["background"], 
                            alpha=0.8, edgecolor=self.colors["current"], linewidth=1))
    
    def _format_chart_professionally(
        self, 
        fig, 
        ax1, 
        ax2, 
        symbol: str, 
        analysis: Dict
    ):
        """Apply ultra-professional formatting to the chart for maximum mobile clarity."""
        # Enhanced main chart title with subtitle
        trend = analysis.get("trend_direction", "NEUTRAL")
        confidence = analysis.get("confidence", 0)
        
        main_title = f"{symbol} • {trend} Signal"
        subtitle = f"Confidence: {confidence:.1f}% • {datetime.now().strftime('%Y-%m-%d %H:%M EST')}"
        
        ax1.set_title(main_title, fontsize=self.chart_config["title_size"],
                     color=self.chart_config["text_color"], weight="bold", pad=25)
        ax1.text(0.5, 0.96, subtitle, transform=ax1.transAxes, 
                fontsize=self.chart_config["subtitle_size"],
                color=self.colors["volume"], horizontalalignment='center')
        
        # Enhanced axis labels with better spacing
        ax1.set_ylabel("Price ($)", fontsize=self.chart_config["label_size"],
                      color=self.chart_config["text_color"], weight="bold", labelpad=15)
        
        # Professional grid styling
        ax1.grid(True, alpha=self.chart_config["grid_alpha"], 
                color=self.colors["grid"], linewidth=1, linestyle='-')
        ax1.set_axisbelow(True)
        
        # Enhanced legend with better positioning
        if ax1.get_legend_handles_labels()[0]:  # Check if legend exists
            legend = ax1.legend(loc="upper left", fontsize=self.chart_config["legend_size"],
                              frameon=True, fancybox=True, shadow=True, 
                              facecolor=self.colors["background"], 
                              edgecolor=self.colors["current"], framealpha=0.9)
            legend.get_frame().set_linewidth(2)
        
        # Enhanced volume chart formatting
        ax2.set_ylabel("Volume", fontsize=self.chart_config["label_size"],
                      color=self.chart_config["text_color"], weight="bold", labelpad=15)
        ax2.set_xlabel("Time Periods (5min bars)", fontsize=self.chart_config["label_size"],
                      color=self.chart_config["text_color"], weight="bold", labelpad=15)
        
        ax2.grid(True, alpha=self.chart_config["grid_alpha"], 
                color=self.colors["grid"], linewidth=1, linestyle='-')
        ax2.set_axisbelow(True)
        
        # Ultra-enhanced tick formatting with better visibility
        for ax in [ax1, ax2]:
            ax.tick_params(labelsize=self.chart_config["tick_size"],
                          colors=self.chart_config["text_color"],
                          width=self.chart_config["spine_width"],
                          length=8, pad=8)
            
            # Enhanced spine styling
            for spine in ax.spines.values():
                spine.set_color(self.colors["current"])
                spine.set_linewidth(self.chart_config["spine_width"])
                spine.set_alpha(0.8)
        
        # Professional layout optimization
        fig.suptitle("", fontsize=1)  # Remove default title
        plt.tight_layout()
        
        # Add professional branding watermark
        fig.text(0.99, 0.01, "📈 RobinhoodBot Pro • Enhanced Analysis", 
                fontsize=10, color=self.colors["volume"], alpha=0.6,
                horizontalalignment='right', verticalalignment='bottom')
    
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
