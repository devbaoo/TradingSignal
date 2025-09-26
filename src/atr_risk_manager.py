"""
Advanced Risk Management with ATR-based stops and professional features
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime


@dataclass
class AdvancedRiskLevel:
    """Advanced risk management parameters"""
    atr_stop_multiplier: float  # ATR multiplier for stop loss
    time_stop_candles: int     # Time-based stop after N candles
    breakeven_ratio: float     # Move to BE when profit >= this ratio
    partial_tp_ratio: float    # Take partial profits at this ratio
    partial_tp_percent: float  # % to close at partial TP
    chandelier_atr_mult: float # ATR multiplier for trailing stop


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
    
    def calculate_atr_stops(self, 
                           df: pd.DataFrame,
                           entry_price: float,
                           direction: str,
                           risk_level: str = 'MODERATE',
                           market_analysis: Dict = None) -> Dict:
        """Calculate ATR-based stop loss and take profit levels"""
        
        if len(df) < 14:
            return self._fallback_levels(entry_price, direction)
        
        risk_params = self.risk_levels[risk_level]
        
        # Calculate ATR (14 period)
        high = df['high']
        low = df['low'] 
        close = df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = true_range.rolling(14).mean().iloc[-1]
        
        if pd.isna(atr) or atr == 0:
            return self._fallback_levels(entry_price, direction)
        
        # DYNAMIC R/R CALCULATION based on market analysis
        dynamic_tp_multiplier = self._calculate_dynamic_tp_multiplier(
            risk_params.partial_tp_ratio, market_analysis, df
        )
        
        # Calculate stops based on direction
        if direction == "LONG":
            # ATR-based stop loss
            stop_loss = entry_price - (atr * risk_params.atr_stop_multiplier)
            
            # Dynamic take profit levels based on analysis
            tp1 = entry_price + (atr * dynamic_tp_multiplier)  # Dynamic TP1
            tp2 = entry_price + (atr * dynamic_tp_multiplier * 1.6)  # Dynamic TP2
            
            # Chandelier exit (trailing stop)
            chandelier_stop = high.rolling(risk_params.time_stop_candles).max().iloc[-1] - \
                             (atr * risk_params.chandelier_atr_mult)
            
        else:  # SHORT
            # ATR-based stop loss
            stop_loss = entry_price + (atr * risk_params.atr_stop_multiplier)
            
            # Dynamic take profit levels based on analysis
            tp1 = entry_price - (atr * dynamic_tp_multiplier)  # Dynamic TP1
            tp2 = entry_price - (atr * dynamic_tp_multiplier * 1.6)  # Dynamic TP2
            
            # Chandelier exit (trailing stop)
            chandelier_stop = low.rolling(risk_params.time_stop_candles).min().iloc[-1] + \
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
            'time_stop_candles': risk_params.time_stop_candles,
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
            'chandelier_stop': stop_loss,
            'atr_value': entry_price * 0.02,  # Fallback ATR
            'risk_amount': risk,
            'reward_1': reward1,
            'reward_2': reward2,
            'rr_ratio_1': reward1 / risk if risk > 0 else 5.0,  # Targets 1:5.0 for high ROI when possible
            'rr_ratio_2': reward2 / risk if risk > 0 else 8.0,  # Target 1:8.0 for 80%+ ROI
            'breakeven_trigger': entry_price + (risk * 0.6) if direction == "LONG" else entry_price - (risk * 0.6),
            'partial_tp_size': 0.5,
            'time_stop_candles': 15,
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