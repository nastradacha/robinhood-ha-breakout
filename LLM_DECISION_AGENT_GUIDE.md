# 🤖 LLM Decision Agent - Complete Usage Guide

**Hands-Free AI-Powered Trading with Enterprise-Grade Safety Rails**

## 🎯 Quick Start

### Basic Unattended Mode (Recommended for Beginners)
```bash
# Exit decisions only - safest configuration
python main.py --loop --unattended --llm-decisions exit \
  --llm-min-confidence 0.70 --llm-exit-bias conservative
```

### Full Automation (Advanced Users)
```bash
# Both entry and exit decisions with Alpaca paper trading
python main.py --loop --unattended --broker alpaca --env paper \
  --llm-decisions entry,exit --llm-min-confidence 0.75 \
  --llm-rate-limit-s 30 --llm-max-api-per-scan 4
```

## 🛡️ Safety Architecture

### Dual-Gate Safety System
Every automated action requires **BOTH** conditions to pass:

#### Gate 1: Objective Rules
- **Exit Triggers**: Profit ≥15% OR Loss ≤-25% OR Time <15min to close
- **Entry Triggers**: Spread ≤50bps AND Liquidity ≥0.7 AND Risk checks pass

#### Gate 2: LLM Confidence
- **Minimum threshold**: 0.60 (configurable via `--llm-min-confidence`)
- **Blocked decisions**: Logged as `BLOCKED_DUAL_GATE` with clear reasoning

### Hard Rails (Never Overrideable)
- Daily/weekly circuit breakers
- Kill switch activation
- Stop loss at -25%
- Force close at 15:45 ET
- All existing pre-LLM safety gates

## ⚙️ Configuration

### CLI Flags
```bash
# Core unattended mode
--unattended                    # Enable hands-free operation
--llm-decisions entry,exit      # Which decisions to automate

# LLM configuration
--llm-primary-model gpt-4o-mini # Primary model (default)
--llm-backup-model deepseek-chat # Backup model (default)
--llm-min-confidence 0.70       # Confidence threshold (0.60 default)
--llm-exit-bias conservative    # Exit strategy bias

# Rate limiting & cost control
--llm-rate-limit-s 30          # Seconds between calls per symbol
--llm-max-api-per-scan 4       # Max API calls per scan cycle
```

### Centralized Configuration (config.yaml)
```yaml
llm:
  min_confidence: 0.70
  exit_bias: conservative
  rate_limit_s: 30
  max_api_per_scan: 4
  primary_model: gpt-4o-mini
  backup_model: deepseek-chat
```

### Environment Variables
```bash
# Override CLI settings
export LLM_MIN_CONFIDENCE="0.75"
export LLM_EXIT_BIAS="conservative"
export LLM_RATE_LIMIT_S="45"
export LLM_PRIMARY_MODEL="gpt-4o-mini"
export LLM_BACKUP_MODEL="deepseek-chat"
```

## 📊 Decision Types & Actions

### Exit Decisions (`--llm-decisions exit`)
- **SELL**: Close position immediately
- **HOLD**: Keep position open
- **WAIT**: Defer decision (rate limited or low confidence)
- **ABSTAIN**: Require manual intervention (hard rails triggered)

### Entry Decisions (`--llm-decisions entry,ro_review`)
- **APPROVE**: Execute the trade
- **REJECT**: Cancel the trade
- **NEED_USER**: Require manual approval (low confidence or poor conditions)
- **ABSTAIN**: Skip this opportunity (hard rails triggered)

## 📱 Slack Audit Trail

### Rich Blocks (Actionable Decisions)
```
🤖 LLM EXIT DECISION
Symbol: SPY
Action: SELL
Confidence: 0.85
Reason: Profit target reached at 15.2%

Position Context:
• P&L: +15.2% ($152.00)
• Time to Close: 30 min
• Exit Bias: CONSERVATIVE

Decision ID: 1692648000-SPY-EXIT
```

### Single-Line Heartbeats (Non-Actionable)
```
🤖 SPY EXIT: WAIT (0.45) - Below confidence threshold, market uncertain...
```

## 🧪 Testing & Validation

### Run Acceptance Tests
```bash
# Validate all safety features
python -m pytest tests/test_llm_acceptance.py -v

# Expected: 9/9 tests passing
```

### Dry-Run Validation
```bash
# Test unattended mode without real trades
python main.py --unattended --llm-decisions entry,exit \
  --dry-run --loop --interval 1 --end-at 10:01

# Verify: No prompts, see APPROVE/REJECT/SELL/HOLD in Slack
```

### Confidence Gate Testing
```bash
# Force low confidence to test blocking
python -c "
from utils.llm_decider import LLMDecider, ExitDecision
# Mock low confidence decision
decision = ExitDecision(action='SELL', confidence=0.45, reason='Test')
print(f'Blocked: {decision.confidence < 0.60}')
"
```

## 🚀 Deployment Scenarios

### Scenario 1: Conservative Exit-Only Automation
**Use Case**: Busy professionals who want automated profit-taking
```bash
python main.py --loop --unattended --llm-decisions exit \
  --llm-min-confidence 0.80 --llm-exit-bias conservative \
  --llm-rate-limit-s 60 --broker alpaca --env paper
```

### Scenario 2: Full Automation for Active Trading
**Use Case**: Experienced traders wanting complete hands-free operation
```bash
python main.py --loop --unattended --llm-decisions entry,exit \
  --llm-min-confidence 0.70 --llm-exit-bias balanced \
  --llm-rate-limit-s 30 --broker alpaca --env paper
```

### Scenario 3: High-Frequency with Tight Controls
**Use Case**: Maximum automation with strict safety limits
```bash
python main.py --loop --unattended --llm-decisions entry,exit \
  --llm-min-confidence 0.85 --llm-exit-bias aggressive \
  --llm-rate-limit-s 15 --llm-max-api-per-scan 6
```

## 📈 Performance Monitoring

### Session Statistics
```python
# View LLM decision performance
stats = llm_decider.get_session_stats()
print(f"Exit decisions: {stats['llm_decisions']['exit_decisions']['total']}")
print(f"Confidence blocks: {stats['llm_decisions']['quality_metrics']['below_confidence']}")
```

### Cost Tracking
- **tokens_used** field in all decisions
- Rate limiting prevents excessive costs
- Configurable API call limits per scan

### Quality Metrics
- Confidence distribution
- Hard rails trigger frequency
- Rate limiting effectiveness
- JSON parsing success rate

## ⚠️ Safety Checklist

### Before Going Live
- [ ] Test with Alpaca paper trading (`--env paper`)
- [ ] Validate Slack notifications working
- [ ] Confirm API keys configured correctly
- [ ] Run acceptance tests (9/9 passing)
- [ ] Set conservative confidence thresholds initially
- [ ] Monitor first few sessions closely

### Ongoing Monitoring
- [ ] Review Slack audit trails daily
- [ ] Check session statistics for quality metrics
- [ ] Monitor API costs and rate limiting
- [ ] Validate hard rails trigger correctly
- [ ] Adjust confidence thresholds based on performance

## 🔧 Troubleshooting

### Common Issues

**"BLOCKED_DUAL_GATE" messages**
- Normal behavior when objective rules or confidence thresholds not met
- Review decision reasoning in logs/Slack
- Consider adjusting confidence threshold if too restrictive

**Rate limiting warnings**
- Increase `--llm-rate-limit-s` to reduce API frequency
- Decrease `--llm-max-api-per-scan` for tighter control
- Normal during high-volatility periods

**JSON parsing failures**
- Automatic fallback to backup model
- Temporary LLM provider issues
- Check API key validity and credits

**Hard rails triggering**
- Expected behavior during circuit breaker/kill switch activation
- Review system status and safety conditions
- Manual intervention required to reset

### Debug Mode
```bash
# Enable detailed logging
python main.py --unattended --log-level DEBUG

# Check logs
tail -f logs/app.log | grep "LLM-"
```

## 📚 Advanced Usage

### Custom Exit Bias Strategies
- **Conservative**: Early profit-taking, capital protection focus
- **Balanced**: Standard profit/loss targets with moderate risk
- **Aggressive**: Hold for maximum gains, higher risk tolerance

### Multi-Symbol Rate Limiting
- Per-symbol rate limiting prevents excessive calls on volatile symbols
- Global scan limits control total API usage per cycle
- Automatic backoff during high-activity periods

### Integration with Existing Workflows
- Maintains all existing safety features
- Compatible with circuit breakers and kill switches
- Preserves manual override capabilities
- Works with both Robinhood and Alpaca execution paths

---

## LLM Decision Agent Guide - Production Ready

## Overview

The LLM Decision Agent enables fully unattended options trading by making intelligent entry and exit decisions using GPT-4o-mini or DeepSeek models. **All critical fixes have been implemented and validated** with enterprise-grade safety rails and comprehensive audit trails.

**Status: ✅ Production Ready - All 9 Critical Fixes Complete**

## 🎉 Ready for Production

The LLM Decision Agent is now production-ready with:
- ✅ Enterprise-grade safety rails
- ✅ Comprehensive testing (9/9 acceptance tests passing)
- ✅ Robust error handling and fallbacks
- ✅ Full audit trail and monitoring
- ✅ Configurable risk controls
- ✅ Cost optimization features

**Start with conservative settings and gradually increase automation as you gain confidence in the system.**
