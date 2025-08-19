"""
Cross-Source Data Validation Module (US-FA-007)

Validates market data quality across multiple sources to ensure trading decisions
are based on accurate, timely information. Prioritizes real-time Alpaca data
while using Yahoo Finance for validation and fallback scenarios.

Key Features:
- Cross-source price validation with configurable tolerance
- Data staleness detection and alerting
- Automatic fallback when primary source fails
- Comprehensive logging for data quality monitoring
- Slack alerts for critical data discrepancies

Data Source Priority:
1. Primary: Alpaca API (real-time, professional-grade)
2. Validation: Yahoo Finance (delayed, for cross-reference)
3. Fallback: Yahoo Finance (when Alpaca unavailable)

Author: Robinhood HA Breakout System
Version: 1.0.0 (US-FA-007)
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import pandas as pd
import yfinance as yf
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
    recommendation: str
    timestamp: datetime


class DataValidator:
    """
    Cross-source data validation system for market data quality assurance
    """
    
    def __init__(self, config: Dict = None):
        """Initialize data validator with configuration"""
        self.config = config or {}
        
        # Validation thresholds
        self.max_discrepancy_pct = self.config.get("DATA_MAX_DISCREPANCY_PCT", 1.0)
        self.max_staleness_seconds = self.config.get("DATA_MAX_STALENESS_SECONDS", 120)
        self.validation_enabled = self.config.get("DATA_VALIDATION_ENABLED", True)
        self.require_validation = self.config.get("DATA_REQUIRE_VALIDATION", False)
        
        # Initialize clients
        self.alpaca_client = None
        self.slack = None
        
        try:
            self.alpaca_client = AlpacaClient()
            logger.info("[DATA-VALIDATION] Alpaca client initialized")
        except Exception as e:
            logger.warning(f"[DATA-VALIDATION] Alpaca client unavailable: {e}")
        
        try:
            self.slack = EnhancedSlackIntegration()
            logger.info("[DATA-VALIDATION] Slack integration initialized")
        except Exception as e:
            logger.warning(f"[DATA-VALIDATION] Slack unavailable: {e}")
    
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
        """Get current price from Yahoo Finance"""
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period="1d", interval="1m")
            
            if not data.empty:
                latest_price = float(data["Close"].iloc[-1])
                latest_time = data.index[-1].to_pydatetime()
                
                return DataPoint(
                    value=latest_price,
                    timestamp=latest_time,
                    source="yahoo",
                    symbol=symbol,
                    data_type="price"
                )
        except Exception as e:
            logger.warning(f"[DATA-VALIDATION] Yahoo price fetch failed for {symbol}: {e}")
        
        return None
    
    def calculate_discrepancy(self, primary: DataPoint, validation: DataPoint) -> float:
        """Calculate percentage discrepancy between two data points"""
        if primary.value == 0:
            return float('inf')
        
        return abs(primary.value - validation.value) / primary.value * 100.0
    
    def validate_symbol_data(self, symbol: str) -> ValidationResult:
        """
        Validate data quality for a single symbol across sources
        
        Returns ValidationResult with quality assessment and recommendations
        """
        issues = []
        
        # Get data from both sources
        alpaca_data = self.get_alpaca_price(symbol)
        yahoo_data = self.get_yahoo_price(symbol)
        
        # Determine primary and validation data
        primary_data = alpaca_data if alpaca_data else yahoo_data
        validation_data = yahoo_data if alpaca_data else None
        
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
        if validation_data and not validation_data.is_stale(300):  # Allow 5min for Yahoo
            discrepancy_pct = self.calculate_discrepancy(primary_data, validation_data)
            
            if discrepancy_pct > self.max_discrepancy_pct:
                issues.append(f"Price discrepancy {discrepancy_pct:.2f}% exceeds threshold {self.max_discrepancy_pct}%")
        
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
        
        # Poor: Stale primary data
        if primary.is_stale(self.max_staleness_seconds):
            if self.require_validation:
                return DataQuality.POOR, "BLOCK_TRADING"
            else:
                return DataQuality.POOR, "PROCEED_WITH_CAUTION"
        
        # Poor: High discrepancy between sources
        if discrepancy_pct and discrepancy_pct > self.max_discrepancy_pct:
            if self.require_validation:
                return DataQuality.POOR, "REQUIRE_MANUAL_APPROVAL"
            else:
                return DataQuality.ACCEPTABLE, "PROCEED_WITH_CAUTION"
        
        # Excellent: Real-time primary + validated
        if primary.source == "alpaca" and validation and discrepancy_pct is not None and discrepancy_pct <= self.max_discrepancy_pct:
            return DataQuality.EXCELLENT, "PROCEED_NORMAL"
        
        # Good: Real-time primary, no validation
        if primary.source == "alpaca":
            return DataQuality.GOOD, "PROCEED_NORMAL"
        
        # Acceptable: Delayed but recent data
        return DataQuality.ACCEPTABLE, "PROCEED_WITH_CAUTION"
    
    def _log_validation_result(self, result: ValidationResult):
        """Log validation result with appropriate level"""
        primary_info = f"{result.primary_data.source}:${result.primary_data.value:.2f}" if result.primary_data else "None"
        validation_info = f"{result.validation_data.source}:${result.validation_data.value:.2f}" if result.validation_data else "None"
        discrepancy_info = f"{result.discrepancy_pct:.2f}%" if result.discrepancy_pct else "N/A"
        
        log_msg = (f"[DATA-VALIDATION] {result.symbol}: Quality={result.quality.value.upper()}, "
                  f"Primary={primary_info}, Validation={validation_info}, "
                  f"Discrepancy={discrepancy_info}, Recommendation={result.recommendation}")
        
        if result.quality in [DataQuality.CRITICAL, DataQuality.POOR]:
            logger.error(log_msg)
            if result.issues:
                logger.error(f"[DATA-VALIDATION] Issues: {', '.join(result.issues)}")
        elif result.quality == DataQuality.ACCEPTABLE:
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
    
    def should_allow_trading(self, symbol: str) -> Tuple[bool, str]:
        """
        Determine if trading should be allowed based on data quality
        
        Returns:
            Tuple of (allow_trading, reason)
        """
        if not self.validation_enabled:
            return True, "Data validation disabled"
        
        result = self.validate_symbol_data(symbol)
        
        if result.recommendation == "BLOCK_TRADING":
            return False, f"Data quality too poor: {', '.join(result.issues)}"
        elif result.recommendation == "REQUIRE_MANUAL_APPROVAL":
            return False, f"Manual approval required: {result.discrepancy_pct:.2f}% discrepancy"
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
