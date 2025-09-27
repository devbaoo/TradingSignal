"""
Advanced Risk Management with ATR-based stops and professional features
Multi-timeframe ATR reference for improved liquidation safety
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class AdvancedRiskLevel:
    """Advanced risk management parameters"""
    atr_stop_multiplier: float  # ATR multiplier for stop loss
    time_stop_candles: int     # Time-based stop after N candles
    breakeven_ratio: float     # Move to BE when profit >= this ratio
    partial_tp_ratio: float    # Take partial profits at this ratio
    partial_tp_percent: float  # % to close at partial TP
    chandelier_atr_mult: float # ATR multiplier for trailing stop

@dataclass 
class TimeframeATRConfig:
    """Configuration for multi-timeframe ATR calculation"""
    base_timeframe: str        # Base timeframe for signals (e.g., '5m')
    reference_timeframe: str   # Higher timeframe for ATR reference (e.g., '1h')
    scaling_factor: float      # Additional scaling for base TF ATR
    min_candles_required: int  # Minimum candles needed for calculation


class ATRRiskManager:
    """Professional risk management using ATR and advanced techniques"""
    
    def __init__(self):
        # Risk levels with HIGHER R/R ratios - 50% ROI target when conditions allow
        self.risk_levels = {
            'CONSERVATIVE': AdvancedRiskLevel(
                atr_stop_multiplier=1.0,    # Tighter stop for better R/R
                time_stop_candles=20,
                breakeven_ratio=0.6,        # Earlier breakeven
                partial_tp_ratio=2.5,       # Higher TP1 targets 50%+ ROI when possible
                partial_tp_percent=0.5,
                chandelier_atr_mult=2.0
            ),
            'MODERATE': AdvancedRiskLevel(
                atr_stop_multiplier=1.2,    # Balanced stop
                time_stop_candles=15,
                breakeven_ratio=0.8,
                partial_tp_ratio=3.0,       # Higher TP1 targets 50%+ ROI when possible
                partial_tp_percent=0.5,
                chandelier_atr_mult=2.2
            ),
            'AGGRESSIVE': AdvancedRiskLevel(
                atr_stop_multiplier=1.5,    # Wider stop but much higher TP
                time_stop_candles=12,
                breakeven_ratio=1.0,
                partial_tp_ratio=3.75,      # Much higher TP1 targets 50%+ ROI when possible
                partial_tp_percent=0.5,
                chandelier_atr_mult=2.5
            )
        }
        
        # Multi-timeframe ATR configurations
        self.timeframe_configs = {
            '1m': TimeframeATRConfig('1m', '5m', 1.5, 50),
            '5m': TimeframeATRConfig('5m', '15m', 1.3, 40), 
            '15m': TimeframeATRConfig('15m', '1h', 1.2, 30),
            '1h': TimeframeATRConfig('1h', '4h', 1.1, 25),
            '4h': TimeframeATRConfig('4h', '1d', 1.0, 20),
            '1d': TimeframeATRConfig('1d', '1d', 1.0, 14)  # Daily uses itself
        }
        
        self.logger = logging.getLogger(__name__)
    
    def get_timeframe_multiplier(self, timeframe: str) -> float:
        """Get ATR scaling factor for timeframe."""
        timeframe_multipliers = {
            '1m': 2.0,   # Higher multiplier for short TFs
            '5m': 1.5,
            '15m': 1.2,
            '1h': 1.0,
            '4h': 0.9,
            '1d': 0.8
        }
        return timeframe_multipliers.get(timeframe, 1.0)
    
    def calculate_multi_timeframe_atr(self, 
                                    base_df: pd.DataFrame,
                                    reference_df: Optional[pd.DataFrame],
                                    timeframe: str) -> float:
        """Calculate ATR using multi-timeframe approach for better safety."""
        try:
            # Get configuration for this timeframe
            config = self.timeframe_configs.get(timeframe, 
                                              TimeframeATRConfig(timeframe, timeframe, 1.0, 14))
            
            # Calculate base timeframe ATR
            base_atr = self._calculate_atr(base_df)
            if pd.isna(base_atr) or base_atr == 0:
                self.logger.warning(f"Invalid base ATR for {timeframe}")
                return 0
            
            # If no reference data, use scaled base ATR
            if reference_df is None or len(reference_df) < 14:
                scaling_factor = self.get_timeframe_multiplier(timeframe)
                return base_atr * scaling_factor
            
            # Calculate reference timeframe ATR
            reference_atr = self._calculate_atr(reference_df)
            
            if pd.isna(reference_atr) or reference_atr == 0:
                # Fallback to scaled base ATR
                scaling_factor = self.get_timeframe_multiplier(timeframe)
                return base_atr * scaling_factor
            
            # Weight combination: prefer reference TF for liquidation safety
            # For shorter timeframes, reference TF gets higher weight
            if timeframe in ['1m', '5m']:
                reference_weight = 0.7  # Higher weight for reference
                base_weight = 0.3
            elif timeframe in ['15m', '1h']:
                reference_weight = 0.6
                base_weight = 0.4
            else:
                reference_weight = 0.5  # Equal weight for longer TFs
                base_weight = 0.5
            
            # Combined ATR with timeframe scaling
            combined_atr = (reference_atr * reference_weight + base_atr * base_weight)
            final_atr = combined_atr * config.scaling_factor
            
            self.logger.debug(f"Multi-TF ATR for {timeframe}: base={base_atr:.6f}, "
                            f"ref={reference_atr:.6f}, final={final_atr:.6f}")
            
            return final_atr
            
        except Exception as e:
            self.logger.error(f"Error calculating multi-TF ATR: {e}")
            # Emergency fallback
            return self._calculate_atr(base_df) * self.get_timeframe_multiplier(timeframe)
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate standard ATR for a dataframe."""
        if len(df) < period:
            return 0
            
        try:
            high = df['high']
            low = df['low']
            close = df['close']
            
            tr1 = high - low
            tr2 = abs(high - close.shift(1))
            tr3 = abs(low - close.shift(1))
            
            true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = true_range.rolling(period).mean().iloc[-1]
            
            return atr if not pd.isna(atr) else 0
            
        except Exception as e:
            self.logger.error(f"Error calculating ATR: {e}")
            return 0
    
    def calculate_atr_stops(self, 
                           df: pd.DataFrame,
                           entry_price: float,
                           direction: str,
                           risk_level: str = 'MODERATE',
                           market_analysis: Dict = None,
                           timeframe: str = '5m',
                           reference_df: Optional[pd.DataFrame] = None) -> Dict:
        """Calculate ATR-based stop loss and take profit levels using multi-timeframe ATR"""
        
        if len(df) < 14:
            return self._fallback_levels(entry_price, direction)
        
        risk_params = self.risk_levels[risk_level]
        
        # Use multi-timeframe ATR calculation for better safety
        atr = self.calculate_multi_timeframe_atr(df, reference_df, timeframe)
        
        if atr == 0:
            return self._fallback_levels(entry_price, direction)
        
        # DYNAMIC R/R CALCULATION based on market analysis
        dynamic_tp_multiplier = self._calculate_dynamic_tp_multiplier(
            risk_params.partial_tp_ratio, market_analysis, df
        )
        
        # Calculate Unified Time Stop using manager
        from src.unified_time_stop_manager import get_time_stop_manager
        time_stop_manager = get_time_stop_manager()
        
        # Determine strategy type from market analysis
        strategy_type = 'momentum'  # Default
        if market_analysis:
            if market_analysis.get('trend_strength', 0) > 0.7:
                strategy_type = 'trend_following'
            elif market_analysis.get('volatility', 'NORMAL') == 'HIGH':
                strategy_type = 'breakout'
        
        # Determine market condition
        market_condition = 'trending'  # Default
        if market_analysis:
            if market_analysis.get('volatility', 'NORMAL') == 'HIGH':
                market_condition = 'high_volatility'
            elif market_analysis.get('trend_score', 0.5) < 0.3:
                market_condition = 'sideways'
        
        # Calculate adaptive time stop
        unified_time_stop = time_stop_manager.calculate_time_stop_candles(
            timeframe=timeframe,
            strategy_type=strategy_type,
            market_condition=market_condition,
            safety_score=int(market_analysis.get('safety_score', 7)) if market_analysis else 7,
            confidence=market_analysis.get('confidence', 0.75) if market_analysis else 0.75
        )
        
        # Calculate stops based on direction
        if direction == "LONG":
            # ATR-based stop loss (using enhanced ATR)
            stop_loss = entry_price - (atr * risk_params.atr_stop_multiplier)
            
            # Dynamic take profit levels based on analysis
            tp1 = entry_price + (atr * dynamic_tp_multiplier)  # Dynamic TP1
            tp2 = entry_price + (atr * dynamic_tp_multiplier * 1.6)  # Dynamic TP2
            
            # LeBeau Chandelier Exit formula using multi-TF ATR and unified time stop
            high = df['high']
            chandelier_stop = high.rolling(unified_time_stop).max().iloc[-1] - \
                             (atr * risk_params.chandelier_atr_mult)
            
        else:  # SHORT
            # ATR-based stop loss (using enhanced ATR)
            stop_loss = entry_price + (atr * risk_params.atr_stop_multiplier)
            
            # Dynamic take profit levels based on analysis
            tp1 = entry_price - (atr * dynamic_tp_multiplier)  # Dynamic TP1
            tp2 = entry_price - (atr * dynamic_tp_multiplier * 1.6)  # Dynamic TP2
            
            # LeBeau Chandelier Exit formula using multi-TF ATR and unified time stop
            low = df['low']
            chandelier_stop = low.rolling(unified_time_stop).min().iloc[-1] + \
                             (atr * risk_params.chandelier_atr_mult)
        
        # Calculate risk/reward ratios
        risk = abs(entry_price - stop_loss)
        reward1 = abs(tp1 - entry_price)
        reward2 = abs(tp2 - entry_price)
        
        return {
            'stop_loss': stop_loss,
            'take_profit_1': tp1,
            'take_profit_2': tp2,
            'chandelier_stop': chandelier_stop,
            'atr_value': atr,
            'risk_amount': risk,
            'reward_1': reward1,
            'reward_2': reward2,
            'rr_ratio_1': reward1 / risk if risk > 0 else 0,
            'rr_ratio_2': reward2 / risk if risk > 0 else 0,
            'breakeven_trigger': entry_price + (risk * risk_params.breakeven_ratio) if direction == "LONG" 
                               else entry_price - (risk * risk_params.breakeven_ratio),
            'partial_tp_size': risk_params.partial_tp_percent,
            'time_stop_candles': unified_time_stop,
            'risk_level': risk_level
        }
    
    def _fallback_levels(self, entry_price: float, direction: str) -> Dict:
        """Fallback levels when ATR calculation fails - 50%+ ROI targets when conditions allow"""
        if direction == "LONG":
            stop_loss = entry_price * 0.98   # 2.0% stop (tight)
            tp1 = entry_price * 1.10         # 10% TP1 (1:5.0 R/R) targets 50%+ ROI with 10x leverage
            tp2 = entry_price * 1.16         # 16% TP2 (1:8.0 R/R) = 80%+ ROI with 10x leverage
        else:
            stop_loss = entry_price * 1.02   # 2.0% stop (tight)
            tp1 = entry_price * 0.90         # 10% TP1 (1:5.0 R/R) targets 50%+ ROI with 10x leverage
            tp2 = entry_price * 0.84         # 16% TP2 (1:8.0 R/R) = 80%+ ROI with 10x leverage
        
        risk = abs(entry_price - stop_loss)
        reward1 = abs(tp1 - entry_price)
        reward2 = abs(tp2 - entry_price)
        
        return {
            'stop_loss': stop_loss,
            'take_profit_1': tp1,
            'take_profit_2': tp2,
            'chandelier_stop': stop_loss,  # Fallback to stop_loss when no data
            'atr_value': entry_price * 0.02,  # Fallback ATR
            'risk_amount': risk,
            'reward_1': reward1,
            'reward_2': reward2,
            'rr_ratio_1': reward1 / risk if risk > 0 else 5.0,  # Targets 1:5.0 for high ROI when possible
            'rr_ratio_2': reward2 / risk if risk > 0 else 8.0,  # Target 1:8.0 for 80%+ ROI
            'breakeven_trigger': entry_price + (risk * 0.6) if direction == "LONG" else entry_price - (risk * 0.6),
            'partial_tp_size': 0.5,
            'time_stop_candles': 20,  # Will be overridden by unified time stop manager
            'risk_level': 'FALLBACK'
        }
    
    def generate_trade_management_plan(self, 
                                     risk_data: Dict,
                                     entry_price: float,
                                     direction: str) -> str:
        """Generate detailed trade management instructions"""
        
        plan = f"""
🎯 ADVANCED TRADE MANAGEMENT PLAN
{'='*45}

📊 ENTRY & STOPS:
   Entry Price: ${entry_price:,.4f}
   ATR Stop Loss: ${risk_data['stop_loss']:,.4f}
   ATR Value: ${risk_data['atr_value']:.4f}
   Risk Level: {risk_data['risk_level']}

🎯 TAKE PROFIT STRATEGY:
   TP1 (50% close): ${risk_data['take_profit_1']:,.4f} | R/R: {risk_data['rr_ratio_1']:.2f}
   TP2 (Final): ${risk_data['take_profit_2']:,.4f} | R/R: {risk_data['rr_ratio_2']:.2f}

🛡️ RISK MANAGEMENT RULES:
   1. BREAK-EVEN MOVE: When price hits ${risk_data['breakeven_trigger']:,.4f}
      → Move stop loss to entry price (${entry_price:,.4f})
   
   2. PARTIAL TAKE PROFIT: At TP1 level
      → Close {risk_data['partial_tp_size']*100:.0f}% of position
      → Trail remaining 50% with Chandelier Exit
   
   3. CHANDELIER TRAILING: ${risk_data['chandelier_stop']:,.4f}
      → Trail stop using {risk_data['time_stop_candles']} period high/low + ATR
   
   4. TIME STOP: Exit if no progress after {risk_data['time_stop_candles']} candles

⚠️ EXECUTION NOTES:
   • Use limit orders near entry for better fills
   • Set OCO orders for TP1 and stop loss
   • Monitor Chandelier exit for trailing stop
   • Exit immediately if time stop triggered
   
💡 PROFESSIONAL TIPS:
   • Never risk more than planned amount
   • Stick to the plan - no emotional decisions
   • Journal the trade outcome for improvement
   • Consider market context and news events
"""
        return plan
    
    def calculate_position_risk(self,
                               entry_price: float,
                               stop_loss: float,
                               position_size_usd: float,
                               leverage: int) -> Dict:
        """Calculate detailed risk metrics for position"""
        
        price_risk_pct = abs(entry_price - stop_loss) / entry_price
        margin_used = position_size_usd / leverage
        max_loss_usd = margin_used  # Max loss = full margin (100% loss)
        max_loss_on_notional = position_size_usd * price_risk_pct
        
        # Actual max loss is the smaller of the two
        actual_max_loss = min(max_loss_usd, max_loss_on_notional)
        
        return {
            'price_risk_percent': price_risk_pct * 100,
            'margin_used': margin_used,
            'position_notional': position_size_usd,
            'max_loss_margin': max_loss_usd,
            'max_loss_price_move': max_loss_on_notional,
            'actual_max_loss': actual_max_loss,
            'leverage': leverage,
            'effective_risk_ratio': actual_max_loss / margin_used
        }
    
    def _calculate_dynamic_tp_multiplier(self, base_tp_ratio: float, 
                                       market_analysis: Dict, df: pd.DataFrame) -> float:
        """
        Calculate dynamic TP multiplier based on market conditions.
        Minimum R/R = 1:2, can go higher based on analysis.
        """
        # Start with base ratio (targets minimum 1:2 R/R when conditions allow)
        dynamic_multiplier = base_tp_ratio
        
        if market_analysis is None:
            return dynamic_multiplier
        
        # TREND STRENGTH ANALYSIS
        trend_strength = market_analysis.get('trend_strength', 0)
        if trend_strength > 0.8:  # Very strong trend
            dynamic_multiplier *= 1.4  # Increase TP by 40%
        elif trend_strength > 0.6:  # Strong trend
            dynamic_multiplier *= 1.2  # Increase TP by 20%
        elif trend_strength > 0.4:  # Medium trend
            dynamic_multiplier *= 1.1  # Increase TP by 10%
        # Weak trend: keep base multiplier (minimum 1:2 R/R)
        
        # VOLATILITY ANALYSIS
        current_atr = df['atr'].iloc[-1] if 'atr' in df.columns else 0
        avg_atr = df['atr'].rolling(50).mean().iloc[-1] if 'atr' in df.columns else 0
        
        if current_atr > 0 and avg_atr > 0:
            volatility_ratio = current_atr / avg_atr
            if volatility_ratio < 0.7:  # Low volatility = more predictable
                dynamic_multiplier *= 1.15  # Increase TP by 15%
            elif volatility_ratio > 1.3:  # High volatility = more risk
                dynamic_multiplier *= 0.95  # Reduce TP slightly but maintain min 1:2
        
        # VOLUME CONFIRMATION
        volume_profile = market_analysis.get('volume_profile', 'MEDIUM')
        if volume_profile == 'HIGH':  # Strong volume = higher confidence
            dynamic_multiplier *= 1.1  # Increase TP by 10%
        
        # RSI MOMENTUM ANALYSIS
        rsi = market_analysis.get('rsi', 50)
        if 45 <= rsi <= 65:  # Healthy momentum range
            dynamic_multiplier *= 1.05  # Slight increase
        
        # SUPPORT/RESISTANCE PROXIMITY
        sr_proximity = market_analysis.get('sr_proximity', 0.5)
        if sr_proximity > 0.8:  # Very close to S/R = higher TP potential
            dynamic_multiplier *= 1.2
        elif sr_proximity > 0.6:  # Close to S/R
            dynamic_multiplier *= 1.1
        
        # TARGET MINIMUM R/R RATIO OF 1:2 (Natural market conditions)
        # If base_tp_ratio is 2.4 and stop is 1.2x, then R/R = 2.4/1.2 = 2.0
        min_multiplier = base_tp_ratio  # This targets at least 1:2 R/R when possible
        dynamic_multiplier = max(dynamic_multiplier, min_multiplier)
        
        # CAP MAXIMUM R/R TO AVOID UNREALISTIC TARGETS
        max_multiplier = base_tp_ratio * 2.0  # Max 2x increase from base
        dynamic_multiplier = min(dynamic_multiplier, max_multiplier)
        
        return dynamic_multiplier
    
    def calculate_leveraged_returns(self,
                                   entry_price: float,
                                   take_profit: float,
                                   stop_loss: float,
                                   leverage: int,
                                   direction: str) -> Dict:
        """Calculate actual ROI percentages with leverage"""
        
        # Price movement percentages
        if direction == "LONG":
            tp_price_change = (take_profit - entry_price) / entry_price
            sl_price_change = (entry_price - stop_loss) / entry_price
        else:  # SHORT
            tp_price_change = (entry_price - take_profit) / entry_price
            sl_price_change = (stop_loss - entry_price) / entry_price
        
        # Leveraged ROI (return on margin)
        tp_roi_percent = tp_price_change * leverage * 100
        sl_risk_percent = sl_price_change * leverage * 100
        
        return {
            'price_change_tp_percent': tp_price_change * 100,
            'price_change_sl_percent': sl_price_change * 100,
            'leveraged_tp_roi_percent': tp_roi_percent,
            'leveraged_sl_risk_percent': sl_risk_percent,
            'leverage': leverage,
            'direction': direction
        }


def create_atr_risk_manager() -> ATRRiskManager:
    """Factory function to create ATR risk manager"""
    return ATRRiskManager()