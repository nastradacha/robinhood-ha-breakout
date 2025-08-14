# 🚀 CLI Reference - Complete Command Guide

**Comprehensive reference for all command-line options in the Robinhood HA Breakout system**

---

## 📋 Quick Reference

### Core Trading Commands

```bash
# Automated Alpaca Trading (Recommended)
python main.py --broker alpaca --multi-symbol --loop --interval 5 --slack-notify

# Position Monitoring (Essential)
python monitor_alpaca.py --interval 2 --slack-notify

# Transaction Data Sync
python -c "from utils.alpaca_transaction_sync import sync_alpaca_transactions; sync_alpaca_transactions()"
```

---

## 🎯 Main Trading System (`main.py`)

### Basic Usage
```bash
python main.py [OPTIONS]
```

### Core Options

#### **Broker Selection**
| Flag | Description | Default | Example |
|------|-------------|---------|---------|
| `--broker {alpaca,robinhood}` | Trading broker to use | `alpaca` | `--broker alpaca` |

#### **Symbol Configuration**
| Flag | Description | Default | Example |
|------|-------------|---------|---------|
| `--symbols SYMBOL [SYMBOL ...]` | Specific symbols to trade | `["SPY"]` | `--symbols SPY QQQ IWM` |
| `--multi-symbol` | Enable multi-symbol trading (19 symbols) | `False` | `--multi-symbol` |

#### **Trading Modes**
| Flag | Description | Default | Example |
|------|-------------|---------|---------|
| `--loop` | Continuous trading mode | `False` | `--loop` |
| `--interval MINUTES` | Loop interval in minutes | `5` | `--interval 3` |
| `--end-at TIME` | Stop trading at specific time | `None` | `--end-at 15:45` |
| `--dry-run` | Simulate trades without execution | `False` | `--dry-run` |

#### **Risk Management**
| Flag | Description | Default | Example |
|------|-------------|---------|---------|
| `--i-understand-live-risk` | Required for live trading | `False` | `--i-understand-live-risk` |
| `--max-trades N` | Maximum trades per session | `None` | `--max-trades 3` |

#### **Notifications**
| Flag | Description | Default | Example |
|------|-------------|---------|---------|
| `--slack-notify` | Enable Slack notifications | `False` | `--slack-notify` |
| `--no-charts` | Disable chart generation | `False` | `--no-charts` |

#### **Advanced Options**
| Flag | Description | Default | Example |
|------|-------------|---------|---------|
| `--config PATH` | Custom config file path | `config.yaml` | `--config custom.yaml` |
| `--log-level {DEBUG,INFO,WARNING,ERROR}` | Logging verbosity | `INFO` | `--log-level DEBUG` |
| `--force-paper` | Force paper trading mode | `False` | `--force-paper` |

### Complete Examples

#### **Production Trading Setup**
```bash
# Full automated trading with monitoring
python main.py --broker alpaca --multi-symbol --loop --interval 5 --end-at 15:45 --slack-notify --i-understand-live-risk
```

#### **Safe Testing Setup**
```bash
# Paper trading with notifications
python main.py --broker alpaca --multi-symbol --loop --interval 5 --slack-notify --force-paper
```

#### **Single Symbol Focus**
```bash
# Trade only SPY with high frequency
python main.py --broker alpaca --symbols SPY --loop --interval 2 --slack-notify
```

---

## 📊 Position Monitor (`monitor_alpaca.py`)

### Basic Usage
```bash
python monitor_alpaca.py [OPTIONS]
```

### Monitor Options

| Flag | Description | Default | Example |
|------|-------------|---------|---------|
| `--interval MINUTES` | Monitoring interval | `2` | `--interval 1` |
| `--slack-notify` | Enable Slack alerts | `False` | `--slack-notify` |
| `--profit-target PERCENT` | Custom profit target | `15` | `--profit-target 20` |
| `--stop-loss PERCENT` | Custom stop loss | `25` | `--stop-loss 30` |
| `--config PATH` | Custom config file | `config.yaml` | `--config custom.yaml` |

### Monitor Examples

#### **Standard Monitoring**
```bash
# Recommended setup - 2-minute intervals with Slack
python monitor_alpaca.py --interval 2 --slack-notify
```

#### **High-Frequency Monitoring**
```bash
# 1-minute intervals for active trading
python monitor_alpaca.py --interval 1 --slack-notify
```

#### **Custom Targets**
```bash
# Conservative 10% profit target, 20% stop loss
python monitor_alpaca.py --interval 2 --slack-notify --profit-target 10 --stop-loss 20
```

---

## 🔧 Utility Scripts

### Transaction Sync
```bash
# Sync last 7 days of Alpaca transactions
python -c "from utils.alpaca_transaction_sync import sync_alpaca_transactions; sync_alpaca_transactions(days=7)"

# Sync specific date range
python -c "from utils.alpaca_transaction_sync import sync_alpaca_transactions; sync_alpaca_transactions(days=1)"
```

### Data Reconciliation
```bash
# Run comprehensive data reconciliation
python reconcile_alpaca_data.py
```

### Configuration Validation
```bash
# Validate configuration file
python -c "from utils.llm import load_config; print('Config valid:', load_config('config.yaml') is not None)"
```

---

## ⚙️ Configuration Validation

### Required Environment Variables
```bash
# Alpaca API credentials
ALPACA_KEY_ID=your_key_id
ALPACA_SECRET_KEY=your_secret_key

# Slack integration (optional)
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_WEBHOOK_URL=https://hooks.slack.com/your-webhook
```

### Config File Validation
The system validates these critical settings:

#### **Broker Configuration**
- `BROKER`: Must be "alpaca" or "robinhood"
- `ALPACA_ENV`: Must be "paper" or "live"

#### **Risk Management**
- `START_CAPITAL`: Must be > 0
- `RISK_FRACTION`: Must be between 0.01 and 1.0
- `SIZE_RULE`: Must be "fixed-qty" or "dynamic-qty"

#### **Multi-Symbol Settings**
- `multi_symbol.enabled`: Boolean
- `multi_symbol.max_concurrent_trades`: Integer ≥ 1
- `multi_symbol.priority_order`: Array of valid symbols

#### **Data Sources**
- `DATA_SOURCE`: Must be "alpaca" or "yfinance"
- `alpaca.enabled`: Boolean
- `alpaca.fallback_to_yahoo`: Boolean

---

## 🚨 Error Handling & Troubleshooting

### Common Issues

#### **API Authentication Errors**
```bash
# Check API credentials
python -c "import os; print('Key ID:', 'Set' if os.getenv('ALPACA_KEY_ID') else 'Missing')"
python -c "import os; print('Secret:', 'Set' if os.getenv('ALPACA_SECRET_KEY') else 'Missing')"
```

#### **Configuration Errors**
```bash
# Validate config syntax
python -c "import yaml; yaml.safe_load(open('config.yaml'))"

# Test Alpaca connection
python -c "from utils.alpaca_client import AlpacaClient; print('Connected:', AlpacaClient().enabled)"
```

#### **Position File Issues**
```bash
# Check position file format
python -c "import csv; print('Positions:', len(list(csv.DictReader(open('positions_alpaca_live.csv')))))"

# Reset position file
echo "entry_time,symbol,expiry,strike,side,contracts,entry_premium" > positions_alpaca_live.csv
```

### Debug Mode
```bash
# Enable debug logging
python main.py --log-level DEBUG --broker alpaca --symbols SPY

# Monitor with debug output
python monitor_alpaca.py --interval 2 --slack-notify --log-level DEBUG
```

---

## 📈 Performance Optimization

### Recommended Settings

#### **Production Environment**
```bash
# Optimal balance of performance and safety
python main.py --broker alpaca --multi-symbol --loop --interval 5 --end-at 15:45 --slack-notify --i-understand-live-risk
python monitor_alpaca.py --interval 2 --slack-notify
```

#### **Development/Testing**
```bash
# Safe testing with full features
python main.py --broker alpaca --multi-symbol --loop --interval 10 --slack-notify --force-paper --dry-run
```

#### **Resource-Constrained Systems**
```bash
# Minimal resource usage
python main.py --broker alpaca --symbols SPY --loop --interval 10 --no-charts
```

---

## 🔒 Security Best Practices

### Environment Variables
- Store API keys in `.env` file (never commit to git)
- Use different keys for paper vs live trading
- Rotate API keys regularly

### Live Trading Safety
- Always test with `--force-paper` first
- Use `--max-trades` to limit exposure
- Monitor with `--slack-notify` for real-time alerts
- Set appropriate `--end-at` times to avoid overnight positions

### Configuration Security
- Keep `config.yaml` in `.gitignore`
- Use environment-specific config files
- Validate all configuration before live trading

---

This CLI reference covers all available options and provides practical examples for every use case. For additional help, use `python main.py --help` or `python monitor_alpaca.py --help`.
