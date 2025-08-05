#!/usr/bin/env python3
"""
Performance Analytics Dashboard for Robinhood HA Breakout Trading System

Provides comprehensive trading statistics, performance metrics, and strategy evaluation
to help optimize your conservative ATM options trading approach.

Usage:
    python analytics_dashboard.py --mode cli
    python analytics_dashboard.py --export html
    python analytics_dashboard.py --slack-summary
"""

import os
import sys
import json
import csv
import argparse
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TradingAnalytics:
    """Comprehensive trading performance analytics and reporting system."""
    
    def __init__(self, trade_log_path: str = "logs/trade_log.csv", 
                 bankroll_path: str = "bankroll.json"):
        """Initialize analytics with data paths."""
        self.trade_log_path = trade_log_path
        self.bankroll_path = bankroll_path
        self.trades_df = None
        self.bankroll_data = None
        self.metrics = {}
        self.load_data()
    
    def load_data(self) -> bool:
        """Load trade log and bankroll data with robust error handling."""
        # Initialize with empty DataFrame to ensure trades_df is never None
        self.trades_df = pd.DataFrame()
        self.bankroll_data = {}
        
        try:
            # Load trade log with robust CSV parsing
            if os.path.exists(self.trade_log_path):
                try:
                    # Try normal CSV parsing first
                    self.trades_df = pd.read_csv(self.trade_log_path)
                    logger.info(f"Loaded {len(self.trades_df)} trades from {self.trade_log_path}")
                except pd.errors.ParserError as e:
                    logger.warning(f"CSV parsing error: {e}. Attempting to fix...")
                    # Try with error handling for inconsistent field counts
                    try:
                        self.trades_df = pd.read_csv(self.trade_log_path, on_bad_lines='skip')
                        logger.info(f"Loaded {len(self.trades_df)} trades (with some lines skipped) from {self.trade_log_path}")
                    except Exception as e2:
                        logger.error(f"Failed to parse CSV even with error handling: {e2}")
                        # Try reading line by line to identify problematic lines
                        self._repair_csv_file()
                
                # Convert timestamp if data was loaded successfully
                if not self.trades_df.empty and 'timestamp' in self.trades_df.columns:
                    try:
                        # Try mixed format parsing to handle both ISO8601 and standard datetime formats
                        self.trades_df['timestamp'] = pd.to_datetime(self.trades_df['timestamp'], format='mixed')
                        logger.info(f"Successfully converted {len(self.trades_df)} timestamps")
                    except Exception as e:
                        logger.warning(f"Error converting timestamps with mixed format: {e}")
                        # Fallback: try infer_datetime_format
                        try:
                            self.trades_df['timestamp'] = pd.to_datetime(self.trades_df['timestamp'], infer_datetime_format=True)
                            logger.info("Successfully converted timestamps with inferred format")
                        except Exception as e2:
                            logger.error(f"Failed to convert timestamps: {e2}")
                            # Keep timestamps as strings if conversion fails
                            logger.warning("Keeping timestamps as strings - some analytics may be limited")
            else:
                logger.warning(f"Trade log not found: {self.trade_log_path}")
            
            # Load bankroll data
            if os.path.exists(self.bankroll_path):
                try:
                    with open(self.bankroll_path, 'r') as f:
                        self.bankroll_data = json.load(f)
                    logger.info(f"Loaded bankroll data from {self.bankroll_path}")
                except Exception as e:
                    logger.error(f"Error loading bankroll data: {e}")
                    self.bankroll_data = {}
            else:
                logger.warning(f"Bankroll file not found: {self.bankroll_path}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            # Ensure trades_df is always a DataFrame, never None
            if self.trades_df is None:
                self.trades_df = pd.DataFrame()
            if self.bankroll_data is None:
                self.bankroll_data = {}
            return False
    
    def _repair_csv_file(self):
        """Attempt to repair corrupted CSV file by reading line by line."""
        try:
            logger.info("Attempting to repair CSV file by reading line by line...")
            
            # Read the file line by line
            with open(self.trade_log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            if not lines:
                logger.warning("CSV file is empty")
                return
            
            # Get header and expected field count
            header = lines[0].strip()
            expected_fields = len(header.split(','))
            logger.info(f"Expected {expected_fields} fields based on header: {header}")
            
            # Process each line and fix field count issues
            valid_lines = [header]
            for i, line in enumerate(lines[1:], 2):  # Start from line 2
                line = line.strip()
                if not line:  # Skip empty lines
                    continue
                
                fields = line.split(',')
                if len(fields) == expected_fields:
                    valid_lines.append(line)
                else:
                    logger.warning(f"Line {i} has {len(fields)} fields, expected {expected_fields}. Skipping: {line[:100]}...")
            
            # Create a temporary repaired file
            repaired_path = self.trade_log_path + '.repaired'
            with open(repaired_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(valid_lines))
            
            # Try to load the repaired file
            self.trades_df = pd.read_csv(repaired_path)
            logger.info(f"Successfully loaded {len(self.trades_df)} trades from repaired CSV")
            
            # Optionally, replace the original file with the repaired one
            # os.replace(repaired_path, self.trade_log_path)
            
        except Exception as e:
            logger.error(f"Error repairing CSV file: {e}")
            self.trades_df = pd.DataFrame()
    
    def calculate_performance_metrics(self) -> Dict:
        """Calculate comprehensive performance metrics."""
        if self.trades_df.empty:
            logger.warning("No trade data available for analysis")
            return {}
        
        metrics = {}
        
        # Basic trade statistics
        total_trades = len(self.trades_df)
        winning_trades = len(self.trades_df[self.trades_df['pnl'] > 0])
        losing_trades = len(self.trades_df[self.trades_df['pnl'] < 0])
        
        metrics['total_trades'] = total_trades
        metrics['winning_trades'] = winning_trades
        metrics['losing_trades'] = losing_trades
        metrics['win_rate'] = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # P&L analysis
        total_pnl = self.trades_df['pnl'].sum()
        avg_pnl = self.trades_df['pnl'].mean()
        avg_winning_trade = self.trades_df[self.trades_df['pnl'] > 0]['pnl'].mean() if winning_trades > 0 else 0
        avg_losing_trade = self.trades_df[self.trades_df['pnl'] < 0]['pnl'].mean() if losing_trades > 0 else 0
        
        metrics['total_pnl'] = total_pnl
        metrics['avg_pnl_per_trade'] = avg_pnl
        metrics['avg_winning_trade'] = avg_winning_trade
        metrics['avg_losing_trade'] = avg_losing_trade
        
        # Risk-reward ratio
        if avg_losing_trade != 0:
            metrics['risk_reward_ratio'] = abs(avg_winning_trade / avg_losing_trade)
        else:
            metrics['risk_reward_ratio'] = float('inf')
        
        # Drawdown analysis
        cumulative_pnl = self.trades_df['pnl'].cumsum()
        running_max = cumulative_pnl.expanding().max()
        drawdown = cumulative_pnl - running_max
        max_drawdown = drawdown.min()
        
        metrics['max_drawdown'] = max_drawdown
        metrics['max_drawdown_pct'] = (max_drawdown / running_max.max() * 100) if running_max.max() != 0 else 0
        
        # Sharpe ratio (annualized)
        if len(self.trades_df) > 1:
            daily_returns = self.trades_df.groupby(self.trades_df['timestamp'].dt.date)['pnl'].sum()
            if daily_returns.std() != 0:
                sharpe_ratio = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
                metrics['sharpe_ratio'] = sharpe_ratio
            else:
                metrics['sharpe_ratio'] = 0
        else:
            metrics['sharpe_ratio'] = 0
        
        # Option type analysis
        if 'option_type' in self.trades_df.columns:
            call_trades = self.trades_df[self.trades_df['option_type'] == 'CALL']
            put_trades = self.trades_df[self.trades_df['option_type'] == 'PUT']
            
            metrics['call_trades'] = len(call_trades)
            metrics['put_trades'] = len(put_trades)
            metrics['call_win_rate'] = (len(call_trades[call_trades['pnl'] > 0]) / len(call_trades) * 100) if len(call_trades) > 0 else 0
            metrics['put_win_rate'] = (len(put_trades[put_trades['pnl'] > 0]) / len(put_trades) * 100) if len(put_trades) > 0 else 0
        
        # Bankroll analysis
        if self.bankroll_data:
            current_bankroll = self.bankroll_data.get('current_bankroll', 0)
            starting_bankroll = self.bankroll_data.get('starting_bankroll', current_bankroll)
            
            metrics['current_bankroll'] = current_bankroll
            metrics['starting_bankroll'] = starting_bankroll
            metrics['total_return'] = current_bankroll - starting_bankroll
            metrics['total_return_pct'] = ((current_bankroll / starting_bankroll - 1) * 100) if starting_bankroll > 0 else 0
        
        self.metrics = metrics
        return metrics
    
    def generate_performance_report(self, format: str = 'cli') -> str:
        """Generate comprehensive performance report."""
        metrics = self.calculate_performance_metrics()
        
        if not metrics:
            return "No trading data available for analysis."
        
        report = []
        report.append("=" * 80)
        report.append("ROBINHOOD HA BREAKOUT - PERFORMANCE ANALYTICS DASHBOARD")
        report.append("=" * 80)
        report.append("")
        
        # Trading Summary
        report.append("TRADING SUMMARY")
        report.append("-" * 40)
        report.append(f"Total Trades:           {metrics.get('total_trades', 0):,}")
        report.append(f"Winning Trades:         {metrics.get('winning_trades', 0):,} ({metrics.get('win_rate', 0):.1f}%)")
        report.append(f"Losing Trades:          {metrics.get('losing_trades', 0):,}")
        report.append("")
        
        # P&L Analysis
        report.append("PROFIT & LOSS ANALYSIS")
        report.append("-" * 40)
        report.append(f"Total P&L:              ${metrics.get('total_pnl', 0):,.2f}")
        report.append(f"Average P&L per Trade:  ${metrics.get('avg_pnl_per_trade', 0):,.2f}")
        report.append(f"Average Winning Trade:  ${metrics.get('avg_winning_trade', 0):,.2f}")
        report.append(f"Average Losing Trade:   ${metrics.get('avg_losing_trade', 0):,.2f}")
        report.append(f"Risk-Reward Ratio:      {metrics.get('risk_reward_ratio', 0):.2f}:1")
        report.append("")
        
        # Risk Metrics
        report.append("RISK METRICS")
        report.append("-" * 40)
        report.append(f"Maximum Drawdown:       ${metrics.get('max_drawdown', 0):,.2f} ({metrics.get('max_drawdown_pct', 0):.1f}%)")
        report.append(f"Sharpe Ratio:           {metrics.get('sharpe_ratio', 0):.2f}")
        report.append("")
        
        # Strategy Performance
        if metrics.get('call_trades', 0) > 0 or metrics.get('put_trades', 0) > 0:
            report.append("STRATEGY PERFORMANCE")
            report.append("-" * 40)
            report.append(f"CALL Trades:            {metrics.get('call_trades', 0):,} (Win Rate: {metrics.get('call_win_rate', 0):.1f}%)")
            report.append(f"PUT Trades:             {metrics.get('put_trades', 0):,} (Win Rate: {metrics.get('put_win_rate', 0):.1f}%)")
            report.append("")
        
        # Bankroll Status
        if metrics.get('current_bankroll'):
            report.append("BANKROLL STATUS")
            report.append("-" * 40)
            report.append(f"Starting Bankroll:      ${metrics.get('starting_bankroll', 0):,.2f}")
            report.append(f"Current Bankroll:       ${metrics.get('current_bankroll', 0):,.2f}")
            report.append(f"Total Return:           ${metrics.get('total_return', 0):,.2f} ({metrics.get('total_return_pct', 0):+.1f}%)")
            report.append("")
        
        # Performance Grade
        grade = self._calculate_performance_grade(metrics)
        report.append("PERFORMANCE GRADE")
        report.append("-" * 40)
        report.append(f"Overall Grade:          {grade['letter']} ({grade['score']:.1f}/100)")
        report.append(f"Assessment:             {grade['assessment']}")
        report.append("")
        
        # Recommendations
        recommendations = self._generate_recommendations(metrics)
        if recommendations:
            report.append("RECOMMENDATIONS")
            report.append("-" * 40)
            for rec in recommendations:
                report.append(f"• {rec}")
            report.append("")
        
        report.append("=" * 80)
        report.append(f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("=" * 80)
        
        return "\n".join(report)
    
    def _calculate_performance_grade(self, metrics: Dict) -> Dict:
        """Calculate overall performance grade."""
        score = 0
        
        # Win rate (30 points max)
        win_rate = metrics.get('win_rate', 0)
        if win_rate >= 60:
            score += 30
        elif win_rate >= 50:
            score += 25
        elif win_rate >= 40:
            score += 20
        else:
            score += 10
        
        # Risk-reward ratio (25 points max)
        rr_ratio = metrics.get('risk_reward_ratio', 0)
        if rr_ratio >= 2.0:
            score += 25
        elif rr_ratio >= 1.5:
            score += 20
        elif rr_ratio >= 1.0:
            score += 15
        else:
            score += 5
        
        # Sharpe ratio (20 points max)
        sharpe = metrics.get('sharpe_ratio', 0)
        if sharpe >= 1.5:
            score += 20
        elif sharpe >= 1.0:
            score += 15
        elif sharpe >= 0.5:
            score += 10
        else:
            score += 5
        
        # Drawdown control (15 points max)
        max_dd_pct = abs(metrics.get('max_drawdown_pct', 0))
        if max_dd_pct <= 5:
            score += 15
        elif max_dd_pct <= 10:
            score += 12
        elif max_dd_pct <= 20:
            score += 8
        else:
            score += 3
        
        # Consistency (10 points max)
        total_trades = metrics.get('total_trades', 0)
        if total_trades >= 50:
            score += 10
        elif total_trades >= 20:
            score += 7
        elif total_trades >= 10:
            score += 5
        else:
            score += 2
        
        # Determine letter grade
        if score >= 90:
            letter = "A+"
            assessment = "Outstanding performance"
        elif score >= 85:
            letter = "A"
            assessment = "Excellent performance"
        elif score >= 80:
            letter = "A-"
            assessment = "Very good performance"
        elif score >= 75:
            letter = "B+"
            assessment = "Good performance"
        elif score >= 70:
            letter = "B"
            assessment = "Above average performance"
        elif score >= 65:
            letter = "B-"
            assessment = "Average performance"
        elif score >= 60:
            letter = "C+"
            assessment = "Below average performance"
        elif score >= 55:
            letter = "C"
            assessment = "Poor performance"
        else:
            letter = "D"
            assessment = "Very poor performance"
        
        return {
            'score': score,
            'letter': letter,
            'assessment': assessment
        }
    
    def _generate_recommendations(self, metrics: Dict) -> List[str]:
        """Generate actionable recommendations based on performance."""
        recommendations = []
        
        win_rate = metrics.get('win_rate', 0)
        rr_ratio = metrics.get('risk_reward_ratio', 0)
        max_dd_pct = abs(metrics.get('max_drawdown_pct', 0))
        
        if win_rate < 50:
            recommendations.append("Consider tightening entry criteria to improve win rate")
        
        if rr_ratio < 1.5:
            recommendations.append("Focus on setups with better risk-reward ratios")
        
        if max_dd_pct > 15:
            recommendations.append("Implement stricter position sizing rules")
        
        return recommendations
    
    def create_performance_charts(self, output_dir: str = "charts") -> List[str]:
        """Create visual performance charts."""
        if self.trades_df.empty:
            logger.warning("No trade data available for charts")
            return []
        
        Path(output_dir).mkdir(exist_ok=True)
        chart_files = []
        
        # Cumulative P&L Chart
        fig, ax = plt.subplots(figsize=(12, 6))
        cumulative_pnl = self.trades_df['pnl'].cumsum()
        ax.plot(range(len(cumulative_pnl)), cumulative_pnl, linewidth=2, color='#2E8B57')
        ax.fill_between(range(len(cumulative_pnl)), cumulative_pnl, alpha=0.3, color='#2E8B57')
        ax.set_title('Cumulative P&L Over Time', fontsize=16, fontweight='bold')
        ax.set_xlabel('Trade Number')
        ax.set_ylabel('Cumulative P&L ($)')
        ax.grid(True, alpha=0.3)
        
        chart_path = os.path.join(output_dir, 'cumulative_pnl.png')
        plt.tight_layout()
        plt.savefig(chart_path, dpi=300, bbox_inches='tight')
        plt.close()
        chart_files.append(chart_path)
        
        logger.info(f"Generated performance charts in {output_dir}")
        return chart_files
    
    def export_report(self, format: str = 'html', filename: str = None) -> str:
        """Export performance report to file."""
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"performance_report_{timestamp}.{format}"
        
        if format == 'html':
            report_content = self._generate_html_report()
        elif format == 'csv':
            report_content = self._generate_csv_report()
        else:
            report_content = self.generate_performance_report('cli')
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        logger.info(f"Performance report exported to {filename}")
        return filename
    
    def _generate_html_report(self) -> str:
        """Generate HTML-formatted performance report."""
        metrics = self.calculate_performance_metrics()
        if not metrics:
            return "<html><body><h1>No trading data available</h1></body></html>"
        
        grade = self._calculate_performance_grade(metrics)
        recommendations = self._generate_recommendations(metrics)
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Trading Performance Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        .header {{ background-color: #2E8B57; color: white; padding: 20px; text-align: center; }}
        .section {{ margin: 20px 0; padding: 15px; border-left: 4px solid #2E8B57; }}
        .metric {{ display: flex; justify-content: space-between; margin: 5px 0; }}
        .grade {{ font-size: 24px; font-weight: bold; color: #2E8B57; }}
        .recommendations {{ background-color: #f9f9f9; padding: 15px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Trading Performance Report</h1>
        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    
    <div class="section">
        <h2>Performance Grade</h2>
        <div class="grade">{grade['letter']} ({grade['score']:.1f}/100)</div>
        <p>{grade['assessment']}</p>
    </div>
    
    <div class="section">
        <h2>Trading Summary</h2>
        <div class="metric"><span>Total Trades:</span><span>{metrics.get('total_trades', 0):,}</span></div>
        <div class="metric"><span>Win Rate:</span><span>{metrics.get('win_rate', 0):.1f}%</span></div>
        <div class="metric"><span>Total P&L:</span><span>${metrics.get('total_pnl', 0):,.2f}</span></div>
    </div>
    
    <div class="section">
        <h2>Risk Metrics</h2>
        <div class="metric"><span>Risk-Reward Ratio:</span><span>{metrics.get('risk_reward_ratio', 0):.2f}:1</span></div>
        <div class="metric"><span>Max Drawdown:</span><span>{metrics.get('max_drawdown_pct', 0):.1f}%</span></div>
        <div class="metric"><span>Sharpe Ratio:</span><span>{metrics.get('sharpe_ratio', 0):.2f}</span></div>
    </div>
    
    <div class="section recommendations">
        <h2>Recommendations</h2>
        <ul>
"""
        
        for rec in recommendations:
            html += f"            <li>{rec}</li>\n"
        
        html += """
        </ul>
    </div>
</body>
</html>
        """
        
        return html
    
    def _generate_csv_report(self) -> str:
        """Generate CSV-formatted performance report."""
        metrics = self.calculate_performance_metrics()
        if not metrics:
            return "Metric,Value\nNo Data,Available"
        
        csv_lines = ["Metric,Value"]
        csv_lines.append(f"Total Trades,{metrics.get('total_trades', 0)}")
        csv_lines.append(f"Win Rate,{metrics.get('win_rate', 0):.1f}%")
        csv_lines.append(f"Total P&L,${metrics.get('total_pnl', 0):.2f}")
        csv_lines.append(f"Average P&L per Trade,${metrics.get('avg_pnl_per_trade', 0):.2f}")
        csv_lines.append(f"Risk-Reward Ratio,{metrics.get('risk_reward_ratio', 0):.2f}")
        csv_lines.append(f"Max Drawdown,{metrics.get('max_drawdown_pct', 0):.1f}%")
        csv_lines.append(f"Sharpe Ratio,{metrics.get('sharpe_ratio', 0):.2f}")
        
        if metrics.get('current_bankroll'):
            csv_lines.append(f"Starting Bankroll,${metrics.get('starting_bankroll', 0):.2f}")
            csv_lines.append(f"Current Bankroll,${metrics.get('current_bankroll', 0):.2f}")
            csv_lines.append(f"Total Return,{metrics.get('total_return_pct', 0):.1f}%")
        
        return "\n".join(csv_lines)
    
    def send_slack_summary(self) -> bool:
        """Send performance summary to Slack."""
        try:
            from utils.enhanced_slack import EnhancedSlackIntegration
            
            slack = EnhancedSlackIntegration()
            if not slack.enabled:
                logger.warning("Slack not configured - skipping summary")
                return False
            
            metrics = self.calculate_performance_metrics()
            if not metrics:
                logger.warning("No metrics available for Slack summary")
                return False
            
            grade = self._calculate_performance_grade(metrics)
            
            summary = f"""**TRADING PERFORMANCE SUMMARY**

**Overall Grade:** {grade['letter']} ({grade['score']:.1f}/100)
**Assessment:** {grade['assessment']}

**Key Metrics:**
• Total Trades: {metrics.get('total_trades', 0):,}
• Win Rate: {metrics.get('win_rate', 0):.1f}%
• Total P&L: ${metrics.get('total_pnl', 0):,.2f}
• Risk-Reward: {metrics.get('risk_reward_ratio', 0):.2f}:1
• Max Drawdown: {metrics.get('max_drawdown_pct', 0):.1f}%

*Conservative ATM options strategy performance*"""
            
            slack.send_heartbeat_with_context(summary, metrics)
            logger.info("Performance summary sent to Slack")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send Slack summary: {e}")
            return False

def main():
    """Main CLI interface for analytics dashboard."""
    parser = argparse.ArgumentParser(description='Trading Performance Analytics Dashboard')
    parser.add_argument('--mode', choices=['cli', 'web'], default='cli',
                       help='Display mode (default: cli)')
    parser.add_argument('--export', choices=['html', 'csv', 'txt'],
                       help='Export report format')
    parser.add_argument('--slack-summary', action='store_true',
                       help='Send performance summary to Slack')
    parser.add_argument('--charts', action='store_true',
                       help='Generate performance charts')
    
    args = parser.parse_args()
    
    # Initialize analytics
    analytics = TradingAnalytics()
    
    # Generate and display report
    if args.mode == 'cli':
        report = analytics.generate_performance_report('cli')
        print(report)
    
    # Export report
    if args.export:
        filename = analytics.export_report(args.export)
        print(f"Report exported to: {filename}")
    
    # Generate charts
    if args.charts:
        chart_files = analytics.create_performance_charts()
        print(f"Generated {len(chart_files)} performance charts")
    
    # Send Slack summary
    if args.slack_summary:
        success = analytics.send_slack_summary()
        if success:
            print("Performance summary sent to Slack")
        else:
            print("Failed to send Slack summary")

if __name__ == "__main__":
    main()
