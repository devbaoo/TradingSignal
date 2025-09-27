"""
Unified Time Stop Management System
Provides timeframe-adaptive time stop configuration.
"""

import logging
from typing import Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class TimeStopConfig:
    """Configuration for time-based stops by timeframe."""
    base_time_stop_candles: int
    min_candles: int
    max_candles: int
    atr_lookback_multiplier: float  # Multiplier for ATR lookback period

class UnifiedTimeStopManager:
    """Manages time-based stops with timeframe and strategy adaptation."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Timeframe-specific time stop configurations
        self.timeframe_configs = {
            '1m': TimeStopConfig(
                base_time_stop_candles=30,  # 30 minutes for 1m charts
                min_candles=20,
                max_candles=60,
                atr_lookback_multiplier=2.0
            ),
            '5m': TimeStopConfig(
                base_time_stop_candles=20,  # 100 minutes for 5m charts  
                min_candles=12,
                max_candles=40,
                atr_lookback_multiplier=1.8
            ),
            '15m': TimeStopConfig(
                base_time_stop_candles=15,  # 225 minutes (3.75h) for 15m charts
                min_candles=10,
                max_candles=25,
                atr_lookback_multiplier=1.5
            ),
            '1h': TimeStopConfig(
                base_time_stop_candles=12,  # 12 hours for 1h charts
                min_candles=8,
                max_candles=20,
                atr_lookback_multiplier=1.2
            ),
            '4h': TimeStopConfig(
                base_time_stop_candles=8,   # 32 hours (1.3 days) for 4h charts
                min_candles=6,
                max_candles=15,
                atr_lookback_multiplier=1.0
            ),
            '1d': TimeStopConfig(
                base_time_stop_candles=5,   # 5 days for daily charts
                min_candles=3,
                max_candles=10,
                atr_lookback_multiplier=0.8
            )
        }
        
        # Strategy-specific adjustments
        self.strategy_multipliers = {
            'momentum': 0.8,      # Shorter stops for momentum trades
            'trend_following': 1.2, # Longer stops for trend following
            'mean_reversion': 0.6,  # Very short stops for mean reversion
            'breakout': 1.0,        # Standard stops for breakouts
            'swing': 1.5,           # Longer stops for swing trades
            'scalp': 0.4            # Very short stops for scalping
        }
        
        # Market condition adjustments
        self.market_condition_multipliers = {
            'high_volatility': 1.3,   # Longer stops in volatile markets
            'low_volatility': 0.8,    # Shorter stops in calm markets
            'trending': 1.1,          # Slightly longer in trending markets
            'sideways': 0.9,          # Shorter stops in ranging markets
            'high_volume': 1.0,       # Standard in high volume
            'low_volume': 0.7         # Shorter in low volume
        }
    
    def calculate_time_stop_candles(self,
                                  timeframe: str,
                                  strategy_type: str = 'momentum',
                                  market_condition: str = 'trending',
                                  safety_score: int = 7,
                                  confidence: float = 0.75) -> int:
        """
        Calculate adaptive time stop based on multiple factors.
        
        Args:
            timeframe: Trading timeframe (1m, 5m, 15m, 1h, 4h, 1d)
            strategy_type: Type of strategy being used
            market_condition: Current market condition
            safety_score: Signal safety score (1-10)
            confidence: Signal confidence (0.0-1.0)
            
        Returns:
            Number of candles for time stop
        """
        
        # Get base configuration
        config = self.timeframe_configs.get(timeframe)
        if not config:
            self.logger.warning(f"Unknown timeframe {timeframe}, using 5m default")
            config = self.timeframe_configs['5m']
        
        base_candles = config.base_time_stop_candles
        
        # Apply strategy adjustment
        strategy_multiplier = self.strategy_multipliers.get(strategy_type, 1.0)
        
        # Apply market condition adjustment
        market_multiplier = self.market_condition_multipliers.get(market_condition, 1.0)
        
        # Apply safety score adjustment (higher safety = longer stops)
        safety_multiplier = self._calculate_safety_multiplier(safety_score)
        
        # Apply confidence adjustment (higher confidence = longer stops)
        confidence_multiplier = self._calculate_confidence_multiplier(confidence)
        
        # Calculate final candles
        calculated_candles = int(
            base_candles * 
            strategy_multiplier * 
            market_multiplier * 
            safety_multiplier * 
            confidence_multiplier
        )
        
        # Apply bounds
        final_candles = max(config.min_candles, 
                           min(config.max_candles, calculated_candles))
        
        self.logger.debug(f"Time stop for {timeframe}: base={base_candles}, "
                         f"strategy={strategy_multiplier:.2f}, "
                         f"market={market_multiplier:.2f}, "
                         f"safety={safety_multiplier:.2f}, "
                         f"confidence={confidence_multiplier:.2f}, "
                         f"final={final_candles}")
        
        return final_candles
    
    def _calculate_safety_multiplier(self, safety_score: int) -> float:
        """Calculate multiplier based on safety score."""
        # Higher safety scores get longer time stops
        multipliers = {
            10: 1.4,  # Exceptional signals get longest stops
            9: 1.3,
            8: 1.2,
            7: 1.0,   # Base multiplier
            6: 0.9,
            5: 0.8,
            4: 0.7,
            3: 0.6,
            2: 0.5,
            1: 0.4    # Poor signals get shortest stops
        }
        return multipliers.get(safety_score, 1.0)
    
    def _calculate_confidence_multiplier(self, confidence: float) -> float:
        """Calculate multiplier based on confidence level."""
        # Higher confidence gets longer stops
        if confidence >= 0.9:
            return 1.3
        elif confidence >= 0.8:
            return 1.2
        elif confidence >= 0.7:
            return 1.1
        elif confidence >= 0.6:
            return 1.0
        elif confidence >= 0.5:
            return 0.9
        else:
            return 0.8
    
    def get_atr_lookback_period(self, timeframe: str) -> int:
        """Get ATR lookback period for timeframe."""
        config = self.timeframe_configs.get(timeframe, self.timeframe_configs['5m'])
        base_atr_period = 14  # Standard ATR period
        
        multiplier = getattr(config, 'atr_lookback_multiplier', 1.0)
        return max(10, int(base_atr_period * multiplier))
    
    def get_time_equivalent_hours(self, timeframe: str, candles: int) -> float:
        """Convert candles to hours for given timeframe."""
        timeframe_minutes = {
            '1m': 1,
            '5m': 5,
            '15m': 15,
            '1h': 60,
            '4h': 240,
            '1d': 1440
        }
        
        minutes = timeframe_minutes.get(timeframe, 5) * candles
        return minutes / 60.0
    
    def validate_time_stop(self, timeframe: str, candles: int) -> bool:
        """Validate if time stop is reasonable for timeframe."""
        config = self.timeframe_configs.get(timeframe)
        if not config:
            return True  # Unknown timeframe, assume valid
        
        return config.min_candles <= candles <= config.max_candles
    
    def get_recommended_time_stops(self, timeframe: str) -> Dict[str, int]:
        """Get recommended time stops for different scenarios."""
        
        scenarios = {
            'conservative': {
                'strategy_type': 'trend_following',
                'safety_score': 8,
                'confidence': 0.8
            },
            'balanced': {
                'strategy_type': 'momentum', 
                'safety_score': 7,
                'confidence': 0.7
            },
            'aggressive': {
                'strategy_type': 'scalp',
                'safety_score': 6,
                'confidence': 0.6
            }
        }
        
        recommendations = {}
        for scenario_name, params in scenarios.items():
            candles = self.calculate_time_stop_candles(
                timeframe=timeframe,
                **params
            )
            hours = self.get_time_equivalent_hours(timeframe, candles)
            recommendations[scenario_name] = {
                'candles': candles,
                'hours': hours
            }
        
        return recommendations
    
    def get_configuration_summary(self) -> str:
        """Get summary of time stop configuration."""
        summary = "Unified Time Stop Configuration:\n\n"
        
        for timeframe, config in self.timeframe_configs.items():
            summary += f"{timeframe}:\n"
            summary += f"  Base: {config.base_time_stop_candles} candles\n"
            summary += f"  Range: {config.min_candles}-{config.max_candles} candles\n"
            
            # Show time equivalents
            base_hours = self.get_time_equivalent_hours(timeframe, config.base_time_stop_candles)
            min_hours = self.get_time_equivalent_hours(timeframe, config.min_candles)  
            max_hours = self.get_time_equivalent_hours(timeframe, config.max_candles)
            
            summary += f"  Time: {base_hours:.1f}h ({min_hours:.1f}h-{max_hours:.1f}h)\n\n"
        
        return summary

# Global instance
_global_time_stop_manager: Optional[UnifiedTimeStopManager] = None

def get_time_stop_manager() -> UnifiedTimeStopManager:
    """Get global time stop manager."""
    global _global_time_stop_manager
    if _global_time_stop_manager is None:
        _global_time_stop_manager = UnifiedTimeStopManager()
    return _global_time_stop_manager