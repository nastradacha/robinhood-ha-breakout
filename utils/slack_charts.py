#!/usr/bin/env python3
"""
Enhanced Slack Integration with Rich Charts and Market Analysis

Generates professional trading charts and technical analysis visualizations
for mobile-friendly Slack alerts. Enables better trading decisions from anywhere.

Key Features:
- Real-time price action charts with Heikin-Ashi candles
- Support/resistance level visualization
- Volume analysis and breakout strength indicators
- Technical indicator overlays (SMA, Bollinger Bands)
- Mobile-optimized chart formatting
- Automatic chart upload to Slack channels

Usage:
    from utils.slack_charts import SlackChartGenerator

    chart_gen = SlackChartGenerator()
    chart_path = chart_gen.create_breakout_chart(market_data, analysis)
    slack_notifier.send_chart_alert(chart_path, "SPY Breakout Signal")
"""

import os
import logging
from datetime import datetime
from typing import Dict, Optional
import pandas as pd
import numpy as np

# Chart generation libraries
# Set non-interactive backend to prevent threading issues
import matplotlib

matplotlib.use("Agg")  # Use Anti-Grain Geometry backend (no GUI)
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import seaborn as sns

# Slack integration
import requests

logger = logging.getLogger(__name__)


class SlackChartGenerator:
    """
    Professional chart generation for enhanced Slack trading alerts.

    Creates mobile-optimized trading charts with technical analysis
    overlays for better decision making from mobile devices.
    """

    def __init__(self, chart_dir: str = "charts"):
        """Initialize chart generator with configuration."""
        self.chart_dir = chart_dir
        os.makedirs(chart_dir, exist_ok=True)

        # Set professional chart styling
        plt.style.use("dark_background")
        sns.set_palette("husl")

        # Enhanced chart configuration for high-quality mobile viewing
        self.chart_config = {
            "figsize": (14, 10),  # Larger for better clarity
            "dpi": 150,  # Higher DPI for crisp images
            "facecolor": "#0d1117",  # GitHub dark theme
            "edgecolor": "#f0f6fc",  # Light text color
            "grid_alpha": 0.4,
            "title_size": 18,  # Larger titles
            "label_size": 14,  # Larger labels
            "tick_size": 12,  # Larger ticks
            "line_width": 2.5,  # Thicker lines for clarity
            "marker_size": 8,  # Larger markers
        }

        logger.info("[CHARTS] Slack chart generator initialized") if not hasattr(self.__class__, '_logged_init') else None
        self.__class__._logged_init = True

    def create_breakout_chart(
        self, market_data: pd.DataFrame, analysis: Dict, symbol: str = "SPY"
    ) -> str:
        """
        Create comprehensive breakout analysis chart.

        Args:
            market_data: Historical OHLCV data
            analysis: Breakout analysis results
            symbol: Stock symbol

        Returns:
            Path to generated chart file
        """
        fig, (ax1, ax2) = plt.subplots(
            2,
            1,
            figsize=self.chart_config["figsize"],
            facecolor=self.chart_config["facecolor"],
            gridspec_kw={"height_ratios": [3, 1]},
        )

        # Prepare data
        data = market_data.tail(100).copy()  # Last 100 bars for mobile viewing

        # Main price chart with Heikin-Ashi
        self._plot_heikin_ashi_candles(ax1, data)
        self._plot_support_resistance(ax1, analysis, data)
        self._plot_technical_indicators(ax1, data)
        self._plot_current_signal(ax1, analysis)

        # Volume chart
        self._plot_volume_analysis(ax2, data, analysis)

        # Chart formatting
        self._format_main_chart(ax1, symbol, analysis)
        self._format_volume_chart(ax2)

        # Save chart
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        chart_path = os.path.join(self.chart_dir, f"{symbol}_breakout_{timestamp}.png")

        plt.tight_layout()
        plt.savefig(
            chart_path,
            dpi=self.chart_config["dpi"],
            facecolor=self.chart_config["facecolor"],
            bbox_inches="tight",
            pad_inches=0.2,
        )
        plt.close()

        logger.info(f"[CHARTS] Created breakout chart: {chart_path}")
        return chart_path

    def create_position_chart(
        self,
        position: Dict,
        current_price: float,
        pnl_pct: float,
        exit_decision: Dict = None,
    ) -> str:
        """
        Create position monitoring chart with P&L visualization.

        Args:
            position: Position details
            current_price: Current stock price
            pnl_pct: Current P&L percentage
            exit_decision: Exit strategy decision data

        Returns:
            Path to generated chart file
        """
        fig, ax = plt.subplots(
            figsize=(10, 6), facecolor=self.chart_config["facecolor"]
        )

        # Create P&L visualization
        entry_price = position["entry_price"]
        symbol = position["symbol"]

        # P&L gauge chart
        self._plot_pnl_gauge(ax, pnl_pct, exit_decision)

        # Add position details
        self._add_position_details(ax, position, current_price, pnl_pct)

        # Save chart
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        chart_path = os.path.join(self.chart_dir, f"{symbol}_position_{timestamp}.png")

        plt.tight_layout()
        plt.savefig(
            chart_path,
            dpi=self.chart_config["dpi"],
            facecolor=self.chart_config["facecolor"],
            bbox_inches="tight",
            pad_inches=0.2,
        )
        plt.close()

        logger.info(f"[CHARTS] Created position chart: {chart_path}")
        return chart_path

    def _plot_heikin_ashi_candles(self, ax, data: pd.DataFrame):
        """Plot Heikin-Ashi candlestick chart."""
        # Calculate Heikin-Ashi if not present
        if "HA_Open" not in data.columns:
            data = self._calculate_heikin_ashi(data)

        # Plot candles
        for i, (idx, row) in enumerate(data.iterrows()):
            color = "#00ff88" if row["HA_Close"] >= row["HA_Open"] else "#ff4444"

            # Candle body
            body_height = abs(row["HA_Close"] - row["HA_Open"])
            body_bottom = min(row["HA_Open"], row["HA_Close"])

            ax.add_patch(
                Rectangle(
                    (i - 0.3, body_bottom), 0.6, body_height, facecolor=color, alpha=0.8
                )
            )

            # Wicks
            ax.plot(
                [i, i],
                [row["HA_Low"], row["HA_High"]],
                color=color,
                linewidth=1,
                alpha=0.6,
            )

        ax.set_xlim(-1, len(data))

    def _plot_support_resistance(self, ax, analysis: Dict, data: pd.DataFrame):
        """Plot support and resistance levels."""
        data_len = len(data)

        # Resistance levels
        for level in analysis.get("resistance_levels", [])[:3]:  # Top 3
            ax.axhline(y=level, color="red", linestyle="--", alpha=0.7, linewidth=1)
            ax.text(
                data_len * 0.02,
                level,
                f"R: ${level:.2f}",
                color="red",
                fontsize=9,
                va="bottom",
            )

        # Support levels
        for level in analysis.get("support_levels", [])[:3]:  # Top 3
            ax.axhline(y=level, color="green", linestyle="--", alpha=0.7, linewidth=1)
            ax.text(
                data_len * 0.02,
                level,
                f"S: ${level:.2f}",
                color="green",
                fontsize=9,
                va="top",
            )

    def _plot_technical_indicators(self, ax, data: pd.DataFrame):
        """Plot technical indicators overlay."""
        has_indicators = False

        # Simple Moving Average
        if len(data) >= 20:
            sma_20 = data["Close"].rolling(20).mean()
            ax.plot(
                range(len(sma_20)),
                sma_20,
                color="orange",
                linewidth=2,
                alpha=0.8,
                label="SMA(20)",
            )
            has_indicators = True

        # Add legend only if we have indicators
        if has_indicators:
            ax.legend(loc="upper left", fontsize=9)

    def _plot_current_signal(self, ax, analysis: Dict):
        """Highlight current trading signal."""
        current_price = analysis.get("current_price", 0)
        trend = analysis.get("trend_direction", "NEUTRAL")

        # Signal arrow and text
        if trend == "BULLISH":
            ax.annotate(
                "📈 BULLISH",
                xy=(len(ax.get_xlim()) * 0.7, current_price),
                xytext=(10, 20),
                textcoords="offset points",
                fontsize=12,
                color="#00ff88",
                weight="bold",
                arrowprops=dict(arrowstyle="->", color="#00ff88"),
            )
        elif trend == "BEARISH":
            ax.annotate(
                "📉 BEARISH",
                xy=(len(ax.get_xlim()) * 0.7, current_price),
                xytext=(10, -30),
                textcoords="offset points",
                fontsize=12,
                color="#ff4444",
                weight="bold",
                arrowprops=dict(arrowstyle="->", color="#ff4444"),
            )

    def _plot_volume_analysis(self, ax, data: pd.DataFrame, analysis: Dict):
        """Plot volume analysis in bottom panel."""
        volume = data["Volume"].values
        colors = [
            "#00ff88" if data.iloc[i]["Close"] >= data.iloc[i]["Open"] else "#ff4444"
            for i in range(len(data))
        ]

        bars = ax.bar(range(len(volume)), volume, color=colors, alpha=0.7)

        # Highlight high volume
        volume_avg = np.mean(volume[-20:]) if len(volume) >= 20 else np.mean(volume)
        volume_ratio = analysis.get("volume_ratio", 1.0)

        if volume_ratio > 1.5:
            ax.axhline(y=volume_avg * 1.5, color="yellow", linestyle=":", alpha=0.8)
            ax.text(
                len(volume) * 0.02,
                volume_avg * 1.5,
                "High Volume",
                color="yellow",
                fontsize=9,
                va="bottom",
            )

    def _plot_pnl_gauge(self, ax, pnl_pct: float, exit_decision: Dict = None):
        """Create P&L gauge visualization."""
        # Gauge background
        theta = np.linspace(0, np.pi, 100)

        # Color zones
        ax.fill_between(
            theta,
            0,
            1,
            where=(theta <= np.pi / 3),
            color="red",
            alpha=0.3,
            label="Loss Zone",
        )
        ax.fill_between(
            theta,
            0,
            1,
            where=((theta > np.pi / 3) & (theta <= 2 * np.pi / 3)),
            color="yellow",
            alpha=0.3,
            label="Neutral Zone",
        )
        ax.fill_between(
            theta,
            0,
            1,
            where=(theta > 2 * np.pi / 3),
            color="green",
            alpha=0.3,
            label="Profit Zone",
        )

        # P&L needle
        pnl_angle = np.pi * (pnl_pct + 50) / 100  # Map -50% to +50% to 0 to π
        pnl_angle = max(0, min(np.pi, pnl_angle))

        ax.arrow(
            0,
            0,
            0.8 * np.cos(pnl_angle),
            0.8 * np.sin(pnl_angle),
            head_width=0.05,
            head_length=0.1,
            fc="white",
            ec="white",
        )

        # P&L text
        ax.text(
            0,
            -0.3,
            f"{pnl_pct:+.1f}%",
            ha="center",
            va="center",
            fontsize=20,
            weight="bold",
            color="green" if pnl_pct > 0 else "red" if pnl_pct < 0 else "white",
        )

        ax.set_xlim(-1.2, 1.2)
        ax.set_ylim(-0.5, 1.2)
        ax.set_aspect("equal")
        ax.axis("off")

    def _add_position_details(
        self, ax, position: Dict, current_price: float, pnl_pct: float
    ):
        """Add position details text to chart."""
        details = [
            f"Symbol: {position['symbol']} ${position['strike']} {position['option_type']}",
            f"Entry: ${position['entry_price']:.2f}",
            f"Current: ${current_price:.2f}",
            f"P&L: {pnl_pct:+.1f}%",
        ]

        for i, detail in enumerate(details):
            ax.text(
                0.02,
                0.98 - i * 0.05,
                detail,
                transform=ax.transAxes,
                fontsize=12,
                color="white",
                va="top",
            )

    def _calculate_heikin_ashi(self, data: pd.DataFrame) -> pd.DataFrame:
        """Calculate Heikin-Ashi candles if not present."""
        ha_data = data.copy()

        # Calculate HA_Close first
        ha_data["HA_Close"] = (
            data["Open"] + data["High"] + data["Low"] + data["Close"]
        ) / 4

        # Calculate HA_Open (initialize first value)
        ha_data["HA_Open"] = (data["Open"] + data["Close"]) / 2
        for i in range(1, len(ha_data)):
            ha_data.iloc[i, ha_data.columns.get_loc("HA_Open")] = (
                ha_data.iloc[i - 1]["HA_Open"] + ha_data.iloc[i - 1]["HA_Close"]
            ) / 2

        # Calculate HA_High and HA_Low using the newly created columns
        ha_data["HA_High"] = ha_data[["High", "HA_Open", "HA_Close"]].max(axis=1)
        ha_data["HA_Low"] = ha_data[["Low", "HA_Open", "HA_Close"]].min(axis=1)

        return ha_data

    def _format_main_chart(self, ax, symbol: str, analysis: Dict):
        """Format main price chart."""
        ax.set_title(
            f"{symbol} - Breakout Analysis",
            fontsize=self.chart_config["title_size"],
            color="white",
            pad=20,
        )

        ax.set_ylabel(
            "Price ($)", fontsize=self.chart_config["label_size"], color="white"
        )
        ax.grid(True, alpha=self.chart_config["grid_alpha"])
        ax.tick_params(colors="white", labelsize=self.chart_config["tick_size"])

        # Add analysis summary
        summary = (
            f"Trend: {analysis.get('trend_direction', 'N/A')} | "
            f"Strength: {analysis.get('breakout_strength', 0):.1f} | "
            f"Body: {analysis.get('candle_body_pct', 0):.2f}%"
        )

        ax.text(
            0.02,
            0.98,
            summary,
            transform=ax.transAxes,
            fontsize=10,
            color="cyan",
            va="top",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="black", alpha=0.7),
        )

    def _format_volume_chart(self, ax):
        """Format volume chart."""
        ax.set_ylabel("Volume", fontsize=self.chart_config["label_size"], color="white")
        ax.grid(True, alpha=self.chart_config["grid_alpha"])
        ax.tick_params(colors="white", labelsize=self.chart_config["tick_size"])


class EnhancedSlackNotifier:
    """
    Enhanced Slack notifier with chart upload capabilities.

    Extends the existing SlackNotifier with rich chart integration
    for professional mobile trading alerts.
    """

    def __init__(
        self, webhook_url: Optional[str] = None, bot_token: Optional[str] = None
    ):
        """Initialize enhanced Slack notifier."""
        self.webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
        self.bot_token = bot_token or os.getenv("SLACK_BOT_TOKEN")
        self.channel_id = os.getenv("SLACK_CHANNEL_ID")

        self.chart_generator = SlackChartGenerator()
        self.enabled = bool(self.webhook_url)

        logger.info(f"[SLACK] Enhanced notifier initialized (enabled: {self.enabled})")

    def send_breakout_alert_with_chart(
        self,
        symbol: str,
        decision: str,
        analysis: Dict,
        market_data: pd.DataFrame,
        confidence: float,
    ):
        """Send breakout alert with professional chart."""
        if not self.enabled:
            return

        try:
            # Generate chart
            chart_path = self.chart_generator.create_breakout_chart(
                market_data, analysis, symbol
            )

            # Create rich message
            message = self._create_breakout_message(
                symbol, decision, analysis, confidence
            )

            # Send message with chart
            self._send_message_with_image(message, chart_path)

            logger.info(f"[SLACK] Sent breakout alert with chart for {symbol}")

        except Exception as e:
            logger.error(f"[SLACK] Failed to send breakout alert with chart: {e}")

    def send_position_alert_with_chart(
        self,
        position: Dict,
        current_price: float,
        pnl_pct: float,
        alert_type: str,
        exit_decision: Dict = None,
    ):
        """Send position alert with P&L chart."""
        if not self.enabled:
            return

        try:
            # Generate position chart
            chart_path = self.chart_generator.create_position_chart(
                position, current_price, pnl_pct, exit_decision
            )

            # Create rich message
            message = self._create_position_message(
                position, current_price, pnl_pct, alert_type
            )

            # Send message with chart
            self._send_message_with_image(message, chart_path)

            logger.info(
                f"[SLACK] Sent position alert with chart for {position['symbol']}"
            )

        except Exception as e:
            logger.error(f"[SLACK] Failed to send position alert with chart: {e}")

    def _create_breakout_message(
        self, symbol: str, decision: str, analysis: Dict, confidence: float
    ) -> Dict:
        """Create rich breakout message with technical details."""
        trend_emoji = (
            "📈"
            if analysis.get("trend_direction") == "BULLISH"
            else "📉" if analysis.get("trend_direction") == "BEARISH" else "➡️"
        )
        decision_emoji = (
            "🚀" if decision == "CALL" else "🔻" if decision == "PUT" else "⏸️"
        )

        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{decision_emoji} {symbol} {decision} Signal",
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Price:* ${analysis.get('current_price', 0):.2f}",
                        },
                        {"type": "mrkdwn", "text": f"*Confidence:* {confidence:.1%}"},
                        {
                            "type": "mrkdwn",
                            "text": f"*Trend:* {trend_emoji} {analysis.get('trend_direction', 'N/A')}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Strength:* {analysis.get('breakout_strength', 0):.1f}",
                        },
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Technical Analysis:*\n"
                        f"• Body Size: {analysis.get('candle_body_pct', 0):.2f}%\n"
                        f"• Volume Ratio: {analysis.get('volume_ratio', 0):.1f}x\n"
                        f"• Resistance: ${analysis.get('nearest_resistance', 0):.2f}\n"
                        f"• Support: ${analysis.get('nearest_support', 0):.2f}",
                    },
                },
            ]
        }

    def _create_position_message(
        self, position: Dict, current_price: float, pnl_pct: float, alert_type: str
    ) -> Dict:
        """Create rich position message with P&L details."""
        pnl_emoji = "💰" if pnl_pct > 0 else "🛑" if pnl_pct < -10 else "📊"

        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{pnl_emoji} {position['symbol']} Position Alert",
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Position:* ${position['strike']} {position['option_type']}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Entry:* ${position['entry_price']:.2f}",
                        },
                        {"type": "mrkdwn", "text": f"*Current:* ${current_price:.2f}"},
                        {"type": "mrkdwn", "text": f"*P&L:* {pnl_pct:+.1f}%"},
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Alert Type:* {alert_type.replace('_', ' ').title()}",
                    },
                },
            ]
        }

    def _send_message_with_image(self, message: Dict, image_path: str):
        """Send Slack message with image attachment."""
        if self.bot_token and self.channel_id:
            # Use bot token for file upload
            self._upload_file_with_message(message, image_path)
        else:
            # Fallback to webhook (text only)
            self._send_webhook_message(message)

    def _upload_file_with_message(self, message: Dict, image_path: str):
        """Upload file using Slack bot token."""
        try:
            # Upload file
            with open(image_path, "rb") as file:
                response = requests.post(
                    "https://slack.com/api/files.upload",
                    headers={"Authorization": f"Bearer {self.bot_token}"},
                    data={
                        "channels": self.channel_id,
                        "initial_comment": message.get("text", "Trading Alert"),
                    },
                    files={"file": file},
                )

            if response.status_code == 200:
                logger.debug("[SLACK] File uploaded successfully")
            else:
                logger.warning(f"[SLACK] File upload failed: {response.status_code}")

        except Exception as e:
            logger.error(f"[SLACK] File upload error: {e}")

    def _send_webhook_message(self, message: Dict):
        """Send message via webhook (fallback)."""
        try:
            response = requests.post(self.webhook_url, json=message, timeout=10)
            if response.status_code == 200:
                logger.debug("[SLACK] Webhook message sent successfully")
            else:
                logger.warning(f"[SLACK] Webhook failed: {response.status_code}")
        except Exception as e:
            logger.error(f"[SLACK] Webhook error: {e}")


# Example usage and testing
if __name__ == "__main__":
    # Test chart generation
    chart_gen = SlackChartGenerator()

    # Create sample data for testing
    dates = pd.date_range(start="2025-01-01", periods=50, freq="5min")
    sample_data = pd.DataFrame(
        {
            "Open": np.random.randn(50).cumsum() + 630,
            "High": np.random.randn(50).cumsum() + 632,
            "Low": np.random.randn(50).cumsum() + 628,
            "Close": np.random.randn(50).cumsum() + 630,
            "Volume": np.random.randint(1000000, 5000000, 50),
        },
        index=dates,
    )

    sample_analysis = {
        "current_price": 630.50,
        "trend_direction": "BULLISH",
        "breakout_strength": 7.2,
        "candle_body_pct": 0.15,
        "volume_ratio": 1.8,
        "resistance_levels": [632.0, 635.0, 638.0],
        "support_levels": [628.0, 625.0, 622.0],
        "nearest_resistance": 632.0,
        "nearest_support": 628.0,
    }

    print("=== TESTING ENHANCED SLACK CHARTS ===")
    chart_path = chart_gen.create_breakout_chart(sample_data, sample_analysis, "SPY")
    print(f"Generated chart: {chart_path}")

    print("Enhanced Slack integration ready for mobile trading alerts!")
