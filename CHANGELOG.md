# Changelog

All notable changes to the Robinhood HA Breakout project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2025-08-05

### 🚀 Major New Features

#### Exit-Monitor Auto-Launch Integration
- **NEW**: `utils/monitor_launcher.py` with automatic position monitoring
- **NEW**: `ensure_monitor_running()` function with PID file management
- **NEW**: Auto-spawn `monitor_alpaca.py` processes after trade submission
- **NEW**: `--auto-start-monitor` CLI flag (default: True) for control
- **NEW**: `--no-auto-start-monitor` flag to disable auto-monitoring
- **NEW**: Graceful shutdown with automatic monitor cleanup on exit

#### Enhanced Trade Confirmation Workflow
- **IMPROVED**: `TradeConfirmationManager.record_trade_outcome()` with auto-monitor support
- **IMPROVED**: Automatic position monitoring after SUBMITTED trades
- **IMPROVED**: Multi-symbol support for independent monitor processes
- **IMPROVED**: Robust error handling for monitor launch failures

### 🔧 Technical Improvements

#### Process Management
- **NEW**: PID file tracking (`.monitor_<symbol>.pid`) for process lifecycle
- **NEW**: Process health checks using `psutil` for reliability
- **NEW**: Automatic cleanup of stale PID files and zombie processes
- **NEW**: Force termination with SIGTERM/SIGKILL for unresponsive monitors

#### CLI and User Experience
- **NEW**: Enhanced command-line interface with monitor control flags
- **NEW**: Manual monitor management via `monitor_launcher.py` CLI
- **NEW**: Monitor status listing and cleanup commands
- **IMPROVED**: Graceful KeyboardInterrupt handling with monitor cleanup

### 🧪 Testing and Quality Assurance

#### Comprehensive Unit Tests
- **NEW**: `tests/test_monitor_launcher.py` with 14 test cases (100% pass rate)
- **NEW**: `tests/test_auto_launch_path.py` with 7 test cases (100% pass rate)
- **NEW**: Mock-based testing for subprocess and psutil operations
- **NEW**: Edge case testing for corrupted PID files and process failures
- **NEW**: Integration testing for auto-launch workflow paths

#### Code Quality
- **IMPROVED**: ≥85% unit test coverage maintained
- **IMPROVED**: Robust error handling and logging throughout
- **IMPROVED**: Type hints and comprehensive documentation
- **IMPROVED**: Windows compatibility for process management

### 📚 Documentation

#### README Updates
- **NEW**: "Exit-Monitor Auto-Launch" section with usage examples
- **NEW**: CLI usage examples for auto-monitoring control
- **NEW**: Benefits and workflow explanation
- **NEW**: Manual monitor management documentation

### 🔒 Security and Reliability

#### Process Security
- **NEW**: Detached process spawning with `start_new_session=True`
- **NEW**: Proper signal handling for graceful termination
- **NEW**: Resource cleanup on abnormal exit conditions
- **NEW**: PID validation and process ownership checks

### 🎯 User Benefits

- **Never Miss Exits**: Automatic monitoring ensures profit/loss alerts
- **Mobile-Friendly**: Slack alerts work seamlessly with auto-monitoring
- **Resource Efficient**: Independent monitor processes with automatic cleanup
- **Multi-Symbol**: Each symbol gets dedicated monitoring automatically
- **Fail-Safe**: Robust error handling prevents workflow interruption

### 🔄 Migration Guide

#### For Existing Users
1. **Auto-monitoring is enabled by default** - no action required
2. **To disable**: Use `--no-auto-start-monitor` flag for testing
3. **Manual control**: Use `python utils/monitor_launcher.py` commands
4. **Clean shutdown**: Ctrl+C now automatically stops all monitors

#### Breaking Changes
- None - fully backwards compatible with existing workflows

---

## [0.3.0] - 2025-08-05

### 🎉 Major New Features

#### Slack-Based Trade Confirmation
- **NEW**: Remote trade confirmation via Slack messages
- **NEW**: Support for `submitted`, `filled $X.YZ`, and `cancelled` messages
- **NEW**: Ephemeral bot responses with confirmation details
- **NEW**: Mobile-friendly trading workflow
- **NEW**: Case-insensitive message parsing with robust price extraction

#### Bankroll Reconciliation with Real Fill Prices
- **NEW**: `BankrollManager.apply_fill()` method for accurate cost tracking
- **NEW**: Automatic bankroll adjustment based on actual premiums
- **NEW**: Undo record tracking in `bankroll_history.csv`
- **NEW**: Position-specific cost reconciliation
- **NEW**: Audit trail for all bankroll adjustments

#### Persistent Browser Session Management
- **NEW**: Single `RobinhoodBot` instance across loop iterations
- **NEW**: `ensure_session()` method with configurable idle timeout (15 min default)
- **NEW**: Automatic session restart and recovery
- **NEW**: Selenium exception handling with exponential back-off
- **NEW**: Last action timestamp tracking for session management

### 🔧 Technical Improvements

#### Enhanced Slack Integration
- **IMPROVED**: `EnhancedSlackIntegration` with confirmation message handler
- **IMPROVED**: Trade confirmation manager integration
- **IMPROVED**: Ephemeral message support with fallback to regular messages
- **IMPROVED**: Comprehensive unit test coverage (≥85%)

#### Browser Automation Enhancements
- **IMPROVED**: Persistent browser session reduces login frequency
- **IMPROVED**: Session responsiveness checks and automatic recovery
- **IMPROVED**: Robust error handling for stale sessions and disconnections
- **IMPROVED**: Memory and resource optimization for long-running sessions

#### Trade Confirmation Workflow
- **IMPROVED**: Integration with bankroll reconciliation
- **IMPROVED**: Automatic `apply_fill()` calls on trade submission
- **IMPROVED**: Position ID tracking for accurate cost updates
- **IMPROVED**: Enhanced logging and audit trail

### 🐛 Bug Fixes

#### Session Management
- **FIXED**: Browser session timeouts in loop mode
- **FIXED**: Memory leaks from repeated browser instantiation
- **FIXED**: Stale cookie handling and re-authentication
- **FIXED**: WebDriver exception handling and recovery

#### Bankroll Accuracy
- **FIXED**: Estimated vs actual premium discrepancies
- **FIXED**: Missing cost adjustments for custom fill prices
- **FIXED**: Bankroll state inconsistencies after trades
- **FIXED**: Position cost tracking accuracy

### 📚 Documentation

#### User Documentation
- **NEW**: Slack trade confirmation setup guide
- **NEW**: Message format examples and bot responses
- **NEW**: Mobile trading workflow documentation
- **NEW**: Session management and recovery procedures

#### Developer Documentation
- **NEW**: Unit test suite for Slack confirmation
- **NEW**: API documentation for new methods
- **NEW**: Architecture updates for persistent sessions
- **NEW**: Error handling and recovery patterns

### 🔒 Security & Reliability

#### Enhanced Error Recovery
- **IMPROVED**: Exponential back-off for consecutive failures
- **IMPROVED**: Graceful degradation when services unavailable
- **IMPROVED**: Comprehensive logging for debugging
- **IMPROVED**: Session state validation and recovery

#### Data Integrity
- **IMPROVED**: Bankroll reconciliation prevents cost drift
- **IMPROVED**: Audit trail for all financial transactions
- **IMPROVED**: Position tracking accuracy
- **IMPROVED**: Trade outcome recording reliability

### ⚠️ Breaking Changes

- **CHANGED**: `TradeConfirmationManager.record_trade_outcome()` now calls `apply_fill()` automatically
- **CHANGED**: Browser session management moved from per-cycle to persistent model
- **CHANGED**: Slack integration requires `SLACK_BOT_TOKEN` for confirmation features

### 🔄 Migration Guide

1. **Update Environment Variables**: Add `SLACK_BOT_TOKEN` to `.env` file
2. **Update Dependencies**: Run `pip install -r requirements.txt`
3. **Database Migration**: Existing `bankroll.json` files are compatible
4. **Configuration**: No config changes required, all features backward compatible

---

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
