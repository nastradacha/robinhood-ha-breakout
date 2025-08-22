"""
Cross-Source Data Validation Module (US-FA-007)

Validates market data quality using real-time Alpaca data with internal validation.
Yahoo Finance validation has been removed due to delayed data causing split detection issues.

Key Features:
- Internal Alpaca historical data validation
- Data staleness detection and alerting
- Comprehensive logging for data quality monitoring
- Slack alerts for critical data discrepancies

Data Source Priority:
1. Primary: Alpaca API (real-time, professional-grade)
2. Validation: Alpaca historical data (real-time consistency check)
3. No external delayed data sources

Author: Robinhood HA Breakout System
Version: 1.1.0 (US-FA-007) - Yahoo Finance removed
"""

import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from enum import Enum

from .symbol_state_manager import get_symbol_state_manager, SplitDetector, SymbolState
import pandas as pd
from utils.alpaca_client import AlpacaClient
from utils.enhanced_slack import EnhancedSlackIntegration

logger = logging.getLogger(__name__)


class DataQuality(Enum):
    """Data quality assessment levels"""
    EXCELLENT = "excellent"  # Real-time, validated
    GOOD = "good"           # Real-time, not validated
    ACCEPTABLE = "acceptable" # Delayed but recent
    POOR = "poor"           # Stale or conflicting data
    CRITICAL = "critical"   # No reliable data available


class ValidationRecommendation(Enum):
    """Trading recommendations based on data validation"""
    PROCEED_NORMAL = "proceed_normal"    # Safe to trade normally
    PROCEED_CAUTION = "proceed_caution"  # Trade with extra caution
    BLOCK_TRADING = "block_trading"      # Block all trading


@dataclass
class DataPoint:
    """Represents a single data point with metadata"""
    value: float
    timestamp: datetime
    source: str
    symbol: str
    data_type: str  # 'price', 'volume', etc.
    
    @property
    def age_seconds(self) -> float:
        """Age of data point in seconds"""
        now = datetime.now()
        timestamp = self.timestamp
        
        # Normalize both to naive datetime for comparison
        if timestamp.tzinfo is not None:
            timestamp = timestamp.replace(tzinfo=None)
        if now.tzinfo is not None:
            now = now.replace(tzinfo=None)
            
        return (now - timestamp).total_seconds()
    
    def is_stale(self, max_age_seconds: int = 120) -> bool:
        """Check if data is stale (default: 2 minutes)"""
        return self.age_seconds > max_age_seconds


@dataclass
class ValidationResult:
    """Result of cross-source data validation"""
    symbol: str
    primary_data: Optional[DataPoint]
    validation_data: Optional[DataPoint]
    quality: DataQuality
    discrepancy_pct: Optional[float]
    issues: List[str]
    recommendation: ValidationRecommendation
    timestamp: datetime
    primary_source: str = "alpaca"
    validation_sources: List[str] = None
    message: str = ""
    
    def __post_init__(self):
        if self.validation_sources is None:
            self.validation_sources = []
    
    @property
    def is_valid(self) -> bool:
        """Check if data is valid for trading"""
        return self.recommendation != ValidationRecommendation.BLOCK_TRADING


class DataValidator:
    """
    Cross-source data validation system for market data quality assurance
    """
    _instance = None
    _initialized = False
    
    def __new__(cls, config: Dict = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config: Dict = None):
        """Initialize data validator with configuration (singleton)"""
        if self._initialized:
            return
            
        self.config = config or {}
        
        # Configuration
        self.validation_enabled = self.config.get("DATA_VALIDATION_ENABLED", True)
        self.max_discrepancy_pct = self.config.get("DATA_MAX_DISCREPANCY_PCT", 1.0)
        self.max_staleness_seconds = self.config.get("DATA_MAX_STALENESS_SECONDS", 120)
        self.prioritize_alpaca = self.config.get("DATA_PRIORITIZE_ALPACA", True)
        self.alert_on_discrepancy = self.config.get("DATA_ALERT_ON_DISCREPANCY", True)
        self.require_validation = self.config.get("DATA_REQUIRE_VALIDATION", False)
        
        # Symbol-specific overrides for vendor mismatch tolerance
        self.split_whitelist = self.config.get("DATA_SPLIT_WHITELIST", {"GLD", "SLV", "TLT"})
        self.symbol_attention_thresholds = self.config.get("DATA_SYMBOL_ATTENTION_THRESHOLDS", {
            "GLD": 15.0,  # Higher threshold for GLD due to vendor differences
            "SLV": 12.0,
        })
        
        self.alpaca_client = None
        self.logger = logging.getLogger(__name__)
        
        # Symbol-keyed price cache to prevent cross-contamination
        self.last_good_prices = {}
        
        # Watchlist symbols for ETF split detection guard
        self.watchlist_etfs = {"SPY", "QQQ", "DIA", "IWM", "XLK", "XLF", "XLE", "TLT", "UVXY"}
        
        # Initialize paused symbols tracking (MUST be before other initializations)
        self.paused_symbols = {}
        self.pause_on_validate_fail = config.get("DATA_PAUSE_ON_VALIDATE_FAIL", "30m")
        self.strict_validation = config.get("DATA_STRICT_VALIDATION", False)
        
        # Initialize Alpaca client if available
        try:
            from .alpaca_client import AlpacaClient
            self.alpaca_client = AlpacaClient()
            self.logger.info("[DATA-VALIDATION] Initialized (enabled: True)")
        except Exception as e:
            self.logger.warning(f"[DATA-VALIDATION] Failed to initialize Alpaca client: {e}")
            
        # Initialize Slack notifier
        self.slack_notifier = None
        self.slack = None  # Add legacy slack attribute for compatibility
        try:
            from .enhanced_slack import EnhancedSlackIntegration
            self.slack_notifier = EnhancedSlackIntegration(config)
            self.slack = self.slack_notifier  # Alias for compatibility
        except Exception as e:
            self.logger.warning(f"[DATA-VALIDATION] Failed to initialize Slack: {e}")
            
        self._initialized = True
        self.logger.info(f"[DATA-VALIDATION] Initialized (enabled: {self.validation_enabled})")
    
    def get_alpaca_price(self, symbol: str) -> Optional[DataPoint]:
        """Get current price from Alpaca API"""
        if not self.alpaca_client:
            return None
        
        try:
            price = self.alpaca_client.get_current_price(symbol)
            if price and price > 0:
                return DataPoint(
                    value=price,
                    timestamp=datetime.now(),
                    source="alpaca",
                    symbol=symbol,
                    data_type="price"
                )
        except Exception as e:
            logger.warning(f"[DATA-VALIDATION] Alpaca price fetch failed for {symbol}: {e}")
        
        return None
    
    def get_yahoo_price(self, symbol: str) -> Optional[DataPoint]:
        """Yahoo Finance validation disabled - returns None"""
        logger.debug(f"[DATA-VALIDATION] Yahoo validation disabled for {symbol} (delayed data)")
        return None
    
    def get_internal_validation_price(self, symbol: str, current_price: float) -> Optional[DataPoint]:
        """Get recent intraday price from Alpaca for internal validation"""
        if not self.alpaca_client:
            return None
            
        try:
            # Fetch recent intraday data (5-minute bars for last hour) instead of daily
            # This provides fresher validation data to avoid stale price mismatches
            # Note: AlpacaClient.get_market_data() uses "5d" period for 5-minute intervals
            df = self.alpaca_client.get_market_data(symbol, period="5d")
            
            if df is None or df.empty:
                logger.warning(f"[DATA-VALIDATION] No internal validation data for {symbol}")
                return None
                
            # Find the close price column (could be 'close', 'Close', or other)
            close_col = None
            for col in ['close', 'Close', 'c']:
                if col in df.columns:
                    close_col = col
                    break
            
            if close_col is not None:
                # Use the most recent close price for validation (not average)
                recent_closes = df[close_col].tail(3).tolist()  # Last 3 bars
                if recent_closes:
                    # Use the most recent close, not average, to avoid stale data
                    validation_price = recent_closes[-1]
                    latest_timestamp = df.index[-1]
                    
                    # Ensure timestamp is a datetime object, not tuple
                    if isinstance(latest_timestamp, tuple):
                        # Handle MultiIndex case - take the first element
                        latest_timestamp = latest_timestamp[0]
                    
                    # Convert to datetime if it's a pandas Timestamp
                    if hasattr(latest_timestamp, 'to_pydatetime'):
                        latest_timestamp = latest_timestamp.to_pydatetime()
                    elif not isinstance(latest_timestamp, datetime):
                        # Fallback to current time if conversion fails
                        latest_timestamp = datetime.now()
                        logger.debug(f"[DATA-VALIDATION] Using current time as fallback for {symbol} timestamp")
                    
                    # Check for suspected corporate actions (splits, etc.)
                    state_manager = get_symbol_state_manager()
                    split_detection = SplitDetector.detect_split(current_price, validation_price)
                    
                    # Calculate proper percentage difference
                    price_ratio = current_price / validation_price if validation_price > 0 else float('inf')
                    price_diff_pct = abs(current_price - validation_price) / max(current_price, validation_price) * 100
                    
                    if price_diff_pct > 20.0:  # Large price difference
                        if split_detection:
                            # Suspected corporate action - quarantine symbol
                            split_factor, split_desc = split_detection
                            state_manager.quarantine_symbol(
                                symbol, 
                                f"Suspected corporate action: {split_desc}",
                                current_price, 
                                validation_price, 
                                split_detection
                            )
                            logger.warning(f"[DATA-VALIDATION] {symbol}: QUARANTINED - {split_desc} (ratio: {price_ratio:.2f}x): current=${current_price:.2f}, historical=${validation_price:.2f}")
                        else:
                            # Large unexplained difference - quarantine for safety
                            state_manager.quarantine_symbol(
                                symbol,
                                f"Large price discrepancy: {price_diff_pct:.1f}%",
                                current_price,
                                validation_price
                            )
                            logger.warning(f"[DATA-VALIDATION] {symbol}: QUARANTINED - unexplained price difference ({price_diff_pct:.1f}%): current=${current_price:.2f}, historical=${validation_price:.2f}")
                        return None
                        
                    logger.debug(f"[DATA-VALIDATION] Internal validation: current={current_price:.2f}, historical={validation_price:.2f} (diff: {price_diff_pct:.1f}%)")
                    
                    return DataPoint(
                        value=validation_price,
                        timestamp=latest_timestamp,
                        source="alpaca_historical",
                        symbol=symbol,
                        data_type="price"
                    )
                else:
                    logger.warning(f"[DATA-VALIDATION] No close price column found in historical data for {symbol}. Columns: {list(df.columns)}")
                
        except Exception as e:
            logger.warning(f"[DATA-VALIDATION] Internal validation failed for {symbol}: {e}")
            logger.debug(f"[DATA-VALIDATION] Full error details: {type(e).__name__}: {str(e)}")
        
        return None
    
    def calculate_discrepancy(self, primary: DataPoint, validation: DataPoint) -> float:
        """Calculate percentage discrepancy between two data points using max denominator"""
        if primary.value == 0 or validation.value == 0:
            return float('inf')
        
        # Use max(p1, p2) as denominator for more accurate discrepancy calculation
        return abs(primary.value - validation.value) / max(primary.value, validation.value) * 100.0
    
    def _detect_split_mismatch(self, primary_price: float, validation_price: float, symbol: str) -> Tuple[bool, str]:
        """
        Detect potential stock splits causing price mismatches with cross-symbol contamination protection
        
        Args:
            primary_price: Price from primary source (Alpaca)
            validation_price: Price from validation source 
            symbol: Stock symbol
            
        Returns:
            Tuple of (is_split_detected, reason)
        """
        if primary_price <= 0 or validation_price <= 0:
            return False, ""
            
        # Calculate price ratio
        ratio = max(primary_price, validation_price) / min(primary_price, validation_price)
        
        # Only flag as split if ratio is significantly high (>1.5x)
        if ratio < 1.5:
            return False, ""
        
        # Check for cross-symbol contamination first
        cross_symbol_match = self._check_cross_symbol_contamination(primary_price, validation_price, symbol)
        if cross_symbol_match:
            self.logger.warning(f"[DATA-VALIDATION] {symbol}: Cross-symbol feed contamination detected - {cross_symbol_match}")
            return True, f"CROSS_SYMBOL_FEED_MISMATCH: {cross_symbol_match}"
        
        # ETF split detection guard - require corporate actions confirmation
        if symbol in self.watchlist_etfs:
            # For ETFs, check corporate actions API before flagging as split
            corporate_action_detected = self._check_corporate_actions(symbol, ratio)
            if corporate_action_detected:
                self.logger.info(f"[DATA-VALIDATION] {symbol}: Corporate action confirmed via API - allowing price discrepancy")
                return True, f"CORPORATE_ACTION_CONFIRMED: {corporate_action_detected}"
            else:
                self.logger.debug(f"[DATA-VALIDATION] {symbol}: ETF split detection bypassed - no corporate action found")
                return False, f"ETF_SPLIT_GUARD: {symbol} in watchlist, no corporate action detected"
        
        # Common split ratios: 2:1, 3:1, 4:1, 5:1, 10:1, etc.
        common_splits = [2.0, 3.0, 4.0, 5.0, 10.0, 20.0]
        
        for split_ratio in common_splits:
            # Allow 5% tolerance for split detection
            if abs(ratio - split_ratio) / split_ratio < 0.05:
                return True, f"SUSPECT_SPLIT_MISMATCH ({split_ratio}:1 ratio)"
        
        # Check for reverse splits (fractional ratios)
        for split_ratio in common_splits:
            reverse_ratio = 1.0 / split_ratio
            if abs(ratio - reverse_ratio) / reverse_ratio < 0.05:
                return True, f"SUSPECT_REVERSE_SPLIT ({split_ratio}:1 ratio)"
        
        return False, ""
    
    def _check_corporate_actions(self, symbol: str, ratio: float) -> Optional[str]:
        """
        Check corporate actions API for recent splits/dividends that could explain price discrepancy
        
        Args:
            symbol: Stock symbol to check
            ratio: Price ratio that triggered the check
            
        Returns:
            String describing the corporate action if found, None otherwise
        """
        try:
            # Try Alpaca corporate actions API first
            if self.alpaca_client:
                from datetime import datetime, timedelta
                end_date = datetime.now().date()
                start_date = end_date - timedelta(days=7)  # Check last 7 days
                
                try:
                    # Get corporate actions from Alpaca
                    corporate_actions = self.alpaca_client.get_corporate_actions(
                        symbol, 
                        start=start_date.isoformat(),
                        end=end_date.isoformat()
                    )
                    
                    for action in corporate_actions:
                        action_type = action.get('type', '').lower()
                        if 'split' in action_type:
                            split_ratio = action.get('ratio', 1.0)
                            # Check if the detected ratio matches the corporate action
                            if abs(ratio - split_ratio) / split_ratio < 0.10:  # 10% tolerance
                                return f"Stock split {split_ratio}:1 on {action.get('ex_date', 'unknown')}"
                        elif 'dividend' in action_type:
                            # Large dividends can cause price adjustments
                            dividend_amount = action.get('amount', 0.0)
                            if dividend_amount > 1.0:  # Significant dividend
                                return f"Dividend ${dividend_amount} on {action.get('ex_date', 'unknown')}"
                                
                except Exception as api_err:
                    self.logger.debug(f"[DATA-VALIDATION] Alpaca corporate actions API failed for {symbol}: {api_err}")
            
            # Fallback: Check if ratio matches common corporate action patterns
            common_splits = [2.0, 3.0, 4.0, 5.0, 10.0, 20.0]
            for split_ratio in common_splits:
                if abs(ratio - split_ratio) / split_ratio < 0.05:
                    return f"Suspected {split_ratio}:1 split (API confirmation failed)"
                    
                # Check reverse splits
                reverse_ratio = 1.0 / split_ratio
                if abs(ratio - reverse_ratio) / reverse_ratio < 0.05:
                    return f"Suspected 1:{split_ratio} reverse split (API confirmation failed)"
            
            return None
            
        except Exception as e:
            self.logger.warning(f"[DATA-VALIDATION] Corporate actions check failed for {symbol}: {e}")
            return None
    
    def _check_cross_symbol_contamination(self, primary_price: float, validation_price: float, symbol: str) -> Optional[str]:
        """
        Check if the price mismatch is due to cross-symbol feed contamination
        
        Returns:
            String describing the contamination if detected, None otherwise
        """
        # Check if either price matches another symbol's last known price within 0.05%
        for other_symbol, last_price in self.last_good_prices.items():
            if other_symbol == symbol:
                continue
                
            # Check if primary_price matches another symbol
            if abs(primary_price - last_price) / last_price < 0.0005:  # 0.05%
                return f"primary_price {primary_price} matches {other_symbol} last_price {last_price}"
                
            # Check if validation_price matches another symbol  
            if abs(validation_price - last_price) / last_price < 0.0005:  # 0.05%
                return f"validation_price {validation_price} matches {other_symbol} last_price {last_price}"
                
        return None
    
    def validate_data(self, symbol: str, current_price: float, source: str = "alpaca") -> ValidationResult:
        """Validate current price data against multiple sources"""
        logger.debug(f"[DATA-VALIDATION] Starting validation for {symbol}: ${current_price:.2f} from {source}")
        
        # Check if symbol is quarantined
        state_manager = get_symbol_state_manager()
        if not state_manager.is_symbol_tradeable(symbol):
            symbol_state = state_manager.get_symbol_state(symbol)
            symbol_info = state_manager.get_symbol_info(symbol)
            reason = symbol_info.get('reason', 'Unknown')
            logger.warning(f"[DATA-VALIDATION] {symbol} is {symbol_state.value.upper()} - {reason}")
            return ValidationResult(
                symbol=symbol,
                primary_data=None,
                validation_data=None,
                quality=DataQuality.POOR,
                discrepancy_pct=0.0,
                issues=[],
                recommendation=ValidationRecommendation.BLOCK_TRADING,
                timestamp=datetime.now(),
                primary_source=source,
                validation_sources=[],
                message=f"Symbol quarantined: {reason}"
            )
        
        # Get validation data points
        validation_points = []
        
        # Internal validation (Alpaca historical)
        internal_point = self.get_internal_validation_price(symbol, current_price)
        if internal_point:
            validation_points.append(internal_point)
        
        # Determine quality and recommendation based on available data
        if validation_points:
            quality = DataQuality.EXCELLENT
            recommendation = ValidationRecommendation.PROCEED_NORMAL
        else:
            quality = DataQuality.GOOD
            recommendation = ValidationRecommendation.PROCEED_NORMAL
        
        # If we have validation data, calculate discrepancy and check stability
        if validation_points:
            primary_point = DataPoint(
                value=current_price,
                timestamp=datetime.now(),
                source=source,
                symbol=symbol,
                data_type="price"
            )
            
            # Use the first (and typically only) validation point
            validation_point = validation_points[0]
            discrepancy = self.calculate_discrepancy(primary_point, validation_point)
            
            # Record stable scan for previously quarantined symbols
            if symbol in state_manager.states:
                is_unquarantined = state_manager.record_stable_scan(symbol, current_price, validation_point.value)
                if not is_unquarantined:
                    # Still quarantined, block trading
                    symbol_info = state_manager.get_symbol_info(symbol)
                    stable_scans = symbol_info.get('stable_scans', 0)
                    required_scans = state_manager.stability_required_scans
                    logger.info(f"[DATA-VALIDATION] {symbol} still quarantined - stable scans: {stable_scans}/{required_scans}")
                    return ValidationResult(
                        symbol=symbol,
                        primary_data=None,
                        validation_data=validation_points[0] if validation_points else None,
                        quality=DataQuality.POOR,
                        discrepancy_pct=discrepancy,
                        issues=[],
                        recommendation=ValidationRecommendation.BLOCK_TRADING,
                        timestamp=datetime.now(),
                        primary_source=source,
                        validation_sources=[vp.source for vp in validation_points],
                        message=f"Symbol recovering from quarantine ({stable_scans}/{required_scans} stable scans)"
                    )
            
            logger.info(f"[DATA-VALIDATION] {symbol}: {current_price:.2f} vs {validation_point.value:.2f} (diff {discrepancy:.1f}%) -> {recommendation.value.upper()}")
            
            return ValidationResult(
                symbol=symbol,
                primary_data=None,
                validation_data=validation_point,
                quality=quality,
                discrepancy_pct=discrepancy,
                issues=[],
                recommendation=recommendation,
                timestamp=datetime.now(),
                primary_source=source,
                validation_sources=[validation_point.source],
                message=f"Validated against {validation_point.source}"
            )
        else:
            # No validation data available - check if this is due to quarantine
            if symbol in state_manager.states:
                symbol_info = state_manager.get_symbol_info(symbol)
                logger.warning(f"[DATA-VALIDATION] {symbol}: No validation data while quarantined - {symbol_info.get('reason', 'Unknown')}")
                return ValidationResult(
                    symbol=symbol,
                    primary_data=None,
                    validation_data=None,
                    quality=DataQuality.POOR,
                    discrepancy_pct=0.0,
                    issues=[],
                    recommendation=ValidationRecommendation.BLOCK_TRADING,
                    timestamp=datetime.now(),
                    primary_source=source,
                    validation_sources=[],
                    message=f"No validation data (quarantined: {symbol_info.get('reason', 'Unknown')})"
                )
            
            logger.info(f"[DATA-VALIDATION] {symbol}: {current_price:.2f} (no validation data) -> PROCEED_NORMAL")
            return ValidationResult(
                symbol=symbol,
                primary_data=None,
                validation_data=None,
                quality=DataQuality.GOOD,
                discrepancy_pct=0.0,
                issues=[],
                recommendation=ValidationRecommendation.PROCEED_NORMAL,
                timestamp=datetime.now(),
                primary_source=source,
                validation_sources=[],
                message="No validation data available"
            )

    def validate_symbol_data(self, symbol: str) -> ValidationResult:
        
        # Get primary data from Alpaca
        alpaca_data = self.get_alpaca_price(symbol)
        
        # Determine validation source based on configuration
        validation_data = None
        if self.config.get("DATA_USE_INTERNAL_VALIDATION", True) and alpaca_data:
            # Use internal Alpaca historical data for validation
            validation_data = self.get_internal_validation_price(symbol, alpaca_data.value)
        # Yahoo Finance validation completely disabled (delayed data issues)
        
        # Set primary data and update symbol-keyed cache
        primary_data = alpaca_data if alpaca_data else validation_data
        if primary_data and primary_data.value > 0:
            self.last_good_prices[symbol] = primary_data.value
        
        # Check data availability
        if not primary_data:
            return ValidationResult(
                symbol=symbol,
                primary_data=None,
                validation_data=None,
                quality=DataQuality.CRITICAL,
                discrepancy_pct=None,
                issues=["No data available from any source"],
                recommendation="BLOCK_TRADING",
                timestamp=datetime.now()
            )
        
        # Check data staleness
        if primary_data.is_stale(self.max_staleness_seconds):
            issues.append(f"Primary data is stale ({primary_data.age_seconds:.0f}s old)")
        
        # Cross-source validation if both sources available
        discrepancy_pct = None
        split_detected = False
        split_reason = ""
        
        if validation_data and not validation_data.is_stale(300):  # Allow 5min for Yahoo
            discrepancy_pct = self.calculate_discrepancy(primary_data, validation_data)
            split_detected, split_reason = self._detect_split_mismatch(primary_data.value, validation_data.value, symbol)
            
            if split_detected and symbol not in self.split_whitelist:
                issues.append(f"Potential split mismatch detected: {split_reason}")
            elif split_detected and symbol in self.split_whitelist:
                # Log but don't flag as issue for whitelisted symbols
                logger.info(f"[DATA-VALIDATION] {symbol}: Split mismatch ignored (whitelisted): {split_reason}")
            elif discrepancy_pct > 10.0:  # Major discrepancy threshold
                issues.append(f"Major price discrepancy {discrepancy_pct:.1f}% - possible data error")
            else:
                # Use symbol-specific attention threshold
                attention_threshold = self.symbol_attention_thresholds.get(symbol, 2.0)
                if discrepancy_pct > attention_threshold:
                    issues.append(f"Price discrepancy {discrepancy_pct:.1f}% requires attention")
        
        # Determine quality and recommendation
        quality, recommendation = self._assess_quality(primary_data, validation_data, discrepancy_pct, issues)
        
        result = ValidationResult(
            symbol=symbol,
            primary_data=primary_data,
            validation_data=validation_data,
            quality=quality,
            discrepancy_pct=discrepancy_pct,
            issues=issues,
            recommendation=recommendation,
            timestamp=datetime.now()
        )
        
        # Log validation result
        self._log_validation_result(result)
        
        # Send alerts for critical issues
        if quality in [DataQuality.POOR, DataQuality.CRITICAL]:
            self._send_data_quality_alert(result)
        
        return result
    
    def _assess_quality(self, primary: DataPoint, validation: Optional[DataPoint], 
                       discrepancy_pct: Optional[float], issues: List[str]) -> Tuple[DataQuality, str]:
        """Assess overall data quality and provide recommendation"""
        
        # Critical: No primary data
        if not primary:
            return DataQuality.CRITICAL, "BLOCK_TRADING"
        
        # Check for split mismatch - always pause trading
        split_issues = [issue for issue in issues if "split mismatch" in issue.lower()]
        if split_issues:
            return DataQuality.POOR, "PAUSE_SYMBOL"
        
        # Check for major discrepancies (>10%)
        major_discrepancy = [issue for issue in issues if "Major price discrepancy" in issue]
        if major_discrepancy:
            return DataQuality.POOR, "PAUSE_SYMBOL"
        
        # Poor: Stale primary data
        if primary.is_stale(self.max_staleness_seconds):
            if self.require_validation:
                return DataQuality.POOR, "BLOCK_TRADING"
            else:
                return DataQuality.POOR, "PROCEED_WITH_CAUTION"
        
        # Attention: Moderate discrepancy (2-10%)
        attention_issues = [issue for issue in issues if "requires attention" in issue]
        if attention_issues:
            return DataQuality.ACCEPTABLE, "ATTENTION"
        
        # Poor: High discrepancy between sources (legacy check)
        if discrepancy_pct and discrepancy_pct > self.max_discrepancy_pct:
            if self.require_validation:
                return DataQuality.POOR, "REQUIRE_MANUAL_APPROVAL"
            else:
                return DataQuality.ACCEPTABLE, "PROCEED_WITH_CAUTION"
        
        # Excellent: Real-time primary + validated
        if primary.source == "alpaca" and validation and discrepancy_pct is not None and discrepancy_pct <= 2.0:
            return DataQuality.EXCELLENT, "PROCEED_NORMAL"
        
        # Good: Real-time primary, no validation
        if primary.source == "alpaca":
            return DataQuality.GOOD, "PROCEED_NORMAL"
        
        # Acceptable: Delayed but recent data
        return DataQuality.ACCEPTABLE, "PROCEED_WITH_CAUTION"
    
    def _log_validation_result(self, result: ValidationResult):
        """Log validation result with clear, actionable information"""
        if not result.primary_data:
            logger.error(f"[DATA-VALIDATION] {result.symbol}: No data available → BLOCK_TRADING")
            return
        
        # Build price comparison string
        if result.validation_data:
            price_comparison = f"{result.primary_data.value:.2f} vs {result.validation_data.value:.2f}"
            if result.discrepancy_pct:
                price_comparison += f" (diff {result.discrepancy_pct:.1f}%)"
        else:
            price_comparison = f"{result.primary_data.value:.2f} (no validation data)"
        
        # Create single actionable log message (using ASCII arrow for Windows compatibility)
        log_msg = f"[DATA-VALIDATION] {result.symbol}: {price_comparison} -> {result.recommendation}"
        
        # Add specific issue context
        if result.issues:
            issue_context = result.issues[0]  # Show most important issue
            if "split mismatch" in issue_context.lower():
                log_msg += f" ({issue_context})"
            elif "Major price discrepancy" in issue_context:
                log_msg += f" (major discrepancy)"
            elif "requires attention" in issue_context:
                log_msg += f" (attention needed)"
        
        # Log at appropriate level
        if result.recommendation in ["BLOCK_TRADING", "PAUSE_SYMBOL"]:
            logger.error(log_msg)
        elif result.recommendation in ["ATTENTION", "PROCEED_WITH_CAUTION"]:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)
    
    def _send_data_quality_alert(self, result: ValidationResult):
        """Send Slack alert for data quality issues"""
        if not self.slack:
            return
        
        try:
            urgency = "🚨 CRITICAL" if result.quality == DataQuality.CRITICAL else "⚠️ WARNING"
            
            primary_info = f"{result.primary_data.source}: ${result.primary_data.value:.2f}" if result.primary_data else "None"
            validation_info = f"{result.validation_data.source}: ${result.validation_data.value:.2f}" if result.validation_data else "None"
            
            message = (
                f"{urgency} **DATA QUALITY ISSUE**\n\n"
                f"**Symbol:** {result.symbol}\n"
                f"**Quality:** {result.quality.value.upper()}\n"
                f"**Primary Source:** {primary_info}\n"
                f"**Validation Source:** {validation_info}\n"
                f"**Discrepancy:** {result.discrepancy_pct:.2f}%" if result.discrepancy_pct else "N/A"
                f"\n**Recommendation:** {result.recommendation}\n\n"
            )
            
            if result.issues:
                message += f"**Issues:**\n" + "\n".join(f"• {issue}" for issue in result.issues)
            
            self.slack.send_alert(message)
            logger.info(f"[DATA-VALIDATION] Sent data quality alert for {result.symbol}")
            
        except Exception as e:
            logger.error(f"[DATA-VALIDATION] Failed to send alert: {e}")
    
    def validate_multiple_symbols(self, symbols: List[str]) -> Dict[str, ValidationResult]:
        """Validate data quality for multiple symbols"""
        results = {}
        
        for symbol in symbols:
            try:
                results[symbol] = self.validate_symbol_data(symbol)
            except Exception as e:
                logger.error(f"[DATA-VALIDATION] Failed to validate {symbol}: {e}")
                results[symbol] = ValidationResult(
                    symbol=symbol,
                    primary_data=None,
                    validation_data=None,
                    quality=DataQuality.CRITICAL,
                    discrepancy_pct=None,
                    issues=[f"Validation error: {e}"],
                    recommendation="BLOCK_TRADING",
                    timestamp=datetime.now()
                )
        
        return results
    
    def _parse_duration(self, duration_str: str) -> int:
        """Parse duration string like '30m', '1h' into seconds."""
        if not duration_str:
            return 0
        
        duration_str = duration_str.lower().strip()
        if duration_str.endswith('m'):
            return int(duration_str[:-1]) * 60
        elif duration_str.endswith('h'):
            return int(duration_str[:-1]) * 3600
        elif duration_str.endswith('s'):
            return int(duration_str[:-1])
        else:
            # Assume minutes if no unit
            return int(duration_str) * 60
    
    def _is_symbol_paused(self, symbol: str) -> Tuple[bool, str]:
        """Check if symbol is currently paused due to validation failures."""
        if symbol not in self.paused_symbols:
            return False, ""
        
        pause_expiry = self.paused_symbols[symbol]
        if datetime.now() > pause_expiry:
            # Pause expired, remove from list
            del self.paused_symbols[symbol]
            logger.info(f"[DATA-VALIDATION] {symbol}: Pause expired, resuming validation")
            return False, ""
        
        remaining = (pause_expiry - datetime.now()).total_seconds()
        return True, f"Symbol paused for {remaining/60:.0f}m due to validation failures"
    
    def _pause_symbol(self, symbol: str, reason: str):
        """Pause symbol for configured duration due to validation failure."""
        if not self.pause_on_validate_fail:
            return
        
        duration_seconds = self._parse_duration(self.pause_on_validate_fail)
        if duration_seconds <= 0:
            return
        
        pause_expiry = datetime.now() + timedelta(seconds=duration_seconds)
        self.paused_symbols[symbol] = pause_expiry
        
        logger.warning(f"[DATA-VALIDATION] {symbol}: Paused for {self.pause_on_validate_fail} - {reason}")
        
        # Send Slack alert for symbol pause
        if self.slack:
            try:
                self.slack.send_alert(
                    f"⏸️ **SYMBOL PAUSED**\n\n"
                    f"**Symbol:** {symbol}\n"
                    f"**Duration:** {self.pause_on_validate_fail}\n"
                    f"**Reason:** {reason}\n"
                    f"**Auto-resume:** {pause_expiry.strftime('%H:%M:%S')}"
                )
            except Exception as e:
                logger.error(f"[DATA-VALIDATION] Failed to send pause alert: {e}")

    def should_allow_trading(self, symbol: str) -> Tuple[bool, str]:
        """
        Determine if trading should be allowed based on data quality
        
        Returns:
            Tuple of (allow_trading, reason)
        """
        if not self.validation_enabled:
            return True, "Data validation disabled"
        
        # Check if symbol is currently paused
        is_paused, pause_reason = self._is_symbol_paused(symbol)
        if is_paused:
            return False, pause_reason
        
        result = self.validate_symbol_data(symbol)
        
        # In strict validation mode, any validation issue blocks trading
        if self.strict_validation:
            if result.recommendation not in ["PROCEED_NORMAL"]:
                reason = f"Strict validation: {', '.join(result.issues) if result.issues else result.recommendation}"
                self._pause_symbol(symbol, reason)
                return False, reason
        
        # Standard validation logic
        if result.recommendation in ["BLOCK_TRADING", "PAUSE_SYMBOL"]:
            reason = f"Trading blocked: {', '.join(result.issues)}"
            self._pause_symbol(symbol, reason)
            return False, reason
        elif result.recommendation == "REQUIRE_MANUAL_APPROVAL":
            reason = f"Manual approval required: {result.discrepancy_pct:.1f}% discrepancy"
            if self.strict_validation:
                self._pause_symbol(symbol, reason)
            return False, reason
        elif result.recommendation == "ATTENTION":
            reason = f"Data requires attention: {result.discrepancy_pct:.1f}% discrepancy"
            if self.strict_validation:
                self._pause_symbol(symbol, reason)
            return False, reason
        else:
            return True, f"Data quality acceptable ({result.quality.value})"


# Convenience functions for easy integration
def validate_symbol_data_quality(symbol: str, config: Dict = None) -> ValidationResult:
    """Convenience function to validate single symbol data quality"""
    validator = DataValidator(config)
    return validator.validate_symbol_data(symbol)


def check_trading_allowed(symbol: str, config: Dict = None) -> Tuple[bool, str]:
    """Convenience function to check if trading is allowed for symbol"""
    validator = DataValidator(config)
    return validator.should_allow_trading(symbol)


def get_data_validator(config: Dict = None) -> DataValidator:
    """Get singleton data validator instance"""
    if not hasattr(get_data_validator, '_instance'):
        get_data_validator._instance = DataValidator(config)
    return get_data_validator._instance
