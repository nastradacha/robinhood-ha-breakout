"""
Historical backtesting module for robinhood-ha-breakout strategy.
Tests Heikin-Ashi breakout patterns against historical SPY data.
"""

import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import yfinance as yf
from dataclasses import dataclass

from .data import calculate_heikin_ashi, analyze_breakout_pattern, prepare_llm_payload
from .llm import LLMClient


@dataclass
class BacktestTrade:
    """Represents a single backtested trade."""

    entry_date: datetime
    exit_date: datetime
    direction: str  # CALL or PUT
    entry_price: float
    exit_price: float
    strike_price: float
    premium_paid: float
    quantity: int
    pnl: float
    confidence: float
    reason: str
    win: bool


@dataclass
class BacktestResults:
    """Contains comprehensive backtest results."""

    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    max_drawdown: float
    sharpe_ratio: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    trades: List[BacktestTrade]
    equity_curve: List[float]
    daily_returns: List[float]


class StrategyBacktester:
    """Backtests the Heikin-Ashi breakout strategy on historical data."""

    def __init__(self, config: Dict, use_llm: bool = True):
        """Initialize backtester with configuration."""
        self.config = config
        self.use_llm = use_llm
        self.logger = logging.getLogger(__name__)

        # Initialize LLM if requested
        if self.use_llm:
            try:
                self.llm_client = LLMClient(config.get("MODEL", "gpt-4o-mini"))
                self.logger.info("LLM client initialized for backtesting")
            except Exception as e:
                self.logger.warning(
                    f"Failed to initialize LLM: {e}. Using rule-based decisions."
                )
                self.use_llm = False

        # Trading parameters
        self.min_confidence = config.get("MIN_CONFIDENCE", 35)
        self.risk_fraction = config.get("RISK_FRACTION", 0.5)
        self.lookback_bars = config.get("LOOKBACK_BARS", 20)
        self.min_body_pct = config.get("MIN_BODY_PCT", 0.3)

        # Options simulation parameters
        self.option_multiplier = 100  # Standard options contract
        self.commission = 0.65  # Per contract commission
        self.bid_ask_spread = 0.05  # Estimated spread as % of premium

    def fetch_historical_data(
        self, symbol: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """Fetch historical market data for backtesting."""
        try:
            self.logger.info(
                f"Fetching historical data for {symbol} from {start_date} to {end_date}"
            )

            ticker = yf.Ticker(symbol)

            # Calculate days between start and end
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            days_diff = (end_dt - start_dt).days

            # Use 5m data for recent periods (< 60 days), daily for longer periods
            if days_diff <= 60:
                interval = "5m"
                self.logger.info("Using 5-minute data for recent backtest")
            else:
                interval = "1d"
                self.logger.info(
                    "Using daily data for longer backtest (5m data limited to 60 days)"
                )

            data = ticker.history(
                start=start_date,
                end=end_date,
                interval=interval,
                auto_adjust=True,
                prepost=False,
            )

            if data.empty:
                # Try with daily data as fallback
                if interval == "5m":
                    self.logger.warning("5m data failed, trying daily data")
                    data = ticker.history(
                        start=start_date,
                        end=end_date,
                        interval="1d",
                        auto_adjust=True,
                        prepost=False,
                    )

                if data.empty:
                    raise ValueError(f"No data retrieved for {symbol}")

            self.logger.info(
                f"Retrieved {len(data)} bars of {interval} historical data"
            )
            return data

        except Exception as e:
            self.logger.error(f"Failed to fetch historical data: {e}")
            raise

    def simulate_option_premium(
        self, underlying_price: float, strike_price: float, direction: str, dte: int = 0
    ) -> float:
        """Simulate option premium based on underlying price and strike."""
        # Simple Black-Scholes approximation for backtesting
        # In reality, you'd use actual historical options data

        moneyness = underlying_price / strike_price

        if direction == "CALL":
            if moneyness > 1.02:  # ITM
                intrinsic = underlying_price - strike_price
                time_value = underlying_price * 0.01  # 1% time value
            elif moneyness > 0.98:  # ATM
                intrinsic = 0
                time_value = underlying_price * 0.02  # 2% time value
            else:  # OTM
                intrinsic = 0
                time_value = underlying_price * 0.005  # 0.5% time value
        else:  # PUT
            if moneyness < 0.98:  # ITM
                intrinsic = strike_price - underlying_price
                time_value = underlying_price * 0.01
            elif moneyness < 1.02:  # ATM
                intrinsic = 0
                time_value = underlying_price * 0.02
            else:  # OTM
                intrinsic = 0
                time_value = underlying_price * 0.005

        premium = max(intrinsic + time_value, 0.01)  # Minimum $0.01
        return premium

    def make_trade_decision(
        self, analysis: Dict, win_history: List[bool]
    ) -> Tuple[str, float, str]:
        """Make trade decision using LLM or rule-based logic."""
        if self.use_llm:
            try:
                llm_payload = prepare_llm_payload(analysis)
                decision = self.llm_client.make_trade_decision(llm_payload, win_history)
                return decision.decision, decision.confidence, decision.reason
            except Exception as e:
                self.logger.warning(
                    f"LLM decision failed: {e}. Using rule-based fallback."
                )

        # Rule-based fallback logic
        trend = analysis.get("trend_direction", "NEUTRAL")
        body_pct = analysis.get("candle_body_pct", 0)

        # Check minimum body percentage
        if body_pct < self.min_body_pct:
            return (
                "NO_TRADE",
                0.0,
                f"Candle body {body_pct:.2f}% below minimum {self.min_body_pct}%",
            )

        # Simple trend-following logic
        if trend == "BULLISH" and body_pct > self.min_body_pct:
            confidence = min(body_pct * 10, 85)  # Scale body % to confidence
            return "CALL", confidence, f"Bullish breakout with {body_pct:.2f}% body"
        elif trend == "BEARISH" and body_pct > self.min_body_pct:
            confidence = min(body_pct * 10, 85)
            return "PUT", confidence, f"Bearish breakout with {body_pct:.2f}% body"
        else:
            return "NO_TRADE", 0.0, f"No clear breakout signal (trend: {trend})"

    def calculate_exit_price(
        self,
        entry_premium: float,
        underlying_entry: float,
        underlying_exit: float,
        direction: str,
        strike: float,
    ) -> float:
        """Calculate option exit price based on underlying movement."""
        # Simplified exit calculation
        underlying_change_pct = (underlying_exit - underlying_entry) / underlying_entry

        if direction == "CALL":
            if underlying_change_pct > 0.01:  # Profitable move
                exit_premium = entry_premium * (
                    1 + underlying_change_pct * 3
                )  # 3x leverage
            else:
                exit_premium = entry_premium * 0.1  # Time decay loss
        else:  # PUT
            if underlying_change_pct < -0.01:  # Profitable move
                exit_premium = entry_premium * (1 + abs(underlying_change_pct) * 3)
            else:
                exit_premium = entry_premium * 0.1  # Time decay loss

        return max(exit_premium, 0.01)  # Minimum $0.01

    def run_backtest(
        self,
        symbol: str = "SPY",
        start_date: str = "2024-01-01",
        end_date: str = "2024-12-31",
        initial_capital: float = 10000,
    ) -> BacktestResults:
        """Run comprehensive backtest on historical data."""
        self.logger.info(f"Starting backtest: {symbol} from {start_date} to {end_date}")

        # Fetch historical data
        market_data = self.fetch_historical_data(symbol, start_date, end_date)

        # Calculate Heikin-Ashi candles
        ha_data = calculate_heikin_ashi(market_data)

        # Initialize tracking variables
        trades = []
        equity_curve = [initial_capital]
        current_capital = initial_capital
        win_history = []
        max_equity = initial_capital
        max_drawdown = 0.0

        # Simulate trading day by day
        for i in range(self.lookback_bars, len(ha_data) - 1):  # Leave room for exit
            current_date = ha_data.index[i]

            # Skip if not during market hours (rough approximation)
            if current_date.hour < 9 or current_date.hour > 15:
                continue

            # Get data slice for analysis
            data_slice = ha_data.iloc[i - self.lookback_bars : i + 1]

            try:
                # Analyze breakout pattern
                analysis = analyze_breakout_pattern(data_slice, self.lookback_bars)

                # Make trade decision
                decision, confidence, reason = self.make_trade_decision(
                    analysis, win_history[-10:]
                )

                # Skip if no trade or low confidence
                if decision == "NO_TRADE" or confidence < self.min_confidence:
                    continue

                # Calculate position size
                current_price = analysis["current_price"]
                strike_price = current_price  # ATM option

                premium = self.simulate_option_premium(
                    current_price, strike_price, decision
                )

                # Position sizing based on risk fraction
                max_risk = current_capital * self.risk_fraction
                max_contracts = int(max_risk / (premium * self.option_multiplier))

                if max_contracts == 0:
                    continue  # Not enough capital

                quantity = min(max_contracts, 10)  # Limit to 10 contracts max
                total_cost = (premium * quantity * self.option_multiplier) + (
                    self.commission * quantity
                )

                if total_cost > current_capital:
                    continue  # Not enough capital

                # Enter trade
                entry_date = current_date
                entry_price = current_price

                # Simulate holding for rest of day or until profit/loss target
                exit_idx = min(
                    i + 12, len(ha_data) - 1
                )  # Hold for ~1 hour (12 bars of 5min)
                exit_date = ha_data.index[exit_idx]
                exit_price = ha_data.iloc[exit_idx]["Close"]

                # Calculate exit premium
                exit_premium = self.calculate_exit_price(
                    premium, entry_price, exit_price, decision, strike_price
                )

                # Account for bid-ask spread
                exit_premium *= 1 - self.bid_ask_spread

                # Calculate P&L
                gross_pnl = (exit_premium - premium) * quantity * self.option_multiplier
                net_pnl = gross_pnl - (
                    self.commission * quantity * 2
                )  # Entry + exit commissions

                # Update capital
                current_capital += net_pnl

                # Track win/loss
                is_win = net_pnl > 0
                win_history.append(is_win)

                # Create trade record
                trade = BacktestTrade(
                    entry_date=entry_date,
                    exit_date=exit_date,
                    direction=decision,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    strike_price=strike_price,
                    premium_paid=premium,
                    quantity=quantity,
                    pnl=net_pnl,
                    confidence=confidence,
                    reason=reason,
                    win=is_win,
                )

                trades.append(trade)
                equity_curve.append(current_capital)

                # Track drawdown
                if current_capital > max_equity:
                    max_equity = current_capital
                else:
                    drawdown = (max_equity - current_capital) / max_equity
                    max_drawdown = max(max_drawdown, drawdown)

                self.logger.debug(
                    f"Trade {len(trades)}: {decision} @ ${entry_price:.2f} -> "
                    f"P&L: ${net_pnl:.2f} | Capital: ${current_capital:.2f}"
                )

            except Exception as e:
                self.logger.warning(f"Error processing bar {i}: {e}")
                continue

        # Calculate performance metrics
        results = self._calculate_performance_metrics(
            trades, equity_curve, initial_capital
        )

        self.logger.info(
            f"Backtest completed: {results.total_trades} trades, "
            f"{results.win_rate:.1f}% win rate, "
            f"${results.total_pnl:.2f} total P&L"
        )

        return results

    def _calculate_performance_metrics(
        self,
        trades: List[BacktestTrade],
        equity_curve: List[float],
        initial_capital: float,
    ) -> BacktestResults:
        """Calculate comprehensive performance metrics."""
        if not trades:
            return BacktestResults(
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                total_pnl=0.0,
                max_drawdown=0.0,
                sharpe_ratio=0.0,
                avg_win=0.0,
                avg_loss=0.0,
                profit_factor=0.0,
                trades=[],
                equity_curve=equity_curve,
                daily_returns=[],
            )

        # Basic metrics
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t.win)
        losing_trades = total_trades - winning_trades
        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0

        # P&L metrics
        total_pnl = sum(t.pnl for t in trades)
        winning_pnl = sum(t.pnl for t in trades if t.win)
        losing_pnl = sum(t.pnl for t in trades if not t.win)

        avg_win = winning_pnl / winning_trades if winning_trades > 0 else 0
        avg_loss = losing_pnl / losing_trades if losing_trades > 0 else 0
        profit_factor = (
            abs(winning_pnl / losing_pnl) if losing_pnl != 0 else float("inf")
        )

        # Calculate max drawdown
        max_equity = initial_capital
        max_drawdown = 0.0
        for equity in equity_curve:
            if equity > max_equity:
                max_equity = equity
            else:
                drawdown = (max_equity - equity) / max_equity
                max_drawdown = max(max_drawdown, drawdown)

        # Calculate daily returns for Sharpe ratio
        daily_returns = []
        for i in range(1, len(equity_curve)):
            daily_return = (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
            daily_returns.append(daily_return)

        # Sharpe ratio (assuming 0% risk-free rate)
        if daily_returns and np.std(daily_returns) > 0:
            sharpe_ratio = (
                np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252)
            )  # Annualized
        else:
            sharpe_ratio = 0.0

        return BacktestResults(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_pnl=total_pnl,
            max_drawdown=max_drawdown * 100,  # Convert to percentage
            sharpe_ratio=sharpe_ratio,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            trades=trades,
            equity_curve=equity_curve,
            daily_returns=daily_returns,
        )

    def generate_report(self, results: BacktestResults, output_file: str = None) -> str:
        """Generate a comprehensive backtest report."""
        report = []
        report.append("=" * 60)
        report.append("ROBINHOOD HA BREAKOUT - BACKTEST REPORT")
        report.append("=" * 60)
        report.append("")

        # Summary metrics
        report.append("PERFORMANCE SUMMARY")
        report.append("-" * 30)
        report.append(f"Total Trades: {results.total_trades}")
        report.append(f"Winning Trades: {results.winning_trades}")
        report.append(f"Losing Trades: {results.losing_trades}")
        report.append(f"Win Rate: {results.win_rate:.1f}%")
        report.append("")

        # P&L metrics
        report.append("PROFIT & LOSS")
        report.append("-" * 30)
        report.append(f"Total P&L: ${results.total_pnl:,.2f}")
        report.append(f"Average Win: ${results.avg_win:.2f}")
        report.append(f"Average Loss: ${results.avg_loss:.2f}")
        report.append(f"Profit Factor: {results.profit_factor:.2f}")
        report.append("")

        # Risk metrics
        report.append("RISK METRICS")
        report.append("-" * 30)
        report.append(f"Max Drawdown: {results.max_drawdown:.1f}%")
        report.append(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
        report.append("")

        # Trade details (last 10 trades)
        if results.trades:
            report.append("RECENT TRADES (Last 10)")
            report.append("-" * 30)
            for trade in results.trades[-10:]:
                pnl_str = f"${trade.pnl:+.2f}"
                report.append(
                    f"{trade.entry_date.strftime('%Y-%m-%d %H:%M')} | "
                    f"{trade.direction} | ${trade.entry_price:.2f} | "
                    f"{pnl_str} | {trade.confidence:.0f}%"
                )

        report.append("")
        report.append("=" * 60)

        report_text = "\n".join(report)

        # Save to file if requested
        if output_file:
            with open(output_file, "w") as f:
                f.write(report_text)
            self.logger.info(f"Backtest report saved to {output_file}")

        return report_text


def run_quick_backtest(
    config_file: str = "config.yaml", days: int = 30
) -> BacktestResults:
    """Run a quick backtest for the last N days."""
    import yaml
    from pathlib import Path

    # Load configuration
    config_path = Path(config_file)
    if config_path.exists():
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    else:
        # Default configuration
        config = {
            "MODEL": "gpt-4o-mini",
            "MIN_CONFIDENCE": 35,
            "RISK_FRACTION": 0.5,
            "LOOKBACK_BARS": 20,
            "MIN_BODY_PCT": 0.3,
        }

    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    # Run backtest
    backtester = StrategyBacktester(config, use_llm=False)  # Use rule-based for speed
    results = backtester.run_backtest(
        symbol="SPY",
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
        initial_capital=10000,
    )

    return results


if __name__ == "__main__":
    # Example usage

    # Setup logging
    logging.basicConfig(level=logging.INFO)

    # Run quick backtest
    print("Running 30-day backtest...")
    results = run_quick_backtest(days=30)

    # Generate and display report
    backtester = StrategyBacktester({})
    report = backtester.generate_report(results, "backtest_report.txt")
    print(report)
