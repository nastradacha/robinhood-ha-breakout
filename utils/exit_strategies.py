#!/usr/bin/env python3
"""
Advanced Exit Strategies Module

Implements sophisticated exit strategies for maximizing profits and minimizing losses:
- Trailing stops (percentage-based)
- Time-based exits (market close protection)
- Profit target laddering
- Risk management automation

Key Features:
- Dynamic trailing stop adjustment as position becomes profitable
- Automatic position closure alerts before market close
- Configurable exit strategy parameters
- Integration with Slack alerts and position monitoring
- Real-time Alpaca data for accurate exit decisions

Usage:
    from utils.exit_strategies import ExitStrategyManager
    
    exit_manager = ExitStrategyManager()
    exit_decision = exit_manager.evaluate_exit(position, current_price, option_price)
"""

import logging
from datetime import datetime, time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class ExitReason(Enum):
    """Exit reasons for trade decisions."""
    TRAILING_STOP = "trailing_stop"
    TIME_BASED = "time_based"
    PROFIT_TARGET = "profit_target"
    STOP_LOSS = "stop_loss"
    MANUAL = "manual"
    NO_EXIT = "no_exit"

@dataclass
class ExitDecision:
    """Exit decision with reasoning and parameters."""
    should_exit: bool
    reason: ExitReason
    current_pnl_pct: float
    trailing_stop_price: Optional[float] = None
    time_to_close_minutes: Optional[int] = None
    message: str = ""
    urgency: str = "normal"  # "low", "normal", "high", "critical"

@dataclass
class ExitStrategyConfig:
    """Configuration for exit strategies."""
    # Trailing Stop Settings
    trailing_stop_enabled: bool = True
    trailing_stop_activation_pct: float = 10.0  # Start trailing after 10% profit
    trailing_stop_distance_pct: float = 5.0    # Trail 5% behind peak
    
    # Time-Based Exit Settings
    time_based_exit_enabled: bool = True
    market_close_time: str = "15:45"  # 3:45 PM ET
    warning_minutes_before_close: int = 15
    
    # Profit Target Settings
    profit_targets: List[float] = None  # [15.0, 25.0, 35.0] - percentage levels
    
    # Stop Loss Settings
    stop_loss_pct: float = 25.0  # 25% loss threshold
    
    def __post_init__(self):
        if self.profit_targets is None:
            self.profit_targets = [15.0, 25.0, 35.0]

class ExitStrategyManager:
    """
    Advanced exit strategy manager with trailing stops and time-based exits.
    
    Maximizes profits while protecting capital through sophisticated exit logic.
    """
    
    def __init__(self, config: Optional[ExitStrategyConfig] = None):
        """Initialize exit strategy manager with configuration."""
        self.config = config or ExitStrategyConfig()
        self.position_peaks = {}  # Track peak profit for each position
        self.trailing_stops = {}  # Track trailing stop levels
        
        logger.info("[EXIT] Advanced exit strategy manager initialized")
        logger.info(f"[EXIT] Trailing stop: {self.config.trailing_stop_enabled} "
                   f"(activate at +{self.config.trailing_stop_activation_pct}%, "
                   f"trail {self.config.trailing_stop_distance_pct}%)")
        logger.info(f"[EXIT] Time-based exit: {self.config.time_based_exit_enabled} "
                   f"(close by {self.config.market_close_time})")
    
    def evaluate_exit(self, position: Dict, current_stock_price: float, 
                     current_option_price: float) -> ExitDecision:
        """
        Evaluate whether to exit a position based on advanced strategies.
        
        Args:
            position: Position data (symbol, strike, entry_price, etc.)
            current_stock_price: Current underlying stock price
            current_option_price: Current option price
            
        Returns:
            ExitDecision with recommendation and reasoning
        """
        position_key = self._get_position_key(position)
        
        # Calculate current P&L
        entry_price = position['entry_price']
        current_pnl_pct = ((current_option_price - entry_price) / entry_price) * 100
        
        # Update peak tracking
        self._update_peak_tracking(position_key, current_pnl_pct, current_option_price)
        
        # Check exit strategies in order of priority
        
        # 1. Check trailing stop
        trailing_decision = self._check_trailing_stop(position_key, current_pnl_pct, current_option_price)
        if trailing_decision.should_exit:
            return trailing_decision
        
        # 2. Check time-based exit
        time_decision = self._check_time_based_exit(current_pnl_pct)
        if time_decision.should_exit:
            return time_decision
        
        # 3. Check traditional stop loss
        stop_loss_decision = self._check_stop_loss(current_pnl_pct)
        if stop_loss_decision.should_exit:
            return stop_loss_decision
        
        # 4. Check profit targets (informational)
        profit_decision = self._check_profit_targets(current_pnl_pct)
        if profit_decision.should_exit:
            return profit_decision
        
        # No exit recommended
        return ExitDecision(
            should_exit=False,
            reason=ExitReason.NO_EXIT,
            current_pnl_pct=current_pnl_pct,
            message=f"Hold position (P&L: {current_pnl_pct:+.1f}%)"
        )
    
    def _get_position_key(self, position: Dict) -> str:
        """Generate unique key for position tracking."""
        return f"{position['symbol']}_{position['strike']}_{position['option_type']}_{position.get('entry_time', 'unknown')}"
    
    def _update_peak_tracking(self, position_key: str, current_pnl_pct: float, current_price: float):
        """Update peak profit tracking for trailing stops."""
        if position_key not in self.position_peaks:
            self.position_peaks[position_key] = {
                'peak_pnl_pct': current_pnl_pct,
                'peak_price': current_price
            }
        else:
            # Update peak if current is higher
            if current_pnl_pct > self.position_peaks[position_key]['peak_pnl_pct']:
                self.position_peaks[position_key]['peak_pnl_pct'] = current_pnl_pct
                self.position_peaks[position_key]['peak_price'] = current_price
                
                # Update trailing stop if position is profitable enough
                if (self.config.trailing_stop_enabled and 
                    current_pnl_pct >= self.config.trailing_stop_activation_pct):
                    
                    # Calculate new trailing stop level
                    trailing_stop_pct = current_pnl_pct - self.config.trailing_stop_distance_pct
                    self.trailing_stops[position_key] = trailing_stop_pct
                    
                    logger.debug(f"[EXIT] Updated trailing stop for {position_key}: {trailing_stop_pct:.1f}%")
    
    def _check_trailing_stop(self, position_key: str, current_pnl_pct: float, 
                           current_price: float) -> ExitDecision:
        """Check if trailing stop should trigger."""
        if not self.config.trailing_stop_enabled:
            return ExitDecision(False, ExitReason.NO_EXIT, current_pnl_pct)
        
        if position_key not in self.trailing_stops:
            return ExitDecision(False, ExitReason.NO_EXIT, current_pnl_pct)
        
        trailing_stop_level = self.trailing_stops[position_key]
        
        if current_pnl_pct <= trailing_stop_level:
            peak_pnl = self.position_peaks[position_key]['peak_pnl_pct']
            
            return ExitDecision(
                should_exit=True,
                reason=ExitReason.TRAILING_STOP,
                current_pnl_pct=current_pnl_pct,
                trailing_stop_price=current_price,
                message=f"Trailing stop triggered! Peak: +{peak_pnl:.1f}%, Current: {current_pnl_pct:+.1f}%, Stop: {trailing_stop_level:.1f}%",
                urgency="high"
            )
        
        return ExitDecision(False, ExitReason.NO_EXIT, current_pnl_pct)
    
    def _check_time_based_exit(self, current_pnl_pct: float) -> ExitDecision:
        """Check if time-based exit should trigger."""
        if not self.config.time_based_exit_enabled:
            return ExitDecision(False, ExitReason.NO_EXIT, current_pnl_pct)
        
        now = datetime.now()
        market_close = datetime.strptime(self.config.market_close_time, "%H:%M").replace(
            year=now.year, month=now.month, day=now.day
        )
        
        time_to_close_minutes = (market_close - now).total_seconds() / 60
        
        if time_to_close_minutes <= self.config.warning_minutes_before_close:
            urgency = "critical" if time_to_close_minutes <= 5 else "high"
            
            return ExitDecision(
                should_exit=True,
                reason=ExitReason.TIME_BASED,
                current_pnl_pct=current_pnl_pct,
                time_to_close_minutes=int(time_to_close_minutes),
                message=f"Market closes in {int(time_to_close_minutes)} minutes! Close position to avoid overnight risk.",
                urgency=urgency
            )
        
        return ExitDecision(False, ExitReason.NO_EXIT, current_pnl_pct)
    
    def _check_stop_loss(self, current_pnl_pct: float) -> ExitDecision:
        """Check traditional stop loss."""
        if current_pnl_pct <= -self.config.stop_loss_pct:
            return ExitDecision(
                should_exit=True,
                reason=ExitReason.STOP_LOSS,
                current_pnl_pct=current_pnl_pct,
                message=f"Stop loss triggered at {current_pnl_pct:.1f}% loss",
                urgency="high"
            )
        
        return ExitDecision(False, ExitReason.NO_EXIT, current_pnl_pct)
    
    def _check_profit_targets(self, current_pnl_pct: float) -> ExitDecision:
        """Check profit targets (informational alerts)."""
        for target in self.config.profit_targets:
            if current_pnl_pct >= target:
                # This is informational - not a forced exit
                return ExitDecision(
                    should_exit=False,  # Don't force exit, just alert
                    reason=ExitReason.PROFIT_TARGET,
                    current_pnl_pct=current_pnl_pct,
                    message=f"Profit target {target}% reached! Consider taking profits ({current_pnl_pct:+.1f}%)",
                    urgency="normal"
                )
        
        return ExitDecision(False, ExitReason.NO_EXIT, current_pnl_pct)
    
    def get_position_status(self, position_key: str) -> Dict:
        """Get current status of position tracking."""
        return {
            'peak_data': self.position_peaks.get(position_key, {}),
            'trailing_stop': self.trailing_stops.get(position_key, None),
            'config': {
                'trailing_stop_enabled': self.config.trailing_stop_enabled,
                'activation_threshold': self.config.trailing_stop_activation_pct,
                'trail_distance': self.config.trailing_stop_distance_pct,
                'market_close_time': self.config.market_close_time
            }
        }
    
    def reset_position_tracking(self, position_key: str):
        """Reset tracking for a closed position."""
        if position_key in self.position_peaks:
            del self.position_peaks[position_key]
        if position_key in self.trailing_stops:
            del self.trailing_stops[position_key]
        
        logger.info(f"[EXIT] Reset tracking for {position_key}")

def load_exit_config_from_file(config_path: str = "config.yaml") -> ExitStrategyConfig:
    """Load exit strategy configuration from YAML file."""
    try:
        import yaml
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        
        exit_config = config_data.get('exit_strategies', {})
        
        return ExitStrategyConfig(
            trailing_stop_enabled=exit_config.get('trailing_stop_enabled', True),
            trailing_stop_activation_pct=exit_config.get('trailing_stop_activation_pct', 10.0),
            trailing_stop_distance_pct=exit_config.get('trailing_stop_distance_pct', 5.0),
            time_based_exit_enabled=exit_config.get('time_based_exit_enabled', True),
            market_close_time=exit_config.get('market_close_time', "15:45"),
            warning_minutes_before_close=exit_config.get('warning_minutes_before_close', 15),
            profit_targets=exit_config.get('profit_targets', [15.0, 25.0, 35.0]),
            stop_loss_pct=exit_config.get('stop_loss_pct', 25.0)
        )
    
    except Exception as e:
        logger.warning(f"[EXIT] Could not load config from {config_path}: {e}")
        return ExitStrategyConfig()

# Example usage and testing
if __name__ == "__main__":
    # Test the exit strategy manager
    config = ExitStrategyConfig(
        trailing_stop_activation_pct=10.0,
        trailing_stop_distance_pct=5.0,
        profit_targets=[15.0, 25.0, 35.0]
    )
    
    manager = ExitStrategyManager(config)
    
    # Simulate a position
    test_position = {
        'symbol': 'SPY',
        'strike': 628.0,
        'option_type': 'CALL',
        'entry_price': 1.42,
        'entry_time': '2025-08-04 09:55'
    }
    
    # Test scenarios
    scenarios = [
        (628.5, 1.50),  # Small gain
        (630.0, 1.65),  # 16% gain - should activate trailing stop
        (632.0, 1.85),  # 30% gain - update trailing stop
        (631.0, 1.75),  # Pullback - should trigger trailing stop
    ]
    
    print("=== EXIT STRATEGY TESTING ===")
    for stock_price, option_price in scenarios:
        decision = manager.evaluate_exit(test_position, stock_price, option_price)
        print(f"Stock: ${stock_price:.2f}, Option: ${option_price:.2f}")
        print(f"Decision: {decision.should_exit}, Reason: {decision.reason.value}")
        print(f"Message: {decision.message}")
        print("---")
