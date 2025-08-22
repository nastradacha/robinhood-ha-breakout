"""
Symbol State Management for Corporate Actions and Data Validation

Manages symbol states during suspected corporate actions (splits, dividends, etc.)
to prevent trading on inconsistent data.
"""

import json
import logging
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
    """Detects probable stock splits from price ratios"""
    
    COMMON_SPLIT_RATIOS = [0.5, 0.333, 0.25, 0.2, 2.0, 3.0, 4.0, 5.0]
    SPLIT_TOLERANCE = 0.05  # 5% tolerance for split detection
    
    @classmethod
    def detect_split(cls, current_price: float, historical_price: float) -> Optional[Tuple[float, str]]:
        """
        Detect if price difference suggests a stock split
        
        Returns:
            Tuple of (split_factor, description) or None if no split detected
        """
        if current_price <= 0 or historical_price <= 0:
            return None
            
        ratio = current_price / historical_price
        
        # Check against common split ratios
        for split_ratio in cls.COMMON_SPLIT_RATIOS:
            if abs(ratio - split_ratio) <= cls.SPLIT_TOLERANCE:
                if split_ratio < 1.0:
                    # Forward split (e.g., 2:1, 3:1)
                    split_factor = 1.0 / split_ratio
                    return (split_factor, f"{int(split_factor)}:1 forward split")
                else:
                    # Reverse split (e.g., 1:2, 1:3)
                    return (split_ratio, f"1:{int(split_ratio)} reverse split")
        
        # Check for large price differences that might be splits
        if ratio < 0.1 or ratio > 10.0:
            return (ratio, f"unusual price ratio {ratio:.2f}x")
            
        return None

class SymbolStateManager:
    """
    Manages symbol states during corporate actions and data validation issues
    """
    
    def __init__(self, state_file: str = "symbol_states.json"):
        self.state_file = Path(state_file)
        self.states = self._load_states()
        self.stability_required_scans = 3  # Require 3 stable scans before unquarantining
        
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
        """Get current state of a symbol"""
        symbol_data = self.states.get(symbol, {})
        state_str = symbol_data.get("state", "normal")
        try:
            return SymbolState(state_str)
        except ValueError:
            return SymbolState.NORMAL
    
    def is_symbol_tradeable(self, symbol: str) -> bool:
        """Check if symbol is safe for trading"""
        state = self.get_symbol_state(symbol)
        return state == SymbolState.NORMAL
    
    def quarantine_symbol(self, symbol: str, reason: str, current_price: float, 
                         historical_price: float, suspected_split: Optional[Tuple[float, str]] = None):
        """Quarantine a symbol due to suspected corporate action"""
        now = datetime.now().isoformat()
        
        symbol_data = {
            "state": SymbolState.QUARANTINED.value,
            "reason": reason,
            "quarantined_at": now,
            "current_price": current_price,
            "historical_price": historical_price,
            "stable_scans": 0,
            "last_scan": now
        }
        
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
    
    def record_stable_scan(self, symbol: str, current_price: float, validation_price: float) -> bool:
        """
        Record a stable scan for a quarantined symbol
        
        Returns:
            True if symbol should be unquarantined, False otherwise
        """
        if symbol not in self.states:
            return True  # Not quarantined
            
        symbol_data = self.states[symbol]
        state = SymbolState(symbol_data.get("state", "normal"))
        
        if state != SymbolState.QUARANTINED:
            return True  # Not quarantined
        
        # Check if prices are stable (within 2% of each other)
        price_diff_pct = abs(current_price - validation_price) / max(current_price, validation_price) * 100
        is_stable = price_diff_pct <= 2.0
        
        if is_stable:
            symbol_data["stable_scans"] = symbol_data.get("stable_scans", 0) + 1
            logger.info(f"[SYMBOL-STATE] {symbol} stable scan {symbol_data['stable_scans']}/{self.stability_required_scans}")
        else:
            # Reset stable scan count if prices are unstable
            symbol_data["stable_scans"] = 0
            logger.info(f"[SYMBOL-STATE] {symbol} unstable scan - prices differ by {price_diff_pct:.1f}%")
        
        symbol_data["last_scan"] = datetime.now().isoformat()
        symbol_data["last_current_price"] = current_price
        symbol_data["last_validation_price"] = validation_price
        
        # Check if we have enough stable scans to unquarantine
        if symbol_data["stable_scans"] >= self.stability_required_scans:
            logger.info(f"[SYMBOL-STATE] {symbol} UNQUARANTINED after {symbol_data['stable_scans']} stable scans")
            symbol_data["state"] = SymbolState.NORMAL.value
            symbol_data["unquarantined_at"] = datetime.now().isoformat()
            self._save_states()
            return True
        
        self._save_states()
        return False
    
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
