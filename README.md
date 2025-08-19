# 📈 Robinhood HA Breakout Trading Assistant

**Fully Automated AI-Powered Options Trading System with Real-Time Alpaca Integration**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: Personal](https://img.shields.io/badge/license-Personal-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.12.0-brightgreen.svg)](CHANGELOG.md)
[![Multi-Symbol](https://img.shields.io/badge/multi--symbol-19%20Symbols-orange.svg)](#-multi-symbol-trading)
[![Real-Time Data](https://img.shields.io/badge/data-Alpaca%20API-blue.svg)](#-real-time-market-data)
[![Automated Execution](https://img.shields.io/badge/execution-Fully%20Automated-green.svg)](#-automated-execution)

---

## 🌟 What Is This?

**Robinhood HA Breakout** is a fully automated options trading system that:

- 📊 **Monitors 19 symbols** simultaneously with real-time Alpaca market data
- 🧠 **Makes intelligent decisions** using AI (OpenAI GPT-4o-mini or DeepSeek) with advanced market indicators
- 🚀 **Executes trades automatically** through Alpaca API (paper and live trading)
- 🎯 **Tracks positions in real-time** with automatic profit-taking at 15% targets
- 💰 **Manages risk intelligently** with symbol-specific liquidity requirements
- 📱 **Sends comprehensive Slack alerts** with charts, analysis, and execution confirmations
- 🔄 **Operates hands-free** with full automation from detection to execution
- 📈 **Syncs transaction data** directly from Alpaca API for 100% accuracy

**This is a complete automated trading system** - from market analysis to trade execution, position monitoring, and profit-taking, all running autonomously with your oversight.

### 🚀 **Current Features (v2.12.0 - SYSTEM ROBUSTNESS ENHANCEMENTS!)**
- 🚨 **Weekly Drawdown Protection**: Automatic system disable when weekly losses exceed 15% threshold
- 🚨 **Daily Drawdown Circuit Breaker**: Automatic trading halt when daily losses exceed 5% threshold
- 🚨 **VIX-Adjusted Position Sizing**: Dynamic position size reduction based on market volatility (VIX levels)
- 🚨 **VIX Spike Detection**: Automatic volatility monitoring blocks new trades when VIX > 30
- 🕒 **Market Hours Validation**: Enhanced validation with holidays and early close detection
- 📊 **Earnings Calendar Blocking**: Prevents trades within 24h of earnings announcements
- 📊 **Real-Time Status Dashboard**: Complete system monitoring via Slack `/trading-status` command  
- 🔄 **Automated Recovery System**: Self-healing with exponential backoff and escalation alerts
- 🎯 **Complete Automation Pipeline**: End-to-end automated trading system
  - ✅ **Multi-Symbol Scanning**: 19 symbols with symbol-specific liquidity requirements
  - ✅ **Real-Time Alpaca Integration**: Live market data and options pricing
  - ✅ **Automated Trade Execution**: Direct API order submission (paper & live)
  - ✅ **Intelligent Position Monitoring**: Real-time P&L tracking with 15% profit targets
  - ✅ **Hands-Free Exit Management**: Automatic sell orders via Alpaca API
  - ✅ **Transaction Data Sync**: Direct Alpaca API reconciliation ensures no missed trades
- 🧠 **Advanced AI Decision Engine**: Professional-grade market analysis
  - 📊 **VWAP Deviation Analysis**: Volume-weighted price deviation detection
  - 🎯 **ATM Delta Optimization**: Black-Scholes calculated option sensitivity
  - 💧 **Liquidity Assessment**: Real-time open interest and volume analysis
  - 🏛️ **Dealer Gamma Integration**: Market maker positioning insights
  - 🧠 **Context Memory System**: AI learns from recent trading patterns
- 🔒 **Enterprise-Grade Risk Management**: Multi-layered safety systems
  - 🚨 **Weekly Drawdown Protection**: System-wide disable at 15% weekly loss with manual reset requirement
  - 🚨 **Daily Drawdown Circuit Breaker**: Halts trading when daily losses exceed 5% threshold
  - 🚨 **VIX-Adjusted Position Sizing**: Dynamic position size reduction (50-75%) during high volatility periods
  - 🚨 **VIX Spike Protection**: Blocks new trades when volatility > 30 (configurable)
  - 🕒 **Market Hours Validation**: Holiday and early close detection prevents invalid trades
  - 📊 **Earnings Calendar Protection**: Blocks trades within 24h of earnings announcements
  - 💰 **Symbol-Specific Risk Controls**: Tailored position sizing per asset
  - 🛡️ **Environment Isolation**: Separate paper/live bankroll tracking
  - 🚨 **Real-Time Monitoring**: Continuous position and P&L surveillance
  - 📊 **Comprehensive Logging**: Full audit trail of all decisions and executions
- 📱 **Professional Notifications**: Mobile-optimized trading alerts
  - 📈 **Rich Slack Integration**: Charts, analysis, and execution confirmations
  - 🎯 **Real-Time Alerts**: Profit targets, stop losses, and market events
  - 📊 **Performance Reporting**: Daily, weekly, and monthly trading summaries

---

## 🎯 How It Works (Simple Explanation)

### The Magic Behind the Scenes

1. **📈 Market Analysis**
   - Downloads the latest SPY stock price data
   - Converts regular price charts to "Heikin-Ashi" charts (smoother, clearer trends)
   - Finds important support and resistance levels (like floors and ceilings for the stock price)

2. **🤖 AI Decision Making**
   - Sends all the market data to an AI (like ChatGPT)
   - The AI analyzes patterns and decides: "Buy a Call", "Buy a Put", or "Do Nothing"
   - Provides confidence levels and reasoning for each decision

3. **💰 Money Management**
   - Calculates how much money to risk based on your account size
   - Tracks all your trades and profits/losses
   - Never risks more than you can afford to lose

4. **🌐 Browser Automation**
   - Opens Chrome and logs into your Robinhood account
   - Navigates to the options trading page
   - Fills out the trade details automatically
   - **STOPS at the final "Submit" button** - you decide whether to click it!

### 🔄 Two Ways to Use It

#### 🎯 **One-Shot Mode** (Traditional)
- Run once, get one trade recommendation
- Perfect for manual trading sessions
- You control exactly when it runs

#### 🔄 **Continuous Loop Mode** (NEW!)
- Runs automatically every few minutes
- Monitors the market all morning
- Sends you notifications when opportunities arise
- Automatically stops at a time you set

---

## 🚀 Getting Started (Step-by-Step)

### What You'll Need

- **A computer** (Windows, Mac, or Linux)
- **Python 3.11 or newer** ([Download here](https://www.python.org/downloads/))
- **Google Chrome browser** (version 120 or newer)
- **A Robinhood account** with options trading enabled
- **An AI API key** (OpenAI or DeepSeek - we'll show you how to get one)
- **About 30 minutes** to set everything up

### Step 1: Download and Install

1. **Download this project** to your computer
2. **Open a terminal/command prompt** and navigate to the project folder
3. **Create a safe environment** for the project:
   ```bash
   python -m venv .venv
   ```
4. **Activate the environment**:
   - **Windows**: `.venv\Scripts\activate`
   - **Mac/Linux**: `source .venv/bin/activate`
5. **Install required software**:
   ```bash
   pip install -r requirements.txt
   ```

### Step 2: Get Your API Keys

#### Option A: OpenAI (Recommended for beginners)
1. Go to [OpenAI's website](https://platform.openai.com/)
2. Create an account and add a payment method
3. Generate an API key
4. **Cost**: About $0.10-0.50 per trading session

#### Option B: DeepSeek (Cheaper alternative)
1. Go to [DeepSeek's website](https://platform.deepseek.com/)
2. Create an account
3. Generate an API key
4. **Cost**: About $0.02-0.10 per trading session

### Step 3: Configure Your Settings

1. **Copy the example configuration**:
   ```bash
   cp config.example.yaml config.yaml
   ```

2. **Create your environment file**:
   ```bash
   cp .env.example .env
   ```

---

## 📊 **System Status Dashboard (NEW v2.5.0)**

### **Real-Time Monitoring via Slack**

Get complete system status with a single Slack command:

```bash
/trading-status
```

**Dashboard Features:**
- 🟢 **System Health**: Real-time monitoring (healthy/degraded/critical)
- 💰 **Active Positions**: P&L across all broker/environment combinations  
- 📈 **Daily Summary**: Trades, win rate, realized P&L
- 🏛️ **Market Conditions**: Market hours, VIX volatility, time to close
- 🔗 **API Status**: Connectivity to Alpaca, Slack, Yahoo Finance
- 🔄 **Recovery Status**: Automated recovery attempts and escalations

**Mobile-Optimized Display:**
```
🟢 Trading System Status

Status: Healthy          Uptime: 2h 15m
Last Update: 13:37:25    Recovery Active: No

Active Positions (3):
🟢 SPY (ALPACA/PAPER): $125.50 (+8.2%)
🔴 QQQ (ALPACA/PAPER): -$45.20 (-3.1%)

Trades Today: 2          Daily P&L: 🟢 $233.02
Win Rate: 🎯 100.0%      Total Unrealized: $158.60

Market: 🟢 Open          VIX: 🟡 18.5
API Status: 🟢 Alpaca | 🟢 Slack | 🟢 Yahoo_Finance
```

### **Automated Recovery System (v2.4.0)**

The system now includes self-healing capabilities:

- **🔄 Exponential Backoff**: Progressive retry delays (1s → 2s → 4s → 8s)
- **🌐 Network Monitoring**: Connectivity checks to all critical APIs
- **⚡ Auto-Recovery**: Handles API timeouts, network issues, service interruptions
- **📊 Escalation Alerts**: Manual intervention alerts after 3 failed attempts
- **📝 Comprehensive Logging**: All recovery attempts logged to `logs/recovery.log`

**Enhanced Error Handling:**
- Graceful degradation for Alpaca options authorization errors
- Improved logging precision with detailed rejection reasons
- Actionable error messages for troubleshooting

---

3. **Edit the `.env` file** with your information:
   ```
   RH_USER=your_robinhood_email@gmail.com
   RH_PASS=your_robinhood_password
   OPENAI_API_KEY=your_openai_key_here
   # OR
   DEEPSEEK_API_KEY=your_deepseek_key_here
   ```

4. **Edit the `config.yaml` file** to match your preferences:
   ```yaml
   START_CAPITAL: 1000.0        # Your starting trading capital
   RISK_FRACTION: 0.02          # Risk 2% of capital per trade
   MIN_CONFIDENCE: 0.65         # Only trade when AI is 65%+ confident
   MODEL: "gpt-4o-mini"         # AI model to use
   ```

---

## 🎮 How to Use It

### 🧪 Test Mode (Start Here!)

**Always test first!** This mode analyzes the market but doesn't open your browser:

```bash
# Single symbol analysis
python main.py --dry-run

# Multi-symbol analysis (NEW!)
python main.py --multi-symbol --symbols SPY QQQ IWM --dry-run
```

**What you'll see:**
- Market analysis results for all symbols
- AI's trading decisions and reasoning
- Risk calculations and opportunity prioritization
- No browser automation (safe to run anytime)

### 🚀 Live Trading Mode

**For single trade sessions:**

```bash
# Single symbol trading
python main.py

# Multi-symbol trading (scans all, trades best opportunity)
python main.py --multi-symbol --symbols SPY QQQ IWM
```

**What happens:**
1. Analyzes current market conditions across selected symbols
2. AI prioritizes opportunities by confidence and technical strength
3. Opens Chrome and logs into Robinhood
4. Navigates to the options page for the best opportunity
5. Fills out the trade details
6. **Stops at the Review screen** - you decide whether to submit!

### 🚀 Automated Alpaca Trading (FULLY OPERATIONAL)

**Complete automated trading system with real-time execution:**

```bash
# Paper trading (safe testing environment)
python main.py --broker alpaca --symbols SPY

# Multi-symbol automated trading (19 symbols)
python main.py --broker alpaca --multi-symbol

# Live trading (requires explicit risk acknowledgment)
python main.py --broker alpaca --symbols SPY --i-understand-live-risk

# Continuous automated trading with monitoring
python main.py --broker alpaca --multi-symbol --loop --interval 5 --slack-notify

# Position monitoring only (track existing positions)
python monitor_alpaca.py --interval 2 --slack-notify
```

**Complete Automated Workflow:**
1. **Multi-Symbol Scanning**: Monitors 19 symbols simultaneously with real-time Alpaca data
2. **AI Decision Engine**: Advanced market analysis with VWAP, delta, and gamma indicators
3. **Automated Execution**: Direct API order submission with no manual intervention
4. **Real-Time Monitoring**: Continuous position tracking with 15% profit targets
5. **Automatic Exit Management**: Hands-free sell orders when profit targets hit
6. **Transaction Sync**: Direct Alpaca API reconciliation ensures 100% accuracy
7. **Comprehensive Alerts**: Slack notifications for all trading events and P&L updates

**Automation Features:**
- ✅ **Symbol-Specific Risk Management**: Tailored liquidity requirements per asset
- ✅ **Intelligent Contract Selection**: ATM options with optimal volume/OI ratios
- ✅ **Hands-Free Execution**: Complete automation from detection to profit-taking
- ✅ **Real-Time Data Integration**: Professional Alpaca market feeds
- ✅ **Advanced Exit Strategies**: 15% profit targets with automatic execution
- ✅ **Enterprise Logging**: Full audit trail of all decisions and executions

### 🔄 Continuous Loop Mode (NEW!)

**For automated morning scanning:**

```bash
# Basic single-symbol loop - checks SPY every 5 minutes
python main.py --loop

# Multi-symbol loop - scans SPY, QQQ, IWM every 5 minutes
python main.py --multi-symbol --symbols SPY QQQ IWM --loop

# Custom interval - checks every 3 minutes
python main.py --multi-symbol --symbols SPY QQQ IWM --loop --interval 3

# Full production setup - multi-symbol with Slack alerts
python main.py --multi-symbol --symbols SPY QQQ IWM --loop --interval 5 --end-at 15:45 --slack-notify

# Conservative single-symbol with notifications
python main.py --loop --interval 5 --end-at 15:45 --slack-notify
```

**What happens in loop mode:**
- Runs continuously until you stop it (Ctrl+C) or reach the end time
- Checks the market every few minutes
- Sends "heartbeat" messages when there's no trade opportunity
- When it finds a good trade, it prepares everything and notifies you
- Keeps the browser open between checks (more efficient)
- Automatically restarts the browser if it's been idle for 4+ hours

### 🧠 Enhanced LLM Decision Engine (NEW!)

**Professional-grade AI trading with 4 new enhanced features:**

- **📊 VWAP Deviation Analysis**: Real-time deviation from 5-minute volume-weighted average price
- **🎯 ATM Delta Calculation**: Black-Scholes option sensitivity for optimal timing
- **💧 Liquidity Assessment**: Open interest analysis for better trade execution
- **🏛️ Market Structure Intelligence**: Dealer gamma positioning for volatility prediction
- **🧠 Context Memory**: LLM learns from recent trades and adapts strategy
- **🔄 Robust Data Fallback**: Automatic Yahoo Finance backup when Alpaca is unavailable

### Enhanced LLM Features

The system includes professional-grade market analysis features with dynamic threshold adjustment:

### VWAP Deviation Analysis
- Real-time deviation from 5-minute volume-weighted average price
- Identifies when price moves significantly from institutional levels
- Helps confirm breakout authenticity
- **Rule**: >0.2% deviation suggests institutional interest

### ATM Delta Calculation
- Black-Scholes option sensitivity analysis
- Optimal timing for option entry based on delta values
- Risk assessment for position sizing
- **Rule**: Delta 0.45-0.55 optimal for ATM trades

### ATM Open Interest Assessment
- Liquidity analysis for better trade execution
- Market maker positioning insights
- Volume confirmation signals
- **Rule**: >10,000 OI suggests good liquidity

### Dealer Gamma Intelligence
- Market maker positioning data for volatility prediction
- Gamma exposure analysis for market direction
- Enhanced breakout confirmation
- **Rule**: Negative gamma = higher volatility expected

### Dynamic Candle-Body Threshold (NEW in v0.6.1)
- **Adaptive threshold based on dealer gamma exposure**
- Standard threshold: 0.05% candle body
- Strong negative gamma (<-$1M): Lowered to 0.025% (50% reduction)
- Moderate negative gamma (<$0): Lowered to 0.0375% (25% reduction)
- Positive gamma: Standard 0.05% threshold maintained
- **Rationale**: Negative dealer gamma indicates market makers are short gamma, leading to higher volatility and more significant price moves on smaller candle bodies

### 🤖 Ensemble LLM Decision Engine (v0.6.0)

**Two-model ensemble for enhanced decision reliability:**

- **🗳️ Majority Voting**: GPT-4o-mini and DeepSeek-V2 both analyze market data and vote
- **🎯 Tie-Breaking**: Higher confidence model wins when decisions differ
- **📊 Confidence Averaging**: Final confidence is average of winning class
- **🛡️ Fault Tolerance**: Single-model fallback if one provider fails
- **⚙️ Configuration Toggle**: Enable/disable via `ENSEMBLE_ENABLED` setting

**Benefits:**
- Reduced model bias through diverse LLM architectures
- Improved decision reliability with majority consensus
- Enhanced confidence scoring with ensemble validation
- Robust operation even with provider failures

**Configuration options in `config.yaml`:**
```yaml
# Enhanced LLM Features
MEMORY_DEPTH: 5  # Number of recent trades to remember
GAMMA_FEED_PATH: "data/spotgamma_dummy.csv"  # SpotGamma data source

# Ensemble LLM Decision Engine (v0.6.0)
ENSEMBLE_ENABLED: true  # Enable two-model ensemble decision making
ENSEMBLE_MODELS:        # List of models to use in ensemble
  - "gpt-4o-mini"
  - "deepseek-chat"

# Multi-Symbol Trading
llm_batch_analysis: true  # Enable batching for cost savings
multi_symbol:
  enabled: true
  max_concurrent_trades: 1  # Conservative approach
  priority_order: ["SPY", "QQQ", "IWM"]  # Trade preference order

# Data Sources (with fallback)
alpaca:
  enabled: true  # Primary real-time data source
  fallback_to_yahoo: true  # Automatic fallback on connection issues
```

### 🔄 AI Reliability & Error Recovery

**Bulletproof multi-symbol LLM integration with advanced error recovery:**

- **Robust Error Recovery**: Automatic retry logic with exponential backoff for API failures
- **Rate Limit Protection**: Smart delays and progressive wait times to prevent API throttling
- **Context Isolation**: Fresh AI analysis for each symbol to prevent cross-contamination
- **Standardized Data**: Consistent market data structure ensures reliable AI decisions
- **Batch Analysis**: Optional batching for multiple symbols to reduce API costs
- **Graceful Degradation**: Falls back to safe NO_TRADE decisions on persistent failures

### 📊 Position Monitoring (FULLY AUTOMATED)

**Real-time position tracking with automatic profit-taking:**

```bash
# Standard monitoring (recommended)
python monitor_alpaca.py --interval 2 --slack-notify

# High-frequency monitoring
python monitor_alpaca.py --interval 1 --slack-notify

# Monitoring with custom profit targets
python monitor_alpaca.py --interval 2 --slack-notify --profit-target 20
```

**Automated Position Management:**
- ✅ **Real-Time P&L Tracking**: Live Alpaca market data with 2-minute intervals
- ✅ **Automatic Profit-Taking**: 15% target triggers interactive exit confirmation
- ✅ **Hands-Free Execution**: Choose [S] and system submits sell orders via API
- ✅ **Stop-Loss Protection**: 25% loss threshold with automatic alerts
- ✅ **End-of-Day Management**: 3:45 PM ET warnings for position closure
- ✅ **Transaction Reconciliation**: Direct Alpaca API sync ensures accuracy
- ✅ **Mobile Notifications**: Comprehensive Slack alerts with charts and analysis

**Complete monitoring workflow:**

1. **Start your trading session:**
   ```bash
   python main.py --loop --interval 5 --end-at 15:45 --slack-notify
   ```

2. **When you get a position, start monitoring:**
   ```bash
   python monitor_alpaca.py  # In a separate terminal
   ```

3. **Get mobile alerts for:**
   - 🎯 **Profit targets hit** (5%, 10%, 15%, 20%+)
   - 🛑 **Stop loss triggered** (25% loss protection)
   - ⏰ **End-of-day warnings** (close by 3:45 PM ET)

**Example monitoring output:**
```
[MONITOR] SPY $628.0 CALL: $1.83 (+28.9%)
[ALERT] Profit target 25% hit for SPY $628.0 CALL
[SLACK] Mobile notification sent
```

**Data quality advantage:**
- Uses **Alpaca real-time data** (same quality as professional traders)
- No more **15-20 minute delays** that cause missed opportunities
- **Professional option price estimation** using current volatility
- **Same data quality** that enabled your +28.9% manual profit

---

## 📱 Slack Notifications (Optional)

**Get real-time updates on your phone!**

### Setup Slack Integration

1. **Create a Slack workspace** (if you don't have one)
2. **Create a Slack app** and get a webhook URL
3. **Add to your `.env` file**:
   ```
   SLACK_WEBHOOK_URL=your_slack_webhook_url_here
   ```
4. **Use the `--slack-notify` flag** when running

### What You'll Receive

#### 📊 **Heartbeat Messages** (Loop Mode)
```
⏳ 09:35 · No breakout (body 0.07%)
⏳ 09:40 · No breakout (body 0.12%)
⚠️ 09:45 · Low confidence CALL (0.58)
```

#### 🚨 **Trade Alert Messages**
```
📈 09:50 · CALL ready
Strike     $635
Δ          0.42
Confidence 0.68
Reason: Strong bullish breakout above resistance
```

---

## ⚙️ Configuration Options

### Basic Settings (`config.yaml`)

```yaml
# Trading Parameters
SYMBOL: "SPY"                    # Stock to trade (currently only SPY)
START_CAPITAL: 1000.0            # Your starting trading capital
RISK_FRACTION: 0.02              # Risk 2% of capital per trade
MIN_CONFIDENCE: 0.65             # Minimum AI confidence to trade

# AI Settings
MODEL: "gpt-4o-mini"             # AI model (gpt-4o-mini or deepseek-chat)

# Technical Analysis
LOOKBACK_BARS: 20                # How many candles to analyze
MIN_BODY_PCT: 0.3                # Minimum candle body size

# Browser Settings
HEADLESS: false                  # Show browser (true = hidden)
IMPLICIT_WAIT: 10                # How long to wait for elements
PAGE_LOAD_TIMEOUT: 30            # Page load timeout

# File Locations
TRADE_LOG_FILE: "trade_log.csv"   # Where to save trade history
BANKROLL_FILE: "bankroll.json"   # Where to save money tracking
LOG_FILE: "logs/app.log"         # Where to save system logs
```

### Advanced Options

- **`--config custom.yaml`**: Use a different configuration file
- **`--log-level DEBUG`**: See detailed technical information
- **`--dry-run`**: Test mode - no browser automation
- **`--slack-notify`**: Enable Slack notifications

---

## 🛡️ Safety Features

### What Keeps You Safe

1. **🚫 Never Auto-Submits Trades**
   - Always stops at Robinhood's Review screen
   - You have final control over every trade
   - No "fat finger" accidents

2. **💰 Built-in Risk Management**
   - Never risks more than your set percentage
   - Tracks your total capital in real-time
   - Prevents over-leveraging

3. **🧠 AI Confidence Filtering**
   - Only suggests trades when AI is highly confident
   - You can adjust the minimum confidence level
   - Provides reasoning for every decision

4. **📊 Complete Transparency**
   - Logs every decision and calculation
   - Shows you exactly what the AI is thinking
   - Tracks all trades for tax purposes

5. **🔒 Secure Credential Handling**
   - Stores passwords in encrypted environment files
   - Never logs sensitive information
   - Uses secure browser automation

### What Could Go Wrong (And How We Handle It)

- **🌐 Internet Connection Issues**: The system will retry and log errors
- **🏦 Robinhood Login Problems**: You'll get clear error messages
- **🤖 AI Service Downtime**: The system will skip that cycle and try again
- **💻 Browser Crashes**: Automatic restart in loop mode
- **📱 Phone Notifications**: Optional Slack alerts keep you informed

---

## 📊 Understanding the Output

### What the AI Tells You

```
[DECISION] LLM Decision: CALL (confidence: 0.72)
[REASON] Strong bullish breakout above $634 resistance with high volume
```

**Translation**: The AI thinks you should buy a Call option because the stock price broke above an important resistance level with strong buying pressure. It's 72% confident in this decision.

### Market Analysis Example

```
[MARKET] Market analysis: BULLISH trend, price $635.42, body 0.45%
```

**Translation**: The overall trend is bullish (upward), SPY is currently at $635.42, and the latest candle has a 0.45% body size (indicating moderate momentum).

### Risk Calculations

```
[BANKROLL] Current bankroll: $1000.00
[POSITION] Position size: $20.00 (2.0% risk)
```

**Translation**: You have $1,000 to trade with, and this trade will risk $20 (2% of your capital).

---

## 🔧 Troubleshooting

### Common Issues and Solutions

#### "ModuleNotFoundError" when running
**Problem**: Missing Python packages
**Solution**: 
```bash
pip install -r requirements.txt
```

#### "ChromeDriver not found"
**Problem**: Chrome browser issues
**Solution**: 
- Update Chrome to the latest version
- Restart your computer
- Try running with `--headless` flag

#### "Login failed" in Robinhood
**Problem**: Authentication issues
**Solution**: 
- Check your username/password in `.env`
- Complete MFA on your phone when prompted
- Make sure your Robinhood account has options trading enabled

#### "API key invalid"
**Problem**: AI service authentication
**Solution**: 
- Double-check your API key in `.env`
- Make sure you have credits/billing set up
- Try regenerating the API key

#### "No trade signal" repeatedly
**Problem**: Market conditions or settings
**Solution**: 
- Lower the `MIN_CONFIDENCE` in config.yaml
- Check if the market is open
- Try `--dry-run` to see the AI's reasoning

### Getting Help

1. **Check the logs**: Look in `logs/app.log` for detailed error messages
2. **Run in debug mode**: Use `--log-level DEBUG` for more information
3. **Test in dry-run**: Use `--dry-run` to isolate issues
4. **Check your configuration**: Verify all settings in `config.yaml` and `.env`

---

## 🏦 Broker & Environment (v0.9.0)

**Safe Paper Trading & Live Trading Support** - Test strategies without risk!

### 🎯 Trading Environments

The system now supports multiple broker/environment combinations with completely isolated ledgers:

#### 📊 **Alpaca Paper Trading** (Recommended for Testing)
```bash
# Paper trading with virtual money
python main.py --broker alpaca --alpaca-env paper --loop --interval 5
```
- ✅ **Risk-free testing** with virtual $100,000 account
- ✅ **Real market data** and conditions
- ✅ **Full system validation** without financial risk
- ✅ **Separate ledger files** for isolated tracking

#### 💰 **Alpaca Live Trading** (Real Money)
```bash
# Live trading with real money (requires safety flag)
python main.py --broker alpaca --alpaca-env live --i-understand-live-risk --loop
```
- ⚠️ **Real money at risk** - use with extreme caution
- ✅ **Professional execution** with institutional-grade infrastructure
- ✅ **Separate ledger files** for isolated tracking
- 🛡️ **Safety interlocks** require explicit acknowledgment

#### 🤖 **Robinhood Trading** (Browser Automation)
```bash
# Traditional Robinhood browser automation
python main.py --broker robinhood
```
- ✅ **Manual confirmation** required for every trade
- ✅ **Browser automation** with human oversight
- ✅ **Separate ledger files** for isolated tracking

### 🗂️ Separate Ledger Files

Each broker/environment combination maintains completely isolated files:

```
# Alpaca Paper Trading
bankroll_alpaca_paper.json
logs/trade_history_alpaca_paper.csv
positions_alpaca_paper.csv

# Alpaca Live Trading
bankroll_alpaca_live.json
logs/trade_history_alpaca_live.csv
positions_alpaca_live.csv

# Robinhood Trading
bankroll_robinhood_live.json
logs/trade_history_robinhood_live.csv
positions_robinhood_live.csv
```

### 🔧 Configuration

Add to your `config.yaml`:
```yaml
# Broker & Environment Configuration
BROKER: "robinhood"            # "alpaca" | "robinhood"
ALPACA_ENV: "paper"             # "paper" | "live"
ALPACA_PAPER_BASE_URL: "https://paper-api.alpaca.markets"
ALPACA_LIVE_BASE_URL: "https://api.alpaca.markets"
START_CAPITAL_DEFAULT: 500      # seed for new ledgers
```

Add to your `.env` file:
```bash
# Alpaca API Credentials
ALPACA_KEY_ID=your_alpaca_key_id
ALPACA_SECRET_KEY=your_alpaca_secret_key
```

### 🛡️ Safety Features

#### Live Trading Protection
- **Explicit flag required**: `--i-understand-live-risk` must be provided
- **Automatic fallback**: Defaults to paper trading if flag missing
- **Clear warnings**: Loud alerts when live trading is active
- **Separate ledgers**: No risk of contaminating paper trading data

#### Dry Run Override
```bash
# Test full pipeline without placing orders
python main.py --broker alpaca --alpaca-env paper --dry-run
```

### 📊 Usage Examples

#### Start with Paper Trading
```bash
# Test the system safely
python main.py --broker alpaca --alpaca-env paper --multi-symbol --loop --interval 5 --end-at 11:00
```

#### Graduate to Live Trading
```bash
# When ready for real money (use with caution!)
python main.py --broker alpaca --alpaca-env live --i-understand-live-risk --symbols SPY --loop
```

#### Monitor Paper Positions
```bash
# Monitor paper trading positions
python main.py --broker alpaca --alpaca-env paper --monitor-positions --interval 15
```

### 🔄 Switching Between Environments

You can safely switch between environments without affecting other ledgers:

```bash
# Morning: Test strategy in paper
python main.py --broker alpaca --alpaca-env paper --loop --end-at 10:00

# Afternoon: Execute in live (if confident)
python main.py --broker alpaca --alpaca-env live --i-understand-live-risk --loop --end-at 15:45
```

Each environment maintains its own:
- 💰 **Bankroll tracking**
- 📈 **Trade history**
- 📊 **Position monitoring**
- 📱 **Slack notifications** (tagged with [PAPER]/[LIVE]/[RH])

### 🏷️ Slack Environment Tags

All Slack messages are tagged with the current environment:

```
🚀 [PAPER] Submitted CALL SPY 580 x1 @ MKT
⏳ 09:42 · SPY · no breakout · [ALPACA:PAPER]
🟢 [LIVE] Monitor started for QQQ
📊 [RH] Daily Summary: 3 trades, +$45.50
```

---

## 📱 Slack UX Improvements (v0.7.0)

**Zero Manual Terminal Watching Required** - Get all updates directly in Slack!

### 🟢 S1: Monitor Breadcrumbs
Automatic start/stop notifications when position monitoring begins or ends:
```
🟢 Monitor started for SPY
🔴 Monitor stopped for SPY
```

### ⏳ S2: Throttled Heartbeat
Periodic "still alive" messages during loop mode to confirm system is running:
```
⏳ Cycle 6 (14:30) · SPY $580.25 · NO_TRADE
⏳ Cycle 12 (15:00) · SPY $582.10, QQQ $485.50 · NO_TRADE
```
- Configurable via `HEARTBEAT_EVERY` in config.yaml (default: every 3 cycles)
- Prevents Slack spam while keeping you informed

### ✅ S3: Fill-Price Echo
Immediate confirmation when trades are recorded with actual fill prices:
```
✅ Trade recorded: CALL 580 @ $1.28 · Qty 1
❌ Trade cancelled: PUT 485
```
- Shows actual fill price vs. estimated price
- Confirms successful trade recording
- Mobile-friendly format for quick review

### 📊 S4: Daily Summary Block
End-of-day wrap-up when loop mode exits at `--end-at` time:
```
📊 Daily Wrap-Up 15:45 EST
Trades: 3
Wins/Loss: 2/1
P&L: $45.50
Peak balance: $545.50
Current balance: $540.25
```

### Configuration
Add to your `config.yaml`:
```yaml
# Slack UX Settings
HEARTBEAT_EVERY: 3  # Send heartbeat every N cycles (0 = disabled)
```

### Benefits
- **No terminal watching**: Get all updates in Slack
- **Mobile trading**: Make decisions from your phone
- **Peace of mind**: Always know system status
- **Complete audit trail**: Every action is logged to Slack

---

## 📈 Performance and Costs

### Expected Costs

- **OpenAI API**: $0.10-0.50 per trading session
- **DeepSeek API**: $0.02-0.10 per trading session
- **Loop mode**: Multiply by number of cycles (e.g., 8 hours × 12 cycles/hour = 96 cycles)

### Performance Tips

- **Use DeepSeek** for lower API costs
- **Increase interval** in loop mode to reduce API calls
- **Set end times** to avoid unnecessary cycles
- **Use dry-run** for testing without costs

### System Requirements

- **RAM**: 4GB minimum, 8GB recommended
- **CPU**: Any modern processor
- **Internet**: Stable broadband connection
- **Storage**: 1GB free space for logs and data

---

## 🎓 Learning Resources

### Understanding the Strategy

- **Heikin-Ashi Candles**: Smoothed candlesticks that filter out market noise
- **Support/Resistance**: Price levels where stocks tend to bounce or break through
- **Breakout Trading**: Buying when price breaks above resistance (calls) or below support (puts)
- **Risk Management**: Never risking more than a small percentage of your capital

### Recommended Reading

- "Options as a Strategic Investment" by Lawrence G. McMillan
- "Technical Analysis of the Financial Markets" by John J. Murphy
- "The Intelligent Investor" by Benjamin Graham

### Practice Recommendations

1. **Start with dry-run mode** for at least a week
2. **Use small position sizes** when you start live trading
3. **Keep detailed notes** of what works and what doesn't
4. **Review your trade log regularly** to learn from results

---

## 📋 Quick Reference

### Essential Commands

```bash
# Test mode (safe)
python main.py --dry-run

# Single trade
python main.py

# Continuous monitoring
python main.py --loop --interval 5 --end-at 12:00 --slack-notify

# Debug mode
python main.py --dry-run --log-level DEBUG
```

### Important Files

- **`.env`**: Your passwords and API keys
- **`config.yaml`**: Trading settings and preferences
- **`trade_log.csv`**: History of all trades and decisions
- **`bankroll.json`**: Your current capital and performance
- **`logs/app.log`**: Detailed system logs

### Safety Checklist

- ✅ Tested in dry-run mode first
- ✅ Set appropriate risk limits
- ✅ Verified Robinhood login works
- ✅ Confirmed API keys are valid
- ✅ Understood that final trade approval is manual
- ✅ Set up Slack notifications (optional)
- ✅ Reviewed configuration settings

---

**Remember: This tool is designed to assist your trading decisions, not replace your judgment. Always review each trade carefully before submitting, and never risk more than you can afford to lose.**

*Happy Trading! 📈*

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+**
- **Chrome 120+** (ChromeDriver handled automatically)
- **Robinhood account** with MFA enabled
- **LLM API key**: OpenAI or DeepSeek

### Installation

```bash
# Clone or download the project
cd robinhood-ha-breakout

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Environment Setup

1. Copy the environment template:
```bash
cp .env.example .env
```

2. Edit `.env` with your credentials:
```bash
# Robinhood Credentials
RH_USER=your_email@example.com
RH_PASS=your_password_here

# LLM API Key (choose one)
OPENAI_API_KEY=sk-your_openai_key_here
# OR
DEEPSEEK_API_KEY=your_deepseek_key_here
```

### First Run

```bash
# Test with dry run (no browser automation)
python main.py --dry-run

# Full run (opens browser, requires MFA)
python main.py
```

## 📋 How It Works

### 1. Enhanced Market Data Analysis
- **Real-Time Data**: Alpaca API for professional-grade market data (falls back to Yahoo Finance)
- **Multi-Timeframe**: Fetches 1-minute and 5-minute candles for comprehensive analysis
- **Heikin-Ashi Conversion**: Smoother trend analysis with reduced noise
- **Support/Resistance**: Advanced pivot point detection for key levels
- **Volatility Metrics**: True Range and ATR calculations
- **Enhanced Features**: 4 new professional-grade metrics for LLM analysis

### 2. Enhanced LLM Decision Making
The LLM now receives enriched market data with professional-grade features:

```json
{
  "decision": "CALL|PUT|NO_TRADE",
  "confidence": 0.75,
  "reason": "Strong bullish breakout with volume confirmation",
  "enhanced_features": {
    "vwap_deviation_pct": 0.8,
    "atm_delta": 0.55,
    "atm_oi": 12500,
    "dealer_gamma_$": -250000000
  },
  "recent_trades_context": "Last 5 trades: 3 wins, 2 losses"
}
```

**🧠 Enhanced LLM Features:**
- **📊 VWAP Deviation**: Real-time deviation from 5-minute volume-weighted average price
  - Positive = Price above institutional benchmark (bullish pressure)
  - Negative = Price below institutional benchmark (bearish pressure)
- **🎯 ATM Delta**: Black-Scholes calculated option sensitivity
  - Higher delta = More sensitive to price moves (better for momentum)
  - Lower delta = Less sensitive (safer but lower profit potential)
- **💧 ATM Open Interest**: Liquidity assessment for trade execution
  - High OI (10,000+) = Tight spreads, easy entry/exit
  - Low OI (<1,000) = Wide spreads, poor execution
- **🏛️ Dealer Gamma**: Market maker positioning from SpotGamma
  - Negative gamma = Volatility amplification expected
  - Positive gamma = Range-bound behavior likely

**🧠 Context Memory System:**
- LLM remembers last 5 trades and their outcomes
- Learns from previous decisions and market conditions
- Adapts strategy based on recent performance patterns

**Decision Rules:**
- Enhanced features weighted into confidence calculation
- VWAP deviation signals momentum strength
- ATM delta optimizes risk/reward timing
- Open interest ensures good execution quality
- Dealer gamma predicts volatility behavior
- Context memory prevents repeating recent mistakes
- Confidence < 0.35 overrides to NO_TRADE

### 3. Risk Management
- **Position Sizing**: Fixed quantity or dynamic based on bankroll percentage
- **Risk Validation**: Blocks trades exceeding 50% of bankroll
- **Bankroll Tracking**: Maintains running P/L and performance metrics

### 4. Browser Automation
- Launches undetected Chrome to avoid bot detection
- Logs into Robinhood with manual MFA approval
- Navigates to SPY options chain
- Selects nearest-expiry ATM contract
- Pre-fills order and **STOPS at Review screen**

### 5. Manual Review
You decide whether to:
- ✅ Click "Submit" to execute the trade
- ❌ Cancel if you disagree with the analysis
- 🔄 Request similar trade suggestions

## 🏦 Bankroll Management

### Initial Setup
- **Start Capital**: $40 (configurable in `config.yaml`)
- **Risk Fraction**: 50% max per trade (configurable)
- **Size Rules**: 
  - `fixed-qty`: Always trade 1 contract (default)
  - `dynamic-qty`: Size based on risk percentage

### Position Sizing Examples

**Fixed Quantity (default):**
```yaml
SIZE_RULE: "fixed-qty"
CONTRACT_QTY: 1
```
- Always trades 1 contract
- Blocks trade if premium > 50% of bankroll

**Dynamic Quantity:**
```yaml
SIZE_RULE: "dynamic-qty" 
RISK_FRACTION: 0.30  # Risk 30% of bankroll
```
- If bankroll = $100, risk = $30
- If option premium = $5, trade 6 contracts ($30 ÷ $5)
- If option premium = $40, trade 1 contract (minimum)

## 📖 Detailed Usage Guide

### Basic Usage

#### 1. Test Run (Recommended First)
```bash
# Dry run - analyzes market but skips browser automation
python main.py --dry-run
```
**What happens:**
- Fetches SPY market data
- Calculates Heikin-Ashi candles and support/resistance
- Gets LLM trade decision
- Shows what trade would be made
- No browser opens, no login required

#### 2. Live Trading Run
```bash
# Full run - opens browser and navigates to Review screen
python main.py
```
**What happens:**
- All dry-run analysis steps
- Opens Chrome browser
- Logs into Robinhood (requires MFA)
- Navigates to options chain
- Pre-fills order and stops at Review
- You manually decide to submit or cancel

#### 3. With Slack Notifications
```bash
# Get real-time alerts on your phone/desktop
python main.py --slack-notify
```
**Requires:** `SLACK_WEBHOOK_URL` in your `.env` file

### Advanced Usage

#### Position Management
The system now tracks open positions and automatically determines whether to OPEN or CLOSE trades:

```bash
# View current positions
python manage_positions.py list

# Add position manually (if opened outside the system)
python manage_positions.py add

# Remove position by ID
python manage_positions.py remove 1

# Show position statistics
python manage_positions.py stats
```

#### Trade Outcome Recording
For LLM confidence calibration, record your trade results:

```bash
# Record a winning trade
python record_trade_outcome.py win

# Record a losing trade
python record_trade_outcome.py loss

# View current statistics
python record_trade_outcome.py stats
```

### Typical Trading Workflow

#### Morning Setup (5-10 minutes)
1. **Check Market Conditions**
   ```bash
   python main.py --dry-run
   ```
   - Review LLM decision and confidence
   - Check if market conditions favor trading

2. **Review Positions**
   ```bash
   python manage_positions.py list
   ```
   - See open positions from previous sessions
   - Check if any need closing

#### Live Trading Session
1. **Run Full System**
   ```bash
   python main.py --slack-notify
   ```

2. **System Analysis** (Automatic)
   - Fetches latest 5-min SPY data
   - Calculates Heikin-Ashi candles
   - Identifies support/resistance levels
   - LLM analyzes breakout potential

3. **Position Logic** (Automatic)
   - **OPEN**: No existing position → Opens new trade
   - **CLOSE**: Existing position found → Closes existing trade

4. **Browser Navigation** (Automatic)
   - Opens Chrome with Robinhood
   - Handles login (you approve MFA)
   - Navigates to appropriate page:
     - **OPEN**: Options chain → ATM contract
     - **CLOSE**: Positions page → Your position
   - Pre-fills order details
   - **STOPS at Review screen**

5. **Manual Decision** (Your Choice)
   ```
   ========================================
   [OPEN TRADE READY FOR REVIEW]
   ========================================
   Direction: CALL
   Strike: $635
   Quantity: 1 contracts
   Premium: $2.50 per contract
   Total Cost: $2.50
   Confidence: 0.65
   
   🚨 MANUAL REVIEW REQUIRED - DO NOT AUTO-SUBMIT
   ✅ Review the order details above and submit manually if approved
   ========================================
   ```
   
   **Your options:**
   - ✅ **Submit**: Click Submit in browser if you agree
   - ❌ **Cancel**: Close browser if you disagree
   - 🤔 **Research**: Use browser to check additional indicators

6. **Post-Trade Actions**
   - **If OPEN**: Enter actual fill price when prompted
   - **If CLOSE**: Enter exit price and record win/loss
   - System updates position ledger automatically

### 📱 Slack Trade Confirmation

The system now supports remote trade confirmation via Slack messages, perfect for mobile trading:

#### Setup
1. Ensure `SLACK_BOT_TOKEN` is configured in your `.env` file
2. Invite the bot to your trading channel
3. The bot will listen for confirmation messages

#### Confirmation Messages
After reaching the Review screen, send one of these messages to your Slack channel:

**✅ Submitted at Expected Price:**
```
submitted
```

**✅ Submitted at Custom Price:**
```
filled $1.27
filled 0.85
```

**❌ Cancelled Trade:**
```
cancelled
```

#### Bot Responses
The bot will respond with an ephemeral confirmation:
```
✅ Trade recorded (SUBMITTED @ $1.27)
❌ Trade recorded (CANCELLED)
```

#### Benefits
- **Mobile-friendly**: Confirm trades from your phone
- **Accurate logging**: Automatically records actual fill prices
- **Bankroll reconciliation**: Adjusts bankroll based on real premiums
- **Audit trail**: All confirmations logged with timestamps

#### End of Session
1. **Record Outcomes** (if not done automatically)
   ```bash
   python record_trade_outcome.py win   # or 'loss'
   ```

2. **Review Performance**
   ```bash
   python manage_positions.py stats
   python record_trade_outcome.py stats
   ```

### Configuration Examples

#### Conservative Setup
```yaml
# config.yaml
START_CAPITAL: 40.0
RISK_FRACTION: 0.25          # Risk only 25% per trade
SIZE_RULE: "fixed-qty"
CONTRACT_QTY: 1
MIN_CONFIDENCE: 0.50         # Higher confidence threshold
MIN_CANDLE_BODY_PCT: 0.20    # Larger breakouts only
```

#### Aggressive Setup
```yaml
# config.yaml
START_CAPITAL: 100.0
RISK_FRACTION: 0.50          # Risk up to 50% per trade
SIZE_RULE: "dynamic-qty"     # Size based on bankroll
MIN_CONFIDENCE: 0.35         # Lower confidence threshold
MIN_CANDLE_BODY_PCT: 0.10    # Smaller breakouts accepted
```

### Troubleshooting Common Issues

#### "No Trade Signal"
```
[DECISION] LLM Decision: NO_TRADE (confidence: 0.00)
[REASON] Reason: Candle body < 0.1% of price
```
**Solutions:**
- Lower `MIN_CANDLE_BODY_PCT` in config.yaml
- Wait for more volatile market conditions
- Check if `MIN_CONFIDENCE` is too high

#### "Risk Limit Exceeded"
```
WARNING - Fixed quantity $40.00 exceeds risk limit $20.00
```
**Solutions:**
- Increase `RISK_FRACTION` in config.yaml
- Switch to `SIZE_RULE: "dynamic-qty"`
- Wait for cheaper options

#### Browser Issues
- **MFA Timeout**: Approve MFA notification quickly
- **Login Failed**: Check RH_USER/RH_PASS in .env
- **Page Load Error**: Increase `PAGE_LOAD_TIMEOUT` in config.yaml

### Safety Reminders

#### ✅ What the System Does
- Analyzes market data objectively
- Navigates to Review screen automatically
- Tracks positions and P/L accurately
- Enforces risk management rules
- Provides detailed logging

#### ❌ What the System Never Does
- **Auto-submit orders** (always stops at Review)
- **Trade without your approval**
- **Override your manual decisions**
- **Access your funds directly**
- **Make guarantees about profitability**

#### 🛡️ Your Responsibilities
- **Review every trade** before submitting
- **Understand the risks** of options trading
- **Never trade more** than you can afford to lose
- **Keep credentials secure** (.env file permissions)
- **Monitor positions** regularly
- **Record outcomes** for system learning

### Performance Optimization

#### LLM Confidence Calibration
The system learns from your trade outcomes:
- **Win Rate Tracking**: Last 20 trades influence confidence
- **Confidence Formula**: `confidence = wins_last20 / 20` (capped at 50%)
- **Regular Recording**: Use `record_trade_outcome.py` consistently

#### Position Management
- **Daily Review**: Check `manage_positions.py list` each morning
- **Clean Ledger**: Remove old positions that were closed externally
- **Accurate Fills**: Enter precise fill prices for accurate P/L

#### Market Timing
- **Best Hours**: 9:30-11:00 AM and 2:00-4:00 PM ET
- **Avoid**: First 15 minutes after open, last 15 minutes before close
- **High Volume**: Look for volume confirmation in breakouts

### Bankroll Updates
The LLM can suggest bankroll updates after significant P/L (>5% change):

```json
{
  "new_bankroll": 45.0,
  "reason": "Successful trade increased bankroll by 12.5%"
}
```

## ⚙️ Configuration

Edit `config.yaml` to customize behavior:

```yaml
# Trading Parameters
CONTRACT_QTY: 1
LOOKBACK_BARS: 20
MODEL: "gpt-4o-mini"  # or "deepseek-chat"

# Bankroll Management  
START_CAPITAL: 40.0
RISK_FRACTION: 0.50
SIZE_RULE: "fixed-qty"  # or "dynamic-qty"

# Risk Controls
MAX_PREMIUM_PCT: 0.50    # Max 50% of bankroll per trade
MIN_CONFIDENCE: 0.35     # Minimum LLM confidence to trade
IV_THRESHOLD: 45.0       # High IV threshold

# Browser Settings
HEADLESS: false          # Set true for headless mode
IMPLICIT_WAIT: 10        # Selenium wait time
```

## 📊 Logging & Monitoring

### Trade Log (`logs/trade_log.csv`)
Every decision is logged with:
- Timestamp, symbol, decision, confidence
- Market conditions (price, volatility, trend)
- Trade details (strike, premium, quantity)
- Bankroll before/after
- Realized P/L (when trade is closed)

### Bankroll File (`bankroll.json`)
Tracks:
- Current bankroll and total P/L
- Trade history with full details
- Performance metrics (win rate, max drawdown)
- Peak bankroll and drawdown tracking

### Application Logs (`logs/app.log`)
Technical logs for debugging:
- Market data fetch results
- LLM API calls and responses
- Browser automation steps
- Error handling and warnings

## 🧪 Testing

Run the comprehensive test suite:

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=utils --cov-report=html

# Run specific test file
pytest tests/test_data.py -v

# Run dry-run test
python main.py --dry-run
```

**Test Coverage**: ≥90% for all utility modules

## 🐳 Docker Deployment

Build and run in a container:

```bash
# Build image
docker build -t robinhood-ha-breakout .

# Run interactively (required for MFA)
docker run -it --rm \
  -v $(pwd)/.env:/app/.env \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/bankroll.json:/app/bankroll.json \
  robinhood-ha-breakout

# Run dry-run in container
docker run --rm \
  -v $(pwd)/.env:/app/.env \
  robinhood-ha-breakout --dry-run
```

## 🔒 Security & Risk

### Security Measures
- ✅ Credentials stored in `.env` (never committed)
- ✅ Undetected ChromeDriver reduces bot detection
- ✅ Manual MFA approval required
- ✅ No hardcoded secrets in code

### Risk Controls
- ✅ **NEVER auto-submits orders** - always requires manual Review
- ✅ Position size validation against bankroll
- ✅ Confidence thresholds block low-probability trades  
- ✅ Maximum 1 contract until proven strategy
- ✅ Comprehensive logging for audit trail

### Compliance Notes
- 📋 **Personal use only** - not for redistribution
- 📋 **Educational/learning purposes**
- 📋 **Manual oversight required** - never runs fully automated
- 📋 **Respects Robinhood ToS** - no high-frequency or unattended trading

## 📅 Scheduling (Optional)

### Windows Task Scheduler
Create a task to run weekday mornings:
```batch
# Command
python C:\path\to\robinhood-ha-breakout\main.py

# Working Directory  
C:\path\to\robinhood-ha-breakout

# Schedule: Daily at 9:35 AM, weekdays only
```

### Linux/macOS Cron
```bash
# Edit crontab
crontab -e

# Add line (runs at 9:35 AM weekdays)
35 9 * * 1-5 cd /path/to/robinhood-ha-breakout && source .venv/bin/activate && python main.py
```

## 🎛️ Command Line Options

```bash
# Basic run
python main.py

# Dry run (analysis only, no browser)
python main.py --dry-run

# Custom config file
python main.py --config custom_config.yaml

# Debug logging
python main.py --log-level DEBUG

# Help
python main.py --help
```

## 🔧 Troubleshooting

### Common Issues

**"No data returned for SPY"**
- Check internet connection
- Verify yfinance is working: `python -c "import yfinance; print(yfinance.Ticker('SPY').history(period='1d'))"`

**"OPENAI_API_KEY required"**
- Ensure `.env` file exists and contains valid API key
- Check API key has sufficient credits

**"Login failed"**
- Verify Robinhood credentials in `.env`
- Ensure MFA is enabled on account
- Try logging in manually first to check for account issues

**"Could not find ATM option"**
- Market might be closed
- Options chain might not be loaded
- Try running during market hours (9:30 AM - 4:00 PM ET)

**Browser detection issues**
- Update Chrome to latest version
- Clear browser cache and cookies
- Try running with `--headless false` in config

### Debug Mode
```bash
# Enable debug logging
python main.py --log-level DEBUG

# Check logs
tail -f logs/app.log
```

## 📈 Performance Tracking

Monitor your strategy performance:

```python
# View bankroll summary
from utils.bankroll import BankrollManager
manager = BankrollManager()
summary = manager.get_performance_summary()
print(f"Win Rate: {summary['win_rate_pct']:.1f}%")
print(f"Total Return: {summary['total_return_pct']:.1f}%")
```

## 🔄 Exit-Monitor Auto-Launch

**Automatic Position Monitoring After Trade Execution**

When you submit a trade, the system automatically starts monitoring your position for profit/loss targets. This ensures you never miss important exit opportunities.

### How It Works

1. **Auto-Start**: After confirming a trade (clicking Submit), a background monitor process automatically starts
2. **Real-Time Tracking**: Monitors your position every 15 seconds using real-time market data
3. **Smart Alerts**: Sends Slack notifications when profit targets or stop-loss levels are hit
4. **Graceful Cleanup**: Automatically stops monitoring when you exit the main script

### CLI Usage

```bash
# Enable auto-monitoring (default behavior)
python main.py --loop --auto-start-monitor --interval 2

# Disable auto-monitoring for testing
python main.py --loop --no-auto-start-monitor --interval 5

# Manual monitor management
python utils/monitor_launcher.py start --symbol SPY
python utils/monitor_launcher.py list
python utils/monitor_launcher.py cleanup
```

### Benefits

- **Never Miss Exits**: Automatic monitoring ensures you're alerted to profit opportunities
- **Mobile-Friendly**: Get Slack alerts on your phone while away from computer
- **Resource Efficient**: Monitors run independently and clean up automatically
- **Multi-Symbol**: Each symbol gets its own dedicated monitor process

### Key Metrics to Watch
- **Win Rate**: Target >60% for profitable strategy
- **Average Return per Trade**: Should exceed commission costs
- **Maximum Drawdown**: Keep below 20% of peak bankroll
- **Sharpe Ratio**: Calculate from daily returns for risk-adjusted performance

## 🤝 Contributing

This is a personal trading tool. If you fork it:

1. **Never share credentials or API keys**
2. **Test thoroughly before live trading**
3. **Understand the risks involved**
4. **Follow your local financial regulations**

## ⚠️ Disclaimer

**This software is for educational and personal use only.**

- ❌ **Not financial advice** - make your own trading decisions
- ❌ **No guarantees** - trading involves risk of loss
- ❌ **Use at your own risk** - author not liable for losses
- ❌ **Not for redistribution** - personal use license only

**Always review trades manually before submitting. Never trade more than you can afford to lose.**

## 📄 License

Personal Use License - See LICENSE file for details.

---

**Happy Trading! 🚀📈**

*Remember: The script stops at Review - you always have the final say.*
