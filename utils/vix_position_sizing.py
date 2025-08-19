"""
VIX-Adjusted Position Sizing Module (US-FA-006)

Automatically adjusts position sizes based on market volatility (VIX levels) to reduce risk
during volatile periods. Integrates with existing VIX monitoring infrastructure.

Position Sizing Rules:
- VIX < 20: Normal position sizing (100%)
- VIX 20-25: Normal position sizing (100%) 
- VIX > 25: Reduce position size by 50%
- VIX > 35: Reduce position size by 75%
"""

import logging
from typing import Dict, Tuple, Optional
from .vix_monitor import get_vix_monitor, VIXData
from .llm import load_config

logger = logging.getLogger(__name__)


class VIXPositionSizer:
    """
    VIX-based position sizing calculator that adjusts trade sizes based on market volatility.
    
    Uses the existing VIX monitoring infrastructure to determine appropriate position sizes
    during different volatility regimes.
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """Initialize VIX position sizer with configuration."""
        if config is None:
            config = load_config()
        
        self.config = config
        self.enabled = config.get("VIX_POSITION_SIZING_ENABLED", True)
        self.normal_threshold = config.get("VIX_NORMAL_THRESHOLD", 20.0)
        self.moderate_threshold = config.get("VIX_MODERATE_THRESHOLD", 25.0)
        self.high_threshold = config.get("VIX_HIGH_THRESHOLD", 35.0)
        self.moderate_reduction = config.get("VIX_MODERATE_REDUCTION", 0.5)  # 50% reduction
        self.high_reduction = config.get("VIX_HIGH_REDUCTION", 0.25)  # 75% reduction
        
        # Get VIX monitor instance
        self.vix_monitor = get_vix_monitor()
        
        logger.info(f"[VIX-SIZING] Initialized: enabled={self.enabled}, "
                   f"thresholds=({self.normal_threshold}, {self.moderate_threshold}, {self.high_threshold})")
    
    def get_vix_adjustment_factor(self) -> Tuple[float, str, Optional[float]]:
        """
        Get VIX-based position size adjustment factor
        
        Returns:
            Tuple of (adjustment_factor, reason, vix_value)
            - adjustment_factor: multiplier for position size (0.25-1.0)
            - reason: explanation of adjustment
            - vix_value: current VIX level or None if unavailable
        """
        if not self.enabled:
            return 1.0, "VIX position sizing disabled", None
        
        try:
            vix_data = self.vix_monitor.get_current_vix()
            if not vix_data:
                return 1.0, "VIX data unavailable - using normal sizing", None
            
            vix_value = vix_data.value
            
            if vix_value > self.high_threshold:
                return self.high_reduction, f"High volatility (VIX {vix_value:.1f}) - 75% size reduction", vix_value
            elif vix_value > self.moderate_threshold:
                return self.moderate_reduction, f"Moderate volatility (VIX {vix_value:.1f}) - 50% size reduction", vix_value
            else:
                return 1.0, f"Low volatility (VIX {vix_value:.1f}) - normal sizing", vix_value
        
        except Exception as e:
            logger.error(f"[VIX-SIZING] Error getting VIX data: {e}")
            return 1.0, "VIX data unavailable - using normal sizing", None
    
    def adjust_position_size(self, base_position_size: float, symbol: str = "SPY") -> Tuple[float, Dict]:
        """
        Adjust position size based on current VIX level.
        
        Args:
            base_position_size: Original calculated position size
            symbol: Trading symbol for logging context
            
        Returns:
            Tuple of (adjusted_size, adjustment_info)
            - adjusted_size: VIX-adjusted position size
            - adjustment_info: Dictionary with adjustment details for logging
        """
        if not self.enabled:
            return base_position_size, {
                "vix_enabled": False,
                "vix_value": None,
                "adjustment_factor": 1.0,
                "reason": "VIX position sizing disabled"
            }
        
        # Get VIX adjustment factor
        adjustment_factor, reason, vix_value = self.get_vix_adjustment_factor()
        
        # Calculate adjusted position size
        adjusted_size = base_position_size * adjustment_factor
        
        # Get VIX data for timestamp
        vix_data = self.vix_monitor.get_current_vix()
        
        # Create adjustment info for logging
        adjustment_info = {
            "vix_enabled": True,
            "vix_value": vix_value,
            "adjustment_factor": adjustment_factor,
            "base_size": base_position_size,
            "adjusted_size": adjusted_size,
            "size_reduction_pct": (1 - adjustment_factor) * 100,
            "reason": reason,
            "symbol": symbol,
            "timestamp": vix_data.timestamp.isoformat() if vix_data else None
        }
        
        # Log the adjustment
        if adjustment_factor < 1.0:
            logger.info(f"[VIX-SIZING] {symbol}: ${base_position_size:.2f} → ${adjusted_size:.2f} "
                       f"({adjustment_factor:.0%} sizing due to VIX {vix_value:.1f})")
        else:
            logger.debug(f"[VIX-SIZING] {symbol}: ${base_position_size:.2f} (no VIX adjustment)")
        
        return adjusted_size, adjustment_info
    
    def get_volatility_regime(self) -> Tuple[str, Optional[float]]:
        """
        Classify current market volatility regime based on VIX level.
        
        Returns:
            Tuple of (regime, vix_value)
            - regime: "LOW", "NORMAL", "MODERATE", "HIGH", or "EXTREME"
            - vix_value: Current VIX level or None
        """
        if not self.enabled:
            return "UNKNOWN", None
        
        vix_data = self.vix_monitor.get_current_vix()
        if not vix_data:
            return "UNKNOWN", None
        
        vix_value = vix_data.value
        
        if vix_value < self.normal_threshold:
            regime = "LOW"
        elif vix_value <= self.moderate_threshold:
            regime = "NORMAL"
        elif vix_value <= self.high_threshold:
            regime = "MODERATE"
        else:
            regime = "HIGH"
        
        return regime, vix_value
    
    def should_reduce_exposure(self) -> Tuple[bool, str, Optional[float]]:
        """
        Check if current VIX level suggests reducing overall market exposure.
        
        Returns:
            Tuple of (should_reduce, reason, vix_value)
        """
        if not self.enabled:
            return False, "VIX position sizing disabled", None
        
        adjustment_factor, reason, vix_value = self.get_vix_adjustment_factor()
        should_reduce = adjustment_factor < 1.0
        
        return should_reduce, reason, vix_value


# Singleton instance for global access
_vix_sizer_instance: Optional[VIXPositionSizer] = None


def get_vix_position_sizer(config: Optional[Dict] = None) -> VIXPositionSizer:
    """Get singleton VIX position sizer instance."""
    global _vix_sizer_instance
    if _vix_sizer_instance is None:
        _vix_sizer_instance = VIXPositionSizer(config)
    return _vix_sizer_instance


def calculate_vix_adjusted_size(base_size: float, symbol: str = "SPY") -> Tuple[float, Dict]:
    """
    Convenience function to calculate VIX-adjusted position size.
    
    Args:
        base_size: Original position size
        symbol: Trading symbol
        
    Returns:
        Tuple of (adjusted_size, adjustment_info)
    """
    sizer = get_vix_position_sizer()
    return sizer.adjust_position_size(base_size, symbol)


if __name__ == "__main__":
    # Test VIX position sizing
    sizer = VIXPositionSizer()
    
    print("VIX Position Sizing Test:")
    
    # Test adjustment factor
    factor, reason, vix_value = sizer.get_vix_adjustment_factor()
    print(f"VIX Value: {vix_value:.2f}" if vix_value else "VIX Value: N/A")
    print(f"Adjustment Factor: {factor:.2f}")
    print(f"Reason: {reason}")
    
    # Test position adjustment
    base_size = 1000.0
    adjusted_size, info = sizer.adjust_position_size(base_size, "SPY")
    print(f"\nPosition Size Test:")
    print(f"Base Size: ${base_size:.2f}")
    print(f"Adjusted Size: ${adjusted_size:.2f}")
    print(f"Reduction: {info['size_reduction_pct']:.1f}%")
    
    # Test volatility regime
    regime, vix = sizer.get_volatility_regime()
    print(f"\nVolatility Regime: {regime}")
