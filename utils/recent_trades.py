"""Recent trade history loader for LLM context memory.

Functions
---------
load_recent(n: int) -> list[dict]
    Return a list of the last *n* trades from ``trade_history.csv`` (or
    ``TRADE_LOG_FILE`` configured in *config.yaml*).  The function is
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

# NOTE: Avoid circular import by not importing utils.llm at module load time.
DEFAULT_TRADE_FILE = Path("logs/trade_log.csv")


def _classify_result(pnl_pct: str) -> str:
    """Return WIN / LOSS / FLAT given the PnL percent string."""
    try:
        pnl = float(pnl_pct)
    except (TypeError, ValueError):
        return "FLAT"
    if pnl > 0.1:
        return "WIN"
    if pnl < -0.1:
        return "LOSS"
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

    # Read file backwards efficiently
    rows: List[List[str]] = []
    with tf_path.open(newline="", encoding="utf-8") as fh:
        for line in fh:
            rows.append(line.rstrip("\n").split(","))

    recent_rows = rows[-n:]
    results: List[Dict[str, str]] = []
    for r in recent_rows:
        if len(r) < 11:
            # malformed legacy row
            continue
        ts_raw, symbol, action, *_rest, pnl_pct, _status, _reason = r + [""] * (
            12 - len(r)
        )
        stamp = ""
        try:
            stamp = datetime.fromisoformat(ts_raw).strftime("%H:%M")
        except ValueError:
            # fallback – try space‐separated datetime
            try:
                stamp = datetime.strptime(ts_raw[:19], "%Y-%m-%d %H:%M:%S").strftime(
                    "%H:%M"
                )
            except Exception:
                stamp = ts_raw[-5:]
        decision = (
            "NO_TRADE"
            if action == "NO_TRADE"
            else ("CALL" if "CALL" in action else "PUT")
        )
        result = _classify_result(pnl_pct)
        results.append({"stamp": stamp, "decision": decision, "result": result})
    return results
