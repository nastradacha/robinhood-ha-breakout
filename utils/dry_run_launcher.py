"""
Dry Run Launcher for US-FA-014 Full Automation Validation
Provides launch script with all safety checks and monitoring setup.
"""

import sys
import os
import yaml
import logging
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logging_setup import setup_logging
from utils.safety_hooks import validate_dry_run_config, check_time_gate_exit, session_phase

ET = ZoneInfo("America/New_York")


def launch_dry_run():
    """Launch dry run with full validation and safety checks."""
    
    print("US-FA-014: Full Automation Dry Run Launcher")
    print("=" * 60)
    
    # Load dry run configuration
    config_path = "config/config_dryrun.yaml"
    if not os.path.exists(config_path):
        print(f"ERROR: Dry run config not found: {config_path}")
        sys.exit(1)
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Validate configuration
    if not validate_dry_run_config(config):
        print("ERROR: Dry run configuration validation failed")
        sys.exit(1)
    
    # Set up enhanced logging
    metrics_logger = setup_logging(config)
    logger = logging.getLogger(__name__)
    
    # Check environment variables
    required_env = ['ALPACA_API_KEY', 'ALPACA_SECRET_KEY', 'SLACK_BOT_TOKEN']
    missing_env = [var for var in required_env if not os.getenv(var)]
    if missing_env:
        logger.error("Missing required environment variables: %s", missing_env)
        sys.exit(1)
    
    # Verify paper trading environment
    if os.getenv('ALPACA_ENV') != 'paper':
        logger.error("ALPACA_ENV must be set to 'paper' for dry run")
        sys.exit(1)
    
    # Check current session
    now_et = datetime.now(ET)
    phase = session_phase(now_et)
    logger.info("Current session: %s (%s ET)", phase, now_et.strftime("%H:%M"))
    
    if phase == "Weekend":
        logger.warning("Weekend detected - system will wait for market open")
    
    # Log dry run start
    logger.info("Starting US-FA-014 Full Automation Dry Run")
    logger.info("Configuration: %s", config_path)
    logger.info("Symbols: %s", config['app']['symbols'])
    logger.info("Position sizing: %s%%", config['broker']['position_sizing_pct'] * 100)
    logger.info("Safety: Strict validation enabled, 30m pause on failures")
    logger.info("End time: %s ET", config['app']['end_at'])
    
    # Log incident for dry run start
    metrics_logger.log_incident(
        event_type="dry_run_start",
        severity="info",
        context=f"Phase: {phase}",
        notes="US-FA-014 Full Automation Dry Run initiated"
    )
    
    # Create monitoring directories
    os.makedirs("monitoring", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    
    # Display launch command
    launch_cmd = [
        "python", "main.py",
        "--broker", "alpaca",
        "--alpaca-env", "paper",
        "--multi-symbol",
        "--config", config_path,
        "--strict-validation",
        "--end-at", config['app']['end_at']
    ]
    
    print("\nLaunch Command:")
    print(" ".join(launch_cmd))
    print("\nMonitoring:")
    print(f"  • Logs: logs/dryrun.log")
    print(f"  • Metrics: logs/dryrun_metrics.jsonl")
    print(f"  • Incidents: monitoring/incident_log.csv")
    print(f"  • Slack: {config['notifiers']['slack']['channel']}")
    
    print("\nPre-flight checks complete. Ready for dry run launch!")
    print("Remember to monitor the first 72 hours intensively.")
    
    return launch_cmd


if __name__ == "__main__":
    try:
        launch_cmd = launch_dry_run()
        
        # Ask for confirmation
        response = input("\nLaunch dry run now? (y/N): ").strip().lower()
        if response == 'y':
            print("\nLaunching dry run...")
            os.execvp("python", launch_cmd)
        else:
            print("Dry run launch cancelled. Use the command above when ready.")
            
    except KeyboardInterrupt:
        print("\nDry run launcher interrupted")
        sys.exit(0)
    except Exception as e:
        print(f"\nERROR: {e}")
        sys.exit(1)
