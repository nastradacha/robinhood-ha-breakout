"""
Symbol State Management for Corporate Actions and Data Validation

Manages symbol states during suspected corporate actions (splits, dividends, etc.)
to prevent trading on inconsistent data.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple, List
from enum import Enum
import math

logger = logging.getLogger(__name__)

class SymbolState(Enum):
    """Symbol validation states"""
    NORMAL = "normal"
    SUSPECTED_SPLIT = "suspected_split"
    QUARANTINED = "quarantined"
    UNSTABLE = "unstable"

class SplitDetector:
    """Detects probable stock splits from price ratios with ETF protection and multi-scan confirmation"""
    
    COMMON_SPLIT_RATIOS = [0.5, 0.333, 0.25, 0.2, 2.0, 3.0, 4.0, 5.0]
    SPLIT_TOLERANCE = 0.02  # 2% tolerance for split detection (tighter)
    SPLIT_TOLERANCE_ETF = 0.005  # 0.5% tolerance for ETFs (much tighter)
    
    # ETFs that should have higher tolerance for price discrepancies
    ETF_WHITELIST = {
        'SPY', 'QQQ', 'IWM', 'DIA', 'XLK', 'XLF', 'XLE', 'XLI', 'XLV', 'XLY', 
        'XLP', 'XLB', 'XLU', 'XLRE', 'TLT', 'GLD', 'SLV', 'VIX', 'UVXY', 'SQQQ', 'TQQQ'
    }
    
    # Legacy alias for backward compatibility
    SAFE_ETFS = ETF_WHITELIST
    
    # Multi-scan confirmation requirements
    CONSEC_REQUIRED = 2      # Regular symbols need 2 consecutive confirmations
    CONSEC_REQUIRED_ETF = 5  # ETFs need 5 consecutive confirmations (increased from 3)
    STABLE_SCANS_UNQUARANTINE = 2  # Require 2 clean scans to release
    
    # Enhanced ETF protection thresholds
    ETF_MIN_GAP = 0.20      # 20%+ absolute gap required for ETFs (reduced from 35%)
    RATIO_TOLERANCE = 0.005  # within 0.5% of exact ratios (2.0x, 4.0x, etc.) - tighter
    
    # Minimum ratio threshold for split detection (prevents minor discrepancies)
    MIN_SPLIT_RATIO_THRESHOLD = 1.8  # Must be at least 1.8x difference
    
    @classmethod
    def detect_split(cls, current_price: float, historical_price: float, symbol: str = None) -> Optional[Tuple[float, str]]:
        """
        Detect if price difference suggests a stock split with enhanced ETF protection
        
        Args:
            current_price: Current market price
            historical_price: Historical reference price
            symbol: Symbol being checked (for ETF whitelist)
        
        Returns:
            Tuple of (split_factor, description) or None if no split detected
        """
        if current_price <= 0 or historical_price <= 0:
            return None
            
        ratio = current_price / historical_price
        
        # Early parity guard: if prices are within 5%, immediately return None
        if abs(ratio - 1.0) < 0.05:  # ±5% parity check
            return None
            
        is_etf = symbol and symbol in cls.ETF_WHITELIST
        
        # Enhanced ETF protection with much stricter criteria
        if is_etf:
            price_diff_pct = abs(current_price - historical_price) / max(current_price, historical_price)
            
            # Require significant gap for ETFs (reduced threshold but still protective)
            if price_diff_pct < cls.ETF_MIN_GAP:
                return None
            
            # For ETFs, only trigger on extreme ratios that are very close to clean splits
            extreme_ratios = [0.2, 0.25, 0.333, 0.5, 2.0, 3.0, 4.0, 5.0]  # Only extreme splits
            tolerance = cls.SPLIT_TOLERANCE_ETF  # Much tighter tolerance for ETFs
            
            is_clean_ratio = any(abs(ratio - r) <= tolerance for r in extreme_ratios)
            
            if not is_clean_ratio:
                logger.debug(f"[SPLIT-DETECTOR] ETF {symbol} gap {price_diff_pct:.1%} but ratio {ratio:.3f}x not extreme clean split")
                return None
                
            # Reject mid-range ratios for ETFs (belt-and-suspenders guard)
            # Make this more exclusive - reject anything close to 2.0 for ETFs
            if 0.35 < ratio < 2.8:
                logger.debug(f"[SPLIT-DETECTOR] ETF {symbol} ratio {ratio:.3f}x in mid-range - rejected for ETF protection")
                return None
                
            logger.debug(f"[SPLIT-DETECTOR] ETF {symbol} passed enhanced protection: {price_diff_pct:.1%} gap, {ratio:.3f}x extreme ratio")
        
        # Require minimum threshold to avoid false positives
        if cls.MIN_SPLIT_RATIO_THRESHOLD > ratio > (1.0 / cls.MIN_SPLIT_RATIO_THRESHOLD):
            return None
        
        # Use appropriate tolerance based on symbol type
        tolerance = cls.SPLIT_TOLERANCE_ETF if is_etf else cls.SPLIT_TOLERANCE
        
        # Check against common split ratios
        for split_ratio in cls.COMMON_SPLIT_RATIOS:
            if abs(ratio - split_ratio) <= tolerance:
                if split_ratio < 1.0:
                    # Forward split (e.g., 2:1, 3:1)
                    split_factor = 1.0 / split_ratio
                    return (split_factor, f"{int(split_factor)}:1 forward split")
                else:
                    # Reverse split (e.g., 1:2, 1:3)
                    return (split_ratio, f"1:{int(split_ratio)} reverse split")
        
        # Check for large price differences that might be splits (more conservative for ETFs)
        extreme_threshold = 0.05 if is_etf else 0.1  # ETFs need 20x difference, others 10x
        if ratio < extreme_threshold or ratio > (1.0 / extreme_threshold):
            return (ratio, f"unusual price ratio {ratio:.2f}x")
            
        return None
    
    @classmethod
    def is_etf(cls, symbol: str) -> bool:
        """Check if symbol is in ETF whitelist"""
        return symbol.upper() in cls.ETF_WHITELIST

class SymbolStateManager:
    """
    Manages symbol states during corporate actions and data validation issues
    with self-healing quarantine capabilities
    """
    
    # Quarantine TTL and stability constants
    QUARANTINE_TTL_SEC = 30 * 60   # 30 minutes auto-expiry
    STABLE_RELEASE_SCANS = 2        # 2 consecutive clean scans for release
    STABLE_RELEASE_TOLERANCE = 0.01 # 1% diff considered "normal" for release
    
    def __init__(self, state_file: str = "symbol_states.json"):
        self.state_file = Path(state_file)
        self.states = self._load_states()
        self.stability_required_scans = self.STABLE_RELEASE_SCANS
        
    def _load_states(self) -> Dict:
        """Load symbol states from file"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"[SYMBOL-STATE] Error loading states: {e}")
        
        return {}
    
    def _save_states(self):
        """Save symbol states to file"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.states, f, indent=2)
        except Exception as e:
            logger.error(f"[SYMBOL-STATE] Error saving states: {e}")
    
    def get_symbol_state(self, symbol: str) -> SymbolState:
        """Get current state of a symbol with TTL auto-expiry"""
        symbol_data = self.states.get(symbol, {})
        
        # Check TTL auto-expiry for quarantined symbols
        if symbol_data.get("state") == SymbolState.QUARANTINED.value:
            quarantined_at = symbol_data.get("quarantined_timestamp")
            if quarantined_at and (time.time() - quarantined_at) > self.QUARANTINE_TTL_SEC:
                self._unquarantine_symbol(symbol, "ttl_expired")
                return SymbolState.NORMAL
        
        state_str = symbol_data.get("state", "normal")
        try:
            return SymbolState(state_str)
        except ValueError:
            return SymbolState.NORMAL
    
    def is_symbol_tradeable(self, symbol: str) -> bool:
        """Check if symbol is safe for trading (includes TTL check)"""
        state = self.get_symbol_state(symbol)  # This handles TTL auto-expiry
        return state == SymbolState.NORMAL
    
    def is_quarantined(self, symbol: str) -> bool:
        """Check if symbol is quarantined (includes TTL auto-expiry)"""
        state = self.get_symbol_state(symbol)  # This handles TTL auto-expiry
        return state == SymbolState.QUARANTINED
    
    def record_suspected_split(self, symbol: str, reason: str, current_price: float, 
                              historical_price: float, suspected_split: Optional[Tuple[float, str]] = None) -> bool:
        """Record a suspected split and return True if symbol should be quarantined"""
        now = datetime.now().isoformat()
        is_etf = SplitDetector.is_etf(symbol)
        required_hits = SplitDetector.CONSEC_REQUIRED_ETF if is_etf else SplitDetector.CONSEC_REQUIRED
        
        # Get or create symbol data
        if symbol not in self.states:
            self.states[symbol] = {
                "state": SymbolState.NORMAL.value,
                "suspect_hits": 0,
                "stable_scans": 0
            }
        
        symbol_data = self.states[symbol]
        
        # Increment suspect hits
        symbol_data["suspect_hits"] = symbol_data.get("suspect_hits", 0) + 1
        symbol_data["last_suspect_scan"] = now
        symbol_data["last_suspect_reason"] = reason
        symbol_data["last_current_price"] = current_price
        symbol_data["last_historical_price"] = historical_price
        
        if suspected_split:
            split_factor, split_desc = suspected_split
            symbol_data["last_suspected_split"] = {
                "factor": split_factor,
                "description": split_desc,
                "detected_at": now
            }
        
        logger.info(f"[SYMBOL-STATE] {symbol} suspect hit {symbol_data['suspect_hits']}/{required_hits} - {reason}")
        
        # Check if we should quarantine
        if symbol_data["suspect_hits"] >= required_hits:
            self._do_quarantine(symbol, reason, current_price, historical_price, suspected_split)
            return True
        
        self._save_states()
        return False
    
    def record_clean_scan(self, symbol: str):
        """Record a clean scan (no split detected) - resets suspect hits"""
        if symbol in self.states:
            symbol_data = self.states[symbol]
            if symbol_data.get("suspect_hits", 0) > 0:
                logger.info(f"[SYMBOL-STATE] {symbol} clean scan - resetting suspect hits from {symbol_data.get('suspect_hits', 0)} to 0")
                symbol_data["suspect_hits"] = 0
                symbol_data["last_clean_scan"] = datetime.now().isoformat()
                self._save_states()
    
    def _do_quarantine(self, symbol: str, reason: str, current_price: float, 
                      historical_price: float, suspected_split: Optional[Tuple[float, str]] = None):
        """Actually quarantine a symbol after confirmation"""
        now = datetime.now().isoformat()
        
        symbol_data = self.states.get(symbol, {})
        symbol_data.update({
            "state": SymbolState.QUARANTINED.value,
            "reason": reason,
            "quarantined_at": now,
            "quarantined_timestamp": time.time(),  # For TTL calculations
            "current_price": current_price,
            "historical_price": historical_price,
            "stable_scans": 0,
            "last_scan": now
        })
        
        if suspected_split:
            split_factor, split_desc = suspected_split
            symbol_data["suspected_split"] = {
                "factor": split_factor,
                "description": split_desc,
                "detected_at": now
            }
            logger.warning(f"[SYMBOL-STATE] {symbol} QUARANTINED - {split_desc}: ${current_price:.2f} vs ${historical_price:.2f}")
        else:
            logger.warning(f"[SYMBOL-STATE] {symbol} QUARANTINED - {reason}")
        
        self.states[symbol] = symbol_data
        self._save_states()
    
    def quarantine_symbol(self, symbol: str, reason: str, current_price: float, 
                         historical_price: float, suspected_split: Optional[Tuple[float, str]] = None):
        """Legacy method - directly quarantine (for non-split issues)"""
        self._do_quarantine(symbol, reason, current_price, historical_price, suspected_split)
    
    def record_stable_scan(self, symbol: str, price_diff_pct: float) -> bool:
        """
        Record a stable scan for a quarantined symbol with enhanced release logic
        
        Args:
            symbol: Symbol to check
            price_diff_pct: Price difference percentage from validation
        
        Returns:
            True if symbol should be unquarantined, False otherwise
        """
        if symbol not in self.states:
            return True  # Not quarantined
            
        symbol_data = self.states[symbol]
        state = SymbolState(symbol_data.get("state", "normal"))
        
        if state != SymbolState.QUARANTINED:
            return True  # Not quarantined
        
        # Check if price difference is within stable tolerance (convert percentage to decimal)
        is_stable = abs(price_diff_pct) <= (self.STABLE_RELEASE_TOLERANCE * 100)
        
        if is_stable:
            symbol_data["stable_scans"] = symbol_data.get("stable_scans", 0) + 1
            logger.info(f"[SYMBOL-STATE] {symbol} stable scan {symbol_data['stable_scans']}/{self.stability_required_scans} (diff: {price_diff_pct:.3f}%)")
        else:
            # Reset stable scan count if prices are unstable
            symbol_data["stable_scans"] = 0
            logger.info(f"[SYMBOL-STATE] {symbol} unstable scan - price diff {price_diff_pct:.3f}% > {self.STABLE_RELEASE_TOLERANCE:.1%}")
        
        symbol_data["last_scan"] = datetime.now().isoformat()
        symbol_data["last_price_diff_pct"] = price_diff_pct
        
        # Check if we have enough stable scans to unquarantine
        if symbol_data["stable_scans"] >= self.stability_required_scans:
            self._unquarantine_symbol(symbol, "stable_scans_ok")
            return True
        
        self._save_states()
        return False
    
    def _unquarantine_symbol(self, symbol: str, reason: str):
        """Unquarantine a symbol with enhanced logging"""
        if symbol in self.states:
            symbol_data = self.states[symbol]
            stable_scans = symbol_data.get("stable_scans", 0)
            required_scans = SplitDetector.STABLE_SCANS_UNQUARANTINE
            
            logger.info(f"[SYMBOL-STATE] {symbol} UNQUARANTINED - {reason} (stable_scans={stable_scans}/{required_scans})")
            
            symbol_data["state"] = SymbolState.NORMAL.value
            symbol_data["unquarantined_at"] = datetime.now().isoformat()
            symbol_data["unquarantine_reason"] = reason
            symbol_data["suspect_hits"] = 0  # Reset suspect hits on unquarantine
            self._save_states()
    
    def cleanup_old_states(self, max_age_hours: int = 24):
        """Remove old quarantine states"""
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        to_remove = []
        
        for symbol, data in self.states.items():
            quarantined_at = data.get("quarantined_at")
            if quarantined_at:
                try:
                    quarantine_time = datetime.fromisoformat(quarantined_at)
                    if quarantine_time < cutoff:
                        to_remove.append(symbol)
                except ValueError:
                    to_remove.append(symbol)  # Invalid timestamp
        
        for symbol in to_remove:
            logger.info(f"[SYMBOL-STATE] Cleaning up old state for {symbol}")
            del self.states[symbol]
        
        if to_remove:
            self._save_states()
    
    def get_quarantined_symbols(self) -> List[str]:
        """Get list of currently quarantined symbols"""
        quarantined = []
        for symbol, data in self.states.items():
            if data.get("state") == SymbolState.QUARANTINED.value:
                quarantined.append(symbol)
        return quarantined
    
    def get_symbol_info(self, symbol: str) -> Dict:
        """Get detailed info about a symbol's state"""
        return self.states.get(symbol, {"state": "normal"})


# Global instance
_symbol_state_manager = None

def get_symbol_state_manager() -> SymbolStateManager:
    """Get singleton instance of SymbolStateManager"""
    global _symbol_state_manager
    if _symbol_state_manager is None:
        _symbol_state_manager = SymbolStateManager()
    return _symbol_state_manager
