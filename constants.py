#!/usr/bin/env python3
"""
TradingInsight Pro v4.2.1 - Core Constants
Critical system constants for unified behavior across all modules.
Last Updated: September 27, 2025
"""

# Risk/Reward Minimum Threshold
# All signals with R/R below this value will be rejected
MIN_RR = 2.0

# Portfolio Risk Limits
MAX_POSITIONS = 3
MAX_PORTFOLIO_RISK_PERCENT = 6.0
MAX_SINGLE_POSITION_RISK_PERCENT = 2.5

# Safety Score Bounds
MIN_SAFETY_SCORE = 1
MAX_SAFETY_SCORE = 10
DEFAULT_MIN_SAFETY_THRESHOLD = 5

# Regime Analysis Constants
DEFAULT_REGIME_STRENGTH = 0.5
MIN_REGIME_STRENGTH_FOR_TRADING = 0.3

# Futures Trading Constants
DEFAULT_LEVERAGE = 20
MAX_LEVERAGE = 50
MIN_POSITION_SIZE_USDT = 100

# Time-based Constants
DEFAULT_TIMEFRAME = '1h'
CHANDELIER_PERIODS = 22
CHANDELIER_MULTIPLIER = 3.0

# Market Analysis Constants
HIGH_VOLUME_THRESHOLD = 1.5
NORMAL_VOLATILITY_MAX = 0.03
HIGH_VOLATILITY_MIN = 0.05


def get_regime_strength(regime):
    """
    Safe regime strength accessor that handles dict/object/None types
    
    Args:
        regime: Can be dict, object with attributes, or None
        
    Returns:
        float: Regime strength value (0.0-1.0), defaults to DEFAULT_REGIME_STRENGTH
    """
    if regime is None:
        return DEFAULT_REGIME_STRENGTH
    if isinstance(regime, dict):
        return float(regime.get('strength', DEFAULT_REGIME_STRENGTH))
    # Handle object with attributes
    if hasattr(regime, 'strength'):
        return float(getattr(regime, 'strength', DEFAULT_REGIME_STRENGTH))
    if hasattr(regime, 'regime_strength'):
        return float(getattr(regime, 'regime_strength', DEFAULT_REGIME_STRENGTH))
    return DEFAULT_REGIME_STRENGTH


def safe_get_signal_field(signal_data, field_name, default=None):
    """
    Safe signal field accessor with fallbacks for formatter hardening
    
    Args:
        signal_data: Signal dictionary
        field_name: Field name to access
        default: Default value if field missing
        
    Returns:
        Field value or default
    """
    if not isinstance(signal_data, dict):
        return default
    
    # Special handling for common fields with sensible defaults
    if field_name == 'regime_strength':
        regime = signal_data.get('regime')
        return get_regime_strength(regime)
    elif field_name == 'confidence_level':
        confidence = signal_data.get('confidence', 0.5)
        return f"{confidence:.2f}"
    elif field_name == 'futures_status':
        return 'Approved' if signal_data.get('futures_approved', True) else 'Rejected'
    elif field_name == 'leverage':
        return signal_data.get('leverage', DEFAULT_LEVERAGE)
    elif field_name == 'safety_score':
        return signal_data.get('safety_score', DEFAULT_MIN_SAFETY_THRESHOLD)
    
    return signal_data.get(field_name, default)