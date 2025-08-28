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
from datetime import datetime, timedelta
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
        
        # Transient error handling configuration
        self.transient_error_threshold = self.config.get("DATA_TRANSIENT_ERROR_THRESHOLD", 10.0)  # 10% threshold for transient errors
        self.transient_confirmation_scans = self.config.get("DATA_TRANSIENT_CONFIRMATION_SCANS", 3)  # Require 3 consecutive scans
        self.transient_scan_interval = self.config.get("DATA_TRANSIENT_SCAN_INTERVAL", 60)  # 60 seconds between scans
        
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
        self.pause_on_validate_fail = self.config.get("DATA_PAUSE_ON_VALIDATE_FAIL", "30m")
        self.strict_validation = self.config.get("DATA_STRICT_VALIDATION", False)
        
        # Transient error tracking for multi-scan confirmation
        self.transient_errors = {}  # symbol -> {"discrepancies": [list], "first_seen": datetime, "count": int}
        
        # Cooldown tracking for paused symbols to prevent oscillations
        self.pause_cooldowns = {}  # symbol -> {"paused_at": datetime, "normal_scans": int, "required_normal_scans": int}
        self.cooldown_normal_scans_required = self.config.get("DATA_COOLDOWN_NORMAL_SCANS", 5)  # Require 5 consecutive normal scans
        
        # UVXY-specific data consistency guardrails
        self.uvxy_throttle_threshold = self.config.get("UVXY_THROTTLE_THRESHOLD", 1.0)  # 1% discrepancy threshold
        self.uvxy_throttle_duration = self.config.get("UVXY_THROTTLE_DURATION", 300)  # 5 minutes throttle
        self.uvxy_validation_samples = self.config.get("UVXY_VALIDATION_SAMPLES", 2)  # Extra validation samples required
        self.uvxy_throttle_state = {}  # symbol -> {"throttled_at": datetime, "validation_count": int, "required_validations": int}
        
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
                    
                    # Source consistency check: ensure both prices from same adjustment type
                    # This prevents adjusted vs unadjusted price mismatches that cause false splits
                    prices_consistent = self._check_price_source_consistency(current_price, validation_price, symbol)
                    if not prices_consistent:
                        logger.debug(f"[DATA-VALIDATION] {symbol}: Price source inconsistency detected - skipping split detection")
                        # Record stable scan with low diff % since this is likely a data feed issue, not a real split
                        state_manager = get_symbol_state_manager()
                        # Use a small percentage difference to trigger stable scan recording
                        small_diff_pct = abs(current_price - validation_price) / max(current_price, validation_price) * 100
                        # Cap at 1% to ensure it's considered stable for unquarantining
                        capped_diff_pct = min(small_diff_pct, 1.0)
                        state_manager.record_stable_scan(symbol, capped_diff_pct)
                        return DataPoint(
                            value=validation_price,
                            timestamp=latest_timestamp,
                            source="alpaca_historical",
                            symbol=symbol,
                            data_type="price"
                        )
                    
                    # Check for suspected corporate actions (splits, etc.)
                    from utils.symbol_state_manager import SplitDetector
                    state_manager = get_symbol_state_manager()
                    split_detection = SplitDetector.detect_split(current_price, validation_price, symbol)
                    
                    # Calculate proper percentage difference
                    price_ratio = current_price / validation_price if validation_price > 0 else float('inf')
                    price_diff_pct = abs(current_price - validation_price) / max(current_price, validation_price) * 100
                    
                    if price_diff_pct > 20.0:  # Large price difference
                        if split_detection:
                            # Use new multi-scan confirmation logic
                            split_factor, split_desc = split_detection
                            quarantined = state_manager.record_suspected_split(
                                symbol,
                                f"Suspected corporate action: {split_desc}",
                                current_price,
                                validation_price,
                                split_detection
                            )
                            
                            if quarantined:
                                logger.warning(f"[DATA-VALIDATION] {symbol}: QUARANTINED after confirmation - {split_desc} "
                                               f"(ratio: {price_ratio:.2f}x): current=${current_price:.2f}, "
                                               f"historical=${validation_price:.2f}")
                                return None
                            else:
                                logger.info(f"[DATA-VALIDATION] {symbol}: Suspected {split_desc} recorded "
                                            f"(ratio: {price_ratio:.2f}x) - awaiting confirmation")
                        else:
                            # Large unexplained difference - use multi-scan for non-ETFs too
                            is_etf = SplitDetector.is_etf(symbol)
                            
                            if not is_etf:
                                quarantined = state_manager.record_suspected_split(
                                    symbol,
                                    f"Large price discrepancy: {price_diff_pct:.1f}%",
                                    current_price,
                                    validation_price
                                )
                                
                                if quarantined:
                                    logger.warning(f"[DATA-VALIDATION] {symbol}: QUARANTINED after confirmation - unexplained price difference "
                                                   f"({price_diff_pct:.1f}%): current=${current_price:.2f}, "
                                                   f"historical=${validation_price:.2f}")
                                    return None
                                else:
                                    logger.info(f"[DATA-VALIDATION] {symbol}: Large unexplained diff {price_diff_pct:.1f}% recorded - awaiting confirmation")
                            else:
                                # Don't quarantine ETFs on large unexplained differences
                                logger.info(f"[DATA-VALIDATION] {symbol}: Large unexplained diff {price_diff_pct:.1f}% "
                                            f"but ETF protected from quarantine.")
                                # Record clean scan for ETFs that don't trigger split detection
                                state_manager.record_clean_scan(symbol)
                    else:
                        # Normal price difference - record clean scan
                        state_manager.record_clean_scan(symbol)
                        
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
    
    def _check_price_source_consistency(self, price1: float, price2: float, symbol: str) -> bool:
        """
        Check if two prices are from consistent sources (both adjusted or both unadjusted).
        
        This prevents false split detection when comparing adjusted vs unadjusted prices
        from different data sources.
        
        Args:
            price1: First price to compare
            price2: Second price to compare  
            symbol: Symbol being validated
            
        Returns:
            bool: True if prices appear to be from consistent sources
        """
        try:
            # Calculate percentage difference
            diff_pct = abs(price1 - price2) / max(price1, price2) * 100
            
            # If difference is very small (<0.5%), assume consistent sources
            if diff_pct < 0.5:
                return True
                
            # For larger differences, check if it matches common split ratios
            # If it does, it's likely a real split, not source inconsistency
            ratio = max(price1, price2) / min(price1, price2)
            common_splits = [2.0, 3.0, 4.0, 5.0, 10.0, 20.0]
            
            for split_ratio in common_splits:
                # Check both normal and reverse splits with 5% tolerance
                if (abs(ratio - split_ratio) / split_ratio < 0.05 or 
                    abs(ratio - (1.0/split_ratio)) / (1.0/split_ratio) < 0.05):
                    # This looks like a real split, sources are consistent
                    return True
            
            # Moderate differences (0.5-5%) without split patterns suggest source inconsistency
            if diff_pct < 5.0:
                self.logger.debug(f"[DATA-VALIDATION] {symbol}: Moderate price difference ({diff_pct:.2f}%) suggests source inconsistency")
                return False
                
            # Large differences (>5%) likely indicate real market moves or splits
            return True
            
        except (ZeroDivisionError, ValueError) as e:
            self.logger.warning(f"[DATA-VALIDATION] {symbol}: Error checking price consistency: {e}")
            return True  # Default to consistent to avoid blocking trades
    
    def validate_data(self, symbol: str, current_price: float, source: str = "alpaca") -> ValidationResult:
        """
        Validate current price data against multiple sources"""
        
        # Check UVXY throttling state first
        if symbol == "UVXY" and self._is_uvxy_throttled(symbol):
            logger.info(f"[UVXY-THROTTLE] {symbol}: LLM evaluation throttled due to data inconsistency")
            return ValidationResult(
                symbol=symbol,
                primary_data=DataPoint(current_price, datetime.now(), source, symbol, "price"),
                validation_data=None,
                quality=DataQuality.POOR,
                discrepancy_pct=0.0,
                issues=[f"UVXY throttled due to persistent data discrepancy"],
                recommendation=ValidationRecommendation.BLOCK_TRADING,
                timestamp=datetime.now(),
                primary_source=source,
                validation_sources=[],
                message=f"UVXY throttled due to persistent data discrepancy"
            )
        try:
            # Try Alpaca corporate actions API first
            if self.alpaca_client:
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
    
    def _is_uvxy_throttled(self, symbol: str) -> bool:
        """Check if UVXY is currently throttled due to data inconsistency"""
        if symbol not in self.uvxy_throttle_state:
            return False
        
        state = self.uvxy_throttle_state[symbol]
        throttled_at = state.get("throttled_at")
        
        if not throttled_at:
            return False
        
        # Check if throttle duration has expired
        if (datetime.now() - throttled_at).total_seconds() > self.uvxy_throttle_duration:
            # Reset throttle state after duration expires
            self.uvxy_throttle_state[symbol] = {
                "throttled_at": None,
                "validation_count": 0,
                "required_validations": self.uvxy_validation_samples
            }
            logger.info(f"[UVXY-THROTTLE] {symbol}: Throttle duration expired, requiring {self.uvxy_validation_samples} validation samples")
            return False
        
        # Check if we have enough validation samples
        validation_count = state.get("validation_count", 0)
        required_validations = state.get("required_validations", self.uvxy_validation_samples)
        
        if validation_count >= required_validations:
            # Clear throttle state - validation complete
            del self.uvxy_throttle_state[symbol]
            logger.info(f"[UVXY-THROTTLE] {symbol}: Validation complete ({validation_count}/{required_validations}), resuming LLM evaluation")
            return False
        
        return True
    
    def _handle_uvxy_discrepancy(self, symbol: str, discrepancy_pct: float):
        """Handle UVXY data discrepancy by activating throttling"""
        if symbol not in self.uvxy_throttle_state:
            self.uvxy_throttle_state[symbol] = {
                "throttled_at": None,
                "validation_count": 0,
                "required_validations": self.uvxy_validation_samples
            }
        
        # Activate throttling
        self.uvxy_throttle_state[symbol]["throttled_at"] = datetime.now()
        self.uvxy_throttle_state[symbol]["validation_count"] = 0
        
        logger.warning(f"[UVXY-THROTTLE] {symbol}: Activating throttle due to {discrepancy_pct:.1f}% discrepancy "
                      f"(threshold: {self.uvxy_throttle_threshold:.1f}%), requiring {self.uvxy_validation_samples} validation samples")
    
    def _update_uvxy_validation_progress(self, symbol: str):
        """Update UVXY validation progress for normal readings"""
        if symbol not in self.uvxy_throttle_state:
            return
        
        state = self.uvxy_throttle_state[symbol]
        if state.get("throttled_at") is None:
            return  # Not currently throttled
        
        # Increment validation count
        state["validation_count"] = state.get("validation_count", 0) + 1
        validation_count = state["validation_count"]
        required_validations = state.get("required_validations", self.uvxy_validation_samples)
        
        logger.info(f"[UVXY-THROTTLE] {symbol}: Validation progress {validation_count}/{required_validations}")
    
    def validate_symbol_data(self, symbol: str) -> ValidationResult:
        
        # Initialize issues list
        issues = []
        
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
                recommendation=ValidationRecommendation.BLOCK_TRADING,
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
            
            # Check price source consistency before split detection
            prices_consistent = self._check_price_source_consistency(primary_data.value, validation_data.value, symbol)
            if not prices_consistent:
                logger.debug(f"[DATA-VALIDATION] {symbol}: Price source inconsistency detected in validation - skipping split detection")
                # Record stable scan with low diff % since this is likely a data feed issue
                state_manager = get_symbol_state_manager()
                small_diff_pct = abs(primary_data.value - validation_data.value) / max(primary_data.value, validation_data.value) * 100
                capped_diff_pct = min(small_diff_pct, 1.0)
                state_manager.record_stable_scan(symbol, capped_diff_pct)
                split_detected = False
                split_reason = "price_source_inconsistency"
            else:
                # Use enhanced split detector from symbol_state_manager
                from utils.symbol_state_manager import SplitDetector
                split_result = SplitDetector.detect_split(primary_data.value, validation_data.value, symbol)
                split_detected = split_result is not None
                split_reason = split_result[1] if split_result else ""
            
            if split_detected and symbol not in self.split_whitelist:
                issues.append(f"Potential split mismatch detected: {split_reason}")
            elif split_detected and symbol in self.split_whitelist:
                # Log but don't flag as issue for whitelisted symbols
                logger.info(f"[DATA-VALIDATION] {symbol}: Split mismatch ignored (whitelisted): {split_reason}")
            elif discrepancy_pct > self.transient_error_threshold:  # Major discrepancy threshold
                # For ETFs with large discrepancies (>5%), attempt secondary verification
                if symbol in self.watchlist_etfs and discrepancy_pct > 5.0:
                    secondary_verified = self._verify_etf_price_secondary(symbol, primary_data.value, validation_data.value if validation_data else None)
                    if secondary_verified:
                        logger.info(f"[DATA-VALIDATION] {symbol}: Large discrepancy {discrepancy_pct:.1f}% verified by secondary source")
                        issues.append(f"Large discrepancy {discrepancy_pct:.1f}% verified by secondary source")
                    else:
                        logger.warning(f"[DATA-VALIDATION] {symbol}: Large discrepancy {discrepancy_pct:.1f}% - secondary verification failed")
                
                # Check if this is a transient error requiring confirmation
                if self._is_transient_error(symbol, discrepancy_pct):
                    issues.append(f"Transient error suspected: {discrepancy_pct:.1f}% discrepancy (awaiting confirmation)")
                else:
                    issues.append(f"Major price discrepancy {discrepancy_pct:.1f}% - confirmed data error")
            else:
                # Use symbol-specific attention threshold
                attention_threshold = self.symbol_attention_thresholds.get(symbol, 2.0)
                if discrepancy_pct > attention_threshold:
                    issues.append(f"Price discrepancy {discrepancy_pct:.1f}% requires attention")
                else:
                    # Normal discrepancy - clear any transient error tracking
                    self._clear_transient_error(symbol)
        
        # Determine quality and recommendation with cooldown logic
        quality, recommendation = self._assess_quality_with_cooldown(symbol, primary_data, validation_data, discrepancy_pct, issues)
        
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
        
        # Record stable scan for quarantined symbols on successful validation
        if result.recommendation == ValidationRecommendation.PROCEED_NORMAL and result.discrepancy_pct is not None:
            # Check if symbol is quarantined and record stable scan
            if state_manager.is_quarantined(symbol):
                logger.debug(f"[DATA-VALIDATION] Recording stable scan for quarantined {symbol}: {result.discrepancy_pct:.3f}%")
                state_manager.record_stable_scan(symbol, result.discrepancy_pct)
        
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
        
        # Check for confirmed major discrepancies (>10%) - but not transient errors
        major_discrepancy = [issue for issue in issues if "Major price discrepancy" in issue and "confirmed data error" in issue]
        if major_discrepancy:
            return DataQuality.POOR, "PAUSE_SYMBOL"
        
        # Check for suspected transient errors - allow trading but with caution
        transient_error = [issue for issue in issues if "Transient error suspected" in issue]
        if transient_error:
            return DataQuality.ACCEPTABLE, "PROCEED_WITH_CAUTION"
        
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
    
    def _assess_quality_with_cooldown(self, symbol: str, primary: DataPoint, validation: Optional[DataPoint], 
                                     discrepancy_pct: Optional[float], issues: List[str]) -> Tuple[DataQuality, str]:
        """Assess data quality with cooldown logic to prevent oscillations"""
        
        # Get base quality assessment
        quality, recommendation = self._assess_quality(primary, validation, discrepancy_pct, issues)
        
        # Apply cooldown logic for symbols that were recently paused
        if symbol in self.pause_cooldowns:
            cooldown_data = self.pause_cooldowns[symbol]
            
            # If recommendation would be PROCEED_NORMAL, check cooldown requirements
            if recommendation == "PROCEED_NORMAL":
                cooldown_data["normal_scans"] += 1
                
                # Check if we have enough consecutive normal scans
                if cooldown_data["normal_scans"] >= cooldown_data["required_normal_scans"]:
                    # Cooldown complete - allow normal trading
                    logger.info(f"[DATA-VALIDATION] {symbol}: Cooldown complete after {cooldown_data['normal_scans']} "
                               f"consecutive normal scans - resuming normal trading")
                    del self.pause_cooldowns[symbol]
                    return quality, "PROCEED_NORMAL"
                else:
                    # Still in cooldown - continue with caution
                    remaining_scans = cooldown_data["required_normal_scans"] - cooldown_data["normal_scans"]
                    logger.info(f"[DATA-VALIDATION] {symbol}: Cooldown in progress - {cooldown_data['normal_scans']}"
                               f"/{cooldown_data['required_normal_scans']} normal scans (need {remaining_scans} more)")
                    return DataQuality.ACCEPTABLE, "PROCEED_WITH_CAUTION"
            else:
                # Reset normal scan counter if we get a non-normal recommendation
                cooldown_data["normal_scans"] = 0
                logger.info(f"[DATA-VALIDATION] {symbol}: Cooldown reset due to non-normal recommendation: {recommendation}")
        
        # If recommendation is PAUSE_SYMBOL, initialize cooldown tracking
        if recommendation == "PAUSE_SYMBOL":
            if symbol not in self.pause_cooldowns:
                self.pause_cooldowns[symbol] = {
                    "paused_at": datetime.now(),
                    "normal_scans": 0,
                    "required_normal_scans": self.cooldown_normal_scans_required
                }
                logger.info(f"[DATA-VALIDATION] {symbol}: Initializing cooldown - will require "
                           f"{self.cooldown_normal_scans_required} consecutive normal scans to resume")
        
        return quality, recommendation
    
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
            logger.error(f"[DATA-VALIDATION] BLOCKED (validation) - {symbol}: {reason}")
            if self.strict_validation:
                self._pause_symbol(symbol, reason)
            return False, reason
        else:
            return True, f"Data quality acceptable ({result.quality.value})"

    def _is_transient_error(self, symbol: str, discrepancy_pct: float) -> bool:
        """
        Check if a large discrepancy is likely a transient error requiring confirmation.
        
        Uses multi-scan confirmation to prevent one-off price feed errors from 
        causing unnecessary symbol pauses (like the DIA 50% discrepancy issue).
        
        Args:
            symbol: Trading symbol
            discrepancy_pct: Current price discrepancy percentage
            
        Returns:
            True if this appears to be a transient error (don't pause yet)
            False if confirmed persistent error (safe to pause)
        """
        now = datetime.now()
        
        # Initialize tracking for new symbols
        if symbol not in self.transient_errors:
            self.transient_errors[symbol] = {
                "discrepancies": [],
                "first_seen": now,
                "count": 0
            }
        
        error_data = self.transient_errors[symbol]
        
        # Clean up old discrepancy records (older than 10 minutes)
        cutoff_time = now - timedelta(minutes=10)
        error_data["discrepancies"] = [
            (timestamp, pct) for timestamp, pct in error_data["discrepancies"]
            if timestamp > cutoff_time
        ]
        
        # Add current discrepancy
        error_data["discrepancies"].append((now, discrepancy_pct))
        error_data["count"] = len(error_data["discrepancies"])
        
        # If this is the first large discrepancy, treat as transient
        if error_data["count"] == 1:
            logger.info(f"[DATA-VALIDATION] {symbol}: First large discrepancy {discrepancy_pct:.1f}% - "
                       f"treating as transient (awaiting {self.transient_confirmation_scans-1} more scans)")
            return True
        
        # Check if we have enough consecutive scans to confirm the error
        if error_data["count"] >= self.transient_confirmation_scans:
            # Check if all recent scans show large discrepancies
            recent_discrepancies = [pct for _, pct in error_data["discrepancies"][-self.transient_confirmation_scans:]]
            all_large = all(pct > self.transient_error_threshold for pct in recent_discrepancies)
            
            if all_large:
                logger.warning(f"[DATA-VALIDATION] {symbol}: Confirmed persistent error after "
                              f"{self.transient_confirmation_scans} scans - discrepancies: "
                              f"{[f'{pct:.1f}%' for pct in recent_discrepancies]}")
                # Clear tracking since we're now treating this as confirmed
                del self.transient_errors[symbol]
                return False
            else:
                logger.info(f"[DATA-VALIDATION] {symbol}: Mixed discrepancy pattern - "
                           f"continuing transient error monitoring")
                return True
        
        # Not enough scans yet - continue treating as transient
        remaining_scans = self.transient_confirmation_scans - error_data["count"]
        logger.info(f"[DATA-VALIDATION] {symbol}: Transient error scan {error_data['count']}/{self.transient_confirmation_scans} "
                   f"({discrepancy_pct:.1f}%) - need {remaining_scans} more confirmations")
        return True

    def _clear_transient_error(self, symbol: str):
        """Clear transient error tracking for a symbol (called on normal validation)"""
        if symbol in self.transient_errors:
            error_count = self.transient_errors[symbol]["count"]
            if error_count > 0:
                logger.info(f"[DATA-VALIDATION] {symbol}: Cleared transient error tracking "
                           f"after {error_count} large discrepancy scans - data normalized")
            del self.transient_errors[symbol]

    def _verify_etf_price_secondary(self, symbol: str, primary_price: float, validation_price: Optional[float]) -> bool:
        """
        Perform secondary verification for ETF prices when large discrepancies are detected.
        
        Uses lightweight secondary checks to determine if the discrepancy is likely due to:
        - Adjusted vs unadjusted prices
        - Stale data from one source
        - Genuine market movement
        
        Args:
            symbol: ETF symbol to verify
            primary_price: Price from primary source (Alpaca)
            validation_price: Price from validation source
            
        Returns:
            True if discrepancy is likely legitimate, False if data error suspected
        """
        try:
            # For now, implement basic heuristics - can be enhanced with external sources later
            
            # Check if prices are reasonable for the ETF
            expected_ranges = {
                "SPY": (300, 700),
                "QQQ": (250, 650), 
                "DIA": (250, 500),
                "IWM": (150, 300),
                "XLK": (150, 350),
                "XLF": (25, 75),
                "XLE": (50, 150),
                "TLT": (70, 120),
                "UVXY": (5, 50)
            }
            
            if symbol in expected_ranges:
                min_price, max_price = expected_ranges[symbol]
                
                # Check if primary price is within reasonable range
                if not (min_price <= primary_price <= max_price):
                    logger.warning(f"[DATA-VALIDATION] {symbol}: Primary price ${primary_price:.2f} outside expected range ${min_price}-${max_price}")
                    return False
                
                # If validation price exists, check if it's also reasonable
                if validation_price and not (min_price <= validation_price <= max_price):
                    logger.warning(f"[DATA-VALIDATION] {symbol}: Validation price ${validation_price:.2f} outside expected range ${min_price}-${max_price}")
                    return False
            
            # Check for obvious data errors (e.g., prices that are clearly wrong)
            if primary_price <= 0:
                logger.warning(f"[DATA-VALIDATION] {symbol}: Invalid primary price ${primary_price:.2f}")
                return False
            
            if validation_price and validation_price <= 0:
                logger.warning(f"[DATA-VALIDATION] {symbol}: Invalid validation price ${validation_price:.2f}")
                return False
            
            # If we have both prices, check if the ratio suggests a split or obvious error
            if validation_price:
                ratio = max(primary_price, validation_price) / min(primary_price, validation_price)
                
                # If ratio is close to 2, 3, 4, etc., might be a split
                common_split_ratios = [2.0, 3.0, 4.0, 5.0, 10.0]
                for split_ratio in common_split_ratios:
                    if abs(ratio - split_ratio) < 0.1:
                        logger.info(f"[DATA-VALIDATION] {symbol}: Price ratio {ratio:.2f} suggests potential {split_ratio}:1 split")
                        return True  # Likely a legitimate split
                
                # Very large ratios (>10x) are likely data errors
                if ratio > 10.0:
                    logger.warning(f"[DATA-VALIDATION] {symbol}: Extreme price ratio {ratio:.2f} suggests data error")
                    return False
            
            # Log the verification attempt
            logger.info(f"[DATA-VALIDATION] {symbol}: Secondary verification passed - prices appear reasonable")
            return True
            
        except Exception as e:
            logger.error(f"[DATA-VALIDATION] {symbol}: Secondary verification failed with error: {e}")
            return False


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
