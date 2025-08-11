"""Recent trade history loader for LLM context memory.

Functions
---------
load_recent(n: int) -> list[dict]
    Return a list of the last *n* trades from the scoped trade history CSV
    (``TRADE_LOG_FILE`` resolved from config via broker/env). The function is
    purposely lightweight and avoids pandas for performance.

Returned dict schema::
    {
        "stamp": "09:35",          # HH:MM of entry or decision
        "decision": "CALL",        # CALL / PUT / NO_TRADE
        "result": "WIN"            # WIN / LOSS / FLAT (if pnl == 0)
    }

The file may contain malformed lines (e.g. legacy NO_TRADE with fewer
columns).  Those lines are skipped to keep robustness.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Dict
import csv

# NOTE: Avoid circular import by not importing utils.llm at module load time.
# Default to scoped robinhood/live path if config is unavailable.
DEFAULT_TRADE_FILE = Path("logs/trade_history_robinhood_live.csv")


def _classify_from_row(row: Dict[str, str]) -> str:
    """Return WIN / LOSS / FLAT using pnl_pct, then pnl_amount as fallback."""
    # Prefer explicit percent if present
    pnl_pct_val = row.get("pnl_pct")
    if pnl_pct_val not in (None, ""):
        try:
            pnl = float(pnl_pct_val)
            if pnl > 0.1:
                return "WIN"
            if pnl < -0.1:
                return "LOSS"
            return "FLAT"
        except (TypeError, ValueError):
            pass

    # Fallback to absolute P&L amount sign
    pnl_amt_val = row.get("pnl_amount") or row.get("pnl")
    if pnl_amt_val not in (None, ""):
        try:
            pnl_amt = float(pnl_amt_val)
            if pnl_amt > 0:
                return "WIN"
            if pnl_amt < 0:
                return "LOSS"
            return "FLAT"
        except (TypeError, ValueError):
            pass

    return "FLAT"


def load_recent(
    n: int = 5, trade_file: str | Path | None = None
) -> List[Dict[str, str]]:
    """Load the last *n* trade rows from the trade log.

    Only BUY_TO_OPEN rows (actual trades) are considered for WIN/LOSS –
    NO_TRADE entries are still passed through but their *result* will be
    "FLAT".
    """
    if n <= 0:
        return []
    if trade_file is None:
        # Lazy-load config to avoid circular import during module initialization
        try:
            from utils.llm import load_config  # noqa: WPS433

            trade_file = load_config().get("TRADE_LOG_FILE", str(DEFAULT_TRADE_FILE))
        except Exception:
            trade_file = str(DEFAULT_TRADE_FILE)

    tf_path = Path(trade_file)
    if not tf_path.exists():
        return []

    # Read CSV using DictReader for schema-robust parsing
    records: List[Dict[str, str]] = []
    with tf_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            # Skip completely malformed rows
            if not row:
                continue
            records.append(row)

    recent_rows = records[-n:]
    results: List[Dict[str, str]] = []
    for row in recent_rows:
        ts_raw = (row.get("timestamp") or "").strip()
        # Decision normalization across schemas
        raw_decision = (
            row.get("decision")
            or row.get("action")
            or row.get("direction")
            or "NO_TRADE"
        )
        decision = "NO_TRADE"
        if isinstance(raw_decision, str):
            rd = raw_decision.upper()
            if "NO_TRADE" in rd:
                decision = "NO_TRADE"
            elif "CALL" in rd:
                decision = "CALL"
            elif "PUT" in rd:
                decision = "PUT"
            else:
                decision = rd

        # Timestamp -> HH:MM
        stamp = ""
        if ts_raw:
            try:
                stamp = datetime.fromisoformat(ts_raw).strftime("%H:%M")
            except ValueError:
                try:
                    stamp = datetime.strptime(ts_raw[:19], "%Y-%m-%d %H:%M:%S").strftime(
                        "%H:%M"
                    )
                except Exception:
                    stamp = ts_raw[-5:]

        result = _classify_from_row(row)
        results.append({"stamp": stamp, "decision": decision, "result": result})
    return results
