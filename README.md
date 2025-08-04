# 📈 Robinhood HA Breakout Trading Assistant

**Your Personal AI-Powered Options Trading Assistant - Safe, Smart, and Always Under Your Control**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: Personal](https://img.shields.io/badge/license-Personal-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.0.0-brightgreen.svg)](CHANGELOG.md)

---

## 🌟 What Is This?

**Robinhood HA Breakout** is like having a professional trading assistant that:

- 📊 **Watches the market** for you using advanced chart analysis
- 🧠 **Makes smart decisions** using artificial intelligence
- 🤖 **Handles the boring stuff** like clicking through Robinhood's interface
- 🛡️ **Keeps you safe** by never placing trades without your final approval
- 💰 **Manages your money** responsibly with built-in risk controls

**Think of it as your trading co-pilot** - it does all the heavy lifting, but you're always in the driver's seat for the final decision.

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
python main.py --dry-run
```

**What you'll see:**
- Market analysis results
- AI's trading decision and reasoning
- Risk calculations
- No browser automation

### 🎯 One-Shot Trading Mode

**For single trade sessions:**

```bash
python main.py
```

**What happens:**
1. Analyzes current market conditions
2. Gets AI recommendation
3. Opens Chrome and logs into Robinhood
4. Navigates to the options page
5. Fills out the trade details
6. **Stops at the Review screen** - you decide whether to submit!

### 🔄 Continuous Loop Mode (NEW!)

**For automated morning scanning:**

```bash
# Basic loop - checks every 5 minutes
python main.py --loop

# Custom interval - checks every 3 minutes
python main.py --loop --interval 3

# Stop at specific time - ends at 12:00 PM
python main.py --loop --interval 5 --end-at 12:00

# With Slack notifications
python main.py --loop --interval 5 --end-at 12:00 --slack-notify
```

**What happens in loop mode:**
- Runs continuously until you stop it (Ctrl+C) or reach the end time
- Checks the market every few minutes
- Sends "heartbeat" messages when there's no trade opportunity
- When it finds a good trade, it prepares everything and notifies you
- Keeps the browser open between checks (more efficient)
- Automatically restarts the browser if it's been idle for 4+ hours

### 📊 Position Monitoring Mode (NEW!)

**Automated real-time position tracking with profit/loss alerts:**

```bash
# Enhanced monitoring with Alpaca real-time data
python monitor_alpaca.py

# Integrated monitoring mode
python main.py --monitor-positions

# Custom monitoring intervals
python main.py --monitor-positions --interval 1  # Every 1 minute
```

**What position monitoring does:**
- ✅ **Real-time P&L tracking** using Alpaca professional market data
- ✅ **Multi-level profit alerts** at 5%, 10%, 15%, 20%, 25%, 30% gains
- ✅ **Stop-loss protection** alerts at 25% loss threshold
- ✅ **End-of-day warnings** to close positions by 3:45 PM ET
- ✅ **Mobile Slack notifications** for all alerts
- ✅ **1-minute monitoring intervals** for maximum responsiveness
- ✅ **Automatic fallback** to Yahoo Finance if Alpaca unavailable

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

### 1. Market Data Analysis
- Fetches 5-minute SPY candles via yfinance
- Converts to Heikin-Ashi for smoother trend analysis
- Identifies support/resistance levels using pivot points
- Calculates volatility metrics (True Range)

### 2. LLM Decision Making
The LLM receives compact market data and returns a structured decision:

```json
{
  "decision": "CALL|PUT|NO_TRADE",
  "confidence": 0.75,
  "reason": "Strong bullish breakout with volume confirmation"
}
```

**Decision Rules:**
- Confidence calibrated against recent 20-trade win rate
- Low volatility (TR < 40%) reduces confidence by 0.15
- Small candle bodies (< 0.30% of price) trigger NO_TRADE
- Room to next pivot ≥ 0.5% boosts confidence by 0.10
- High IV (> 45%) halves confidence
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
