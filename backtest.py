#!/usr/bin/env python3
"""
Robinhood HA Breakout - Backtesting Script

Run historical backtests to validate the Heikin-Ashi breakout strategy.
"""

import argparse
import logging
import yaml
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

from utils.backtest import StrategyBacktester, run_quick_backtest
from utils.slack import SlackNotifier
from utils.visualizer import create_all_visualizations


def setup_logging(log_level: str = "INFO"):
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('logs/backtest.log')
        ]
    )


def load_config(config_file: str) -> dict:
    """Load configuration from YAML file."""
    config_path = Path(config_file)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_file}")
    
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def main():
    """Main backtesting script."""
    parser = argparse.ArgumentParser(description='Robinhood HA Breakout Backtester')
    parser.add_argument('--config', default='config.yaml',
                       help='Configuration file path')
    parser.add_argument('--symbol', default='SPY',
                       help='Symbol to backtest (default: SPY)')
    parser.add_argument('--start-date', 
                       help='Start date (YYYY-MM-DD). Default: 30 days ago')
    parser.add_argument('--end-date',
                       help='End date (YYYY-MM-DD). Default: today')
    parser.add_argument('--capital', type=float, default=10000,
                       help='Initial capital (default: $10,000)')
    parser.add_argument('--days', type=int, default=30,
                       help='Number of days to backtest (if no start-date specified)')
    parser.add_argument('--use-llm', action='store_true',
                       help='Use LLM for trade decisions (slower but more accurate)')
    parser.add_argument('--output', 
                       help='Output file for detailed report')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Logging level')
    parser.add_argument('--slack-notify', action='store_true',
                       help='Send results to Slack')
    parser.add_argument('--create-charts', action='store_true',
                       help='Generate visual charts and dashboards')
    parser.add_argument('--charts-only', action='store_true',
                       help='Only create charts (skip backtest if results exist)')
    
    args = parser.parse_args()
    
    # Setup logging
    Path('logs').mkdir(exist_ok=True)
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)
    
    # Load environment variables
    load_dotenv()
    
    logger.info("Starting Robinhood HA Breakout Backtester")
    
    try:
        # Load configuration
        config = load_config(args.config)
        
        # Initialize Slack notifier if requested
        slack_notifier = None
        if args.slack_notify:
            slack_notifier = SlackNotifier()
            slack_notifier.send_startup_notification(dry_run=True)  # Backtest is always "dry run"
        
        # Determine date range
        if args.start_date and args.end_date:
            start_date = args.start_date
            end_date = args.end_date
        else:
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
        
        logger.info(f"Backtesting {args.symbol} from {start_date} to {end_date}")
        logger.info(f"Initial capital: ${args.capital:,.2f}")
        logger.info(f"Using {'LLM' if args.use_llm else 'rule-based'} decision making")
        
        # Initialize backtester
        backtester = StrategyBacktester(config, use_llm=args.use_llm)
        
        # Run backtest
        logger.info("Running backtest...")
        results = backtester.run_backtest(
            symbol=args.symbol,
            start_date=start_date,
            end_date=end_date,
            initial_capital=args.capital
        )
        
        # Generate report
        output_file = args.output or f"backtest_report_{args.symbol}_{start_date}_{end_date}.txt"
        report = backtester.generate_report(results, output_file)
        
        # Display results
        print("\n" + report)
        
        # Generate visual charts if requested
        if args.create_charts or args.charts_only:
            logger.info("Generating visual charts...")
            try:
                charts = create_all_visualizations(results)
                
                print("\n" + "="*60)
                print("VISUAL CHARTS CREATED:")
                print("="*60)
                for chart_type, file_path in charts.items():
                    print(f"Chart - {chart_type.replace('_', ' ').title()}: {file_path}")
                print("\nOpen these files to see your trading results visually!")
                print("The 'beginner_summary' chart is perfect for new traders.")
                
                if slack_notifier:
                    # Send chart notification to Slack
                    chart_summary = "\n".join([f"• {name.replace('_', ' ').title()}" for name in charts.keys()])
                    payload = {
                        "attachments": [{
                            "color": "#36a64f",
                            "title": "Visual Charts Generated",
                            "text": f"Created {len(charts)} charts:\n{chart_summary}",
                            "footer": "Chart Generation Complete",
                            "ts": int(datetime.now().timestamp())
                        }]
                    }
                    slack_notifier._send_message(payload)
                
            except Exception as e:
                logger.error(f"Failed to generate charts: {e}")
                print(f"\nChart generation failed: {e}")
        
        # Send to Slack if requested
        if slack_notifier:
            # Send backtest summary to Slack
            summary_text = (
                f"*Backtest Results for {args.symbol}*\n"
                f"Period: {start_date} to {end_date}\n"
                f"Total Trades: {results.total_trades}\n"
                f"Win Rate: {results.win_rate:.1f}%\n"
                f"Total P&L: ${results.total_pnl:,.2f}\n"
                f"Max Drawdown: {results.max_drawdown:.1f}%\n"
                f"Sharpe Ratio: {results.sharpe_ratio:.2f}"
            )
            
            # Determine color based on performance
            if results.total_pnl > 0 and results.win_rate > 50:
                color = "#36a64f"  # Green for good performance
            elif results.total_pnl > 0:
                color = "#ffc107"  # Yellow for mixed performance
            else:
                color = "#d50000"  # Red for poor performance
            
            payload = {
                "attachments": [{
                    "color": color,
                    "title": f"📊 Backtest Complete - {args.symbol}",
                    "text": summary_text,
                    "fields": [
                        {
                            "title": "Profit Factor",
                            "value": f"{results.profit_factor:.2f}",
                            "short": True
                        },
                        {
                            "title": "Avg Win/Loss",
                            "value": f"${results.avg_win:.2f} / ${results.avg_loss:.2f}",
                            "short": True
                        }
                    ],
                    "footer": "Historical Backtest",
                    "ts": int(datetime.now().timestamp())
                }]
            }
            
            slack_notifier._send_message(payload)
        
        # Summary statistics
        logger.info("Backtest completed successfully!")
        logger.info(f"Total trades: {results.total_trades}")
        logger.info(f"Win rate: {results.win_rate:.1f}%")
        logger.info(f"Total P&L: ${results.total_pnl:,.2f}")
        logger.info(f"Max drawdown: {results.max_drawdown:.1f}%")
        logger.info(f"Sharpe ratio: {results.sharpe_ratio:.2f}")
        
        if args.output:
            logger.info(f"Detailed report saved to: {args.output}")
        
    except KeyboardInterrupt:
        logger.info("Backtest interrupted by user")
    except Exception as e:
        logger.error(f"Backtest failed: {e}", exc_info=True)
        if slack_notifier:
            slack_notifier.send_error_alert("Backtest Error", str(e))
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
