"""
System Status Dashboard - Real-time trading system health monitoring.

This module provides comprehensive system status reporting including:
- Active positions and P&L across all broker/environment combinations
- System health monitoring (uptime, connectivity, recovery status)
- Market conditions (VIX, market hours, volatility indicators)
- Recent trade activity summary and performance metrics
- Integration with Slack for mobile-friendly status updates

Author: Robinhood HA Breakout System
Version: 1.0.0
"""

import os
import json
import logging
import psutil
import requests
from datetime import datetime, timedelta, time as dt_time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from pathlib import Path

# Import existing system components
from utils.scoped_files import get_scoped_paths
from utils.llm import load_config
from utils.recovery import get_recovery_manager

logger = logging.getLogger(__name__)


@dataclass
class PositionStatus:
    """Container for position information."""
    symbol: str
    broker: str
    environment: str
    quantity: int
    entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    entry_time: str
    days_held: int


@dataclass
class SystemHealth:
    """Container for system health metrics."""
    status: str  # "healthy", "degraded", "critical"
    uptime: str
    last_update: str
    recovery_active: bool
    recovery_attempts_today: int
    api_connectivity: Dict[str, bool]
    process_health: Dict[str, Any]
    disk_usage_pct: float
    memory_usage_pct: float


@dataclass
class MarketConditions:
    """Container for market condition data."""
    market_open: bool
    market_hours: str
    vix: Optional[float]
    vix_status: str  # "low", "normal", "elevated", "high"
    trading_day_progress: float  # 0.0 to 1.0
    time_to_close: str


@dataclass
class DailySummary:
    """Container for daily trading summary."""
    trades_today: int
    realized_pnl: float
    win_rate: float
    largest_win: float
    largest_loss: float
    total_volume: float
    symbols_traded: List[str]


@dataclass
class SystemStatusReport:
    """Complete system status report."""
    timestamp: str
    system_health: SystemHealth
    positions: List[PositionStatus]
    daily_summary: DailySummary
    market_conditions: MarketConditions
    total_positions: int
    total_unrealized_pnl: float
    account_value: float


class SystemStatusManager:
    """Manages system status data collection and reporting."""
    
    def __init__(self):
        """Initialize the system status manager."""
        self.config = load_config()
        self.start_time = datetime.now()
        self.recovery_manager = get_recovery_manager()
        
    def get_complete_status(self) -> SystemStatusReport:
        """Get complete system status report."""
        logger.info("[SYSTEM-STATUS] Generating complete status report...")
        
        # Collect all status components
        system_health = self._get_system_health()
        positions = self._get_all_positions()
        daily_summary = self._get_daily_summary()
        market_conditions = self._get_market_conditions()
        
        # Calculate aggregates
        total_positions = len(positions)
        total_unrealized_pnl = sum(pos.unrealized_pnl for pos in positions)
        account_value = self._estimate_account_value(positions)
        
        return SystemStatusReport(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S ET"),
            system_health=system_health,
            positions=positions,
            daily_summary=daily_summary,
            market_conditions=market_conditions,
            total_positions=total_positions,
            total_unrealized_pnl=total_unrealized_pnl,
            account_value=account_value
        )
    
    def _get_system_health(self) -> SystemHealth:
        """Get system health metrics."""
        try:
            # Calculate uptime
            uptime_delta = datetime.now() - self.start_time
            uptime_str = self._format_timedelta(uptime_delta)
            
            # Get recovery status
            recovery_stats = self.recovery_manager.get_recovery_stats()
            recovery_active = recovery_stats.get("active_recoveries", 0) > 0
            recovery_attempts_today = self._count_recovery_attempts_today()
            
            # Check API connectivity
            api_connectivity = self._check_api_connectivity()
            
            # Get process health
            process_health = self._get_process_health()
            
            # System resource usage
            disk_usage = psutil.disk_usage('/').percent if os.name != 'nt' else psutil.disk_usage('C:\\').percent
            memory_usage = psutil.virtual_memory().percent
            
            # Determine overall health status
            status = self._determine_health_status(
                api_connectivity, process_health, disk_usage, memory_usage, recovery_active
            )
            
            return SystemHealth(
                status=status,
                uptime=uptime_str,
                last_update=datetime.now().strftime("%H:%M:%S"),
                recovery_active=recovery_active,
                recovery_attempts_today=recovery_attempts_today,
                api_connectivity=api_connectivity,
                process_health=process_health,
                disk_usage_pct=disk_usage,
                memory_usage_pct=memory_usage
            )
            
        except Exception as e:
            logger.error(f"[SYSTEM-STATUS] Error getting system health: {e}")
            return SystemHealth(
                status="critical",
                uptime="unknown",
                last_update=datetime.now().strftime("%H:%M:%S"),
                recovery_active=False,
                recovery_attempts_today=0,
                api_connectivity={},
                process_health={},
                disk_usage_pct=0.0,
                memory_usage_pct=0.0
            )
    
    def _get_all_positions(self) -> List[PositionStatus]:
        """Get positions across all broker/environment combinations."""
        positions = []
        
        try:
            # Get all possible broker/environment combinations
            brokers = ["alpaca", "robinhood"]
            environments = ["paper", "live"]
            
            for broker in brokers:
                for env in environments:
                    try:
                        broker_positions = self._get_positions_for_broker_env(broker, env)
                        positions.extend(broker_positions)
                    except Exception as e:
                        logger.debug(f"[SYSTEM-STATUS] No positions found for {broker}/{env}: {e}")
                        continue
            
            logger.info(f"[SYSTEM-STATUS] Found {len(positions)} total positions")
            return positions
            
        except Exception as e:
            logger.error(f"[SYSTEM-STATUS] Error getting positions: {e}")
            return []
    
    def _get_positions_for_broker_env(self, broker: str, environment: str) -> List[PositionStatus]:
        """Get positions for specific broker/environment combination."""
        positions = []
        
        try:
            # Get scoped file paths
            scoped_paths = get_scoped_paths(broker, environment)
            positions_file = scoped_paths.get("POSITIONS_FILE")
            
            if not positions_file or not os.path.exists(positions_file):
                return []
            
            # Read positions file
            with open(positions_file, 'r') as f:
                positions_data = json.load(f)
            
            # Convert to PositionStatus objects
            for symbol, pos_data in positions_data.items():
                if isinstance(pos_data, dict) and pos_data.get("quantity", 0) != 0:
                    # Calculate current P&L (simplified - would need real-time prices)
                    entry_price = pos_data.get("avg_price", 0.0)
                    current_price = pos_data.get("current_price", entry_price)  # Fallback to entry
                    quantity = pos_data.get("quantity", 0)
                    
                    unrealized_pnl = (current_price - entry_price) * quantity * 100  # Options multiplier
                    unrealized_pnl_pct = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0.0
                    
                    # Calculate days held
                    entry_time_str = pos_data.get("timestamp", "")
                    days_held = self._calculate_days_held(entry_time_str)
                    
                    position = PositionStatus(
                        symbol=symbol,
                        broker=broker,
                        environment=environment,
                        quantity=quantity,
                        entry_price=entry_price,
                        current_price=current_price,
                        unrealized_pnl=unrealized_pnl,
                        unrealized_pnl_pct=unrealized_pnl_pct,
                        entry_time=entry_time_str,
                        days_held=days_held
                    )
                    positions.append(position)
            
            return positions
            
        except Exception as e:
            logger.error(f"[SYSTEM-STATUS] Error reading positions for {broker}/{environment}: {e}")
            return []
    
    def _get_daily_summary(self) -> DailySummary:
        """Get daily trading summary from trade logs."""
        try:
            today = datetime.now().date()
            trades_today = 0
            realized_pnl = 0.0
            wins = 0
            losses = 0
            largest_win = 0.0
            largest_loss = 0.0
            total_volume = 0.0
            symbols_traded = set()
            
            # Check trade logs across all broker/env combinations
            brokers = ["alpaca", "robinhood"]
            environments = ["paper", "live"]
            
            for broker in brokers:
                for env in environments:
                    try:
                        scoped_paths = get_scoped_paths(broker, env)
                        trade_log_file = scoped_paths.get("TRADE_LOG_FILE")
                        
                        if not trade_log_file or not os.path.exists(trade_log_file):
                            continue
                        
                        # Read and parse trade log
                        with open(trade_log_file, 'r') as f:
                            for line in f:
                                try:
                                    if line.strip():
                                        trade_data = json.loads(line.strip())
                                        trade_date = datetime.fromisoformat(trade_data.get("timestamp", "")).date()
                                        
                                        if trade_date == today:
                                            trades_today += 1
                                            pnl = trade_data.get("realized_pnl", 0.0)
                                            realized_pnl += pnl
                                            
                                            if pnl > 0:
                                                wins += 1
                                                largest_win = max(largest_win, pnl)
                                            elif pnl < 0:
                                                losses += 1
                                                largest_loss = min(largest_loss, pnl)
                                            
                                            total_volume += abs(trade_data.get("fill_price", 0.0) * trade_data.get("quantity", 0))
                                            symbols_traded.add(trade_data.get("symbol", ""))
                                            
                                except (json.JSONDecodeError, ValueError, KeyError):
                                    continue
                                    
                    except Exception as e:
                        logger.debug(f"[SYSTEM-STATUS] Error reading trade log for {broker}/{env}: {e}")
                        continue
            
            # Calculate win rate
            total_completed = wins + losses
            win_rate = (wins / total_completed * 100) if total_completed > 0 else 0.0
            
            return DailySummary(
                trades_today=trades_today,
                realized_pnl=realized_pnl,
                win_rate=win_rate,
                largest_win=largest_win,
                largest_loss=largest_loss,
                total_volume=total_volume,
                symbols_traded=list(symbols_traded)
            )
            
        except Exception as e:
            logger.error(f"[SYSTEM-STATUS] Error getting daily summary: {e}")
            return DailySummary(
                trades_today=0,
                realized_pnl=0.0,
                win_rate=0.0,
                largest_win=0.0,
                largest_loss=0.0,
                total_volume=0.0,
                symbols_traded=[]
            )
    
    def _get_market_conditions(self) -> MarketConditions:
        """Get current market conditions."""
        try:
            # Get market hours (simplified - would integrate with Alpaca API)
            now = datetime.now()
            market_open = self._is_market_open(now)
            market_hours = "09:30-16:00 ET"
            
            # Get VIX data (simplified - would use real API)
            vix = self._get_vix_data()
            vix_status = self._classify_vix(vix)
            
            # Calculate trading day progress
            trading_day_progress = self._calculate_trading_day_progress(now)
            
            # Time to market close
            time_to_close = self._calculate_time_to_close(now)
            
            return MarketConditions(
                market_open=market_open,
                market_hours=market_hours,
                vix=vix,
                vix_status=vix_status,
                trading_day_progress=trading_day_progress,
                time_to_close=time_to_close
            )
            
        except Exception as e:
            logger.error(f"[SYSTEM-STATUS] Error getting market conditions: {e}")
            return MarketConditions(
                market_open=False,
                market_hours="Unknown",
                vix=None,
                vix_status="unknown",
                trading_day_progress=0.0,
                time_to_close="Unknown"
            )
    
    def _check_api_connectivity(self) -> Dict[str, bool]:
        """Check connectivity to key APIs."""
        connectivity = {}
        
        # Check Alpaca API
        try:
            response = requests.get("https://paper-api.alpaca.markets/v2/account", timeout=5)
            connectivity["alpaca"] = response.status_code in [200, 401]  # 401 means API is up, just auth issue
        except:
            connectivity["alpaca"] = False
        
        # Check Slack API
        try:
            response = requests.get("https://slack.com/api/api.test", timeout=5)
            connectivity["slack"] = response.status_code == 200
        except:
            connectivity["slack"] = False
        
        # Check Yahoo Finance
        try:
            response = requests.get("https://finance.yahoo.com", timeout=5)
            connectivity["yahoo_finance"] = response.status_code == 200
        except:
            connectivity["yahoo_finance"] = False
        
        return connectivity
    
    def _get_process_health(self) -> Dict[str, Any]:
        """Get process health metrics."""
        try:
            current_process = psutil.Process()
            return {
                "cpu_percent": current_process.cpu_percent(),
                "memory_mb": current_process.memory_info().rss / 1024 / 1024,
                "num_threads": current_process.num_threads(),
                "status": current_process.status()
            }
        except:
            return {}
    
    def _determine_health_status(self, api_connectivity: Dict[str, bool], 
                               process_health: Dict[str, Any], disk_usage: float, 
                               memory_usage: float, recovery_active: bool) -> str:
        """Determine overall system health status."""
        # Critical conditions
        if disk_usage > 95 or memory_usage > 95:
            return "critical"
        
        # Check API connectivity
        critical_apis = ["alpaca", "slack"]
        critical_api_down = any(not api_connectivity.get(api, False) for api in critical_apis)
        
        if critical_api_down:
            return "degraded"
        
        # Check if recovery is actively running
        if recovery_active:
            return "degraded"
        
        # Check resource usage
        if disk_usage > 85 or memory_usage > 85:
            return "degraded"
        
        return "healthy"
    
    def _count_recovery_attempts_today(self) -> int:
        """Count recovery attempts today."""
        try:
            recovery_stats = self.recovery_manager.get_recovery_stats()
            return recovery_stats.get("attempts_today", 0)
        except:
            return 0
    
    def _estimate_account_value(self, positions: List[PositionStatus]) -> float:
        """Estimate total account value."""
        # Simplified calculation - would integrate with broker APIs
        total_position_value = sum(pos.current_price * pos.quantity * 100 for pos in positions)
        return total_position_value  # Would add cash balance from broker API
    
    def _calculate_days_held(self, entry_time_str: str) -> int:
        """Calculate days held for a position."""
        try:
            entry_time = datetime.fromisoformat(entry_time_str)
            return (datetime.now() - entry_time).days
        except:
            return 0
    
    def _is_market_open(self, now: datetime) -> bool:
        """Check if market is currently open (simplified)."""
        # Simplified - would use Alpaca market calendar API
        if now.weekday() >= 5:  # Weekend
            return False
        
        market_open = dt_time(9, 30)
        market_close = dt_time(16, 0)
        current_time = now.time()
        
        return market_open <= current_time <= market_close
    
    def _get_vix_data(self) -> Optional[float]:
        """Get current VIX value (simplified)."""
        # Simplified - would use real financial data API
        try:
            # Placeholder - would fetch from Yahoo Finance or other API
            return 18.5  # Mock VIX value
        except:
            return None
    
    def _classify_vix(self, vix: Optional[float]) -> str:
        """Classify VIX level."""
        if vix is None:
            return "unknown"
        elif vix < 15:
            return "low"
        elif vix < 25:
            return "normal"
        elif vix < 35:
            return "elevated"
        else:
            return "high"
    
    def _calculate_trading_day_progress(self, now: datetime) -> float:
        """Calculate progress through trading day (0.0 to 1.0)."""
        try:
            market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
            market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
            
            if now < market_open:
                return 0.0
            elif now > market_close:
                return 1.0
            else:
                total_minutes = (market_close - market_open).total_seconds() / 60
                elapsed_minutes = (now - market_open).total_seconds() / 60
                return elapsed_minutes / total_minutes
        except:
            return 0.0
    
    def _calculate_time_to_close(self, now: datetime) -> str:
        """Calculate time remaining until market close."""
        try:
            market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
            if now > market_close:
                return "Market closed"
            
            time_remaining = market_close - now
            hours = time_remaining.seconds // 3600
            minutes = (time_remaining.seconds % 3600) // 60
            
            return f"{hours}h {minutes}m"
        except:
            return "Unknown"
    
    def _format_timedelta(self, td: timedelta) -> str:
        """Format timedelta as human-readable string."""
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"


# Global instance
_system_status_manager = None


def get_system_status_manager() -> SystemStatusManager:
    """Get global system status manager instance."""
    global _system_status_manager
    if _system_status_manager is None:
        _system_status_manager = SystemStatusManager()
    return _system_status_manager


def get_system_status() -> SystemStatusReport:
    """Get complete system status report."""
    manager = get_system_status_manager()
    return manager.get_complete_status()
