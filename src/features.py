"""
Feature engineering module.
Creates features for machine learning models including momentum, volatility,
regime filters, and target labeling methods.
"""

import warnings
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler, MinMaxScaler

from .indicators import TechnicalIndicators
from .utils import get_logger

warnings.filterwarnings("ignore", category=RuntimeWarning)
logger = get_logger(__name__)


class FeatureEngineer:
    """
    Feature engineering for trading strategies.
    
    Provides methods to create various types of features:
    - Momentum features
    - Volatility features  
    - Regime filters
    - Market structure features
    - Target labeling for ML models
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize feature engineer.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.feature_config = self.config.get("features", {})
        
    def create_momentum_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create momentum-based features.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with momentum features added
        """
        result = df.copy()
        close = df['close']
        
        # Rate of Change features
        for period in [5, 10, 20]:
            result[f'ROC_{period}'] = TechnicalIndicators.roc(close, period)
        
        # Price momentum
        for period in [5, 10, 20]:
            result[f'Price_Momentum_{period}'] = close / close.shift(period) - 1
        
        # Velocity (rate of change of momentum)
        result['Price_Velocity_5'] = result['Price_Momentum_5'].diff()
        result['Price_Velocity_10'] = result['Price_Momentum_10'].diff()
        
        # Acceleration (rate of change of velocity)
        result['Price_Acceleration_5'] = result['Price_Velocity_5'].diff()
        
        # RSI momentum
        if 'RSI_14' not in df.columns:
            result['RSI_14'] = TechnicalIndicators.rsi(close, 14)
        
        result['RSI_Momentum'] = result['RSI_14'] - result['RSI_14'].shift(1)
        result['RSI_Velocity'] = result['RSI_Momentum'].diff()
        
        # MACD features
        if not all(col in df.columns for col in ['MACD', 'MACD_Signal', 'MACD_Histogram']):
            macd, macd_signal, macd_hist = TechnicalIndicators.macd(close)
            result['MACD'] = macd
            result['MACD_Signal'] = macd_signal
            result['MACD_Histogram'] = macd_hist
        
        result['MACD_Momentum'] = result['MACD'].diff()
        result['MACD_Signal_Momentum'] = result['MACD_Signal'].diff()
        
        # Stochastic momentum
        if not all(col in df.columns for col in ['Stoch_K', 'Stoch_D']):
            stoch_k, stoch_d = TechnicalIndicators.stochastic(
                df['high'], df['low'], close
            )
            result['Stoch_K'] = stoch_k
            result['Stoch_D'] = stoch_d
        
        result['Stoch_Momentum'] = result['Stoch_K'] - result['Stoch_D']
        
        return result
    
    def create_volatility_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create volatility-based features.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with volatility features added
        """
        result = df.copy()
        close = df['close']
        high = df['high']
        low = df['low']
        
        # True Range and ATR
        if 'ATR_14' not in df.columns:
            result['ATR_14'] = TechnicalIndicators.atr(high, low, close, 14)
        
        # ATR as percentage of price
        result['ATR_Pct'] = result['ATR_14'] / close * 100
        
        # ATR percentile rank
        result['ATR_Percentile'] = result['ATR_Pct'].rolling(window=50).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1]
        )
        
        # Historical volatility (rolling standard deviation of returns)
        returns = close.pct_change()
        for period in [10, 20, 50]:
            result[f'Volatility_{period}'] = returns.rolling(window=period).std() * np.sqrt(252) * 100
        
        # Volatility regime
        vol_20 = result['Volatility_20']
        result['Vol_Regime_High'] = (vol_20 > vol_20.rolling(100).quantile(0.75)).astype(int)
        result['Vol_Regime_Low'] = (vol_20 < vol_20.rolling(100).quantile(0.25)).astype(int)
        
        # Intraday range features
        result['Daily_Range'] = (high - low) / close * 100
        result['Daily_Range_MA'] = result['Daily_Range'].rolling(window=20).mean()
        result['Daily_Range_Normalized'] = result['Daily_Range'] / result['Daily_Range_MA']
        
        # Gap features
        result['Gap'] = (df['open'] - close.shift(1)) / close.shift(1) * 100
        result['Gap_Up'] = (result['Gap'] > 0).astype(int)
        result['Gap_Down'] = (result['Gap'] < 0).astype(int)
        
        # Bollinger Band width
        if not all(col in df.columns for col in ['BB_Upper', 'BB_Lower']):
            bb_upper, bb_middle, bb_lower = TechnicalIndicators.bollinger_bands(close)
            result['BB_Upper'] = bb_upper
            result['BB_Middle'] = bb_middle  
            result['BB_Lower'] = bb_lower
        
        result['BB_Width'] = (result['BB_Upper'] - result['BB_Lower']) / close * 100
        result['BB_Width_Percentile'] = result['BB_Width'].rolling(window=50).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1]
        )
        
        # Volatility clustering
        vol_proxy = np.abs(returns) * 100
        result['Vol_Clustering'] = vol_proxy.rolling(window=5).mean() / vol_proxy.rolling(window=20).mean()
        
        return result
    
    def create_regime_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create market regime features.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with regime features added
        """
        result = df.copy()
        close = df['close']
        
        # Moving average regimes
        for ma_period in [50, 100, 200]:
            if f'SMA_{ma_period}' not in df.columns:
                result[f'SMA_{ma_period}'] = TechnicalIndicators.sma(close, ma_period)
            if f'EMA_{ma_period}' not in df.columns:
                result[f'EMA_{ma_period}'] = TechnicalIndicators.ema(close, ma_period)
            
            # Regime definition
            result[f'Regime_Bull_{ma_period}'] = (close > result[f'EMA_{ma_period}']).astype(int)
            result[f'Regime_Bear_{ma_period}'] = (close < result[f'EMA_{ma_period}']).astype(int)
            
            # Distance from moving average
            result[f'Distance_EMA_{ma_period}'] = (close - result[f'EMA_{ma_period}']) / result[f'EMA_{ma_period}'] * 100
        
        # Trend strength
        ema_20 = result.get('EMA_20', TechnicalIndicators.ema(close, 20))
        ema_50 = result.get('EMA_50', TechnicalIndicators.ema(close, 50))
        ema_200 = result.get('EMA_200', TechnicalIndicators.ema(close, 200))
        
        if 'EMA_20' not in result.columns:
            result['EMA_20'] = ema_20
        if 'EMA_50' not in result.columns:
            result['EMA_50'] = ema_50
        
        # MA alignment (all MAs in same direction)
        result['MA_Alignment_Bull'] = (
            (ema_20 > ema_50) & (ema_50 > ema_200)
        ).astype(int)
        
        result['MA_Alignment_Bear'] = (
            (ema_20 < ema_50) & (ema_50 < ema_200)
        ).astype(int)
        
        # Trend consistency
        result['Trend_Consistency'] = result[['MA_Alignment_Bull', 'MA_Alignment_Bear']].sum(axis=1)
        
        # ADX trend strength
        if 'ADX' not in df.columns:
            adx, plus_di, minus_di = TechnicalIndicators.adx(
                df['high'], df['low'], close
            )
            result['ADX'] = adx
            result['Plus_DI'] = plus_di
            result['Minus_DI'] = minus_di
        
        result['Strong_Trend'] = (result['ADX'] > 25).astype(int)
        result['Weak_Trend'] = (result['ADX'] < 20).astype(int)
        
        # Market phase classification
        result['Market_Phase'] = 0  # Consolidation
        result.loc[result['MA_Alignment_Bull'] & result['Strong_Trend'], 'Market_Phase'] = 1  # Bull trend
        result.loc[result['MA_Alignment_Bear'] & result['Strong_Trend'], 'Market_Phase'] = -1  # Bear trend
        
        return result
    
    def create_mean_reversion_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create mean reversion features.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with mean reversion features added
        """
        result = df.copy()
        close = df['close']
        
        # Bollinger Band position
        if not all(col in df.columns for col in ['BB_Upper', 'BB_Lower', 'BB_Middle']):
            bb_upper, bb_middle, bb_lower = TechnicalIndicators.bollinger_bands(close)
            result['BB_Upper'] = bb_upper
            result['BB_Middle'] = bb_middle
            result['BB_Lower'] = bb_lower
        
        # BB position (-1 to 1, where -1 is at lower band, 1 is at upper band)
        bb_width = result['BB_Upper'] - result['BB_Lower']
        result['BB_Position'] = (close - result['BB_Middle']) / (bb_width / 2)
        
        # Distance to bands
        result['Distance_BB_Upper'] = (result['BB_Upper'] - close) / close * 100
        result['Distance_BB_Lower'] = (close - result['BB_Lower']) / close * 100
        
        # RSI mean reversion signals
        if 'RSI_14' not in df.columns:
            result['RSI_14'] = TechnicalIndicators.rsi(close, 14)
        
        result['RSI_Oversold_Extreme'] = (result['RSI_14'] < 20).astype(int)
        result['RSI_Overbought_Extreme'] = (result['RSI_14'] > 80).astype(int)
        
        # Williams %R
        if 'Williams_R_14' not in df.columns:
            result['Williams_R_14'] = TechnicalIndicators.williams_r(
                df['high'], df['low'], close, 14
            )
        
        result['Williams_R_Oversold'] = (result['Williams_R_14'] < -80).astype(int)
        result['Williams_R_Overbought'] = (result['Williams_R_14'] > -20).astype(int)
        
        # Z-score mean reversion
        for period in [20, 50]:
            mean = close.rolling(window=period).mean()
            std = close.rolling(window=period).std()
            result[f'Z_Score_{period}'] = (close - mean) / std
            
            result[f'Z_Score_Extreme_{period}'] = (np.abs(result[f'Z_Score_{period}']) > 2).astype(int)
        
        # Detrended price oscillator
        for period in [20]:
            shifted_ma = TechnicalIndicators.sma(close, period).shift(period // 2 + 1)
            result[f'DPO_{period}'] = close - shifted_ma
            
            dpo_std = result[f'DPO_{period}'].rolling(window=period).std()
            result[f'DPO_Normalized_{period}'] = result[f'DPO_{period}'] / dpo_std
        
        return result
    
    def create_volume_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create volume-based features.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with volume features added
        """
        result = df.copy()
        volume = df['volume']
        close = df['close']
        
        if volume.sum() == 0:
            logger.warning("No volume data available, skipping volume features")
            return result
        
        # Volume moving averages
        for period in [10, 20, 50]:
            result[f'Volume_MA_{period}'] = volume.rolling(window=period).mean()
        
        # Volume ratio
        result['Volume_Ratio_10'] = volume / result['Volume_MA_10']
        result['Volume_Ratio_20'] = volume / result['Volume_MA_20']
        
        # Volume breakout
        result['Volume_Breakout'] = (volume > 2 * result['Volume_MA_20']).astype(int)
        
        # On-Balance Volume
        price_change = close.diff()
        obv_change = volume.copy()
        obv_change.loc[price_change < 0] = -volume.loc[price_change < 0]
        obv_change.loc[price_change == 0] = 0
        result['OBV'] = obv_change.cumsum()
        
        # OBV moving average
        result['OBV_MA_20'] = result['OBV'].rolling(window=20).mean()
        result['OBV_Signal'] = (result['OBV'] > result['OBV_MA_20']).astype(int)
        
        # Volume Price Trend
        vpt_change = volume * (close.pct_change())
        result['VPT'] = vpt_change.cumsum()
        
        # VWAP
        if 'VWAP' not in df.columns:
            result['VWAP'] = TechnicalIndicators.vwap(
                df['high'], df['low'], close, volume
            )
        
        # Distance from VWAP
        result['Distance_VWAP'] = (close - result['VWAP']) / result['VWAP'] * 100
        
        # Money Flow Index
        if 'MFI_14' not in df.columns:
            result['MFI_14'] = TechnicalIndicators.money_flow_index(
                df['high'], df['low'], close, volume, 14
            )
        
        return result
    
    def create_microstructure_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create market microstructure features.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with microstructure features added
        """
        result = df.copy()
        
        open_price = df['open']
        high = df['high']
        low = df['low']
        close = df['close']
        
        # Intraday patterns
        result['Open_Close_Ratio'] = (close - open_price) / open_price
        result['High_Low_Ratio'] = (high - low) / low
        
        # Wicks and body analysis
        body_size = np.abs(close - open_price)
        upper_wick = high - np.maximum(open_price, close)
        lower_wick = np.minimum(open_price, close) - low
        
        result['Body_Size'] = body_size / close * 100
        result['Upper_Wick'] = upper_wick / close * 100
        result['Lower_Wick'] = lower_wick / close * 100
        
        # Wick ratios
        result['Upper_Wick_Ratio'] = upper_wick / (upper_wick + lower_wick + 1e-8)
        result['Body_Wick_Ratio'] = body_size / (upper_wick + lower_wick + 1e-8)
        
        # Candlestick patterns (simplified)
        result['Bullish_Candle'] = (close > open_price).astype(int)
        result['Bearish_Candle'] = (close < open_price).astype(int)
        result['Doji'] = (np.abs(close - open_price) < (high - low) * 0.1).astype(int)
        
        # Long wicks
        avg_range = (high - low).rolling(window=20).mean()
        result['Long_Upper_Wick'] = (upper_wick > avg_range * 0.6).astype(int)
        result['Long_Lower_Wick'] = (lower_wick > avg_range * 0.6).astype(int)
        
        # Price action features
        result['Inside_Bar'] = (
            (high < high.shift(1)) & (low > low.shift(1))
        ).astype(int)
        
        result['Outside_Bar'] = (
            (high > high.shift(1)) & (low < low.shift(1))
        ).astype(int)
        
        return result
    
    def create_target_labels(
        self,
        df: pd.DataFrame,
        method: str = "return_based",
        horizon: int = 5,
        threshold: float = 0.02,
        **kwargs
    ) -> pd.DataFrame:
        """
        Create target labels for machine learning.
        
        Args:
            df: DataFrame with OHLCV data
            method: Labeling method ("return_based", "triple_barrier", "trend_continuation")
            horizon: Forward looking periods
            threshold: Return threshold for classification
            **kwargs: Additional parameters for specific methods
            
        Returns:
            DataFrame with target labels added
        """
        result = df.copy()
        close = df['close']
        
        if method == "return_based":
            # Simple return-based labeling
            future_return = close.shift(-horizon) / close - 1
            
            result['Target_Return'] = future_return
            result['Target_Direction'] = np.where(future_return > threshold, 1,
                                                np.where(future_return < -threshold, -1, 0))
            result['Target_Binary'] = (future_return > threshold).astype(int)
            
        elif method == "triple_barrier":
            # Triple barrier method
            result = self._create_triple_barrier_labels(
                result, horizon, threshold, kwargs.get('stop_loss', threshold)
            )
            
        elif method == "trend_continuation":
            # Trend continuation labeling
            result = self._create_trend_continuation_labels(
                result, horizon, threshold
            )
        
        return result
    
    def _create_triple_barrier_labels(
        self,
        df: pd.DataFrame,
        horizon: int,
        profit_threshold: float,
        stop_loss: float
    ) -> pd.DataFrame:
        """
        Create triple barrier labels (profit taking, stop loss, time exit).
        
        Args:
            df: DataFrame with OHLCV data
            horizon: Maximum holding period
            profit_threshold: Profit taking threshold
            stop_loss: Stop loss threshold
            
        Returns:
            DataFrame with triple barrier labels
        """
        result = df.copy()
        close = df['close']
        
        labels = []
        returns = []
        holding_periods = []
        
        for i in range(len(df) - horizon):
            entry_price = close.iloc[i]
            
            # Look forward up to horizon periods
            future_prices = close.iloc[i+1:i+1+horizon]
            future_returns = future_prices / entry_price - 1
            
            # Check barriers
            hit_profit = future_returns >= profit_threshold
            hit_stop = future_returns <= -stop_loss
            
            if hit_profit.any():
                # Hit profit target first
                exit_idx = hit_profit.idxmax()
                exit_return = future_returns.loc[exit_idx]
                holding_period = (future_returns.index.get_loc(exit_idx) - 
                                future_returns.index.get_loc(future_returns.index[0]) + 1)
                label = 1
            elif hit_stop.any():
                # Hit stop loss first
                exit_idx = hit_stop.idxmax()
                exit_return = future_returns.loc[exit_idx]
                holding_period = (future_returns.index.get_loc(exit_idx) - 
                                future_returns.index.get_loc(future_returns.index[0]) + 1)
                label = -1
            else:
                # Time exit
                exit_return = future_returns.iloc[-1]
                holding_period = horizon
                label = 1 if exit_return > 0 else -1
            
            labels.append(label)
            returns.append(exit_return)
            holding_periods.append(holding_period)
        
        # Pad with NaN for the last horizon periods
        labels.extend([np.nan] * horizon)
        returns.extend([np.nan] * horizon)
        holding_periods.extend([np.nan] * horizon)
        
        result['Target_Triple_Barrier'] = labels
        result['Target_Return_Triple'] = returns
        result['Target_Holding_Period'] = holding_periods
        
        return result
    
    def _create_trend_continuation_labels(
        self,
        df: pd.DataFrame,
        horizon: int,
        threshold: float
    ) -> pd.DataFrame:
        """
        Create trend continuation labels.
        
        Args:
            df: DataFrame with OHLCV data  
            horizon: Forward looking periods
            threshold: Minimum trend strength
            
        Returns:
            DataFrame with trend continuation labels
        """
        result = df.copy()
        close = df['close']
        
        # Calculate current trend
        ema_short = TechnicalIndicators.ema(close, 10)
        ema_long = TechnicalIndicators.ema(close, 20)
        current_trend = np.where(ema_short > ema_long, 1, -1)
        
        # Look forward to see if trend continues
        future_trend = []
        for i in range(len(df)):
            if i + horizon >= len(df):
                future_trend.append(np.nan)
            else:
                # Check if trend continues for majority of horizon
                future_ema_short = ema_short.iloc[i+1:i+1+horizon]
                future_ema_long = ema_long.iloc[i+1:i+1+horizon]
                future_trend_dir = np.where(future_ema_short > future_ema_long, 1, -1)
                
                # Trend continues if same direction for >50% of horizon
                if current_trend[i] == 1:
                    continuation = (future_trend_dir == 1).mean() > 0.6
                else:
                    continuation = (future_trend_dir == -1).mean() > 0.6
                
                future_trend.append(1 if continuation else 0)
        
        result['Target_Trend_Continuation'] = future_trend
        result['Current_Trend'] = current_trend
        
        return result
    
    def create_all_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create all feature types.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with all features added
        """
        logger.info("Creating momentum features...")
        result = self.create_momentum_features(df)
        
        logger.info("Creating volatility features...")  
        result = self.create_volatility_features(result)
        
        logger.info("Creating regime features...")
        result = self.create_regime_features(result)
        
        logger.info("Creating mean reversion features...")
        result = self.create_mean_reversion_features(result)
        
        logger.info("Creating volume features...")
        result = self.create_volume_features(result)
        
        logger.info("Creating microstructure features...")
        result = self.create_microstructure_features(result)
        
        return result
    
    def prepare_ml_features(
        self,
        df: pd.DataFrame,
        feature_columns: Optional[List[str]] = None,
        target_column: str = "Target_Binary",
        scaler_type: str = "standard",
        handle_missing: str = "drop"
    ) -> Tuple[pd.DataFrame, pd.Series, object]:
        """
        Prepare features for machine learning.
        
        Args:
            df: DataFrame with features
            feature_columns: List of feature columns (None for auto-select)
            target_column: Target column name
            scaler_type: Scaler type ("standard", "minmax", "none")
            handle_missing: How to handle missing values ("drop", "forward_fill")
            
        Returns:
            Tuple of (scaled features DataFrame, target Series, fitted scaler)
        """
        # Select feature columns if not provided
        if feature_columns is None:
            # Exclude non-feature columns
            exclude_patterns = [
                'open', 'high', 'low', 'close', 'volume',
                'Target_', 'timestamp', 'date'
            ]
            
            feature_columns = []
            for col in df.columns:
                if not any(pattern in col for pattern in exclude_patterns):
                    if df[col].dtype in ['int64', 'float64']:
                        feature_columns.append(col)
        
        logger.info(f"Using {len(feature_columns)} features for ML")
        
        # Extract features and target
        X = df[feature_columns].copy()
        y = df[target_column].copy() if target_column in df.columns else None
        
        # Handle missing values
        if handle_missing == "drop":
            if y is not None:
                valid_idx = X.notna().all(axis=1) & y.notna()
                X = X[valid_idx]
                y = y[valid_idx]
            else:
                X = X.dropna()
        elif handle_missing == "forward_fill":
            X = X.fillna(method='ffill').fillna(0)
            if y is not None:
                y = y.fillna(method='ffill')
        
        # Scale features
        scaler = None
        if scaler_type == "standard":
            scaler = StandardScaler()
            X_scaled = pd.DataFrame(
                scaler.fit_transform(X),
                columns=X.columns,
                index=X.index
            )
        elif scaler_type == "minmax":
            scaler = MinMaxScaler()
            X_scaled = pd.DataFrame(
                scaler.fit_transform(X),
                columns=X.columns,
                index=X.index
            )
        else:
            X_scaled = X
        
        return X_scaled, y, scaler
    
    def get_feature_importance(self, feature_names: List[str], importances: np.ndarray) -> pd.DataFrame:
        """
        Create feature importance DataFrame.
        
        Args:
            feature_names: List of feature names
            importances: Array of importance values
            
        Returns:
            DataFrame with feature importance rankings
        """
        importance_df = pd.DataFrame({
            'feature': feature_names,
            'importance': importances
        }).sort_values('importance', ascending=False)
        
        importance_df['rank'] = range(1, len(importance_df) + 1)
        importance_df['cumulative_importance'] = importance_df['importance'].cumsum()
        
        return importance_df