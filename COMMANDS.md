# 🚀 Robinhood HA Breakout - Command Reference Guide

**Complete reference for all CLI commands and usage patterns**

---

## 📋 Quick Reference

### 🧪 **Testing & Development**
```bash
# Basic dry run (single symbol)
python main.py --dry-run

# Multi-symbol dry run
python main.py --multi-symbol --symbols SPY QQQ IWM --dry-run

# Debug mode with verbose logging
python main.py --dry-run --log-level DEBUG

# Test with specific symbol
python main.py --dry-run --symbol QQQ
```

### 🎯 **Single Trade Execution**
```bash
# Basic single trade (SPY)
python main.py

# Single trade with Slack notifications
python main.py --slack-notify

# Trade specific symbol
python main.py --symbol QQQ --slack-notify

# Multi-symbol scan, trade best opportunity
python main.py --multi-symbol --symbols SPY QQQ IWM --slack-notify
```

### 🔄 **Continuous Loop Mode**
```bash
# Basic loop mode (SPY, 5-minute intervals)
python main.py --loop

# Multi-symbol continuous scanning
python main.py --multi-symbol --symbols SPY QQQ IWM --loop

# Custom interval (3 minutes)
python main.py --multi-symbol --symbols SPY QQQ IWM --loop --interval 3

# Production setup with end time and Slack
python main.py --multi-symbol --symbols SPY QQQ IWM --loop --interval 5 --end-at 15:45 --slack-notify

# Conservative single-symbol with notifications
python main.py --loop --interval 5 --end-at 15:45 --slack-notify
```

### 📊 **Position Monitoring**
```bash
# Enhanced position monitoring with Alpaca data
python monitor_alpaca.py

# Integrated monitoring mode
python main.py --monitor-positions

# Monitoring with custom interval and end time
python main.py --monitor-positions --interval 2 --end-at 15:45 --slack-notify
```

### 📈 **Analytics & Reporting**
```bash
# Trading performance dashboard
python analytics_dashboard.py

# Trade history viewer
python trade_history_viewer.py

# Generate performance reports
python analytics_dashboard.py --export-html --export-csv

# Send analytics summary to Slack
python analytics_dashboard.py --slack-summary
```

### 🔧 **Utilities & Maintenance**
```bash
# Backup trading data
python backup_trading_data.py

# Manually log a trade
python log_spy_trade.py

# Record trade outcome for LLM calibration
python record_trade_outcome.py --win
python record_trade_outcome.py --loss
python record_trade_outcome.py --status

# Test Alpaca connection
python test_alpaca.py

# Test multi-symbol scanner
python test_multi_symbol.py
```

---

## 🔧 Command Line Arguments

### **Core Arguments**
| Argument | Description | Example |
|----------|-------------|---------|
| `--dry-run` | Analysis only, no browser automation | `--dry-run` |
| `--config` | Custom configuration file | `--config my_config.yaml` |
| `--log-level` | Logging verbosity | `--log-level DEBUG` |
| `--slack-notify` | Enable Slack notifications | `--slack-notify` |

### **Symbol Selection**
| Argument | Description | Example |
|----------|-------------|---------|
| `--symbol` | Single symbol to trade | `--symbol QQQ` |
| `--multi-symbol` | Enable multi-symbol mode | `--multi-symbol` |
| `--symbols` | List of symbols to scan | `--symbols SPY QQQ IWM` |
| `--max-trades` | Max concurrent trades | `--max-trades 2` |

### **Loop Mode**
| Argument | Description | Example |
|----------|-------------|---------|
| `--loop` | Enable continuous loop mode | `--loop` |
| `--interval` | Minutes between scans | `--interval 3` |
| `--end-at` | Stop time (HH:MM format) | `--end-at 15:45` |

### **Monitoring**
| Argument | Description | Example |
|----------|-------------|---------|
| `--monitor-positions` | Position monitoring mode | `--monitor-positions` |

---

## 🎯 Common Usage Patterns

### **Morning Scanner Setup**
```bash
# Conservative approach - single symbol with alerts
python main.py --loop --interval 5 --end-at 15:45 --slack-notify

# Aggressive approach - multi-symbol scanning
python main.py --multi-symbol --symbols SPY QQQ IWM --loop --interval 3 --end-at 15:45 --slack-notify
```

### **Position Management Workflow**
```bash
# 1. Start trading session
python main.py --multi-symbol --symbols SPY QQQ IWM --slack-notify

# 2. Monitor positions (separate terminal)
python monitor_alpaca.py

# 3. Check performance (end of day)
python analytics_dashboard.py --slack-summary
```

### **Testing & Development**
```bash
# 1. Test configuration
python main.py --dry-run --log-level DEBUG

# 2. Test multi-symbol logic
python test_multi_symbol.py

# 3. Test Alpaca connection
python test_alpaca.py

# 4. Verify Slack integration
python main.py --dry-run --slack-notify
```

---

## 🔍 Advanced Examples

### **Custom Trading Sessions**

**Conservative Day Trading:**
```bash
# Single symbol, longer intervals, early close
python main.py --symbol SPY --loop --interval 10 --end-at 14:30 --slack-notify
```

**Aggressive Multi-Symbol:**
```bash
# All symbols, short intervals, full day
python main.py --multi-symbol --symbols SPY QQQ IWM --loop --interval 2 --end-at 15:45 --slack-notify
```

**Paper Trading Simulation:**
```bash
# Dry run with multi-symbol and loop for testing
python main.py --multi-symbol --symbols SPY QQQ IWM --loop --interval 5 --end-at 15:45 --dry-run --slack-notify
```

### **Monitoring Configurations**

**High-Frequency Monitoring:**
```bash
# Check positions every minute
python monitor_alpaca.py --interval 1
```

**Conservative Monitoring:**
```bash
# Check positions every 5 minutes
python main.py --monitor-positions --interval 5 --end-at 15:45
```

### **Analytics & Reporting**

**Daily Performance Review:**
```bash
# Generate comprehensive report
python analytics_dashboard.py --export-html --export-csv --slack-summary
```

**Weekly Analysis:**
```bash
# View trade history and patterns
python trade_history_viewer.py
python analytics_dashboard.py
```

---

## 🛡️ Safety & Best Practices

### **Recommended Testing Sequence**
```bash
# 1. Verify configuration
python main.py --dry-run --log-level DEBUG

# 2. Test Slack integration
python main.py --dry-run --slack-notify

# 3. Test multi-symbol logic
python main.py --multi-symbol --symbols SPY QQQ IWM --dry-run

# 4. Short live test
python main.py --loop --interval 10 --end-at 10:00 --slack-notify

# 5. Full production
python main.py --multi-symbol --symbols SPY QQQ IWM --loop --interval 5 --end-at 15:45 --slack-notify
```

### **Production Monitoring Setup**
```bash
# Terminal 1: Trading scanner
python main.py --multi-symbol --symbols SPY QQQ IWM --loop --interval 5 --end-at 15:45 --slack-notify

# Terminal 2: Position monitoring
python monitor_alpaca.py

# Terminal 3: Available for manual commands
# (analytics, trade logging, etc.)
```

---

## 🔧 Environment Variables Required

```bash
# Robinhood credentials
RH_USER=your_email@example.com
RH_PASS=your_password

# LLM API (choose one)
OPENAI_API_KEY=sk-...
DEEPSEEK_API_KEY=sk-...

# Alpaca API (for real-time data)
ALPACA_API_KEY=your_alpaca_key
ALPACA_SECRET_KEY=your_alpaca_secret
ALPACA_BASE_URL=https://paper-api.alpaca.markets

# Slack integration (optional)
SLACK_WEBHOOK_URL=https://hooks.slack.com/...
SLACK_BOT_TOKEN=xoxb-...
SLACK_CHANNEL_ID=C...
```

---

## 📝 Configuration Files

### **config.yaml** (Main Configuration)
```yaml
# Trading parameters
START_CAPITAL: 500.0
RISK_FRACTION: 0.20
MIN_CONFIDENCE: 0.65

# Multi-symbol settings
SYMBOLS: ['SPY', 'QQQ', 'IWM']
multi_symbol:
  enabled: true
  max_concurrent_trades: 1

# Exit strategies
exit_strategies:
  trailing_stop_enabled: true
  trailing_stop_percentage: 20.0
  time_based_exit_enabled: true
  market_close_time: "15:45"
```

### **Key Files**
- `config.yaml` - Main configuration
- `.env` - Environment variables (credentials)
- `logs/trade_log.csv` - Trade history
- `bankroll.json` - Account balance tracking
- `positions.csv` - Current positions

---

## 🚨 Emergency Commands

### **Stop All Operations**
```bash
# Ctrl+C in any running terminal
# Or force kill if needed:
pkill -f "python main.py"
```

### **Data Recovery**
```bash
# Restore from backup
python backup_trading_data.py --restore

# Repair corrupted trade log
python analytics_dashboard.py  # Auto-repairs CSV
```

### **Reset Configuration**
```bash
# Backup current config
cp config.yaml config.yaml.backup

# Reset to defaults (manual edit required)
# Edit config.yaml with default values
```

---

## 📞 Support & Troubleshooting

### **Common Issues**
1. **Login failures**: Check RH_USER/RH_PASS in .env
2. **API errors**: Verify OPENAI_API_KEY or DEEPSEEK_API_KEY
3. **Slack issues**: Confirm SLACK_BOT_TOKEN and SLACK_CHANNEL_ID
4. **Data issues**: Run `python test_alpaca.py`

### **Debug Mode**
```bash
# Enable verbose logging for any command
python main.py --dry-run --log-level DEBUG
```

### **Log Files**
- `logs/app.log` - Application logs
- `logs/trade_log.csv` - Trade decisions and outcomes
- Console output for real-time status

---

*For detailed setup instructions, see [README.md](README.md)*  
*For system architecture, see [ARCHITECTURE.md](ARCHITECTURE.md)*
