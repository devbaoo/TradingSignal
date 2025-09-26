"""
Live Trading Module for Trading Insight.
Provides paper trading and live trading capabilities with real-time data.
"""

import asyncio
import time
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Union
from threading import Thread, Event

import numpy as np
import pandas as pd

try:
    import ccxt
    import ccxt.pro as ccxtpro
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False
    ccxt = None
    ccxtpro = None

from .utils import get_logger, ensure_dir
from .strategy.rule_based import BaseStrategy
from .risk import RiskManager, Position
from .indicators import TechnicalIndicators
from .data import DataLoader

logger = get_logger(__name__)

# Suppress warnings
warnings.filterwarnings("ignore", category=UserWarning)


@dataclass
class LiveTradingConfig:
    """Configuration for live trading."""
    
    # Trading mode
    paper_trading: bool = True  # Always start with paper trading
    exchange: str = "binance"
    symbol: str = "BTC/USDT"
    timeframe: str = "15m"
    
    # Account settings
    initial_capital: float = 10000.0
    max_positions: int = 1
    
    # Data settings
    lookback_periods: int = 200  # Historical data for indicators
    data_update_interval: int = 60  # seconds
    
    # Strategy settings
    strategy_name: str = "StrategyMomo"
    strategy_params: Dict[str, Any] = field(default_factory=dict)
    
    # Risk settings
    risk_per_trade: float = 0.02
    max_daily_loss: float = 0.05
    stop_loss_pct: float = 0.03
    take_profit_pct: float = 0.06
    
    # Execution settings
    order_timeout: int = 30  # seconds
    slippage_tolerance: float = 0.001  # 0.1%
    min_trade_amount: float = 10.0  # USD
    
    # API settings
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    sandbox: bool = True  # Always use sandbox for safety
    
    # Monitoring settings
    log_trades: bool = True
    save_state: bool = True
    state_file: str = "live_trading_state.json"
    
    # Safety settings
    enable_emergency_stop: bool = True
    max_consecutive_losses: int = 5
    
    def __post_init__(self):
        """Post-initialization setup."""
        if not self.paper_trading and not self.sandbox:
            logger.warning("Live trading with real money is HIGH RISK! Use at your own risk.")
            
        if not CCXT_AVAILABLE:
            raise ImportError("CCXT is required for live trading. Install with: pip install ccxt")


@dataclass
class TradingState:
    """Current state of live trading."""
    
    # Account state
    balance: float = 10000.0
    equity: float = 10000.0
    available_balance: float = 10000.0
    unrealized_pnl: float = 0.0
    
    # Position state
    positions: List[Position] = field(default_factory=list)
    pending_orders: List[Dict] = field(default_factory=list)
    
    # Performance state
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    daily_pnl: float = 0.0
    max_drawdown: float = 0.0
    peak_equity: float = 10000.0
    
    # Risk state
    consecutive_losses: int = 0
    daily_trades: int = 0
    last_trade_time: Optional[datetime] = None
    emergency_stop: bool = False
    
    # Data state
    last_data_update: Optional[datetime] = None
    current_price: float = 0.0
    market_data: pd.DataFrame = field(default_factory=pd.DataFrame)
    
    def update_equity(self, current_price: float):
        """Update equity with current positions."""
        unrealized = 0.0
        for position in self.positions:
            if position.is_open:
                if position.side == "long":
                    unrealized += position.quantity * (current_price - position.avg_price)
                else:
                    unrealized += position.quantity * (position.avg_price - current_price)
                    
        self.unrealized_pnl = unrealized
        self.equity = self.balance + unrealized
        self.current_price = current_price
        
        # Update peak and drawdown
        if self.equity > self.peak_equity:
            self.peak_equity = self.equity
        
        current_drawdown = (self.peak_equity - self.equity) / self.peak_equity
        if current_drawdown > self.max_drawdown:
            self.max_drawdown = current_drawdown
    
    @property
    def win_rate(self) -> float:
        """Calculate win rate."""
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades
    
    @property
    def profit_factor(self) -> float:
        """Calculate profit factor."""
        if self.losing_trades == 0 or self.total_pnl <= 0:
            return float('inf') if self.winning_trades > 0 else 0.0
        
        avg_win = self.total_pnl / self.winning_trades if self.winning_trades > 0 else 0
        avg_loss = abs(self.total_pnl) / self.losing_trades if self.losing_trades > 0 else 0
        
        return avg_win / avg_loss if avg_loss > 0 else float('inf')


class LiveTrader:
    """Live trading engine with paper trading support."""
    
    def __init__(self, config: LiveTradingConfig):
        self.config = config
        self.state = TradingState(balance=config.initial_capital, equity=config.initial_capital)
        
        # Initialize components
        self.exchange = None
        self.strategy = None
        self.risk_manager = None
        self.technical_indicators = None
        
        # Control flags
        self.is_running = False
        self.stop_event = Event()
        
        # Initialize exchange and strategy
        self._initialize_exchange()
        self._initialize_strategy()
        self._initialize_risk_manager()
        self._initialize_indicators()
        
        logger.info(f"LiveTrader initialized for {config.symbol} on {config.exchange}")
        
    def _initialize_exchange(self):
        """Initialize exchange connection."""
        if not CCXT_AVAILABLE:
            raise ImportError("CCXT is required for live trading")
            
        exchange_class = getattr(ccxt, self.config.exchange)
        
        exchange_config = {
            'apiKey': self.config.api_key,
            'secret': self.config.api_secret,
            'timeout': 30000,
            'enableRateLimit': True,
        }
        
        # Use sandbox for safety
        if self.config.sandbox:
            exchange_config['sandbox'] = True
            
        self.exchange = exchange_class(exchange_config)
        
        # Test connection (paper trading mode)
        if self.config.paper_trading:
            logger.info("Paper trading mode - no real API connection needed")
        else:
            try:
                self.exchange.load_markets()
                logger.info(f"Connected to {self.config.exchange}")
            except Exception as e:
                logger.error(f"Failed to connect to exchange: {e}")
                raise
                
    def _initialize_strategy(self):
        """Initialize trading strategy."""
        from .strategy.rule_based import create_strategy
        
        self.strategy = create_strategy(
            self.config.strategy_name,
            self.config.strategy_params
        )
        
        logger.info(f"Strategy initialized: {self.config.strategy_name}")
        
    def _initialize_risk_manager(self):
        """Initialize risk manager."""
        from .risk import RiskConfig
        
        risk_config = RiskConfig(
            max_positions=self.config.max_positions,
            risk_per_trade=self.config.risk_per_trade,
            max_portfolio_risk=0.2,
            stop_loss_pct=self.config.stop_loss_pct,
            take_profit_pct=self.config.take_profit_pct,
            position_sizing="percent_risk"
        )
        
        self.risk_manager = RiskManager(risk_config)
        
    def _initialize_indicators(self):
        """Initialize technical indicators."""
        indicator_config = {}  # Use default config
        self.technical_indicators = TechnicalIndicators(indicator_config)
        
    async def start_trading(self):
        """Start live trading."""
        logger.info("Starting live trading...")
        self.is_running = True
        
        try:
            # Load initial data
            await self._load_initial_data()
            
            # Main trading loop
            while self.is_running and not self.stop_event.is_set():
                await self._trading_cycle()
                await asyncio.sleep(self.config.data_update_interval)
                
        except KeyboardInterrupt:
            logger.info("Trading interrupted by user")
        except Exception as e:
            logger.error(f"Trading error: {e}")
            logger.exception("Trading error details")
        finally:
            await self._shutdown()
            
    def stop_trading(self):
        """Stop live trading."""
        logger.info("Stopping live trading...")
        self.is_running = False
        self.stop_event.set()
        
    async def _trading_cycle(self):
        """Execute one trading cycle."""
        try:
            # 1. Update market data
            await self._update_market_data()
            
            # 2. Check emergency stops
            if self._check_emergency_stops():
                return
                
            # 3. Update positions and orders
            await self._update_positions()
            
            # 4. Generate signals
            signals = self._generate_signals()
            
            # 5. Execute trades
            if signals:
                await self._execute_signals(signals)
                
            # 6. Update state
            self._update_state()
            
            # 7. Save state
            if self.config.save_state:
                self._save_state()
                
        except Exception as e:
            logger.error(f"Error in trading cycle: {e}")
            
    async def _load_initial_data(self):
        """Load initial market data."""
        logger.info("Loading initial market data...")
        
        # Use DataLoader for initial historical data
        data_loader = DataLoader({})
        
        try:
            # Load lookback data
            end_time = datetime.now()
            start_time = end_time - timedelta(days=30)  # Get 30 days of data
            
            df = data_loader.load_ohlcv(
                self.config.symbol,
                self.config.timeframe,
                start_time.strftime("%Y-%m-%d"),
                end_time.strftime("%Y-%m-%d"),
                exchange=self.config.exchange
            )
            
            # Keep only lookback periods
            df = df.tail(self.config.lookback_periods)
            
            # Add technical indicators
            df_with_indicators = self.technical_indicators.add_all_indicators(df)
            
            self.state.market_data = df_with_indicators
            self.state.last_data_update = datetime.now()
            self.state.current_price = df['close'].iloc[-1]
            
            logger.info(f"Loaded {len(df)} periods of market data")
            
        except Exception as e:
            logger.error(f"Error loading initial data: {e}")
            raise
            
    async def _update_market_data(self):
        """Update market data with latest prices."""
        try:
            if self.config.paper_trading:
                # Paper trading - use DataLoader for latest data
                current_time = datetime.now()
                
                # Only update if enough time has passed
                if (self.state.last_data_update and 
                    (current_time - self.state.last_data_update).seconds < self.config.data_update_interval):
                    return
                
                # Get latest candle
                data_loader = DataLoader({})
                
                # Get recent data (last few periods)
                recent_df = data_loader.load_ohlcv(
                    self.config.symbol,
                    self.config.timeframe,
                    exchange=self.config.exchange,
                    limit=5  # Get last 5 candles
                )
                
                if len(recent_df) > 0:
                    # Add indicators to new data
                    recent_with_indicators = self.technical_indicators.add_all_indicators(recent_df)
                    
                    # Update state
                    self.state.current_price = recent_df['close'].iloc[-1]
                    
                    # Append new data if it's actually new
                    if len(recent_with_indicators) > 0:
                        latest_time = recent_with_indicators.index[-1]
                        if (len(self.state.market_data) == 0 or 
                            latest_time > self.state.market_data.index[-1]):
                            
                            # Concatenate and keep only lookback periods
                            combined = pd.concat([self.state.market_data, recent_with_indicators])
                            combined = combined[~combined.index.duplicated(keep='last')]
                            self.state.market_data = combined.tail(self.config.lookback_periods)
                            
                self.state.last_data_update = current_time
                
            else:
                # Real trading - use exchange websocket (not implemented here)
                logger.warning("Real-time data feed not implemented")
                
        except Exception as e:
            logger.warning(f"Error updating market data: {e}")
            
    def _check_emergency_stops(self) -> bool:
        """Check if emergency stop conditions are met."""
        if not self.config.enable_emergency_stop:
            return False
            
        # Check max daily loss
        daily_loss_pct = abs(self.state.daily_pnl) / self.state.balance
        if daily_loss_pct > self.config.max_daily_loss:
            logger.warning(f"Emergency stop: Daily loss {daily_loss_pct*100:.2f}% exceeds limit")
            self.state.emergency_stop = True
            return True
            
        # Check consecutive losses
        if self.state.consecutive_losses >= self.config.max_consecutive_losses:
            logger.warning(f"Emergency stop: {self.state.consecutive_losses} consecutive losses")
            self.state.emergency_stop = True
            return True
            
        return False
        
    async def _update_positions(self):
        """Update open positions."""
        if not self.state.positions:
            return
            
        current_price = self.state.current_price
        
        for position in self.state.positions:
            if not position.is_open:
                continue
                
            # Check stop loss and take profit
            if position.side == "long":
                # Long position
                pnl_pct = (current_price - position.avg_price) / position.avg_price
                
                # Stop loss
                if position.stop_loss and current_price <= position.stop_loss:
                    await self._close_position(position, "stop_loss", current_price)
                    continue
                    
                # Take profit
                if position.take_profit and current_price >= position.take_profit:
                    await self._close_position(position, "take_profit", current_price)
                    continue
                    
            else:
                # Short position
                pnl_pct = (position.avg_price - current_price) / position.avg_price
                
                # Stop loss
                if position.stop_loss and current_price >= position.stop_loss:
                    await self._close_position(position, "stop_loss", current_price)
                    continue
                    
                # Take profit
                if position.take_profit and current_price <= position.take_profit:
                    await self._close_position(position, "take_profit", current_price)
                    continue
                    
        # Update equity with current prices
        self.state.update_equity(current_price)
        
    def _generate_signals(self) -> Optional[Dict[str, Any]]:
        """Generate trading signals from strategy."""
        if len(self.state.market_data) < 50:  # Need enough data
            return None
            
        try:
            # Generate signals using strategy
            signals = self.strategy.generate_signals(self.state.market_data)
            
            if signals and len(signals) > 0:
                latest_signal = signals.iloc[-1]
                
                # Only act on non-zero signals
                if latest_signal['signal'] != 0:
                    return {
                        'signal': latest_signal['signal'],
                        'confidence': latest_signal.get('confidence', 1.0),
                        'timestamp': signals.index[-1],
                        'price': self.state.current_price
                    }
                    
        except Exception as e:
            logger.error(f"Error generating signals: {e}")
            
        return None
        
    async def _execute_signals(self, signal_data: Dict[str, Any]):
        """Execute trading signals."""
        signal = signal_data['signal']
        price = signal_data['price']
        
        try:
            # Check if we can trade
            if not self._can_trade():
                return
                
            # Determine trade action
            if signal > 0:  # Buy signal
                if not self._has_long_position():
                    await self._open_position("long", price)
                    
            elif signal < 0:  # Sell signal
                if self._has_long_position():
                    # Close long position
                    long_position = self._get_long_position()
                    if long_position:
                        await self._close_position(long_position, "signal", price)
                elif self.strategy.allow_short and not self._has_short_position():
                    await self._open_position("short", price)
                    
        except Exception as e:
            logger.error(f"Error executing signal: {e}")
            
    def _can_trade(self) -> bool:
        """Check if trading is allowed."""
        if self.state.emergency_stop:
            return False
            
        if len(self.state.positions) >= self.config.max_positions:
            return False
            
        if self.state.available_balance < self.config.min_trade_amount:
            return False
            
        return True
        
    def _has_long_position(self) -> bool:
        """Check if there's an open long position."""
        return any(p.is_open and p.side == "long" for p in self.state.positions)
        
    def _has_short_position(self) -> bool:
        """Check if there's an open short position."""
        return any(p.is_open and p.side == "short" for p in self.state.positions)
        
    def _get_long_position(self) -> Optional[Position]:
        """Get the open long position."""
        for p in self.state.positions:
            if p.is_open and p.side == "long":
                return p
        return None
        
    async def _open_position(self, side: str, price: float):
        """Open a new position."""
        try:
            # Calculate position size
            risk_amount = self.state.equity * self.config.risk_per_trade
            quantity = risk_amount / price
            
            # Minimum trade amount check
            trade_value = quantity * price
            if trade_value < self.config.min_trade_amount:
                logger.info(f"Trade value {trade_value:.2f} below minimum {self.config.min_trade_amount}")
                return
                
            # Calculate stop loss and take profit
            if side == "long":
                stop_loss = price * (1 - self.config.stop_loss_pct)
                take_profit = price * (1 + self.config.take_profit_pct)
            else:
                stop_loss = price * (1 + self.config.stop_loss_pct)
                take_profit = price * (1 - self.config.take_profit_pct)
                
            # Create position
            position = Position(
                symbol=self.config.symbol,
                side=side,
                quantity=quantity,
                entry_price=price,
                avg_price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                entry_time=datetime.now()
            )
            
            # Execute order (paper trading)
            if self.config.paper_trading:
                # Paper trading - just record the position
                position.is_open = True
                self.state.positions.append(position)
                
                # Update balance
                self.state.available_balance -= trade_value
                
                logger.info(f"Paper trade: Opened {side} position for {quantity:.4f} {self.config.symbol} at ${price:.4f}")
                
            else:
                # Real trading would place actual orders here
                logger.warning("Real trading execution not implemented")
                return
                
            # Update state
            self.state.daily_trades += 1
            self.state.last_trade_time = datetime.now()
            
        except Exception as e:
            logger.error(f"Error opening position: {e}")
            
    async def _close_position(self, position: Position, reason: str, price: float):
        """Close an existing position."""
        try:
            if not position.is_open:
                return
                
            # Calculate P&L
            if position.side == "long":
                pnl = position.quantity * (price - position.avg_price)
            else:
                pnl = position.quantity * (position.avg_price - price)
                
            pnl_pct = pnl / (position.quantity * position.avg_price)
            
            # Update position
            position.exit_price = price
            position.exit_time = datetime.now()
            position.pnl = pnl
            position.pnl_pct = pnl_pct
            position.exit_reason = reason
            position.is_open = False
            
            # Execute order (paper trading)
            if self.config.paper_trading:
                # Paper trading - just record the trade
                trade_value = position.quantity * price
                self.state.available_balance += trade_value
                self.state.balance += pnl
                
                logger.info(f"Paper trade: Closed {position.side} position at ${price:.4f}, P&L: ${pnl:.2f} ({pnl_pct*100:.2f}%)")
                
            else:
                # Real trading would place actual orders here
                logger.warning("Real trading execution not implemented")
                return
                
            # Update statistics
            self.state.total_trades += 1
            self.state.total_pnl += pnl
            self.state.daily_pnl += pnl
            
            if pnl > 0:
                self.state.winning_trades += 1
                self.state.consecutive_losses = 0
            else:
                self.state.losing_trades += 1
                self.state.consecutive_losses += 1
                
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            
    def _update_state(self):
        """Update trading state."""
        # Reset daily counters at start of new day
        now = datetime.now()
        if (self.state.last_trade_time and 
            now.date() != self.state.last_trade_time.date()):
            self.state.daily_pnl = 0.0
            self.state.daily_trades = 0
            
        # Update equity
        if self.state.current_price > 0:
            self.state.update_equity(self.state.current_price)
            
    def _save_state(self):
        """Save trading state to file."""
        try:
            import json
            
            state_data = {
                'balance': self.state.balance,
                'equity': self.state.equity,
                'total_trades': self.state.total_trades,
                'winning_trades': self.state.winning_trades,
                'losing_trades': self.state.losing_trades,
                'total_pnl': self.state.total_pnl,
                'max_drawdown': self.state.max_drawdown,
                'consecutive_losses': self.state.consecutive_losses,
                'emergency_stop': self.state.emergency_stop,
                'last_update': datetime.now().isoformat()
            }
            
            with open(self.config.state_file, 'w') as f:
                json.dump(state_data, f, indent=2)
                
        except Exception as e:
            logger.warning(f"Error saving state: {e}")
            
    async def _shutdown(self):
        """Shutdown trading system."""
        logger.info("Shutting down live trader...")
        
        # Close all open positions
        for position in self.state.positions:
            if position.is_open:
                await self._close_position(position, "shutdown", self.state.current_price)
                
        # Save final state
        if self.config.save_state:
            self._save_state()
            
        logger.info("Live trader shutdown complete")
        
    def get_status(self) -> Dict[str, Any]:
        """Get current trading status."""
        return {
            'is_running': self.is_running,
            'balance': self.state.balance,
            'equity': self.state.equity,
            'unrealized_pnl': self.state.unrealized_pnl,
            'total_trades': self.state.total_trades,
            'win_rate': self.state.win_rate,
            'total_pnl': self.state.total_pnl,
            'max_drawdown': self.state.max_drawdown,
            'open_positions': len([p for p in self.state.positions if p.is_open]),
            'emergency_stop': self.state.emergency_stop,
            'consecutive_losses': self.state.consecutive_losses,
            'current_price': self.state.current_price,
            'last_update': self.state.last_data_update.isoformat() if self.state.last_data_update else None
        }


def create_live_trader(config: Dict[str, Any]) -> LiveTrader:
    """Factory function to create live trader from config."""
    live_config = LiveTradingConfig(**config)
    return LiveTrader(live_config)


async def run_paper_trading(strategy_name: str,
                           symbol: str = "BTC/USDT",
                           timeframe: str = "15m",
                           initial_capital: float = 10000.0,
                           duration_hours: int = 24) -> Dict[str, Any]:
    """Run paper trading for specified duration."""
    config = LiveTradingConfig(
        paper_trading=True,
        symbol=symbol,
        timeframe=timeframe,
        initial_capital=initial_capital,
        strategy_name=strategy_name
    )
    
    trader = LiveTrader(config)
    
    # Run for specified duration
    start_time = datetime.now()
    end_time = start_time + timedelta(hours=duration_hours)
    
    logger.info(f"Starting paper trading for {duration_hours} hours")
    
    try:
        # Start trading in background
        task = asyncio.create_task(trader.start_trading())
        
        # Wait for duration or completion
        while datetime.now() < end_time and trader.is_running:
            await asyncio.sleep(60)  # Check every minute
            
        # Stop trading
        trader.stop_trading()
        await task
        
    except KeyboardInterrupt:
        trader.stop_trading()
        
    return trader.get_status()