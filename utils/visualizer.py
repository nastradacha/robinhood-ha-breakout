"""
Visualization module for robinhood-ha-breakout trading system.
Creates easy-to-understand charts and dashboards for new traders.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import seaborn as sns
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
from typing import Dict, List, Optional, Tuple
import logging
from pathlib import Path

# Set style for better-looking plots
plt.style.use('seaborn-v0_8')
sns.set_palette("husl")


class TradingVisualizer:
    """Creates comprehensive visualizations for trading data and results."""
    
    def __init__(self, output_dir: str = "charts"):
        """Initialize visualizer with output directory."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.logger = logging.getLogger(__name__)
        
        # Color scheme for consistency
        self.colors = {
            'bullish': '#26a69a',      # Teal green
            'bearish': '#ef5350',      # Red
            'neutral': '#ffa726',      # Orange
            'profit': '#4caf50',       # Green
            'loss': '#f44336',         # Red
        }
    
    def create_beginner_summary(self, results, save_path: str = None) -> str:
        """Create a simple, beginner-friendly summary chart."""
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 10))
        
        # 1. Simple Profit/Loss
        total_pnl = results.total_pnl
        color = self.colors['profit'] if total_pnl > 0 else self.colors['loss']
        
        ax1.bar(['Your Result'], [total_pnl], color=color, alpha=0.8)
        ax1.axhline(y=0, color='black', linestyle='-', linewidth=2)
        ax1.set_title('Total Profit/Loss', fontsize=14, fontweight='bold')
        ax1.set_ylabel('Dollars ($)')
        ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
        
        # Add value annotation
        ax1.text(0, total_pnl + (abs(total_pnl) * 0.1 if total_pnl != 0 else 100), 
                f'${total_pnl:,.2f}', ha='center', 
                va='bottom' if total_pnl > 0 else 'top', 
                fontsize=16, fontweight='bold')
        
        # 2. Win Rate Gauge
        win_rate = results.win_rate
        ax2.pie([win_rate, 100-win_rate], 
               labels=[f'Wins\n{win_rate:.1f}%', f'Losses\n{100-win_rate:.1f}%'],
               colors=[self.colors['profit'], self.colors['loss']], 
               autopct='', startangle=90, 
               textprops={'fontsize': 12, 'fontweight': 'bold'})
        ax2.set_title('Win Rate', fontsize=14, fontweight='bold')
        
        # 3. Trade Count
        ax3.bar(['Total Trades'], [results.total_trades], 
               color=self.colors['neutral'], alpha=0.8)
        ax3.set_title('Number of Trades', fontsize=14, fontweight='bold')
        ax3.set_ylabel('Count')
        
        # Add value annotation
        ax3.text(0, results.total_trades + max(1, results.total_trades * 0.05), 
                str(results.total_trades), ha='center', va='bottom', 
                fontsize=16, fontweight='bold')
        
        # 4. Risk Level
        max_dd = results.max_drawdown
        if max_dd < 10:
            risk_level = "LOW RISK"
            risk_color = self.colors['profit']
        elif max_dd < 25:
            risk_level = "MEDIUM RISK"
            risk_color = self.colors['neutral']
        else:
            risk_level = "HIGH RISK"
            risk_color = self.colors['loss']
        
        ax4.text(0.5, 0.6, risk_level, ha='center', va='center', 
                transform=ax4.transAxes, fontsize=20, fontweight='bold', 
                color=risk_color)
        ax4.text(0.5, 0.4, f'Max Drawdown: {max_dd:.1f}%', ha='center', va='center', 
                transform=ax4.transAxes, fontsize=14)
        ax4.set_title('Risk Level', fontsize=14, fontweight='bold')
        ax4.axis('off')
        
        # Add border around risk level
        rect = Rectangle((0.1, 0.2), 0.8, 0.6, linewidth=3, edgecolor=risk_color, 
                        facecolor='none', transform=ax4.transAxes)
        ax4.add_patch(rect)
        
        plt.suptitle('Your Trading Results - Easy Summary', 
                    fontsize=18, fontweight='bold', y=0.98)
        plt.tight_layout()
        
        if save_path is None:
            save_path = self.output_dir / f"beginner_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        self.logger.info(f"Beginner summary saved to {save_path}")
        return str(save_path)
    
    def create_equity_curve(self, results, save_path: str = None) -> str:
        """Create simple equity curve chart."""
        fig, ax = plt.subplots(figsize=(12, 6))
        
        dates = pd.date_range(start=datetime.now() - timedelta(days=len(results.equity_curve)), 
                             periods=len(results.equity_curve), freq='D')
        
        ax.plot(dates, results.equity_curve, linewidth=3, color=self.colors['bullish'])
        ax.fill_between(dates, results.equity_curve, alpha=0.3, color=self.colors['bullish'])
        
        # Highlight max and min
        max_idx = np.argmax(results.equity_curve)
        min_idx = np.argmin(results.equity_curve)
        
        ax.scatter(dates[max_idx], results.equity_curve[max_idx], 
                  color='green', s=150, zorder=5, marker='^')
        ax.scatter(dates[min_idx], results.equity_curve[min_idx], 
                  color='red', s=150, zorder=5, marker='v')
        
        ax.set_title('📈 Your Portfolio Value Over Time', fontsize=16, fontweight='bold')
        ax.set_ylabel('Portfolio Value ($)')
        ax.grid(True, alpha=0.3)
        
        # Format y-axis as currency
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
        
        # Format x-axis
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
        
        plt.tight_layout()
        
        if save_path is None:
            save_path = self.output_dir / f"equity_curve_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        self.logger.info(f"Equity curve saved to {save_path}")
        return str(save_path)
    
    def create_trade_analysis(self, results, save_path: str = None) -> str:
        """Create trade analysis chart."""
        if not results.trades:
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.text(0.5, 0.5, 'No trades to analyze yet!\nRun a backtest to see results.', 
                   ha='center', va='center', transform=ax.transAxes, 
                   fontsize=16, bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8))
            ax.set_title('Trade Analysis')
            ax.axis('off')
            
            if save_path is None:
                save_path = self.output_dir / f"trade_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            plt.close()
            return str(save_path)
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
        
        # 1. P&L Distribution
        pnls = [trade.pnl for trade in results.trades]
        
        colors = [self.colors['profit'] if pnl > 0 else self.colors['loss'] for pnl in pnls]
        ax1.bar(range(len(pnls)), pnls, color=colors, alpha=0.8)
        ax1.axhline(y=0, color='black', linestyle='-', linewidth=2)
        ax1.set_title('💰 Individual Trade Results', fontweight='bold')
        ax1.set_xlabel('Trade Number')
        ax1.set_ylabel('Profit/Loss ($)')
        ax1.grid(True, alpha=0.3)
        
        # 2. Win/Loss Pie Chart
        wins = sum(1 for trade in results.trades if trade.win)
        losses = len(results.trades) - wins
        
        if wins > 0 or losses > 0:
            ax2.pie([wins, losses], 
                   labels=[f'Winning Trades\n({wins})', f'Losing Trades\n({losses})'],
                   colors=[self.colors['profit'], self.colors['loss']], 
                   autopct='%1.1f%%', startangle=90,
                   textprops={'fontsize': 12, 'fontweight': 'bold'})
        ax2.set_title('🎯 Win/Loss Breakdown', fontweight='bold')
        
        plt.tight_layout()
        
        if save_path is None:
            save_path = self.output_dir / f"trade_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        self.logger.info(f"Trade analysis saved to {save_path}")
        return str(save_path)


def create_all_visualizations(results, market_data: pd.DataFrame = None, 
                            ha_data: pd.DataFrame = None, analysis: Dict = None) -> Dict[str, str]:
    """Create all visualization types and return file paths."""
    visualizer = TradingVisualizer()
    
    charts = {}
    
    try:
        # Create beginner-friendly summary (most important)
        charts['beginner_summary'] = visualizer.create_beginner_summary(results)
        
        # Create equity curve
        charts['equity_curve'] = visualizer.create_equity_curve(results)
        
        # Create trade analysis
        charts['trade_analysis'] = visualizer.create_trade_analysis(results)
        
        logging.info(f"Created {len(charts)} visualization charts")
        
    except Exception as e:
        logging.error(f"Error creating visualizations: {e}")
    
    return charts


if __name__ == "__main__":
    print("Visualization module ready!")
    print("Use create_all_visualizations() to generate charts for your backtest results.")
