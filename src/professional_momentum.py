"""
Enhanced Momentum Strategy with Professional Logic
Fixes textbook approaches with regime-aware and robust signal generation
"""

import numpy as np
import pandas as pd
import talib
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class MarketRegime:
    """Market regime classification"""
    trend_regime: str  # 'BULLISH', 'BEARISH', 'SIDEWAYS'
    volatility_regime: str  # 'LOW', 'NORMAL', 'HIGH'
    momentum_regime: str  # 'STRONG', 'WEAK', 'NEUTRAL'
    is_trending: bool
    regime_strength: float  # 0-1


class ProfessionalMomentumStrategy:
    """Enhanced momentum strategy with regime awareness"""
    
    def __init__(self, 
                 rsi_period: int = 14,
                 ema_fast: int = 12,
                 ema_slow: int = 26,
                 ema_long: int = 200,
                 adx_period: int = 14,
                 bb_period: int = 20,
                 bb_std: float = 2.0,
                 keltner_period: int = 20,
                 keltner_atr_mult: float = 1.5):
        
        self.rsi_period = rsi_period
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.ema_long = ema_long
        self.adx_period = adx_period
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.keltner_period = keltner_period
        self.keltner_atr_mult = keltner_atr_mult
        
        # Regime thresholds
        self.rsi_regime_lookback = 50
        self.adx_trend_threshold = 20
        self.ema_slope_threshold = 0.0001
        self.squeeze_threshold = 0.95  # Bollinger/Keltner squeeze
        
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all required technical indicators"""
        
        data = df.copy()
        
        # Price data
        open_price = data['open'].values
        high = data['high'].values
        low = data['low'].values
        close = data['close'].values
        volume = data.get('volume', pd.Series([1] * len(data))).values
        
        # Moving averages
        data['ema_fast'] = talib.EMA(close, timeperiod=self.ema_fast)
        data['ema_slow'] = talib.EMA(close, timeperiod=self.ema_slow)
        data['ema_long'] = talib.EMA(close, timeperiod=self.ema_long)
        
        # EMA slope (rate of change)
        data['ema_long_slope'] = data['ema_long'].pct_change(5)  # 5-period slope
        
        # RSI and RSI regime
        data['rsi'] = talib.RSI(close, timeperiod=self.rsi_period)
        data['rsi_regime'] = data['rsi'].rolling(self.rsi_regime_lookback).median()
        
        # ADX for trend strength
        data['adx'] = talib.ADX(high, low, close, timeperiod=self.adx_period)
        data['di_plus'] = talib.PLUS_DI(high, low, close, timeperiod=self.adx_period)
        data['di_minus'] = talib.MINUS_DI(high, low, close, timeperiod=self.adx_period)
        
        # MACD
        data['macd'], data['macd_signal'], data['macd_hist'] = talib.MACD(close)
        
        # Bollinger Bands
        data['bb_upper'], data['bb_middle'], data['bb_lower'] = talib.BBANDS(
            close, timeperiod=self.bb_period, nbdevup=self.bb_std, nbdevdn=self.bb_std
        )
        data['bb_percent_b'] = (close - data['bb_lower']) / (data['bb_upper'] - data['bb_lower'])
        data['bb_width'] = (data['bb_upper'] - data['bb_lower']) / data['bb_middle']
        
        # Keltner Channels
        data['keltner_middle'] = talib.EMA(close, timeperiod=self.keltner_period)
        atr = talib.ATR(high, low, close, timeperiod=self.keltner_period)
        data['keltner_upper'] = data['keltner_middle'] + (atr * self.keltner_atr_mult)
        data['keltner_lower'] = data['keltner_middle'] - (atr * self.keltner_atr_mult)
        
        # Squeeze indicator
        data['squeeze'] = (data['bb_upper'] < data['keltner_upper']) & (data['bb_lower'] > data['keltner_lower'])
        data['squeeze_release'] = data['squeeze'].shift(1) & ~data['squeeze']
        
        # Volume indicators
        data['volume_sma'] = talib.SMA(volume.astype(float), timeperiod=20)
        data['volume_ratio'] = volume / data['volume_sma']
        
        # Stochastic
        data['stoch_k'], data['stoch_d'] = talib.STOCH(high, low, close)
        
        return data
    
    def classify_market_regime(self, data: pd.DataFrame, idx: int) -> MarketRegime:
        """Classify current market regime"""
        
        if idx < self.rsi_regime_lookback:
            return MarketRegime('NEUTRAL', 'NORMAL', 'NEUTRAL', False, 0.5)
        
        current = data.iloc[idx]
        
        # Trend regime analysis
        ema_long_slope = current['ema_long_slope']
        ema_fast_vs_slow = current['ema_fast'] > current['ema_slow']
        price_vs_ema_long = current['close'] > current['ema_long']
        adx_strength = current['adx']
        
        # RSI regime (bullish if median RSI > 50 over lookback period)
        rsi_regime_bullish = current['rsi_regime'] > 50
        
        # Determine trend regime
        if (ema_long_slope > self.ema_slope_threshold and 
            ema_fast_vs_slow and 
            price_vs_ema_long and
            rsi_regime_bullish and
            adx_strength > self.adx_trend_threshold):
            trend_regime = 'BULLISH'
            is_trending = True
            
        elif (ema_long_slope < -self.ema_slope_threshold and
              not ema_fast_vs_slow and
              not price_vs_ema_long and
              not rsi_regime_bullish and
              adx_strength > self.adx_trend_threshold):
            trend_regime = 'BEARISH'
            is_trending = True
            
        else:
            trend_regime = 'SIDEWAYS'
            is_trending = adx_strength > self.adx_trend_threshold
        
        # Volatility regime
        bb_width = current['bb_width']
        atr_percentile = self._calculate_atr_percentile(data, idx)
        
        if atr_percentile > 75:
            volatility_regime = 'HIGH'
        elif atr_percentile < 25:
            volatility_regime = 'LOW'
        else:
            volatility_regime = 'NORMAL'
        
        # Momentum regime
        momentum_score = self._calculate_momentum_score(data, idx)
        
        if momentum_score > 0.7:
            momentum_regime = 'STRONG'
        elif momentum_score < 0.3:
            momentum_regime = 'WEAK'
        else:
            momentum_regime = 'NEUTRAL'
        
        # Calculate overall regime strength
        regime_strength = self._calculate_regime_strength(data, idx)
        
        return MarketRegime(
            trend_regime=trend_regime,
            volatility_regime=volatility_regime,
            momentum_regime=momentum_regime,
            is_trending=is_trending,
            regime_strength=regime_strength
        )
    
    def _calculate_atr_percentile(self, data: pd.DataFrame, idx: int, lookback: int = 100) -> float:
        """Calculate ATR percentile ranking"""
        
        if idx < lookback:
            return 50  # Neutral percentile
        
        current_atr = talib.ATR(
            data['high'].iloc[idx-lookback:idx+1].values,
            data['low'].iloc[idx-lookback:idx+1].values,
            data['close'].iloc[idx-lookback:idx+1].values,
            timeperiod=14
        )[-1]
        
        historical_atr = talib.ATR(
            data['high'].iloc[idx-lookback:idx].values,
            data['low'].iloc[idx-lookback:idx].values,
            data['close'].iloc[idx-lookback:idx].values,
            timeperiod=14
        )
        
        if len(historical_atr) == 0:
            return 50
        
        percentile = (historical_atr < current_atr).sum() / len(historical_atr) * 100
        return percentile
    
    def _calculate_momentum_score(self, data: pd.DataFrame, idx: int) -> float:
        """Calculate composite momentum score (0-1)"""
        
        current = data.iloc[idx]
        
        # RSI momentum (normalized)
        rsi_score = 0.5
        if 30 <= current['rsi'] <= 70:
            rsi_score = (current['rsi'] - 30) / 40  # Normalize to 0-1
        elif current['rsi'] > 70:
            rsi_score = 0.8  # Overbought but still positive
        else:  # RSI < 30
            rsi_score = 0.2  # Oversold but still some momentum
        
        # MACD momentum
        macd_score = 0.5
        if current['macd'] > current['macd_signal']:
            macd_score = 0.8
        else:
            macd_score = 0.2
        
        # Price momentum (vs EMA)
        price_momentum = 0.5
        if current['close'] > current['ema_fast'] > current['ema_slow']:
            price_momentum = 0.9
        elif current['close'] < current['ema_fast'] < current['ema_slow']:
            price_momentum = 0.1
        
        # Stochastic momentum
        stoch_score = 0.5
        if current['stoch_k'] > current['stoch_d'] and current['stoch_k'] > 20:
            stoch_score = 0.8
        elif current['stoch_k'] < current['stoch_d'] and current['stoch_k'] < 80:
            stoch_score = 0.2
        
        # Weighted composite score
        weights = [0.3, 0.25, 0.25, 0.2]  # RSI, MACD, Price, Stoch
        scores = [rsi_score, macd_score, price_momentum, stoch_score]
        
        momentum_score = sum(w * s for w, s in zip(weights, scores))
        
        return np.clip(momentum_score, 0, 1)
    
    def _calculate_regime_strength(self, data: pd.DataFrame, idx: int) -> float:
        """Calculate overall regime strength (0-1)"""
        
        current = data.iloc[idx]
        
        # ADX strength
        adx_strength = min(1.0, current['adx'] / 50)  # Normalize to 0-1
        
        # Trend consistency (EMA alignment)
        ema_alignment = 0
        if current['ema_fast'] > current['ema_slow'] > current['ema_long']:
            ema_alignment = 1.0  # Perfect bullish alignment
        elif current['ema_fast'] < current['ema_slow'] < current['ema_long']:
            ema_alignment = 1.0  # Perfect bearish alignment
        else:
            ema_alignment = 0.3  # Mixed signals
        
        # Volume confirmation
        volume_confirmation = min(1.0, current['volume_ratio'] / 2)  # Normalize
        
        # Squeeze/breakout potential
        squeeze_factor = 0.5
        if current['squeeze']:
            squeeze_factor = 0.3  # Lower strength during squeeze
        elif current['squeeze_release']:
            squeeze_factor = 1.0  # High strength on squeeze release
        
        # Weighted combination
        weights = [0.4, 0.3, 0.2, 0.1]
        factors = [adx_strength, ema_alignment, volume_confirmation, squeeze_factor]
        
        regime_strength = sum(w * f for w, f in zip(weights, factors))
        
        return np.clip(regime_strength, 0, 1)
    
    def generate_signals(self, data: pd.DataFrame) -> List[Dict]:
        """Generate enhanced momentum signals with regime awareness"""
        
        # Calculate all indicators
        data = self.calculate_indicators(data)
        
        signals = []
        
        for i in range(self.rsi_regime_lookback, len(data)):
            current = data.iloc[i]
            regime = self.classify_market_regime(data, i)
            
            # Skip if market is in squeeze (unless breakout)
            if current['squeeze'] and not current['squeeze_release']:
                continue
            
            # Long signal conditions (enhanced)
            long_conditions = self._check_long_conditions(current, regime)
            
            # Short signal conditions (enhanced)  
            short_conditions = self._check_short_conditions(current, regime)
            
            if long_conditions['signal'] and regime.regime_strength > 0.5:
                signals.append({
                    'timestamp': data.index[i],
                    'direction': 'LONG',
                    'entry_price': current['close'],
                    'confidence': long_conditions['confidence'],
                    'regime': regime,
                    'conditions_met': long_conditions['conditions'],
                    'strength_score': regime.regime_strength
                })
            
            elif short_conditions['signal'] and regime.regime_strength > 0.5:
                signals.append({
                    'timestamp': data.index[i],
                    'direction': 'SHORT',
                    'entry_price': current['close'],
                    'confidence': short_conditions['confidence'],
                    'regime': regime,
                    'conditions_met': short_conditions['conditions'],
                    'strength_score': regime.regime_strength
                })
        
        return signals
    
    def _check_long_conditions(self, current: pd.Series, regime: MarketRegime) -> Dict:
        """Check enhanced long signal conditions"""
        
        conditions = []
        confidence = 0
        
        # 1. RSI regime bullish (not just RSI > 30)
        if current['rsi_regime'] > 50:
            conditions.append("RSI_REGIME_BULLISH")
            confidence += 0.2
        
        # 2. RSI not overbought but showing momentum
        if 40 <= current['rsi'] <= 75:
            conditions.append("RSI_MOMENTUM")
            confidence += 0.15
        
        # 3. Price above EMA 200 AND EMA slope positive
        if current['close'] > current['ema_long'] and current['ema_long_slope'] > 0:
            conditions.append("LONG_TERM_UPTREND")
            confidence += 0.2
        
        # 4. EMA alignment (fast > slow)
        if current['ema_fast'] > current['ema_slow']:
            conditions.append("SHORT_TERM_MOMENTUM")
            confidence += 0.15
        
        # 5. ADX confirms trend strength
        if current['adx'] > 20 and current['di_plus'] > current['di_minus']:
            conditions.append("TREND_STRENGTH")
            confidence += 0.15
        
        # 6. MACD bullish
        if current['macd'] > current['macd_signal']:
            conditions.append("MACD_BULLISH")
            confidence += 0.1
        
        # 7. Volume confirmation
        if current['volume_ratio'] > 1.2:
            conditions.append("VOLUME_CONFIRMATION")
            confidence += 0.1
        
        # 8. Bollinger %B position (not at extremes unless breakout)
        if 0.2 <= current['bb_percent_b'] <= 0.8 or current['squeeze_release']:
            conditions.append("BOLLINGER_POSITION")
            confidence += 0.05
        
        # 9. Stochastic confirmation
        if current['stoch_k'] > current['stoch_d'] and current['stoch_k'] < 80:
            conditions.append("STOCHASTIC_BULLISH")
            confidence += 0.05
        
        # Require minimum conditions for signal
        min_conditions = 5
        signal = len(conditions) >= min_conditions and confidence >= 0.6
        
        return {
            'signal': signal,
            'confidence': min(1.0, confidence),
            'conditions': conditions
        }
    
    def _check_short_conditions(self, current: pd.Series, regime: MarketRegime) -> Dict:
        """Check enhanced short signal conditions"""
        
        conditions = []
        confidence = 0
        
        # 1. RSI regime bearish
        if current['rsi_regime'] < 50:
            conditions.append("RSI_REGIME_BEARISH")
            confidence += 0.2
        
        # 2. RSI not oversold but showing weakness
        if 25 <= current['rsi'] <= 60:
            conditions.append("RSI_WEAKNESS")
            confidence += 0.15
        
        # 3. Price below EMA 200 AND EMA slope negative
        if current['close'] < current['ema_long'] and current['ema_long_slope'] < 0:
            conditions.append("LONG_TERM_DOWNTREND")
            confidence += 0.2
        
        # 4. EMA alignment (fast < slow)
        if current['ema_fast'] < current['ema_slow']:
            conditions.append("SHORT_TERM_WEAKNESS")
            confidence += 0.15
        
        # 5. ADX confirms trend strength
        if current['adx'] > 20 and current['di_minus'] > current['di_plus']:
            conditions.append("TREND_STRENGTH")
            confidence += 0.15
        
        # 6. MACD bearish
        if current['macd'] < current['macd_signal']:
            conditions.append("MACD_BEARISH")
            confidence += 0.1
        
        # 7. Volume confirmation
        if current['volume_ratio'] > 1.2:
            conditions.append("VOLUME_CONFIRMATION")
            confidence += 0.1
        
        # 8. Bollinger %B position
        if 0.2 <= current['bb_percent_b'] <= 0.8 or current['squeeze_release']:
            conditions.append("BOLLINGER_POSITION")
            confidence += 0.05
        
        # 9. Stochastic confirmation
        if current['stoch_k'] < current['stoch_d'] and current['stoch_k'] > 20:
            conditions.append("STOCHASTIC_BEARISH")
            confidence += 0.05
        
        # Require minimum conditions for signal
        min_conditions = 5
        signal = len(conditions) >= min_conditions and confidence >= 0.6
        
        return {
            'signal': signal,
            'confidence': min(1.0, confidence),
            'conditions': conditions
        }


def create_professional_momentum_strategy(**kwargs) -> ProfessionalMomentumStrategy:
    """Factory function to create professional momentum strategy"""
    return ProfessionalMomentumStrategy(**kwargs)