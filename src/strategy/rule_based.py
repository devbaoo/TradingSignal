"""
Rule-based trading strategies.
Implements momentum and mean-reversion strategies using technical indicators.
"""

import warnings
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ..indicators import TechnicalIndicators, calculate_all_indicators
from ..utils import get_logger

warnings.filterwarnings("ignore", category=RuntimeWarning)
logger = get_logger(__name__)


class BaseStrategy(ABC):
    """
    Base class for all trading strategies.
    
    Defines the interface and common functionality for trading strategies.
    """
    
    def __init__(self, config: Dict):
        """
        Initialize strategy with configuration.
        
        Args:
            config: Strategy configuration dictionary
        """
        self.config = config
        self.name = self.__class__.__name__
        self.parameters = config.get("parameters", {})
        
        # Risk management settings
        self.risk_config = config.get("risk", {})
        self.stop_loss_atr_mult = self.risk_config.get("stop_loss_atr_mult", 2.0)
        self.take_profit_atr_mult = self.risk_config.get("take_profit_atr_mult", 3.0)
        self.trailing_stop_atr_mult = self.risk_config.get("trailing_stop_atr_mult", 1.0)
        
        # Strategy settings
        self.allow_short = config.get("allow_short", False)
        self.position_sizing = config.get("position_sizing", "fixed_fractional")
        self.risk_per_trade = config.get("risk_per_trade", 0.02)
        
        # Internal state
        self.current_position = 0  # 1 for long, -1 for short, 0 for no position
        self.entry_price = None
        self.stop_loss = None
        self.take_profit = None
        self.position_atr = None
        
        logger.info(f"Initialized {self.name} strategy")
    
    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate trading signals based on data.
        
        Args:
            df: DataFrame with OHLCV and indicator data
            
        Returns:
            DataFrame with signal columns added
        """
        pass
    
    def prepare_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Prepare data with required indicators.
        
        Args:
            df: Raw OHLCV DataFrame
            
        Returns:
            DataFrame with indicators added
        """
        # Calculate all technical indicators
        result = calculate_all_indicators(df)
        
        # Add any strategy-specific indicators
        result = self._add_custom_indicators(result)
        
        return result
    
    def _add_custom_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add strategy-specific indicators.
        Override in child classes if needed.
        
        Args:
            df: DataFrame with standard indicators
            
        Returns:
            DataFrame with custom indicators added
        """
        return df
    
    def calculate_position_size(self, price: float, atr: float, balance: float) -> float:
        """
        Calculate position size based on risk management rules.
        
        Args:
            price: Entry price
            atr: Average True Range value
            balance: Current account balance
            
        Returns:
            Position size (number of shares/contracts)
        """
        if self.position_sizing == "fixed_fractional":
            # Risk-based position sizing
            risk_amount = balance * self.risk_per_trade
            stop_distance = atr * self.stop_loss_atr_mult
            position_size = risk_amount / stop_distance
            
        elif self.position_sizing == "fixed_amount":
            # Fixed dollar amount
            fixed_amount = self.risk_config.get("fixed_amount", 1000)
            position_size = fixed_amount / price
            
        elif self.position_sizing == "atr_based":
            # ATR-based sizing
            atr_mult = self.risk_config.get("atr_position_mult", 10)
            position_size = (balance * self.risk_per_trade) / (atr * atr_mult)
            
        else:
            # Default: fixed fractional
            risk_amount = balance * self.risk_per_trade
            stop_distance = atr * self.stop_loss_atr_mult
            position_size = risk_amount / stop_distance
        
        return max(0, position_size)
    
    def update_stop_loss(self, current_price: float, atr: float, position: int) -> Optional[float]:
        """
        Update trailing stop loss.
        
        Args:
            current_price: Current market price
            atr: Current ATR value
            position: Current position (1 for long, -1 for short)
            
        Returns:
            New stop loss level or None if no update
        """
        if self.stop_loss is None or position == 0:
            return None
        
        trailing_distance = atr * self.trailing_stop_atr_mult
        
        if position == 1:  # Long position
            new_stop = current_price - trailing_distance
            if new_stop > self.stop_loss:
                self.stop_loss = new_stop
                return new_stop
        elif position == -1:  # Short position
            new_stop = current_price + trailing_distance
            if new_stop < self.stop_loss:
                self.stop_loss = new_stop
                return new_stop
        
        return None
    
    def check_exit_conditions(
        self, 
        current_price: float, 
        high: float, 
        low: float,
        position: int
    ) -> Tuple[bool, str]:
        """
        Check if exit conditions are met.
        
        Args:
            current_price: Current close price
            high: Current period high
            low: Current period low
            position: Current position
            
        Returns:
            Tuple of (should_exit, reason)
        """
        if position == 0 or self.stop_loss is None:
            return False, ""
        
        if position == 1:  # Long position
            # Check stop loss
            if low <= self.stop_loss:
                return True, "stop_loss"
            
            # Check take profit
            if self.take_profit and high >= self.take_profit:
                return True, "take_profit"
                
        elif position == -1:  # Short position
            # Check stop loss
            if high >= self.stop_loss:
                return True, "stop_loss"
            
            # Check take profit
            if self.take_profit and low <= self.take_profit:
                return True, "take_profit"
        
        return False, ""


class StrategyMomo(BaseStrategy):
    """
    Momentum Strategy.
    
    Entry conditions:
    - Long: Uptrend (Close > EMA200) + RSI 50-70 rising + MACD histogram crossing up
    - Short: Downtrend (Close < EMA200) + RSI 30-50 falling + MACD histogram crossing down
    
    Risk management:
    - Stop loss: 2 x ATR
    - Take profit: 3 x ATR  
    - Trailing stop: 1 x ATR
    """
    
    def __init__(self, config: Dict):
        """Initialize momentum strategy."""
        super().__init__(config)
        
        # Strategy parameters
        params = self.parameters
        self.ema_regime_period = params.get("ema_regime_period", 200)
        self.rsi_period = params.get("rsi_period", 14)
        self.rsi_bull_min = params.get("rsi_bull_min", 50)
        self.rsi_bull_max = params.get("rsi_bull_max", 70)
        self.rsi_bear_min = params.get("rsi_bear_min", 30)
        self.rsi_bear_max = params.get("rsi_bear_max", 50)
        self.macd_fast = params.get("macd_fast", 12)
        self.macd_slow = params.get("macd_slow", 26)
        self.macd_signal = params.get("macd_signal", 9)
        self.vol_filter = params.get("use_volatility_filter", True)
        self.vol_percentile = params.get("volatility_percentile", 0.3)
        
    def _add_custom_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add momentum-specific indicators."""
        result = df.copy()
        
        # Ensure we have the required indicators with correct periods
        if f'EMA_{self.ema_regime_period}' not in df.columns:
            result[f'EMA_{self.ema_regime_period}'] = TechnicalIndicators.ema(
                df['close'], self.ema_regime_period
            )
        
        if f'RSI_{self.rsi_period}' not in df.columns:
            result[f'RSI_{self.rsi_period}'] = TechnicalIndicators.rsi(
                df['close'], self.rsi_period
            )
        
        # MACD with custom parameters
        macd, macd_signal, macd_hist = TechnicalIndicators.macd(
            df['close'], self.macd_fast, self.macd_slow, self.macd_signal
        )
        result['MACD_Custom'] = macd
        result['MACD_Signal_Custom'] = macd_signal
        result['MACD_Hist_Custom'] = macd_hist
        
        # Volatility filter
        if self.vol_filter and 'ATR_14' in df.columns:
            atr_pct = df['ATR_14'] / df['close']
            result['Vol_Filter'] = atr_pct <= atr_pct.rolling(50).quantile(self.vol_percentile)
        else:
            result['Vol_Filter'] = True
        
        return result
    
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate momentum trading signals."""
        result = df.copy()
        
        # Get required columns
        close = df['close']
        ema_regime = df[f'EMA_{self.ema_regime_period}']
        rsi = df[f'RSI_{self.rsi_period}']
        macd_hist = df['MACD_Hist_Custom']
        vol_filter = df['Vol_Filter']
        
        # Calculate signal components
        result['Regime_Bull'] = close > ema_regime
        result['Regime_Bear'] = close < ema_regime
        
        result['RSI_Bull_Zone'] = (rsi >= self.rsi_bull_min) & (rsi <= self.rsi_bull_max)
        result['RSI_Bear_Zone'] = (rsi >= self.rsi_bear_min) & (rsi <= self.rsi_bear_max)
        result['RSI_Rising'] = rsi > rsi.shift(1)
        result['RSI_Falling'] = rsi < rsi.shift(1)
        
        result['MACD_Hist_Cross_Up'] = (
            (macd_hist > 0) & (macd_hist.shift(1) <= 0)
        )
        result['MACD_Hist_Cross_Down'] = (
            (macd_hist < 0) & (macd_hist.shift(1) >= 0)
        )
        
        # Generate entry signals
        result['Signal_Long'] = (
            result['Regime_Bull'] &
            result['RSI_Bull_Zone'] &
            result['RSI_Rising'] &
            result['MACD_Hist_Cross_Up'] &
            vol_filter
        ).astype(int)
        
        if self.allow_short:
            result['Signal_Short'] = (
                result['Regime_Bear'] &
                result['RSI_Bear_Zone'] &
                result['RSI_Falling'] &
                result['MACD_Hist_Cross_Down'] &
                vol_filter
            ).astype(int)
        else:
            result['Signal_Short'] = 0
        
        # Generate exit signals (for strategy validation)
        result['Signal_Exit_Long'] = (
            ~result['Regime_Bull'] | (rsi > 80) | (macd_hist < macd_hist.shift(1))
        ).astype(int)
        
        if self.allow_short:
            result['Signal_Exit_Short'] = (
                ~result['Regime_Bear'] | (rsi < 20) | (macd_hist > macd_hist.shift(1))
            ).astype(int)
        else:
            result['Signal_Exit_Short'] = 0
        
        # Final signal (1 for long, -1 for short, 0 for no signal)
        result['Signal'] = np.where(
            result['Signal_Long'] == 1, 1,
            np.where(result['Signal_Short'] == 1, -1, 0)
        )
        
        return result


class StrategyMeanRev(BaseStrategy):
    """
    Mean Reversion Strategy.
    
    Entry conditions:
    - Long: Price touches/goes below lower Bollinger Band + RSI < 30 + low volatility
    - Short: Price touches/goes above upper Bollinger Band + RSI > 70 + low volatility
    
    Risk management:
    - Stop loss: 1.5 x ATR
    - Take profit: Middle Bollinger Band or 2 x stop distance
    - Trailing stop: 1 x ATR
    """
    
    def __init__(self, config: Dict):
        """Initialize mean reversion strategy."""
        super().__init__(config)
        
        # Override default risk parameters for mean reversion
        self.stop_loss_atr_mult = self.risk_config.get("stop_loss_atr_mult", 1.5)
        self.take_profit_atr_mult = self.risk_config.get("take_profit_atr_mult", 2.0)
        
        # Strategy parameters
        params = self.parameters
        self.bb_period = params.get("bb_period", 20)
        self.bb_std = params.get("bb_std", 2.0)
        self.rsi_period = params.get("rsi_period", 14)
        self.rsi_oversold = params.get("rsi_oversold", 30)
        self.rsi_overbought = params.get("rsi_overbought", 70)
        self.vol_filter = params.get("use_volatility_filter", True)
        self.vol_percentile = params.get("volatility_percentile", 0.4)
        self.williams_r_period = params.get("williams_r_period", 14)
        self.williams_r_oversold = params.get("williams_r_oversold", -80)
        self.williams_r_overbought = params.get("williams_r_overbought", -20)
        
    def _add_custom_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add mean reversion specific indicators."""
        result = df.copy()
        
        # Custom Bollinger Bands
        bb_upper, bb_middle, bb_lower = TechnicalIndicators.bollinger_bands(
            df['close'], self.bb_period, self.bb_std
        )
        result['BB_Upper_Custom'] = bb_upper
        result['BB_Middle_Custom'] = bb_middle
        result['BB_Lower_Custom'] = bb_lower
        
        # Custom RSI
        if f'RSI_{self.rsi_period}' not in df.columns:
            result[f'RSI_{self.rsi_period}'] = TechnicalIndicators.rsi(
                df['close'], self.rsi_period
            )
        
        # Williams %R
        result['Williams_R'] = TechnicalIndicators.williams_r(
            df['high'], df['low'], df['close'], self.williams_r_period
        )
        
        # Volatility filter (low volatility periods)
        if self.vol_filter and 'ATR_14' in df.columns:
            atr_pct = df['ATR_14'] / df['close']
            result['Vol_Filter'] = atr_pct <= atr_pct.rolling(50).quantile(self.vol_percentile)
        else:
            result['Vol_Filter'] = True
        
        # Band position
        bb_width = bb_upper - bb_lower
        result['BB_Position'] = (df['close'] - bb_middle) / (bb_width / 2)
        
        return result
    
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate mean reversion trading signals."""
        result = df.copy()
        
        # Get required columns
        close = df['close']
        high = df['high']
        low = df['low']
        bb_upper = df['BB_Upper_Custom']
        bb_middle = df['BB_Middle_Custom']
        bb_lower = df['BB_Lower_Custom']
        rsi = df[f'RSI_{self.rsi_period}']
        williams_r = df['Williams_R']
        vol_filter = df['Vol_Filter']
        bb_position = df['BB_Position']
        
        # Band touch conditions
        result['BB_Touch_Lower'] = (low <= bb_lower) | (close <= bb_lower)
        result['BB_Touch_Upper'] = (high >= bb_upper) | (close >= bb_upper)
        
        # Extreme conditions
        result['RSI_Oversold'] = rsi < self.rsi_oversold
        result['RSI_Overbought'] = rsi > self.rsi_overbought
        result['Williams_Oversold'] = williams_r < self.williams_r_oversold
        result['Williams_Overbought'] = williams_r > self.williams_r_overbought
        
        # Band squeeze detection (low volatility)
        bb_width = bb_upper - bb_lower
        bb_width_ma = bb_width.rolling(20).mean()
        result['BB_Squeeze'] = bb_width < bb_width_ma * 0.8
        
        # Generate entry signals
        result['Signal_Long'] = (
            result['BB_Touch_Lower'] &
            result['RSI_Oversold'] &
            result['Williams_Oversold'] &
            vol_filter &
            (bb_position < -0.8)  # Close to lower band
        ).astype(int)
        
        if self.allow_short:
            result['Signal_Short'] = (
                result['BB_Touch_Upper'] &
                result['RSI_Overbought'] &
                result['Williams_Overbought'] &
                vol_filter &
                (bb_position > 0.8)  # Close to upper band
            ).astype(int)
        else:
            result['Signal_Short'] = 0
        
        # Generate exit signals
        result['Signal_Exit_Long'] = (
            (close >= bb_middle) |  # Price reaches middle band
            (rsi > 50) |  # RSI normalizes
            (bb_position > 0)  # Price moves above middle
        ).astype(int)
        
        if self.allow_short:
            result['Signal_Exit_Short'] = (
                (close <= bb_middle) |  # Price reaches middle band
                (rsi < 50) |  # RSI normalizes
                (bb_position < 0)  # Price moves below middle
            ).astype(int)
        else:
            result['Signal_Exit_Short'] = 0
        
        # Final signal
        result['Signal'] = np.where(
            result['Signal_Long'] == 1, 1,
            np.where(result['Signal_Short'] == 1, -1, 0)
        )
        
        return result


def get_strategy_class(strategy_name: str) -> BaseStrategy:
    """
    Get strategy class by name.
    
    Args:
        strategy_name: Name of the strategy
        
    Returns:
        Strategy class
        
    Raises:
        ValueError: If strategy name is not recognized
    """
    strategies = {
        "StrategyMomo": StrategyMomo,
        "Strategy_Momo": StrategyMomo,
        "momentum": StrategyMomo,
        "StrategyMeanRev": StrategyMeanRev,
        "Strategy_MeanRev": StrategyMeanRev,
        "mean_reversion": StrategyMeanRev,
    }
    
    if strategy_name not in strategies:
        available = list(strategies.keys())
        raise ValueError(f"Unknown strategy '{strategy_name}'. Available: {available}")
    
    return strategies[strategy_name]


def create_strategy(strategy_name: str, config: Dict) -> BaseStrategy:
    """
    Create strategy instance.
    
    Args:
        strategy_name: Name of the strategy
        config: Strategy configuration
        
    Returns:
        Strategy instance
    """
    strategy_class = get_strategy_class(strategy_name)
    return strategy_class(config)