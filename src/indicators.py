"""
Technical indicators module.
Implements various technical analysis indicators using both custom code and TA-Lib.
"""

import warnings
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
import talib
from scipy import signal

warnings.filterwarnings("ignore", category=RuntimeWarning)


class TechnicalIndicators:
    """
    Collection of technical analysis indicators.
    
    All methods return pandas Series with the same index as input data.
    NaN values are returned for periods where calculation is not possible.
    """
    
    @staticmethod
    def sma(data: pd.Series, period: int) -> pd.Series:
        """
        Simple Moving Average.
        
        Args:
            data: Price series
            period: Number of periods
            
        Returns:
            SMA values
        """
        return data.rolling(window=period, min_periods=period).mean()
    
    @staticmethod
    def ema(data: pd.Series, period: int, alpha: Optional[float] = None) -> pd.Series:
        """
        Exponential Moving Average.
        
        Args:
            data: Price series
            period: Number of periods
            alpha: Smoothing factor (optional, calculated from period if not provided)
            
        Returns:
            EMA values
        """
        if alpha is None:
            alpha = 2.0 / (period + 1.0)
        
        return data.ewm(alpha=alpha, adjust=False).mean()
    
    @staticmethod
    def rsi(data: pd.Series, period: int = 14) -> pd.Series:
        """
        Relative Strength Index.
        
        Args:
            data: Price series
            period: Number of periods (default 14)
            
        Returns:
            RSI values (0-100)
        """
        try:
            # Use TA-Lib if available for better performance
            return pd.Series(
                talib.RSI(data.values, timeperiod=period),
                index=data.index,
                name=f'RSI_{period}'
            )
        except:
            # Fallback implementation
            delta = data.diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            
            avg_gain = gain.rolling(window=period).mean()
            avg_loss = loss.rolling(window=period).mean()
            
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            rsi.name = f'RSI_{period}'
            
            return rsi
    
    @staticmethod
    def macd(
        data: pd.Series,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Moving Average Convergence Divergence.
        
        Args:
            data: Price series
            fast_period: Fast EMA period
            slow_period: Slow EMA period  
            signal_period: Signal line EMA period
            
        Returns:
            Tuple of (MACD line, Signal line, Histogram)
        """
        try:
            # Use TA-Lib if available
            macd_line, signal_line, histogram = talib.MACD(
                data.values,
                fastperiod=fast_period,
                slowperiod=slow_period,
                signalperiod=signal_period
            )
            
            return (
                pd.Series(macd_line, index=data.index, name='MACD'),
                pd.Series(signal_line, index=data.index, name='MACD_Signal'),
                pd.Series(histogram, index=data.index, name='MACD_Histogram')
            )
        except:
            # Fallback implementation
            ema_fast = TechnicalIndicators.ema(data, fast_period)
            ema_slow = TechnicalIndicators.ema(data, slow_period)
            
            macd_line = ema_fast - ema_slow
            signal_line = TechnicalIndicators.ema(macd_line, signal_period)
            histogram = macd_line - signal_line
            
            macd_line.name = 'MACD'
            signal_line.name = 'MACD_Signal'
            histogram.name = 'MACD_Histogram'
            
            return macd_line, signal_line, histogram
    
    @staticmethod
    def bollinger_bands(
        data: pd.Series,
        period: int = 20,
        std_dev: float = 2.0
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Bollinger Bands.
        
        Args:
            data: Price series
            period: Moving average period
            std_dev: Standard deviation multiplier
            
        Returns:
            Tuple of (Upper band, Middle band/SMA, Lower band)
        """
        middle = TechnicalIndicators.sma(data, period)
        std = data.rolling(window=period).std()
        
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        
        upper.name = f'BB_Upper_{period}_{std_dev}'
        middle.name = f'BB_Middle_{period}'
        lower.name = f'BB_Lower_{period}_{std_dev}'
        
        return upper, middle, lower
    
    @staticmethod
    def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """
        Average True Range.
        
        Args:
            high: High price series
            low: Low price series
            close: Close price series
            period: Number of periods
            
        Returns:
            ATR values
        """
        try:
            # Use TA-Lib if available
            return pd.Series(
                talib.ATR(high.values, low.values, close.values, timeperiod=period),
                index=close.index,
                name=f'ATR_{period}'
            )
        except:
            # Fallback implementation
            prev_close = close.shift(1)
            
            tr1 = high - low
            tr2 = np.abs(high - prev_close)
            tr3 = np.abs(low - prev_close)
            
            true_range = np.maximum(tr1, np.maximum(tr2, tr3))
            atr = pd.Series(true_range, index=close.index).rolling(window=period).mean()
            atr.name = f'ATR_{period}'
            
            return atr
    
    @staticmethod
    def supertrend(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 10,
        multiplier: float = 3.0
    ) -> Tuple[pd.Series, pd.Series]:
        """
        Supertrend indicator.
        
        Args:
            high: High price series
            low: Low price series
            close: Close price series
            period: ATR period
            multiplier: ATR multiplier
            
        Returns:
            Tuple of (Supertrend values, Trend direction: 1=up, -1=down)
        """
        hl2 = (high + low) / 2
        atr = TechnicalIndicators.atr(high, low, close, period)
        
        upper_band = hl2 + (multiplier * atr)
        lower_band = hl2 - (multiplier * atr)
        
        # Initialize supertrend and trend direction
        supertrend = pd.Series(index=close.index, dtype=float)
        trend = pd.Series(index=close.index, dtype=int)
        
        # First value
        supertrend.iloc[0] = lower_band.iloc[0]
        trend.iloc[0] = 1
        
        for i in range(1, len(close)):
            # Calculate final upper and lower bands
            if upper_band.iloc[i] < upper_band.iloc[i-1] or close.iloc[i-1] > upper_band.iloc[i-1]:
                final_upper = upper_band.iloc[i]
            else:
                final_upper = upper_band.iloc[i-1]
                
            if lower_band.iloc[i] > lower_band.iloc[i-1] or close.iloc[i-1] < lower_band.iloc[i-1]:
                final_lower = lower_band.iloc[i]
            else:
                final_lower = lower_band.iloc[i-1]
            
            # Determine supertrend and trend direction
            if supertrend.iloc[i-1] == lower_band.iloc[i-1] and close.iloc[i] < final_lower:
                supertrend.iloc[i] = final_lower
                trend.iloc[i] = -1
            elif supertrend.iloc[i-1] == lower_band.iloc[i-1] and close.iloc[i] >= final_lower:
                supertrend.iloc[i] = final_upper
                trend.iloc[i] = 1
            elif supertrend.iloc[i-1] == upper_band.iloc[i-1] and close.iloc[i] > final_upper:
                supertrend.iloc[i] = final_upper
                trend.iloc[i] = 1
            else:
                supertrend.iloc[i] = final_lower
                trend.iloc[i] = -1
        
        supertrend.name = f'Supertrend_{period}_{multiplier}'
        trend.name = f'Supertrend_Trend_{period}_{multiplier}'
        
        return supertrend, trend
    
    @staticmethod
    def adx(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Average Directional Index and Directional Movement Indicators.
        
        Args:
            high: High price series
            low: Low price series
            close: Close price series
            period: Number of periods
            
        Returns:
            Tuple of (ADX, +DI, -DI)
        """
        try:
            # Use TA-Lib if available
            adx_values = talib.ADX(high.values, low.values, close.values, timeperiod=period)
            plus_di = talib.PLUS_DI(high.values, low.values, close.values, timeperiod=period)
            minus_di = talib.MINUS_DI(high.values, low.values, close.values, timeperiod=period)
            
            return (
                pd.Series(adx_values, index=close.index, name=f'ADX_{period}'),
                pd.Series(plus_di, index=close.index, name=f'Plus_DI_{period}'),
                pd.Series(minus_di, index=close.index, name=f'Minus_DI_{period}')
            )
        except:
            # Fallback implementation
            # Calculate True Range and Directional Movement
            tr = TechnicalIndicators.atr(high, low, close, 1) * 1  # True range for 1 period
            
            plus_dm = high.diff()
            minus_dm = low.diff() * -1
            
            plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
            minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
            
            # Smooth the values
            tr_smooth = tr.rolling(window=period).sum()
            plus_dm_smooth = plus_dm.rolling(window=period).sum()
            minus_dm_smooth = minus_dm.rolling(window=period).sum()
            
            # Calculate DI values
            plus_di = 100 * (plus_dm_smooth / tr_smooth)
            minus_di = 100 * (minus_dm_smooth / tr_smooth)
            
            # Calculate ADX
            dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
            adx = dx.rolling(window=period).mean()
            
            adx.name = f'ADX_{period}'
            plus_di.name = f'Plus_DI_{period}'
            minus_di.name = f'Minus_DI_{period}'
            
            return adx, plus_di, minus_di
    
    @staticmethod
    def stochastic(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        k_period: int = 14,
        d_period: int = 3,
        smooth_k: int = 3
    ) -> Tuple[pd.Series, pd.Series]:
        """
        Stochastic Oscillator.
        
        Args:
            high: High price series
            low: Low price series
            close: Close price series
            k_period: %K period
            d_period: %D period
            smooth_k: %K smoothing period
            
        Returns:
            Tuple of (%K, %D)
        """
        try:
            # Use TA-Lib if available
            slowk, slowd = talib.STOCH(
                high.values, low.values, close.values,
                fastk_period=k_period,
                slowk_period=smooth_k,
                slowk_matype=0,
                slowd_period=d_period,
                slowd_matype=0
            )
            
            return (
                pd.Series(slowk, index=close.index, name=f'Stoch_K_{k_period}'),
                pd.Series(slowd, index=close.index, name=f'Stoch_D_{d_period}')
            )
        except:
            # Fallback implementation
            lowest_low = low.rolling(window=k_period).min()
            highest_high = high.rolling(window=k_period).max()
            
            k_percent = 100 * ((close - lowest_low) / (highest_high - lowest_low))
            k_percent_smooth = k_percent.rolling(window=smooth_k).mean()
            d_percent = k_percent_smooth.rolling(window=d_period).mean()
            
            k_percent_smooth.name = f'Stoch_K_{k_period}'
            d_percent.name = f'Stoch_D_{d_period}'
            
            return k_percent_smooth, d_percent
    
    @staticmethod
    def vwap(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        volume: pd.Series
    ) -> pd.Series:
        """
        Volume Weighted Average Price.
        
        Args:
            high: High price series
            low: Low price series
            close: Close price series
            volume: Volume series
            
        Returns:
            VWAP values
        """
        typical_price = (high + low + close) / 3
        vwap = (typical_price * volume).cumsum() / volume.cumsum()
        vwap.name = 'VWAP'
        
        return vwap
    
    @staticmethod
    def roc(data: pd.Series, period: int = 10) -> pd.Series:
        """
        Rate of Change.
        
        Args:
            data: Price series
            period: Number of periods
            
        Returns:
            ROC values (percentage)
        """
        roc = ((data / data.shift(period)) - 1) * 100
        roc.name = f'ROC_{period}'
        return roc
    
    @staticmethod
    def williams_r(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14
    ) -> pd.Series:
        """
        Williams %R.
        
        Args:
            high: High price series
            low: Low price series
            close: Close price series
            period: Number of periods
            
        Returns:
            Williams %R values (-100 to 0)
        """
        highest_high = high.rolling(window=period).max()
        lowest_low = low.rolling(window=period).min()
        
        wr = -100 * (highest_high - close) / (highest_high - lowest_low)
        wr.name = f'Williams_R_{period}'
        
        return wr
    
    @staticmethod
    def commodity_channel_index(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 20
    ) -> pd.Series:
        """
        Commodity Channel Index.
        
        Args:
            high: High price series
            low: Low price series
            close: Close price series
            period: Number of periods
            
        Returns:
            CCI values
        """
        typical_price = (high + low + close) / 3
        sma_tp = typical_price.rolling(window=period).mean()
        mad = typical_price.rolling(window=period).apply(
            lambda x: np.mean(np.abs(x - np.mean(x)))
        )
        
        cci = (typical_price - sma_tp) / (0.015 * mad)
        cci.name = f'CCI_{period}'
        
        return cci
    
    @staticmethod
    def money_flow_index(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        volume: pd.Series,
        period: int = 14
    ) -> pd.Series:
        """
        Money Flow Index.
        
        Args:
            high: High price series
            low: Low price series
            close: Close price series
            volume: Volume series
            period: Number of periods
            
        Returns:
            MFI values (0-100)
        """
        typical_price = (high + low + close) / 3
        money_flow = typical_price * volume
        
        # Positive and negative money flow
        pos_flow = money_flow.where(typical_price > typical_price.shift(1), 0)
        neg_flow = money_flow.where(typical_price < typical_price.shift(1), 0)
        
        # Money flow ratio
        pos_mf_sum = pos_flow.rolling(window=period).sum()
        neg_mf_sum = neg_flow.rolling(window=period).sum()
        
        mfr = pos_mf_sum / neg_mf_sum
        mfi = 100 - (100 / (1 + mfr))
        mfi.name = f'MFI_{period}'
        
        return mfi


def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate all technical indicators for OHLCV data.
    
    Args:
        df: DataFrame with OHLCV columns
        
    Returns:
        DataFrame with all indicators added
    """
    result = df.copy()
    
    # Price series
    high = df['high']
    low = df['low']  
    close = df['close']
    volume = df['volume']
    
    # Moving averages
    for period in [20, 50, 100, 200]:
        result[f'SMA_{period}'] = TechnicalIndicators.sma(close, period)
        result[f'EMA_{period}'] = TechnicalIndicators.ema(close, period)
    
    # RSI
    result['RSI_14'] = TechnicalIndicators.rsi(close, 14)
    
    # MACD
    macd, macd_signal, macd_hist = TechnicalIndicators.macd(close)
    result['MACD'] = macd
    result['MACD_Signal'] = macd_signal
    result['MACD_Histogram'] = macd_hist
    
    # Bollinger Bands
    bb_upper, bb_middle, bb_lower = TechnicalIndicators.bollinger_bands(close)
    result['BB_Upper'] = bb_upper
    result['BB_Middle'] = bb_middle
    result['BB_Lower'] = bb_lower
    
    # ATR
    result['ATR_14'] = TechnicalIndicators.atr(high, low, close, 14)
    
    # Supertrend
    supertrend, supertrend_trend = TechnicalIndicators.supertrend(high, low, close)
    result['Supertrend'] = supertrend
    result['Supertrend_Trend'] = supertrend_trend
    
    # ADX
    adx, plus_di, minus_di = TechnicalIndicators.adx(high, low, close)
    result['ADX'] = adx
    result['Plus_DI'] = plus_di
    result['Minus_DI'] = minus_di
    
    # Stochastic
    stoch_k, stoch_d = TechnicalIndicators.stochastic(high, low, close)
    result['Stoch_K'] = stoch_k
    result['Stoch_D'] = stoch_d
    
    # VWAP (if volume available)
    if volume.sum() > 0:
        result['VWAP'] = TechnicalIndicators.vwap(high, low, close, volume)
        result['MFI_14'] = TechnicalIndicators.money_flow_index(high, low, close, volume)
    
    # Additional indicators
    result['ROC_10'] = TechnicalIndicators.roc(close, 10)
    result['Williams_R_14'] = TechnicalIndicators.williams_r(high, low, close, 14)
    result['CCI_20'] = TechnicalIndicators.commodity_channel_index(high, low, close, 20)
    
    return result


def calculate_indicator_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate trading signals from indicators.
    
    Args:
        df: DataFrame with OHLCV and indicator columns
        
    Returns:
        DataFrame with signal columns added
    """
    result = df.copy()
    
    # RSI signals
    if 'RSI_14' in df.columns:
        result['RSI_Oversold'] = (df['RSI_14'] < 30).astype(int)
        result['RSI_Overbought'] = (df['RSI_14'] > 70).astype(int)
        result['RSI_Rising'] = (df['RSI_14'] > df['RSI_14'].shift(1)).astype(int)
    
    # MACD signals
    if all(col in df.columns for col in ['MACD', 'MACD_Signal']):
        result['MACD_Bull_Cross'] = (
            (df['MACD'] > df['MACD_Signal']) & 
            (df['MACD'].shift(1) <= df['MACD_Signal'].shift(1))
        ).astype(int)
        
        result['MACD_Bear_Cross'] = (
            (df['MACD'] < df['MACD_Signal']) & 
            (df['MACD'].shift(1) >= df['MACD_Signal'].shift(1))
        ).astype(int)
        
        result['MACD_Hist_Rising'] = (df['MACD_Histogram'] > df['MACD_Histogram'].shift(1)).astype(int)
    
    # Bollinger Bands signals
    if all(col in df.columns for col in ['close', 'BB_Upper', 'BB_Lower']):
        result['BB_Squeeze'] = ((df['BB_Upper'] - df['BB_Lower']) / df['close'] < 0.04).astype(int)
        result['BB_Touch_Upper'] = (df['high'] >= df['BB_Upper']).astype(int)
        result['BB_Touch_Lower'] = (df['low'] <= df['BB_Lower']).astype(int)
    
    # Moving average signals
    if all(col in df.columns for col in ['close', 'EMA_20', 'EMA_50']):
        result['MA_Golden_Cross'] = (
            (df['EMA_20'] > df['EMA_50']) & 
            (df['EMA_20'].shift(1) <= df['EMA_50'].shift(1))
        ).astype(int)
        
        result['MA_Death_Cross'] = (
            (df['EMA_20'] < df['EMA_50']) & 
            (df['EMA_20'].shift(1) >= df['EMA_50'].shift(1))
        ).astype(int)
    
    # Regime filter
    if all(col in df.columns for col in ['close', 'EMA_200']):
        result['Regime_Bull'] = (df['close'] > df['EMA_200']).astype(int)
        result['Regime_Bear'] = (df['close'] < df['EMA_200']).astype(int)
    
    # Supertrend signals
    if 'Supertrend_Trend' in df.columns:
        result['Supertrend_Bull'] = (df['Supertrend_Trend'] == 1).astype(int)
        result['Supertrend_Bear'] = (df['Supertrend_Trend'] == -1).astype(int)
        result['Supertrend_Change'] = (df['Supertrend_Trend'] != df['Supertrend_Trend'].shift(1)).astype(int)
    
    # Volatility signals
    if 'ATR_14' in df.columns:
        atr_pct = df['ATR_14'] / df['close']
        result['Volatility_High'] = (atr_pct > atr_pct.rolling(50).quantile(0.8)).astype(int)
        result['Volatility_Low'] = (atr_pct < atr_pct.rolling(50).quantile(0.2)).astype(int)
    
    return result