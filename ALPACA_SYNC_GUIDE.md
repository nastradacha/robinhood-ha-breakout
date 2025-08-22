# Alpaca Data Synchronization Guide

## Overview

The Alpaca Data Synchronization system automatically keeps your local trading system in sync with your Alpaca account. This ensures consistency when manual trades are made outside the automation system.

## Key Features

### 🔄 **Automatic Synchronization**
- **Bankroll Sync**: Updates local balance from Alpaca account equity
- **Position Sync**: Detects manual trades and updates position tracking
- **Transaction Sync**: Imports missing trades from Alpaca order history
- **Pre-Trade Sync**: Automatically syncs before each trade execution

### 🛡️ **Safety & Validation**
- Configurable tolerance thresholds (1% default)
- Conflict detection and resolution
- Comprehensive audit logging
- Slack notifications for sync events

### 📊 **Multi-Environment Support**
- Separate sync for paper and live accounts
- Environment-specific file isolation
- Scoped ledger management

## Configuration

Add these settings to your `config.yaml`:

```yaml
# Alpaca Synchronization Configuration
ALPACA_SYNC_ENABLED: true                    # Enable automatic sync
ALPACA_AUTO_SYNC_BEFORE_TRADE: true         # Sync before each trade
ALPACA_SYNC_TOLERANCE_PCT: 1.0              # Balance tolerance (1%)
ALPACA_SYNC_SLACK_ALERTS: true              # Slack notifications
ALPACA_SYNC_INTERVAL_MINUTES: 15            # Auto-sync interval
```

## Usage

### Command Line Tool

```bash
# Check if sync is needed (paper account)
python sync_alpaca.py --env paper --check-only

# Full synchronization (paper account)
python sync_alpaca.py --env paper --sync-type all

# Sync only bankroll (live account)
python sync_alpaca.py --env live --sync-type bankroll

# Sync only positions
python sync_alpaca.py --env paper --sync-type positions

# Sync only transactions
python sync_alpaca.py --env paper --sync-type transactions

# Verbose logging
python sync_alpaca.py --env paper --sync-type all --verbose
```

### Programmatic Usage

```python
from utils.alpaca_sync import AlpacaSync, sync_before_trade

# Create sync instance
sync = AlpacaSync(env="paper")

# Check if sync needed
sync_needed = sync.check_sync_needed()
print(f"Sync needed: {sync_needed}")

# Perform full sync
results = sync.sync_all()
print(f"Sync results: {results}")

# Sync before trading (convenience function)
success = sync_before_trade(env="paper")
```

## Sync Components

### 1. Bankroll Synchronization

**What it does:**
- Compares local bankroll with Alpaca account equity
- Updates local balance if difference exceeds tolerance
- Preserves transaction history

**When it syncs:**
- Balance difference > 1% (configurable)
- Manual trades detected
- Account deposits/withdrawals

**Example Output:**
```
[ALPACA-SYNC] Alpaca account - Equity: $100,262.75, Cash: $100,262.75
[ALPACA-SYNC] Balance comparison - Local: $95,000.00, Alpaca: $100,262.75
[ALPACA-SYNC] Bankroll synchronized - Updated from $95,000.00 to $100,262.75
```

### 2. Position Synchronization

**What it does:**
- Compares local positions with Alpaca account positions
- Detects manually opened/closed positions
- Updates position tracking files

**Detection scenarios:**
- New positions opened manually in Alpaca web/mobile
- Positions closed outside automation
- Quantity mismatches from partial fills

**Example Output:**
```
[ALPACA-SYNC] Found 2 options positions in Alpaca account
[ALPACA-SYNC] Detected manual position: SPY250822C00635000 (qty: 1)
[ALPACA-SYNC] Position closed manually: QQQ250822P00480000
```

### 3. Transaction Synchronization

**What it does:**
- Imports missing trades from Alpaca order history
- Reconciles local trade log with Alpaca orders
- Maintains complete transaction audit trail

**Import criteria:**
- Filled orders from last 7 days
- Options trades only (US_OPTION asset class)
- Orders not already in local trade history

## Integration Points

### Automatic Pre-Trade Sync

The system automatically syncs before each trade execution:

```python
# In main.py - execute_alpaca_multi_symbol_trade()
alpaca_env = config.get("ALPACA_ENV", "paper")
sync_success = sync_before_trade(env=alpaca_env)
if not sync_success:
    logger.warning(f"Alpaca sync failed - proceeding with caution")
```

### Monitoring Integration

Position monitoring includes sync capabilities:

```python
# In monitor_alpaca.py
from utils.alpaca_sync import AlpacaSync

sync = AlpacaSync(env="paper")
# Periodic sync during monitoring
```

## File Structure

The sync system creates and maintains these files:

```
├── bankroll_alpaca_paper.json          # Paper account bankroll
├── bankroll_alpaca_live.json           # Live account bankroll
├── positions_alpaca_paper.csv          # Paper account positions
├── positions_alpaca_live.csv           # Live account positions
├── logs/
│   ├── trade_history_alpaca_paper.csv  # Paper trade history
│   ├── trade_history_alpaca_live.csv   # Live trade history
│   ├── alpaca_sync_paper.log           # Paper sync audit log
│   └── alpaca_sync_live.log            # Live sync audit log
```

## Sync Events & Logging

### Audit Trail

All sync events are logged with:
- Timestamp and event type
- Before/after values
- Source of changes
- Environment context

### Slack Notifications

Sync results are sent to Slack:

```
✅ Alpaca Sync SUCCESS [PAPER]
Bankroll: ✅ | Positions: ✅ | Transactions: ✅
```

## Common Scenarios

### Scenario 1: Manual Trade in Alpaca Web

1. You manually buy 1 SPY call option in Alpaca web interface
2. Next automation run detects the position mismatch
3. System logs: "Detected manual position: SPY250822C00635000"
4. Position is added to local tracking
5. Slack notification sent about sync event

### Scenario 2: Account Deposit

1. You deposit $5,000 into your Alpaca account
2. Sync detects balance difference: Local $95K vs Alpaca $100K
3. System updates local bankroll to match Alpaca
4. Adjustment logged: "sync_adjustment": 5000.00

### Scenario 3: Partial Fill Outside System

1. You place a large order that fills partially
2. Sync detects quantity mismatch
3. Local position updated to match Alpaca quantity
4. Discrepancy logged for investigation

## Troubleshooting

### Common Issues

**1. Sync Fails with "Path not found"**
```bash
# Solution: Ensure directories exist
mkdir -p logs
python sync_alpaca.py --env paper --sync-type bankroll
```

**2. Balance Tolerance Too Strict**
```yaml
# Increase tolerance in config.yaml
ALPACA_SYNC_TOLERANCE_PCT: 2.0  # 2% tolerance
```

**3. Missing API Credentials**
```bash
# Verify .env file has:
ALPACA_API_KEY=your_key_here
ALPACA_SECRET_KEY=your_secret_here
```

### Debug Mode

Enable verbose logging for troubleshooting:

```bash
python sync_alpaca.py --env paper --sync-type all --verbose
```

## Best Practices

### 1. Regular Sync Checks
```bash
# Add to cron for periodic checks
0 */4 * * * cd /path/to/robinhood-ha-breakout && python sync_alpaca.py --env live --check-only
```

### 2. Pre-Market Sync
```bash
# Sync before market open
30 9 * * 1-5 cd /path/to/robinhood-ha-breakout && python sync_alpaca.py --env live --sync-type all
```

### 3. Monitor Sync Logs
```bash
# Review sync audit trail
tail -f logs/alpaca_sync_paper.log
```

### 4. Slack Integration
- Monitor #trading-alerts channel for sync notifications
- Set up alerts for failed sync operations
- Review sync summaries for unusual activity

## Security Considerations

- Sync logs may contain sensitive account information
- Ensure proper file permissions on sync log files
- Use environment variables for API credentials
- Monitor sync events for unauthorized activity

## API Rate Limits

The sync system respects Alpaca API limits:
- Account info: 200 requests/minute
- Orders history: 200 requests/minute
- Positions: 200 requests/minute

Sync operations are designed to be efficient and stay within limits.

---

## Summary

The Alpaca Data Synchronization system provides seamless integration between your automated trading system and manual Alpaca account activity. It ensures data consistency, maintains audit trails, and provides real-time notifications of account changes.

**Key Benefits:**
- ✅ Never miss manual trades
- ✅ Always have accurate account balance
- ✅ Complete transaction audit trail
- ✅ Real-time sync notifications
- ✅ Multi-environment support
- ✅ Configurable tolerance levels
