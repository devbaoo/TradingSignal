"""
Intelligent Position Sizing Calculator
Replaces placeholder position sizing with real calculations.
"""

import logging
from typing import Dict, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class PositionSizeConfig:
    """Configuration for position sizing calculations."""
    base_risk_per_trade: float = 0.01     # 1% base risk
    max_exposure_per_trade: float = 0.25  # 25% max position size
    min_position_size: float = 10.0       # Minimum position size in USDT
    max_leverage_limit: int = 20          # Maximum leverage allowed
    safety_score_multipliers: Dict[int, float] = None
    confidence_multipliers: Dict[str, float] = None

class IntelligentPositionSizer:
    """Calculates intelligent position sizes with safety-based adjustments."""
    
    def __init__(self, config: Optional[PositionSizeConfig] = None):
        self.config = config or PositionSizeConfig()
        self.logger = logging.getLogger(__name__)
        
        # Set default multipliers if not provided
        if self.config.safety_score_multipliers is None:
            self.config.safety_score_multipliers = {
                10: 1.5,  # +50% for perfect signals
                9: 1.3,   # +30% for excellent signals  
                8: 1.1,   # +10% for very good signals
                7: 1.0,   # Base size for good signals
                6: 0.8,   # -20% for fair signals
                5: 0.6,   # -40% for moderate signals
                4: 0.4,   # -60% for poor signals
                3: 0.3,   # -70% for bad signals
                2: 0.2,   # -80% for very bad signals
                1: 0.1    # -90% for terrible signals
            }
        
        if self.config.confidence_multipliers is None:
            self.config.confidence_multipliers = {
                'very_high': 1.2,  # 90%+ confidence
                'high': 1.1,       # 80-89% confidence  
                'medium': 1.0,     # 70-79% confidence
                'low': 0.9,        # 60-69% confidence
                'very_low': 0.7    # <60% confidence
            }
    
    def classify_confidence_level(self, confidence_score: float) -> str:
        """Classify confidence score into levels."""
        if confidence_score >= 0.9:
            return 'very_high'
        elif confidence_score >= 0.8:
            return 'high'
        elif confidence_score >= 0.7:
            return 'medium'
        elif confidence_score >= 0.6:
            return 'low'
        else:
            return 'very_low'
    
    def calculate_intelligent_position_size(self,
                                          balance: float,
                                          entry_price: float,
                                          stop_loss: float,
                                          leverage: int,
                                          safety_score: int,
                                          confidence: float,
                                          max_leverage_override: Optional[int] = None) -> Optional[Dict]:
        """
        Calculate intelligent position size with safety-based adjustments.
        
        Args:
            balance: Account balance in USDT
            entry_price: Entry price for the trade
            stop_loss: Stop loss price 
            leverage: Leverage to use
            safety_score: Safety score (1-10)
            confidence: Confidence score (0.0-1.0)
            max_leverage_override: Optional override for max leverage
            
        Returns:
            Dictionary with position sizing details or None if invalid
        """
        
        # Input validation
        if balance <= 0 or entry_price <= 0 or leverage <= 0:
            self.logger.error("Invalid inputs for position sizing")
            return None
        
        if not (1 <= safety_score <= 10):
            self.logger.warning(f"Safety score {safety_score} out of range, clamping to 1-10")
            safety_score = max(1, min(10, safety_score))
        
        if not (0.0 <= confidence <= 1.0):
            self.logger.warning(f"Confidence {confidence} out of range, clamping to 0-1")
            confidence = max(0.0, min(1.0, confidence))
        
        try:
            # Step 1: Calculate base risk amount (1% of balance)
            base_risk_amount = balance * self.config.base_risk_per_trade
            
            # Step 2: Calculate price risk percentage
            price_risk_percent = abs(entry_price - stop_loss) / entry_price
            
            if price_risk_percent <= 0:
                self.logger.error("Invalid stop loss - no price risk")
                return None
            
            # Step 3: Calculate base position size
            # Position Size = Risk Amount / Price Risk %
            base_position_size = base_risk_amount / price_risk_percent
            
            # Step 4: Apply safety score multiplier
            safety_multiplier = self.config.safety_score_multipliers.get(safety_score, 1.0)
            
            # Step 5: Apply confidence multiplier
            confidence_level = self.classify_confidence_level(confidence)
            confidence_multiplier = self.config.confidence_multipliers.get(confidence_level, 1.0)
            
            # Step 6: Calculate adjusted position size
            adjusted_position_size = base_position_size * safety_multiplier * confidence_multiplier
            
            # Step 7: Apply maximum position size limit (25% of balance)
            max_position_size = balance * self.config.max_exposure_per_trade
            final_position_size = min(adjusted_position_size, max_position_size)
            
            # Step 8: Apply minimum position size
            if final_position_size < self.config.min_position_size:
                self.logger.warning(f"Position size {final_position_size:.2f} below minimum {self.config.min_position_size}")
                final_position_size = self.config.min_position_size
            
            # Step 9: Calculate margin required
            effective_leverage = max_leverage_override or leverage
            effective_leverage = min(effective_leverage, self.config.max_leverage_limit)
            margin_required = final_position_size / effective_leverage
            
            # Step 10: Validate margin availability (80% of balance max)
            max_margin_allowed = balance * 0.8
            if margin_required > max_margin_allowed:
                self.logger.info(f"Margin {margin_required:.2f} exceeds limit, adjusting position size")
                margin_required = max_margin_allowed
                final_position_size = margin_required * effective_leverage
            
            # Step 11: Calculate final metrics
            position_percent = (final_position_size / balance) * 100
            margin_percent = (margin_required / balance) * 100
            risk_percent = (base_risk_amount / balance) * 100
            
            # Additional safety validation
            if final_position_size < balance * 0.001:  # 0.1% minimum
                self.logger.warning("Position size too small after adjustments")
                return None
            
            result = {
                'position_size_usdt': round(final_position_size, 2),
                'margin_required': round(margin_required, 2),
                'position_percent': round(position_percent, 2),
                'margin_percent': round(margin_percent, 2),
                'risk_percent': round(risk_percent, 2),
                'leverage_used': effective_leverage,
                'max_loss_usdt': round(base_risk_amount, 2),
                'safety_multiplier': safety_multiplier,
                'confidence_multiplier': confidence_multiplier,
                'confidence_level': confidence_level,
                'base_risk_amount': base_risk_amount,
                'price_risk_percent': price_risk_percent * 100,
                'adjustments_applied': {
                    'safety_adjustment': f"{(safety_multiplier - 1.0) * 100:+.1f}%",
                    'confidence_adjustment': f"{(confidence_multiplier - 1.0) * 100:+.1f}%",
                    'max_exposure_limited': adjusted_position_size > max_position_size,
                    'margin_limited': margin_required > max_margin_allowed
                }
            }
            
            self.logger.debug(f"Position sizing complete: {final_position_size:.2f} USDT, "
                            f"margin: {margin_required:.2f} USDT, "
                            f"safety: {safety_score}, confidence: {confidence:.2f}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error calculating position size: {e}")
            return None
    
    def get_sizing_summary(self, sizing_result: Dict) -> str:
        """Generate human-readable summary of position sizing."""
        if not sizing_result:
            return "❌ Position sizing failed"
        
        summary = f"💰 Position Sizing Summary:\n"
        summary += f"Position Size: ${sizing_result['position_size_usdt']:,.2f} ({sizing_result['position_percent']:.1f}% of account)\n"
        summary += f"Margin Required: ${sizing_result['margin_required']:,.2f} ({sizing_result['margin_percent']:.1f}% of account)\n"
        summary += f"Max Risk: ${sizing_result['max_loss_usdt']:,.2f} ({sizing_result['risk_percent']:.1f}% of account)\n"
        summary += f"Leverage: {sizing_result['leverage_used']}x\n"
        
        adjustments = sizing_result.get('adjustments_applied', {})
        if any(adj for adj in [adjustments.get('safety_adjustment'), 
                              adjustments.get('confidence_adjustment')] if adj != "+0.0%"):
            summary += f"\n🔧 Adjustments Applied:\n"
            if adjustments.get('safety_adjustment', '+0.0%') != '+0.0%':
                summary += f"• Safety: {adjustments['safety_adjustment']}\n"
            if adjustments.get('confidence_adjustment', '+0.0%') != '+0.0%':
                summary += f"• Confidence: {adjustments['confidence_adjustment']}\n"
        
        if adjustments.get('max_exposure_limited'):
            summary += f"⚠️ Position size limited by max exposure rule\n"
        if adjustments.get('margin_limited'):
            summary += f"⚠️ Margin limited by account balance\n"
        
        return summary

# Global instance
_global_position_sizer: Optional[IntelligentPositionSizer] = None

def get_position_sizer() -> IntelligentPositionSizer:
    """Get global position sizer instance."""
    global _global_position_sizer
    if _global_position_sizer is None:
        _global_position_sizer = IntelligentPositionSizer()
    return _global_position_sizer