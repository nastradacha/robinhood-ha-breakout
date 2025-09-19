"""
Canonical ledger schema and versioning.
"""

# Schema versions
POSITIONS_SCHEMA_VERSION = "1.1"

# Canonical Alpaca-scoped positions CSV schema
# Keep this the single source of truth across writers/readers
POSITIONS_SCHEMA_ALPACA_V1 = [
    "symbol",
    "occ_symbol",
    "strike",
    "option_type",
    "expiry",
    "quantity",
    "contracts",
    "entry_price",
    "current_price",
    "pnl_pct",
    "pnl_amount",
    "timestamp",
    "status",
    "close_time",
    "market_value",
    "unrealized_pnl",
    "entry_time",
    "source",
    "sync_detected",
]

# Composite key fields used when occ_symbol is missing
POSITIONS_KEY_FIELDS = ("symbol", "expiry", "option_type", "strike")
