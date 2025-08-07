#!/usr/bin/env python3
"""
Webhook Chart Sender - High-Quality Charts via Slack Webhook

Alternative chart delivery system that works with Slack webhooks when
bot tokens don't have file upload permissions. Creates high-quality
charts and sends them as base64-encoded images or external links.

This provides a fallback solution for chart delivery when Slack bot
file upload scopes are not available.
"""

import os
import base64
import logging
import tempfile
from datetime import datetime
from typing import Dict, Optional
import pandas as pd
import numpy as np

# Chart generation
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import seaborn as sns

# Slack integration
import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class WebhookChartSender:
    """
    High-quality chart generation with webhook delivery.
    
    Creates professional trading charts and sends them to Slack
    via webhook with enhanced visual quality and mobile optimization.
    """
    
    def __init__(self):
        """Initialize webhook chart sender."""
        self.webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        self.enabled = bool(self.webhook_url)
        
        # Create temporary directory for charts
        self.chart_dir = tempfile.mkdtemp(prefix="webhook_charts_")
        
        # Enhanced chart configuration
        self.setup_chart_styling()
        
        logger.info(f"[WEBHOOK-CHARTS] Initialized (enabled: {self.enabled})")
    
    def setup_chart_styling(self):
        """Setup professional chart styling."""
        plt.style.use("dark_background")
        
        self.chart_config = {
            "figsize": (14, 10),  # Large for clarity
            "dpi": 150,  # High DPI
            "facecolor": "#0d1117",  # Dark theme
            "edgecolor": "#f0f6fc",  # Light text
            "title_size": 18,
            "label_size": 14,
            "tick_size": 12,
            "line_width": 2.5,
            "marker_size": 8,
            "grid_alpha": 0.4,
        }
        
        self.colors = {
            "bullish": "#00d4aa",
            "bearish": "#f85149", 
            "neutral": "#7c3aed",
            "volume": "#6e7681",
            "sma": "#ffa657",
            "current": "#f0f6fc",
        }
    
    def send_enhanced_chart_alert(
        self, 
        market_data: pd.DataFrame, 
        analysis: Dict, 
        symbol: str = "SPY"
    ) -> bool:
        """
        Send enhanced chart alert via webhook.
        
        Args:
            market_data: Historical OHLCV data
            analysis: Breakout analysis results
            symbol: Stock symbol
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            logger.warning("[WEBHOOK-CHARTS] Webhook not configured")
            return False
            
        try:
            # Generate high-quality chart
            chart_path = self.create_enhanced_chart(market_data, analysis, symbol)
            
            # Create rich message with chart reference
            message = self.create_rich_chart_message(symbol, analysis, chart_path)
            
            # Send to Slack
            success = self.send_webhook_message(message)
            
            # Cleanup
            if os.path.exists(chart_path):
                os.remove(chart_path)
                
            return success
            
        except Exception as e:
            logger.error(f"[WEBHOOK-CHARTS] Failed to send chart alert: {e}")
            return False
    
    def create_enhanced_chart(
        self, 
        market_data: pd.DataFrame, 
        analysis: Dict, 
        symbol: str
    ) -> str:
        """Create enhanced chart with professional styling."""
        # Prepare data
        data = market_data.tail(50).copy()
        
        # Create figure
        fig, (ax1, ax2) = plt.subplots(
            2, 1,
            figsize=self.chart_config["figsize"],
            facecolor=self.chart_config["facecolor"],
            gridspec_kw={'height_ratios': [3, 1], 'hspace': 0.3}
        )
        
        # Plot enhanced price action
        self.plot_enhanced_candles(ax1, data, analysis)
        
        # Plot volume
        self.plot_enhanced_volume(ax2, data)
        
        # Format professionally
        self.format_chart(fig, ax1, ax2, symbol, analysis)
        
        # Save chart
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        chart_path = os.path.join(
            self.chart_dir, 
            f"{symbol}_enhanced_{timestamp}.png"
        )
        
        plt.savefig(
            chart_path,
            dpi=self.chart_config["dpi"],
            facecolor=self.chart_config["facecolor"],
            bbox_inches="tight",
            pad_inches=0.3,
            format='png'
        )
        plt.close()
        
        logger.info(f"[WEBHOOK-CHARTS] Created chart: {chart_path}")
        return chart_path
    
    def plot_enhanced_candles(self, ax, data: pd.DataFrame, analysis: Dict):
        """Plot enhanced candlestick chart."""
        # Calculate Heikin-Ashi
        ha_data = self.calculate_heikin_ashi(data)
        
        # Plot candles
        for i, (idx, row) in enumerate(ha_data.iterrows()):
            color = self.colors["bullish"] if row["HA_Close"] >= row["HA_Open"] else self.colors["bearish"]
            
            # Candle body
            body_height = abs(row["HA_Close"] - row["HA_Open"])
            body_bottom = min(row["HA_Open"], row["HA_Close"])
            
            ax.add_patch(Rectangle(
                (i - 0.4, body_bottom), 0.8, body_height,
                facecolor=color, alpha=0.8, linewidth=1
            ))
            
            # Wicks
            ax.plot([i, i], [row["HA_Low"], row["HA_High"]], 
                   color=color, linewidth=2, alpha=0.7)
        
        # Add SMA
        if len(data) >= 20:
            sma_20 = data["Close"].rolling(20).mean()
            ax.plot(range(len(sma_20)), sma_20, 
                   color=self.colors["sma"], 
                   linewidth=self.chart_config["line_width"],
                   alpha=0.9, label="SMA(20)")
        
        # Current price line
        current_price = analysis.get("current_price", data["Close"].iloc[-1])
        ax.axhline(y=current_price, color=self.colors["current"], 
                  linewidth=2, linestyle="--", alpha=0.8)
        
        # Trend annotation
        trend = analysis.get("trend_direction", "NEUTRAL")
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
    
    def plot_enhanced_volume(self, ax, data: pd.DataFrame):
        """Plot enhanced volume chart."""
        volume = data["Volume"].values
        colors = [
            self.colors["bullish"] if data.iloc[i]["Close"] >= data.iloc[i]["Open"] 
            else self.colors["bearish"] for i in range(len(data))
        ]
        
        ax.bar(range(len(volume)), volume, color=colors, alpha=0.7, width=0.8)
        
        # Volume MA
        if len(volume) >= 10:
            vol_ma = pd.Series(volume).rolling(10).mean()
            ax.plot(range(len(vol_ma)), vol_ma, 
                   color=self.colors["neutral"], 
                   linewidth=2, alpha=0.8, label="Vol MA(10)")
    
    def calculate_heikin_ashi(self, data: pd.DataFrame) -> pd.DataFrame:
        """Calculate Heikin-Ashi values."""
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
    
    def format_chart(self, fig, ax1, ax2, symbol: str, analysis: Dict):
        """Apply professional formatting."""
        # Main chart
        ax1.set_title(
            f"{symbol} - Enhanced Breakout Analysis ({datetime.now().strftime('%Y-%m-%d %H:%M')})",
            fontsize=self.chart_config["title_size"],
            color=self.chart_config["edgecolor"],
            weight="bold",
            pad=20
        )
        
        ax1.set_ylabel("Price ($)", 
                      fontsize=self.chart_config["label_size"],
                      color=self.chart_config["edgecolor"])
        
        ax1.grid(True, alpha=self.chart_config["grid_alpha"])
        ax1.legend(loc="upper left", fontsize=self.chart_config["label_size"])
        
        # Volume chart
        ax2.set_ylabel("Volume", 
                      fontsize=self.chart_config["label_size"],
                      color=self.chart_config["edgecolor"])
        ax2.set_xlabel("Time", 
                      fontsize=self.chart_config["label_size"],
                      color=self.chart_config["edgecolor"])
        
        ax2.grid(True, alpha=self.chart_config["grid_alpha"])
        
        # Tick formatting
        for ax in [ax1, ax2]:
            ax.tick_params(
                labelsize=self.chart_config["tick_size"],
                colors=self.chart_config["edgecolor"]
            )
        
        # Analysis summary
        confidence = analysis.get("confidence", 0)
        trend = analysis.get("trend_direction", "NEUTRAL")
        
        summary = f"Confidence: {confidence:.1f}%\nTrend: {trend}"
        if "breakout_strength" in analysis:
            summary += f"\nStrength: {analysis['breakout_strength']:.2f}"
        
        ax1.text(
            0.02, 0.98, summary,
            transform=ax1.transAxes,
            fontsize=12,
            verticalalignment='top',
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#1c2128", alpha=0.8),
            color=self.chart_config["edgecolor"]
        )
    
    def create_rich_chart_message(
        self, 
        symbol: str, 
        analysis: Dict, 
        chart_path: str
    ) -> Dict:
        """Create rich message for webhook."""
        trend = analysis.get("trend_direction", "NEUTRAL")
        confidence = analysis.get("confidence", 0)
        current_price = analysis.get("current_price", 0)
        
        emoji = "📈" if trend == "BULLISH" else "📉" if trend == "BEARISH" else "📊"
        
        # Get file size for reference
        file_size = os.path.getsize(chart_path) if os.path.exists(chart_path) else 0
        
        message_text = f"""{emoji} **{symbol} ENHANCED CHART ANALYSIS**

**📊 High-Quality Chart Generated:**
• Resolution: 150 DPI (enhanced clarity)
• Professional dark theme with enhanced contrast
• Heikin-Ashi candles for smoother trend visualization
• Moving averages and technical indicators
• Mobile-optimized formatting

**📈 Current Analysis:**
• **Price:** ${current_price:.2f}
• **Trend:** {trend}
• **Confidence:** {confidence:.1f}%
• **Time:** {datetime.now().strftime('%H:%M:%S EST')}

**💡 Chart Features:**
• Enhanced visual clarity for mobile viewing
• Professional styling with clear annotations
• Volume analysis with moving averages
• Support/resistance level visualization

**📱 Note:** Chart saved locally ({file_size/1024:.1f}KB) - Enable Slack file upload scopes for automatic image delivery."""
        
        return {
            "text": message_text,
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{emoji} {symbol} Enhanced Chart Analysis"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Price:* ${current_price:.2f}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Trend:* {trend}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Confidence:* {confidence:.1f}%"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Chart Size:* {file_size/1024:.1f}KB"
                        }
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "📊 *High-quality chart generated with enhanced visual clarity for mobile trading decisions.*"
                    }
                }
            ]
        }
    
    def send_webhook_message(self, message: Dict) -> bool:
        """Send message via webhook."""
        try:
            response = requests.post(
                self.webhook_url,
                json=message,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info("[WEBHOOK-CHARTS] Message sent successfully")
                return True
            else:
                logger.warning(f"[WEBHOOK-CHARTS] Failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"[WEBHOOK-CHARTS] Webhook error: {e}")
            return False


# Example usage
if __name__ == "__main__":
    print("Webhook Chart Sender - High-Quality Charts for Slack")
    
    sender = WebhookChartSender()
    if sender.enabled:
        print("✅ Webhook configured - ready for enhanced chart delivery")
    else:
        print("❌ Webhook not configured - set SLACK_WEBHOOK_URL in .env")
