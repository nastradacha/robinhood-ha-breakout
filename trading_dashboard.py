#!/usr/bin/env python3
"""
Comprehensive Trading Dashboard

Shows all important financial data including:
- Current bankroll and portfolio value
- Transaction history and P&L
- Win/loss statistics
- Risk metrics and performance analysis
- Position tracking and exposure
"""

import json
import csv
import os
import argparse
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import numpy as np
import yaml
import math

from utils.scoped_files import get_scoped_paths, ensure_scoped_files
from utils.enhanced_slack import EnhancedSlackIntegration
from utils.drawdown_circuit_breaker import DrawdownCircuitBreaker


def _load_config() -> Dict:
    """Load config and resolve broker/env-scoped file paths.

    Returns a dict with keys: bankroll, trade_history, positions, broker, env.
    """
    # Load config.yaml (project root or module-adjacent)
    config_path = Path("config.yaml")
    if not config_path.exists():
        alt = Path(__file__).parent / "config.yaml"
        if alt.exists():
            config_path = alt

    cfg: Dict = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

    broker = (cfg.get("BROKER") or "robinhood").lower()
    env = (cfg.get("ALPACA_ENV") or "paper").lower() if broker == "alpaca" else "live"

    paths = get_scoped_paths(broker, env)
    # Ensure files/directories exist with correct headers
    try:
        ensure_scoped_files(paths)
    except Exception:
        pass

    # Allow explicit overrides in config while keeping defaults scoped
    if cfg.get("TRADE_LOG_FILE"):
        paths["trade_history"] = cfg["TRADE_LOG_FILE"]
    if cfg.get("POSITIONS_FILE"):
        paths["positions"] = cfg["POSITIONS_FILE"]
    if cfg.get("BANKROLL_FILE"):
        paths["bankroll"] = cfg["BANKROLL_FILE"]

    paths["broker"] = broker
    paths["env"] = env
    return paths


def load_bankroll_data(paths: Dict) -> Dict:
    """Load current bankroll and financial data using scoped path."""
    bankroll_file = paths.get("bankroll", "bankroll.json")
    try:
        with open(bankroll_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        start_capital = 500.0
        return {
            "current_bankroll": start_capital,
            "start_capital": start_capital,
            "total_trades": 0,
            "winning_trades": 0,
            "total_pnl": 0.0,
            "peak_bankroll": start_capital,
        }
    except Exception as e:
        print(f"Error loading bankroll from {bankroll_file}: {e}")
        return {}


def load_positions(paths: Dict) -> List[Dict]:
    """Load current open positions using scoped positions file."""
    positions = []
    try:
        positions_file = paths.get("positions", "positions.csv")
        with open(positions_file, "r", newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                try:
                    row["quantity"] = int(float(row.get("quantity", 0)))
                except Exception:
                    row["quantity"] = 0
                try:
                    row["entry_price"] = float(row.get("entry_price", 0) or 0)
                except Exception:
                    row["entry_price"] = 0.0
                try:
                    row["strike"] = float(row.get("strike", 0) or 0)
                except Exception:
                    row["strike"] = 0.0
                positions.append(row)
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"Error loading positions: {e}")

    return positions


def load_trade_history(paths: Dict) -> List[Dict]:
    """Load trade history from scoped CSV (15-field schema) with robust fallbacks."""
    trade_file = paths.get("trade_history", "logs/trade_history.csv")
    # Try fast path
    try:
        df = pd.read_csv(trade_file, encoding="utf-8")
    except Exception as e1:
        # Retry with python engine and skip bad lines
        try:
            df = pd.read_csv(
                trade_file,
                engine="python",
                on_bad_lines="skip",
                encoding="utf-8",
                quotechar='"',
                skipinitialspace=True,
            )
        except Exception as e2:
            # Final fallback: csv.DictReader
            try:
                rows: List[Dict] = []
                with open(trade_file, "r", encoding="utf-8", newline="") as f:
                    reader = csv.DictReader(f)
                    for r in reader:
                        # Drop any None keys created by extra columns
                        if None in r:
                            r.pop(None, None)
                        rows.append(r)
                df = pd.DataFrame(rows)
            except Exception as e3:
                print(f"Error loading trade history from {trade_file}: {e1}")
                return []

    # Map legacy columns to new schema where possible
    if "decision" not in df.columns:
        df["decision"] = np.nan
    # Fill from action and direction when decision missing/blank
    if "action" in df.columns:
        df["decision"] = df["decision"].fillna(df["action"])
    if "direction" in df.columns:
        df["decision"] = df["decision"].fillna(df["direction"])
    # Normalize blank strings to NaN then backfill
    if "decision" in df.columns:
        df.loc[df["decision"].astype(str).str.strip() == "", "decision"] = np.nan
        if "action" in df.columns:
            df["decision"] = df["decision"].fillna(df["action"])
        if "direction" in df.columns:
            df["decision"] = df["decision"].fillna(df["direction"])
    if "pnl_amount" not in df.columns and "pnl" in df.columns:
        df["pnl_amount"] = pd.to_numeric(df["pnl"], errors="coerce")
    if "fill_price" not in df.columns and "price" in df.columns:
        df["fill_price"] = pd.to_numeric(df["price"], errors="coerce")
    if "pnl_pct" in df.columns:
        df["pnl_pct"] = pd.to_numeric(df["pnl_pct"], errors="coerce")

    # Exclude NO_TRADE entries
    if "decision" in df.columns:
        df = df[df["decision"].astype(str).str.upper() != "NO_TRADE"].copy()

    # Ensure numeric types for later analytics
    for col in [
        "pnl_amount",
        "pnl_pct",
        "total_cost",
        "premium",
        "fill_price",
        "current_price",
        "quantity",
        "strike",
        "confidence",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.to_dict("records")


def calculate_portfolio_value(positions: List[Dict]) -> float:
    """Calculate current portfolio value (simplified)."""
    total_value = 0.0
    for position in positions:
        # Simplified calculation - in reality you'd get current option prices
        position_value = position["entry_price"] * position["quantity"] * 100
        total_value += position_value
    return total_value


def analyze_trades(trades: List[Dict], start_capital: float, limit: Optional[int] = None) -> Dict:
    """Analyze trade performance using scoped 15-field schema.

    Returns a metrics dict including win/loss stats, P&L, profit factor,
    Sharpe ratio, and drawdown.
    """
    if not trades:
        return {
            "total_closed": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "profit_factor": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "max_drawdown_amt": 0.0,
            "closed_trades_df": pd.DataFrame(),
        }

    df = pd.DataFrame(trades)

    # Normalize timestamp and sort
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.sort_values("timestamp")

    # Normalize numeric columns
    for col in [
        "pnl_amount",
        "pnl_pct",
        "total_cost",
        "premium",
        "fill_price",
        "current_price",
        "quantity",
        "strike",
        "confidence",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Identify closed trades
    # Ensure we operate on Series even if columns are missing
    decision_series = df["decision"] if "decision" in df.columns else pd.Series(["" ] * len(df), index=df.index)
    status_series = df["status"] if "status" in df.columns else pd.Series(["" ] * len(df), index=df.index)
    decision_upper = decision_series.astype(str).str.upper()
    status_upper = status_series.astype(str).str.upper()
    closed_mask = (
        decision_upper.str.startswith("CLOSE_")
        | decision_upper.str.startswith("SELL_")
        | status_upper.isin(["CLOSED_PROFIT", "CLOSED_LOSS"])
    )
    closed_df = df[closed_mask].copy()
    # If limiting, keep most recent N by timestamp when available
    if limit is not None and limit > 0:
        if "timestamp" in closed_df.columns:
            closed_df = closed_df.sort_values("timestamp").tail(limit)
        else:
            closed_df = closed_df.tail(limit)

    if closed_df.empty:
        return {
            "total_closed": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "profit_factor": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "max_drawdown_amt": 0.0,
            "closed_trades_df": closed_df,
        }

    # Realized P&L
    pnl = pd.to_numeric(closed_df.get("pnl_amount", 0), errors="coerce").fillna(0.0)
    winners = (pnl > 0)
    losers = (pnl < 0)
    total_pnl = float(pnl.sum())
    winning_trades = int(winners.sum())
    losing_trades = int(losers.sum())
    total_closed = int(len(closed_df))
    win_rate = (winning_trades / total_closed * 100.0) if total_closed > 0 else 0.0

    avg_win = float(pnl[winners].mean()) if winning_trades > 0 else 0.0
    avg_loss = float(pnl[losers].mean()) if losing_trades > 0 else 0.0

    pos_sum = float(pnl[winners].sum()) if winning_trades > 0 else 0.0
    neg_sum = float(pnl[losers].sum()) if losing_trades > 0 else 0.0
    profit_factor = (pos_sum / abs(neg_sum)) if neg_sum < 0 else 0.0

    # Compute trade returns and daily Sharpe
    cost = pd.to_numeric(closed_df.get("total_cost", np.nan), errors="coerce")
    est_cost = pd.to_numeric(closed_df.get("premium", np.nan), errors="coerce") * \
        pd.to_numeric(closed_df.get("quantity", 1), errors="coerce").fillna(1) * 100
    trade_cost = cost.where(cost.notna() & (cost > 0), est_cost)
    trade_cost = trade_cost.replace([np.inf, -np.inf], np.nan).fillna(0)
    with np.errstate(divide='ignore', invalid='ignore'):
        trade_returns = pnl / trade_cost.replace(0, np.nan)
    trade_returns = trade_returns.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    if "timestamp" in closed_df.columns:
        dates = pd.to_datetime(closed_df["timestamp"], errors="coerce").dt.date
        daily_returns = pd.Series(trade_returns.values, index=dates).groupby(level=0).sum()
        if daily_returns.std(ddof=0) > 0:
            sharpe_ratio = float(np.sqrt(252) * daily_returns.mean() / daily_returns.std(ddof=0))
        else:
            sharpe_ratio = 0.0
    else:
        sharpe_ratio = 0.0

    # Drawdown via equity curve (start_capital + cumulative pnl)
    equity = start_capital + pnl.cumsum()
    running_max = equity.cummax()
    drawdown = (running_max - equity) / running_max.replace(0, np.nan)
    max_drawdown_pct = float((drawdown.max() * 100.0) if len(drawdown) else 0.0)
    try:
        peak_equity = float(running_max.max()) if len(running_max) else start_capital
        trough_equity = float(equity[running_max.idxmax():].min()) if len(equity) else start_capital
        max_drawdown_amt = float(peak_equity - trough_equity)
    except Exception:
        max_drawdown_amt = 0.0

    return {
        "total_closed": total_closed,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown_pct": max_drawdown_pct,
        "max_drawdown_amt": max_drawdown_amt,
        "closed_trades_df": closed_df,
    }


def export_reports(metrics: Dict, paths: Dict, export_csv: bool, export_html: bool) -> Optional[Dict[str, str]]:
    """Export performance metrics to CSV and/or HTML in reports/ directory."""
    if not export_csv and not export_html:
        return None

    reports_dir = Path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)

    broker = paths.get("broker", "robinhood")
    env = paths.get("env", "live")
    outputs: Dict[str, str] = {}

    if export_csv:
        csv_path = reports_dir / f"performance_summary_{broker}_{env}.csv"
        # Flatten metrics excluding the DataFrame
        rows = {k: v for k, v in metrics.items() if k != "closed_trades_df"}
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["metric", "value"])
            for k, v in rows.items():
                writer.writerow([k, v])
        outputs["csv"] = str(csv_path)

    if export_html:
        html_path = reports_dir / f"performance_report_{broker}_{env}.html"
        closed_df = metrics.get("closed_trades_df", pd.DataFrame())
        # Build simple HTML
        html = [
            "<html><head><meta charset='utf-8'><title>Performance Report</title>",
            "<style>body{font-family:Arial,sans-serif;margin:20px} table{border-collapse:collapse} td,th{border:1px solid #ccc;padding:6px 8px}</style>",
            "</head><body>",
            f"<h1>Performance Report [{broker.upper()} / {env.upper()}]</h1>",
            "<h2>Summary Metrics</h2>",
            "<table>",
        ]
        for k, v in metrics.items():
            if k == "closed_trades_df":
                continue
            html.append(f"<tr><th>{k}</th><td>{v}</td></tr>")
        html.append("</table>")
        if not closed_df.empty:
            html.append("<h2>Closed Trades</h2>")
            html.append(closed_df.to_html(index=False))
        html.append("</body></html>")
        html_content = "\n".join(html)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        outputs["html"] = str(html_path)

    return outputs if outputs else None


def send_slack_summary(metrics: Dict, paths: Dict) -> bool:
    """Send analytics summary to Slack via EnhancedSlackIntegration."""
    try:
        slack = EnhancedSlackIntegration()
        if not slack.enabled:
            return False
        broker = paths.get("broker", "robinhood").upper()
        env = paths.get("env", "live").upper()
        msg = (
            f"PERFORMANCE SUMMARY [{broker}/{env}]\n"
            f"Closed Trades: {metrics['total_closed']}\n"
            f"Win Rate: {metrics['win_rate']:.1f}%  (W {metrics['winning_trades']} / L {metrics['losing_trades']})\n"
            f"Total P&L: ${metrics['total_pnl']:+.2f} | Profit Factor: {metrics['profit_factor']:.2f}\n"
            f"Sharpe: {metrics['sharpe_ratio']:.2f} | Max DD: {metrics['max_drawdown_pct']:.1f}% (${metrics['max_drawdown_amt']:.2f})"
        )
        slack.basic_notifier.send_heartbeat(msg)
        return True
    except Exception:
        return False


def display_dashboard(export_csv: bool = False, export_html: bool = False, slack: bool = False, limit: Optional[int] = None):
    """Display comprehensive trading dashboard with optional exports/Slack."""
    print("=" * 60)
    print("         COMPREHENSIVE TRADING DASHBOARD")
    print("=" * 60)
    print()

    # Load all data
    paths = _load_config()
    bankroll_data = load_bankroll_data(paths)
    positions = load_positions(paths)
    trades = load_trade_history(paths)

    # Calculate metrics
    portfolio_value = calculate_portfolio_value(positions)
    start_capital = float(bankroll_data.get("start_capital", 500.0))
    trade_analysis = analyze_trades(trades, start_capital, limit=limit)

    # Current Financial Status
    print("=== FINANCIAL OVERVIEW ===")
    current_bankroll = bankroll_data.get("current_bankroll", 0)
    start_capital = bankroll_data.get("start_capital", 500)
    peak_bankroll = bankroll_data.get("peak_bankroll", current_bankroll)

    print(f"Current Bankroll: ${current_bankroll:,.2f}")
    print(f"Starting Capital: ${start_capital:,.2f}")
    print(f"Peak Bankroll: ${peak_bankroll:,.2f}")

    # Circuit Breaker Status
    try:
        config = {}
        if hasattr(paths, 'get') and 'config' in paths:
            config = paths['config']
        elif 'broker' in paths and 'env' in paths:
            # Load config from file for circuit breaker check
            config_path = Path("config.yaml")
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}
        
        circuit_breaker = DrawdownCircuitBreaker(config)
        cb_status = circuit_breaker.get_circuit_breaker_status()
        
        print("\n=== DAILY DRAWDOWN PROTECTION ===")
        if cb_status['is_active']:
            print(f"🔴 CIRCUIT BREAKER ACTIVE")
            print(f"   Activated: {cb_status.get('activation_date', 'Unknown')} at {cb_status.get('activation_time', 'Unknown')}")
            print(f"   Reason: {cb_status.get('activation_reason', 'Daily loss threshold exceeded')}")
            print(f"   Loss at Activation: {cb_status.get('activation_pnl_percent', 0):.2f}%")
            if cb_status.get('manual_reset_required', False):
                print(f"   ⚠️  Manual reset required to resume trading")
        else:
            print(f"🟢 Circuit Breaker: INACTIVE")
            print(f"   Daily P&L Tracking: {'ENABLED' if cb_status.get('enabled', False) else 'DISABLED'}")
            if cb_status.get('enabled', False):
                print(f"   Loss Threshold: {cb_status.get('threshold_percent', 5.0):.1f}%")
                daily_pnl = cb_status.get('current_daily_pnl_percent', 0)
                pnl_color = "🟢" if daily_pnl >= 0 else "🟡" if daily_pnl > -2.5 else "🟠" if daily_pnl > -4.0 else "🔴"
                print(f"   Today's P&L: {pnl_color} {daily_pnl:+.2f}%")
                
    except Exception as e:
        print(f"\n=== DAILY DRAWDOWN PROTECTION ===")
        print(f"⚠️  Status check failed: {e}")
        print(f"   Circuit breaker may be unavailable")
    print(
        f"Total Return: ${current_bankroll - start_capital:+,.2f} ({((current_bankroll - start_capital) / start_capital * 100):+.1f}%)"
    )
    print(f"Portfolio Value: ${portfolio_value:,.2f}")
    print(f"Total Account Value: ${current_bankroll + portfolio_value:,.2f}")
    print()

    # Trading Performance
    print("=== TRADING PERFORMANCE ===")
    print(f"Total Trades: {trade_analysis['total_closed']}")
    print(f"Winning Trades: {trade_analysis['winning_trades']}")
    print(f"Losing Trades: {trade_analysis['losing_trades']}")
    print(f"Win Rate: {trade_analysis['win_rate']:.1f}%")
    print(f"Total P&L: ${trade_analysis['total_pnl']:+,.2f}")
    if trade_analysis["avg_win"] != 0:
        print(f"Average Win: ${trade_analysis['avg_win']:,.2f}")
    if trade_analysis["avg_loss"] != 0:
        print(f"Average Loss: ${trade_analysis['avg_loss']:,.2f}")
    if trade_analysis["profit_factor"] != 0:
        print(f"Profit Factor: {trade_analysis['profit_factor']:.2f}")
    if trade_analysis["sharpe_ratio"] != 0:
        print(f"Sharpe Ratio: {trade_analysis['sharpe_ratio']:.2f}")
    if trade_analysis["max_drawdown_pct"] != 0:
        print(
            f"Max Drawdown: {trade_analysis['max_drawdown_pct']:.1f}% (${trade_analysis['max_drawdown_amt']:.2f})"
        )
    print()

    # Current Positions
    print("=== CURRENT POSITIONS ===")
    if positions:
        total_invested = 0
        for pos in positions:
            position_cost = pos["entry_price"] * pos["quantity"] * 100
            total_invested += position_cost
            opt_type = pos.get('option_type', pos.get('direction', '?'))
            print(
                f"  {pos['symbol']} ${pos['strike']} {opt_type} x{pos['quantity']}"
            )
            print(f"    Entry: ${pos['entry_price']:.2f} | Cost: ${position_cost:,.2f}")
            if 'expiry' in pos and pos['expiry']:
                print(f"    Expiry: {pos['expiry']}")

        print(f"\nTotal Invested: ${total_invested:,.2f}")
        print(f"Available Cash: ${current_bankroll:,.2f}")
        print(
            f"Buying Power Used: {(total_invested / (current_bankroll + total_invested) * 100):.1f}%"
        )
    else:
        print("  No open positions")
        print(f"  Available Cash: ${current_bankroll:,.2f}")
    print()

    # Recent Activity
    print("=== RECENT TRANSACTIONS ===")
    recent_trades = sorted(trades, key=lambda x: str(x.get("timestamp", "")), reverse=True)[:5]

    if recent_trades:
        for trade in recent_trades:
            timestamp = str(trade.get("timestamp", "Unknown"))[:16]  # YYYY-MM-DD HH:MM
            action = trade.get("decision", trade.get("action", "Unknown"))
            symbol = trade.get("symbol", "Unknown")
            strike = trade.get("strike", "Unknown")
            option_type = trade.get("option_type", trade.get("direction", "Unknown"))
            price = trade.get("fill_price") or trade.get("premium") or trade.get("price", "Unknown")
            status = trade.get("status", trade.get("state", "Unknown"))

            pnl_str = ""
            pnl_val = trade.get("pnl_amount") or trade.get("realized_pnl")
            try:
                pnl = float(pnl_val) if pnl_val not in (None, "") else None
            except Exception:
                pnl = None
            if pnl is not None and not (isinstance(pnl, float) and math.isnan(pnl)):
                pnl_str = f" (${pnl:+.2f})"

            print(
                f"  {timestamp} | {action} {symbol} ${strike} {option_type} @ ${price}{pnl_str}"
            )
            print(f"    Status: {status}")
    else:
        print("  No recent transactions")
    print()

    # Risk Metrics
    print("=== RISK ANALYSIS ===")
    if positions:
        total_at_risk = sum(
            pos["entry_price"] * pos["quantity"] * 100 for pos in positions
        )
        risk_percentage = (total_at_risk / (current_bankroll + total_at_risk)) * 100
        print(
            f"Capital at Risk: ${total_at_risk:,.2f} ({risk_percentage:.1f}% of account)"
        )
    else:
        print("No capital currently at risk")

    # Prefer computed drawdown from trades if available
    if trade_analysis.get("max_drawdown_pct", 0) != 0:
        print(
            f"Computed Max DD: {trade_analysis['max_drawdown_pct']:.1f}% (${trade_analysis['max_drawdown_amt']:.2f})"
        )

    print()

    # Performance Summary
    print("=== PERFORMANCE SUMMARY ===")
    if trade_analysis["total_closed"] > 0:
        print(
            f"[OK] {trade_analysis['total_closed']} completed trades with {trade_analysis['win_rate']:.1f}% win rate"
        )
        print(f"[OK] Total profit: ${trade_analysis['total_pnl']:+,.2f}")
        print(
            f"[OK] Account growth: {((current_bankroll - start_capital) / start_capital * 100):+.1f}%"
        )
    else:
        print("[INFO] No completed trades yet")

    if positions:
        print(f"[INFO] {len(positions)} open position(s) being monitored")

    # Optional exports and Slack
    outputs = export_reports(trade_analysis, paths, export_csv, export_html)
    if outputs:
        for kind, out_path in outputs.items():
            print(f"[OK] Exported {kind.upper()} report -> {out_path}")

    if slack:
        sent = send_slack_summary(trade_analysis, paths)
        print("[OK] Sent Slack summary" if sent else "[INFO] Slack not enabled or send failed")

    print()
    print("=" * 60)
    print("Run 'python trading_dashboard.py' anytime to see updated data")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Performance analytics dashboard")
    parser.add_argument("--export-csv", action="store_true", help="Export summary CSV to reports/")
    parser.add_argument("--export-html", action="store_true", help="Export HTML report to reports/")
    parser.add_argument("--slack", action="store_true", help="Send summary to Slack")
    parser.add_argument("--limit", type=int, default=None, help="Limit closed trades considered (most recent N)")
    args = parser.parse_args()

    display_dashboard(export_csv=args.export_csv, export_html=args.export_html, slack=args.slack, limit=args.limit)
