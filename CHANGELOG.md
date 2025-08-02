# Changelog

All notable changes to the Robinhood HA Breakout project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2025-01-02

### 🎉 Major New Features

#### Continuous Morning-Scanner Mode
- **NEW**: `--loop` flag for unattended continuous market monitoring
- **NEW**: `--interval N` to set scan frequency (default: 5 minutes)
- **NEW**: `--end-at HH:MM` to automatically stop at specified time
- **NEW**: Persistent browser session with 4-hour idle restart
- **NEW**: Smart session recovery with `ensure_open()` method

#### Enhanced Slack Integration
- **NEW**: Lightweight heartbeat messages for NO_TRADE cycles
- **NEW**: Rich trade alert blocks with strike, delta, and confidence
- **NEW**: Loop mode status notifications
- **NEW**: `send_heartbeat()` method for minimal status updates

#### Improved Browser Automation
- **NEW**: Robust buy-button discovery using `data-testid` attributes
- **NEW**: Hardened cookie injection with graceful error handling
- **NEW**: Browser window maximization for better visibility
- **NEW**: Stale element recovery and session validation

### 🔧 Technical Improvements

#### Architecture Refactoring
- **CHANGED**: Extracted `run_once()` function for single trading cycles
- **CHANGED**: Added `main_loop()` for continuous operation
- **CHANGED**: Separated one-shot mode into `run_one_shot_mode()`
- **CHANGED**: Enhanced error handling and recovery mechanisms

#### Risk Management
- **IMPROVED**: Persistent bankroll tracking across loop cycles
- **IMPROVED**: Position size calculations with confidence weighting
- **IMPROVED**: Enhanced logging for audit trail compliance

#### Browser Stability
- **FIXED**: Cookie loading failures no longer abort entire session
- **FIXED**: Stale element exceptions in long-running sessions
- **FIXED**: Memory leaks in continuous browser operation
- **IMPROVED**: Chrome stealth mode configuration

### 📚 Documentation

#### User Experience
- **NEW**: Comprehensive non-technical README.md
- **NEW**: System architecture document (ARCHITECTURE.md)
- **NEW**: Step-by-step setup guide for beginners
- **NEW**: Troubleshooting section with common solutions

#### Developer Resources
- **NEW**: Loop timing test suite (`test_loop_timing.py`)
- **IMPROVED**: Code documentation and inline comments
- **IMPROVED**: Configuration examples and templates

### 🛡️ Safety & Security

#### Enhanced Safety Features
- **CONFIRMED**: Never auto-submits trades (always stops at Review)
- **IMPROVED**: Multiple layers of risk validation
- **IMPROVED**: Comprehensive error logging and recovery
- **NEW**: Browser session timeout protection

#### Security Improvements
- **IMPROVED**: Secure credential handling in environment files
- **IMPROVED**: API key validation and error reporting
- **IMPROVED**: Browser fingerprint randomization

### 🎯 Usage Examples

#### New Command-Line Options
```bash
# Basic continuous loop
python main.py --loop

# Custom interval with end time
python main.py --loop --interval 3 --end-at 12:00

# Full morning scanner with notifications
python main.py --loop --interval 5 --end-at 12:00 --slack-notify
```

#### Slack Notifications
```
# Heartbeat messages
⏳ 09:35 · No breakout (body 0.07%)
⚠️ 09:45 · Low confidence CALL (0.58)

# Trade alerts
📈 09:50 · CALL ready
Strike     $635
Δ          0.42
Confidence 0.68
```

### 🔄 Backwards Compatibility

- **MAINTAINED**: All existing command-line flags work unchanged
- **MAINTAINED**: Configuration file format remains compatible
- **MAINTAINED**: One-shot trading mode operates identically
- **MAINTAINED**: All existing safety mechanisms preserved

### 📊 Performance

#### Efficiency Improvements
- **IMPROVED**: Reduced browser startup overhead in loop mode
- **IMPROVED**: Optimized API call frequency
- **IMPROVED**: Memory usage optimization for long-running sessions
- **IMPROVED**: Faster option chain navigation

#### Cost Optimization
- **NEW**: DeepSeek API support for lower costs ($0.02-0.10 vs $0.10-0.50)
- **IMPROVED**: Configurable intervals to control API usage
- **IMPROVED**: Smart session reuse to minimize overhead

### 🧪 Testing

#### New Test Coverage
- **NEW**: Loop timing accuracy tests
- **NEW**: Interval calculation validation
- **NEW**: End time parsing and logic tests
- **NEW**: Slack heartbeat integration tests
- **IMPROVED**: Browser automation test stability

#### Quality Assurance
- **IMPROVED**: Error handling test coverage
- **IMPROVED**: Configuration validation tests
- **IMPROVED**: Integration test reliability

---

## [1.0.0] - 2024-12-15

### 🎉 Initial Release

#### Core Trading Features
- **NEW**: SPY options trading automation
- **NEW**: Heikin-Ashi candle analysis
- **NEW**: Support/resistance level detection
- **NEW**: LLM-powered trade decisions (OpenAI GPT-4o-mini)
- **NEW**: Automated browser navigation to Review screen

#### Risk Management
- **NEW**: Configurable bankroll management
- **NEW**: Position sizing based on confidence levels
- **NEW**: Risk fraction controls (default 2% per trade)
- **NEW**: Trade logging and audit trail

#### Browser Automation
- **NEW**: Undetected Chrome WebDriver integration
- **NEW**: Robinhood login and MFA handling
- **NEW**: Options chain navigation
- **NEW**: ATM option selection and order preparation

#### Notifications & Logging
- **NEW**: Slack webhook integration
- **NEW**: Comprehensive CSV trade logging
- **NEW**: JSON bankroll tracking
- **NEW**: Detailed system logging

#### Safety Features
- **NEW**: Manual review requirement (never auto-submits)
- **NEW**: Dry-run mode for testing
- **NEW**: Confidence threshold filtering
- **NEW**: Position size validation

#### Configuration
- **NEW**: YAML configuration file support
- **NEW**: Environment variable management
- **NEW**: Customizable trading parameters
- **NEW**: Flexible logging levels

---

## Development Roadmap

### Planned Features (v2.1.0)
- [ ] Multiple symbol support (QQQ, IWM, etc.)
- [ ] Advanced technical indicators
- [ ] Machine learning model integration
- [ ] Mobile app companion
- [ ] Paper trading mode

### Under Consideration
- [ ] Multi-timeframe analysis
- [ ] Options Greeks calculation
- [ ] Portfolio optimization
- [ ] Social sentiment integration
- [ ] Backtesting framework

---

## Migration Guide

### Upgrading from v1.x to v2.0

#### No Breaking Changes
The v2.0 release is fully backwards compatible. All existing configurations, scripts, and workflows will continue to work without modification.

#### New Features Available
1. **Add loop mode**: Simply add `--loop` to your existing commands
2. **Configure intervals**: Add `--interval N` for custom timing
3. **Set end times**: Add `--end-at HH:MM` for automatic stopping
4. **Enhanced notifications**: Existing Slack integration gets new message types

#### Recommended Updates
1. **Update README**: Review the new documentation for additional features
2. **Test loop mode**: Try `--dry-run --loop` to see the new functionality
3. **Configure intervals**: Adjust `--interval` based on your trading style
4. **Set up heartbeats**: Enable Slack notifications for better monitoring

---

## Support & Feedback

### Getting Help
- **Documentation**: Check README.md and ARCHITECTURE.md
- **Troubleshooting**: Review the troubleshooting section
- **Logs**: Examine `logs/app.log` for detailed error information
- **Testing**: Use `--dry-run` mode to isolate issues

### Reporting Issues
When reporting issues, please include:
1. Version number (`python main.py --version`)
2. Command used and configuration
3. Relevant log entries from `logs/app.log`
4. Expected vs actual behavior
5. System information (OS, Python version, Chrome version)

### Contributing
We welcome contributions! Please:
1. Follow the existing code style (black formatting)
2. Add tests for new features (≥90% coverage)
3. Update documentation for user-facing changes
4. Test backwards compatibility

---

*For detailed usage instructions, see [README.md](README.md)*
*For system architecture details, see [ARCHITECTURE.md](ARCHITECTURE.md)*
