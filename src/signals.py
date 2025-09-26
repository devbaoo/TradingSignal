"""
Trading Signal Generator for Futures Trading
Generates actionable trading signals with specific parameters.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import json

from .utils import get_logger
from .data import DataLoader
from .strategy.rule_based import create_strategy
from .backtest import BacktestEngine, BacktestConfig

logger = get_logger(__name__)


@dataclass
class TradingSignal:
    """Trading signal with specific parameters for futures trading."""
    
    # Basic signal info
    symbol: str
    direction: str  # "LONG" or "SHORT"
    timestamp: datetime
    strategy_name: str
    timeframe: str
    
    # Entry parameters
    entry_price: float
    entry_price_range: Tuple[float, float]  # (min, max) for limit orders
    
    # Risk management
    stop_loss: float
    take_profit: List[float]  # Multiple TP levels
    
    # Position sizing
    risk_per_trade: float  # % of account
    recommended_leverage: int
    position_size_usdt: float
    position_size_percent: float  # % of account balance
    
    # Safety assessment
    safety_score: int  # 1-10 (10 = safest)
    confidence_level: str  # "LOW", "MEDIUM", "HIGH"
    risk_level: str  # "CONSERVATIVE", "MODERATE", "AGGRESSIVE"
    
    # Market analysis
    trend_strength: float  # 0-1
    volatility_percentile: float  # 0-100
    volume_profile: str  # "LOW", "MEDIUM", "HIGH"
    
    # Technical indicators summary
    rsi: float
    ema_trend: str  # "BULLISH", "BEARISH", "NEUTRAL"
    macd_signal: str  # "BUY", "SELL", "NEUTRAL"
    support_resistance: Dict[str, float]
    
    # Trading instructions
    market_conditions: str
    execution_notes: str
    validity_period: int  # minutes
    
    @property
    def risk_reward_ratio(self) -> float:
        """Calculate risk/reward ratio."""
        risk = abs(self.entry_price - self.stop_loss)
        reward = abs(self.take_profit[0] - self.entry_price) if self.take_profit else 0
        return reward / risk if risk > 0 else 0
    
    @property
    def trading_command(self) -> str:
        """Generate formatted trading command."""
        return f"""
🎯 FUTURES TRADING SIGNAL
{'='*40}
📊 Symbol: {self.symbol}
📈 Direction: {self.direction}
⏰ Entry Time: {self.timestamp.strftime('%H:%M:%S')}
🎯 Strategy: {self.strategy_name} ({self.timeframe})

💰 ENTRY PARAMETERS:
   Entry Price: ${self.entry_price:,.4f}
   Entry Range: ${self.entry_price_range[0]:,.4f} - ${self.entry_price_range[1]:,.4f}
   
🛡️ RISK MANAGEMENT:
   Stop Loss: ${self.stop_loss:,.4f}
   Take Profit 1: ${self.take_profit[0]:,.4f}
   Take Profit 2: ${self.take_profit[1]:,.4f if len(self.take_profit) > 1 else 0}
   R/R Ratio: {self.risk_reward_ratio:.2f}

📦 POSITION SIZING:
   Risk per Trade: {self.risk_per_trade*100:.1f}%
   Recommended Leverage: {self.recommended_leverage}x
   Position Size: ${self.position_size_usdt:,.0f}
   Account %: {self.position_size_percent:.1f}%

🔍 SIGNAL QUALITY:
   Safety Score: {self.safety_score}/10 ({self.confidence_level})
   Risk Level: {self.risk_level}
   Trend Strength: {self.trend_strength*100:.0f}%

⚠️ EXECUTION NOTES:
   {self.execution_notes}
   Valid for: {self.validity_period} minutes
"""


class SafetyScorer:
    """Calculates safety score for trading signals."""
    
    def __init__(self):
        self.weights = {
            'trend_strength': 0.25,
            'volatility': 0.20,
            'volume': 0.15,
            'risk_reward': 0.15,
            'support_resistance': 0.15,
            'backtest_performance': 0.10
        }
    
    def calculate_score(self, 
                       signal_data: Dict[str, Any],
                       backtest_results: Optional[Dict] = None) -> Tuple[int, str, str]:
        """Calculate safety score and confidence level."""
        
        score_components = {}
        
        # 1. Trend strength (0-10)
        trend_strength = signal_data.get('trend_strength', 0.5)
        score_components['trend_strength'] = min(10, trend_strength * 20)
        
        # 2. Volatility score (lower volatility = higher safety)
        volatility_pct = signal_data.get('volatility_percentile', 50)
        if volatility_pct < 25:
            volatility_score = 9  # Very stable
        elif volatility_pct < 50:
            volatility_score = 7  # Stable
        elif volatility_pct < 75:
            volatility_score = 5  # Moderate
        else:
            volatility_score = 3  # High volatility
        score_components['volatility'] = volatility_score
        
        # 3. Volume profile
        volume_profile = signal_data.get('volume_profile', 'MEDIUM')
        volume_scores = {'LOW': 4, 'MEDIUM': 7, 'HIGH': 9}
        score_components['volume'] = volume_scores.get(volume_profile, 5)
        
        # 4. Risk/Reward ratio
        risk_reward = signal_data.get('risk_reward', 1.0)
        if risk_reward >= 3.0:
            rr_score = 10
        elif risk_reward >= 2.0:
            rr_score = 8
        elif risk_reward >= 1.5:
            rr_score = 6
        else:
            rr_score = 3
        score_components['risk_reward'] = rr_score
        
        # 5. Support/Resistance proximity
        proximity = signal_data.get('sr_proximity', 0.5)  # How close to S/R levels
        if proximity < 0.2:
            sr_score = 9  # Very close to S/R
        elif proximity < 0.5:
            sr_score = 7
        else:
            sr_score = 4
        score_components['support_resistance'] = sr_score
        
        # 6. Backtest performance
        if backtest_results:
            win_rate = backtest_results.get('win_rate', 0.5)
            profit_factor = backtest_results.get('profit_factor', 1.0)
            bt_score = min(10, (win_rate * 5) + (min(profit_factor, 2.0) * 2.5))
        else:
            bt_score = 5  # Neutral if no backtest data
        score_components['backtest_performance'] = bt_score
        
        # Calculate weighted score
        total_score = sum(
            score_components[component] * self.weights[component]
            for component in score_components
        )
        
        # Round to integer 1-10
        safety_score = max(1, min(10, round(total_score)))
        
        # Determine confidence and risk level
        if safety_score >= 8:
            confidence = "HIGH"
            risk_level = "CONSERVATIVE"
        elif safety_score >= 6:
            confidence = "MEDIUM"
            risk_level = "MODERATE"
        else:
            confidence = "LOW"
            risk_level = "AGGRESSIVE"
        
        logger.debug(f"Safety score components: {score_components}")
        logger.debug(f"Final safety score: {safety_score}")
        
        return safety_score, confidence, risk_level


class PositionSizer:
    """Calculates optimal position size based on risk and safety with conservative limits."""
    
    def __init__(self, account_balance: float = 10000):
        self.account_balance = account_balance
        self.max_portfolio_risk = 0.07  # Max 7% total portfolio risk
        self.max_concurrent_positions = 3  # Max 3 positions at once
        self.max_exposure_per_trade = 0.25  # Max 25% account per trade
        self.daily_loss_limit = 0.03  # Circuit breaker: 3% daily loss
        self.max_consecutive_losses = 3  # Stop after 3 consecutive losses
        
    def calculate_position_size(self,
                              entry_price: float,
                              stop_loss: float,
                              safety_score: int,
                              base_risk_per_trade: float = 0.01) -> Tuple[float, int, float, float]:  # Reduced to 1%
        """Calculate conservative position size with multiple risk controls."""
        
        # Conservative risk multipliers (max 1.1x)
        risk_multiplier = {
            10: 1.1,  # Safest - slightly more risk (max 1.1%)
            9: 1.0,   # High safety - normal risk (1.0%)
            8: 0.9,   # Good safety - slight reduction
            7: 0.7,   # Medium safety - moderate reduction
            6: 0.5,   # Lower safety - significant reduction
            5: 0.4,   # Moderate risk - conservative
            4: 0.3,   # Higher risk - very conservative
            3: 0.2,   # High risk - minimal
            2: 0.1,   # Very high risk - tiny position
            1: 0.05   # Extremely risky - micro position
        }.get(safety_score, 0.3)
        
        adjusted_risk = base_risk_per_trade * risk_multiplier
        
        # Calculate position size
        risk_amount = self.account_balance * adjusted_risk
        price_diff = abs(entry_price - stop_loss)
        position_value = risk_amount / (price_diff / entry_price)
        
        # Conservative leverage recommendation based on safety
        if safety_score >= 8:
            max_leverage = min(8, int(10 * risk_multiplier))  # Reduced max leverage
        elif safety_score >= 6:
            max_leverage = min(5, int(7 * risk_multiplier))
        elif safety_score >= 4:
            max_leverage = min(3, int(5 * risk_multiplier))
        else:
            max_leverage = min(2, int(3 * risk_multiplier))
        
        # Ensure minimum leverage of 1
        recommended_leverage = max(1, max_leverage)
        
        # Position size with conservative limits
        position_size_usdt = min(
            position_value / recommended_leverage, 
            self.account_balance * self.max_exposure_per_trade  # Max 25% exposure
        )
        position_size_percent = (position_size_usdt / self.account_balance) * 100
        
        # Additional safety checks
        if position_size_percent > self.max_exposure_per_trade * 100:
            position_size_percent = self.max_exposure_per_trade * 100
            position_size_usdt = self.account_balance * self.max_exposure_per_trade
        
        return position_size_usdt, recommended_leverage, adjusted_risk, position_size_percent
    
    def check_circuit_breaker(self, daily_pnl: float, consecutive_losses: int) -> bool:
        """Circuit breaker to stop trading on bad days."""
        daily_loss_pct = abs(daily_pnl) / self.account_balance
        
        if daily_loss_pct >= self.daily_loss_limit:
            return True  # Stop trading - daily loss limit reached
        
        if consecutive_losses >= self.max_consecutive_losses:
            return True  # Stop trading - too many consecutive losses
        
        return False


class TradingSignalGenerator:
    """Main class for generating trading signals."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.data_loader = DataLoader(config.get('data', {}))
        
        # Create backtest config with only valid parameters
        backtest_config_params = config.get('backtest', {})
        valid_backtest_params = {}
        
        # Only include parameters that BacktestConfig accepts
        for param in ['initial_capital', 'fee_rate', 'slippage_bps']:
            if param in backtest_config_params:
                valid_backtest_params[param] = backtest_config_params[param]
        
        # Set defaults if not provided
        if 'initial_capital' not in valid_backtest_params:
            valid_backtest_params['initial_capital'] = 10000
        if 'fee_rate' not in valid_backtest_params:
            valid_backtest_params['fee_rate'] = 0.001
        if 'slippage_bps' not in valid_backtest_params:
            valid_backtest_params['slippage_bps'] = 2.0
        
        self.backtest_engine = BacktestEngine(BacktestConfig(**valid_backtest_params))
        self.safety_scorer = SafetyScorer()
        self.position_sizer = PositionSizer(config.get('account_balance', 10000))
        
    def analyze_market_conditions(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze current market conditions."""
        
        if len(df) < 50:
            return {}
        
        # Calculate technical indicators
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume'] if 'volume' in df.columns else pd.Series([1] * len(df))
        
        # RSI
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1] if len(rsi) > 0 else 50
        
        # EMA trend
        ema_12 = close.ewm(span=12).mean()
        ema_26 = close.ewm(span=26).mean()
        
        if ema_12.iloc[-1] > ema_26.iloc[-1]:
            ema_trend = "BULLISH"
        elif ema_12.iloc[-1] < ema_26.iloc[-1]:
            ema_trend = "BEARISH"
        else:
            ema_trend = "NEUTRAL"
        
        # MACD
        macd_line = ema_12 - ema_26
        macd_signal = macd_line.ewm(span=9).mean()
        
        if macd_line.iloc[-1] > macd_signal.iloc[-1]:
            macd_signal_str = "BUY"
        elif macd_line.iloc[-1] < macd_signal.iloc[-1]:
            macd_signal_str = "SELL"
        else:
            macd_signal_str = "NEUTRAL"
        
        # Volatility
        returns = close.pct_change().dropna()
        current_vol = returns.rolling(20).std().iloc[-1] * np.sqrt(365)
        vol_percentile = (current_vol > returns.rolling(100).std() * np.sqrt(365)).sum() / 100 * 100
        
        # Volume profile
        avg_volume = volume.rolling(20).mean().iloc[-1]
        recent_volume = volume.iloc[-5:].mean()
        
        if recent_volume > avg_volume * 1.5:
            volume_profile = "HIGH"
        elif recent_volume > avg_volume * 0.8:
            volume_profile = "MEDIUM"
        else:
            volume_profile = "LOW"
        
        # Trend strength
        price_change = (close.iloc[-1] - close.iloc[-20]) / close.iloc[-20]
        trend_strength = min(1.0, abs(price_change) * 10)
        
        # Support/Resistance levels
        recent_highs = high.rolling(20).max()
        recent_lows = low.rolling(20).min()
        
        current_price = close.iloc[-1]
        resistance = recent_highs.iloc[-1]
        support = recent_lows.iloc[-1]
        
        return {
            'rsi': current_rsi,
            'ema_trend': ema_trend,
            'macd_signal': macd_signal_str,
            'volatility_percentile': vol_percentile,
            'volume_profile': volume_profile,
            'trend_strength': trend_strength,
            'support_resistance': {
                'support': support,
                'resistance': resistance,
                'current': current_price
            },
            'market_conditions': self._assess_market_conditions(current_rsi, ema_trend, vol_percentile)
        }
    
    def _assess_market_conditions(self, rsi: float, trend: str, volatility: float) -> str:
        """Assess overall market conditions."""
        
        conditions = []
        
        if volatility > 75:
            conditions.append("HIGH_VOLATILITY")
        elif volatility < 25:
            conditions.append("LOW_VOLATILITY")
        else:
            conditions.append("NORMAL_VOLATILITY")
        
        if rsi > 70:
            conditions.append("OVERBOUGHT")
        elif rsi < 30:
            conditions.append("OVERSOLD")
        else:
            conditions.append("NEUTRAL_RSI")
        
        if trend == "BULLISH":
            conditions.append("UPTREND")
        elif trend == "BEARISH":
            conditions.append("DOWNTREND")
        else:
            conditions.append("SIDEWAYS")
        
        return "_".join(conditions)
    
    def generate_signal(self, 
                       symbol: str, 
                       timeframe: str = "1h",
                       strategy_name: str = "StrategyMomo") -> Optional[TradingSignal]:
        """Generate a complete trading signal."""
        
        logger.info(f"Generating signal for {symbol} {timeframe}")
        
        try:
            # Load recent data
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            
            df = self.data_loader.load_ohlcv(symbol, timeframe, start_date, end_date)
            
            if len(df) < 50:
                logger.warning(f"Insufficient data for {symbol}")
                return None
            
            # Analyze market conditions
            market_analysis = self.analyze_market_conditions(df)
            
            if not market_analysis:
                return None
            
            # Run backtest to get performance metrics
            strategy_params = self.config.get('strategy_params', {}).get(strategy_name, {})
            strategy = create_strategy(strategy_name, strategy_params)
            
            backtest_results = self.backtest_engine.run_backtest(df, strategy, start_date, end_date)
            
            # Check if we have a current signal
            if not backtest_results.trades:
                logger.info(f"No trades generated for {symbol}")
                return None
            
            # Get the most recent trade as signal
            latest_trade = backtest_results.trades[-1]
            current_price = df['close'].iloc[-1]
            
            # Determine signal direction based on strategy logic
            direction = "LONG" if latest_trade.get('side') == 'buy' else "SHORT"
            
            # Calculate entry parameters
            entry_price = current_price
            entry_range = (entry_price * 0.999, entry_price * 1.001)  # 0.1% range
            
            # Calculate stop loss and take profit based on strategy
            if direction == "LONG":
                stop_loss = entry_price * (1 - strategy_params.get('stop_loss_pct', 0.03))
                take_profit_1 = entry_price * (1 + strategy_params.get('take_profit_pct', 0.06))
                take_profit_2 = entry_price * (1 + strategy_params.get('take_profit_pct', 0.06) * 1.5)
            else:
                stop_loss = entry_price * (1 + strategy_params.get('stop_loss_pct', 0.03))
                take_profit_1 = entry_price * (1 - strategy_params.get('take_profit_pct', 0.06))
                take_profit_2 = entry_price * (1 - strategy_params.get('take_profit_pct', 0.06) * 1.5)
            
            # Prepare signal data for safety scoring
            signal_data = {
                'trend_strength': market_analysis['trend_strength'],
                'volatility_percentile': market_analysis['volatility_percentile'],
                'volume_profile': market_analysis['volume_profile'],
                'risk_reward': abs(take_profit_1 - entry_price) / abs(entry_price - stop_loss),
                'sr_proximity': self._calculate_sr_proximity(entry_price, market_analysis['support_resistance'])
            }
            
            # Calculate safety score
            safety_score, confidence, risk_level = self.safety_scorer.calculate_score(
                signal_data, backtest_results.metrics
            )
            
            # Calculate position sizing
            position_size_usdt, recommended_leverage, risk_per_trade, position_size_percent = \
                self.position_sizer.calculate_position_size(entry_price, stop_loss, safety_score)
            
            # Generate execution notes
            execution_notes = self._generate_execution_notes(market_analysis, safety_score)
            
            # Create trading signal
            signal = TradingSignal(
                symbol=symbol,
                direction=direction,
                timestamp=datetime.now(),
                strategy_name=strategy_name,
                timeframe=timeframe,
                entry_price=entry_price,
                entry_price_range=entry_range,
                stop_loss=stop_loss,
                take_profit=[take_profit_1, take_profit_2],
                risk_per_trade=risk_per_trade,
                recommended_leverage=recommended_leverage,
                position_size_usdt=position_size_usdt,
                position_size_percent=position_size_percent,
                safety_score=safety_score,
                confidence_level=confidence,
                risk_level=risk_level,
                trend_strength=market_analysis['trend_strength'],
                volatility_percentile=market_analysis['volatility_percentile'],
                volume_profile=market_analysis['volume_profile'],
                rsi=market_analysis['rsi'],
                ema_trend=market_analysis['ema_trend'],
                macd_signal=market_analysis['macd_signal'],
                support_resistance=market_analysis['support_resistance'],
                market_conditions=market_analysis['market_conditions'],
                execution_notes=execution_notes,
                validity_period=240  # 4 hours
            )
            
            logger.info(f"Generated signal for {symbol}: {direction} with safety score {safety_score}")
            return signal
            
        except Exception as e:
            logger.error(f"Error generating signal for {symbol}: {e}")
            return None
    
    def _calculate_sr_proximity(self, price: float, sr_levels: Dict[str, float]) -> float:
        """Calculate proximity to support/resistance levels."""
        support = sr_levels['support']
        resistance = sr_levels['resistance']
        
        range_size = resistance - support
        if range_size == 0:
            return 0.5
        
        # Distance from nearest S/R level
        dist_to_support = abs(price - support) / range_size
        dist_to_resistance = abs(price - resistance) / range_size
        
        return min(dist_to_support, dist_to_resistance)
    
    def _generate_execution_notes(self, market_analysis: Dict, safety_score: int) -> str:
        """Generate execution notes based on market conditions."""
        
        notes = []
        
        # Volatility notes
        if market_analysis['volatility_percentile'] > 75:
            notes.append("⚠️ High volatility - Consider smaller position size")
        elif market_analysis['volatility_percentile'] < 25:
            notes.append("✅ Low volatility - Good for larger positions")
        
        # Volume notes
        if market_analysis['volume_profile'] == "HIGH":
            notes.append("📈 High volume confirms signal strength")
        elif market_analysis['volume_profile'] == "LOW":
            notes.append("⚠️ Low volume - Wait for confirmation")
        
        # RSI notes
        rsi = market_analysis['rsi']
        if rsi > 75:
            notes.append("⚠️ Overbought conditions - Watch for reversal")
        elif rsi < 25:
            notes.append("⚠️ Oversold conditions - Watch for bounce")
        
        # Safety-based notes
        if safety_score >= 8:
            notes.append("🟢 High confidence signal - Safe to execute")
        elif safety_score >= 6:
            notes.append("🟡 Medium confidence - Use standard risk management")
        else:
            notes.append("🔴 Low confidence - Consider reducing position or waiting")
        
        return " | ".join(notes) if notes else "Standard execution recommended"


def create_signal_generator(config: Dict[str, Any]) -> TradingSignalGenerator:
    """Factory function to create signal generator."""
    return TradingSignalGenerator(config)