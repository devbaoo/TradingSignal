"""
Risk management module.
Handles position sizing, stop-loss/take-profit management, and portfolio risk controls.
"""

import warnings
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .utils import get_logger, safe_divide

warnings.filterwarnings("ignore", category=RuntimeWarning)
logger = get_logger(__name__)


@dataclass
class Position:
    """Represents a trading position."""
    symbol: str
    side: str  # 'long' or 'short'
    size: float  # Position size (number of shares/contracts)
    entry_price: float
    entry_time: datetime
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    trailing_stop: Optional[float] = None
    atr_at_entry: Optional[float] = None
    risk_amount: Optional[float] = None
    
    @property
    def market_value(self) -> float:
        """Calculate market value of position."""
        return self.size * self.entry_price
    
    def unrealized_pnl(self, current_price: float) -> float:
        """Calculate unrealized P&L."""
        if self.side == 'long':
            return self.size * (current_price - self.entry_price)
        else:  # short
            return self.size * (self.entry_price - current_price)
    
    def unrealized_pnl_pct(self, current_price: float) -> float:
        """Calculate unrealized P&L as percentage."""
        pnl = self.unrealized_pnl(current_price)
        return safe_divide(pnl, self.market_value)


@dataclass
class Trade:
    """Represents a completed trade."""
    symbol: str
    side: str
    size: float
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    pnl: float
    pnl_pct: float
    fees: float
    exit_reason: str  # 'take_profit', 'stop_loss', 'trailing_stop', 'signal', 'manual'
    holding_period_hours: float


class RiskManager:
    """
    Comprehensive risk management system.
    
    Handles:
    - Position sizing
    - Stop-loss and take-profit management
    - Portfolio risk limits
    - Drawdown monitoring
    - Risk metrics calculation
    """
    
    def __init__(self, config: Dict):
        """
        Initialize risk manager.
        
        Args:
            config: Risk management configuration
        """
        self.config = config
        self.risk_config = config.get("risk", {})
        
        # Position sizing settings
        self.position_sizing_method = self.risk_config.get("position_sizing", "fixed_fractional")
        self.risk_per_trade = self.risk_config.get("risk_per_trade", 0.02)
        self.fixed_amount = self.risk_config.get("fixed_amount", 1000)
        self.atr_position_mult = self.risk_config.get("atr_position_mult", 10)
        
        # Portfolio limits
        self.max_positions = self.risk_config.get("max_positions", 3)
        self.max_risk_per_symbol = self.risk_config.get("max_risk_per_symbol", 0.05)
        self.max_daily_risk = self.risk_config.get("max_daily_risk", 0.10)
        self.max_drawdown = self.risk_config.get("max_drawdown", 0.20)
        
        # Circuit breakers
        self.daily_loss_limit = self.risk_config.get("daily_loss_limit", 0.05)
        self.consecutive_loss_limit = self.risk_config.get("consecutive_losses", 5)
        
        # State tracking
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.equity_curve = []
        self.initial_capital = 0.0
        self.current_capital = 0.0
        self.peak_capital = 0.0
        
        # Risk state
        self.trading_enabled = True
        self.risk_override = False
        
        logger.info("Risk manager initialized")
    
    def set_initial_capital(self, capital: float) -> None:
        """Set initial trading capital."""
        self.initial_capital = capital
        self.current_capital = capital
        self.peak_capital = capital
        self.equity_curve = [capital]
        logger.info(f"Initial capital set to: ${capital:,.2f}")
    
    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        side: str = 'long',
        atr: Optional[float] = None
    ) -> Tuple[float, Dict]:
        """
        Calculate optimal position size based on risk management rules.
        
        Args:
            symbol: Trading symbol
            entry_price: Planned entry price
            stop_loss: Stop loss price
            side: Position side ('long' or 'short')
            atr: Average True Range value
            
        Returns:
            Tuple of (position_size, risk_info)
        """
        risk_info = {
            "method": self.position_sizing_method,
            "risk_per_trade": self.risk_per_trade,
            "risk_amount": 0.0,
            "stop_distance": 0.0,
            "warnings": []
        }
        
        # Calculate stop distance
        if side == 'long':
            stop_distance = entry_price - stop_loss
        else:  # short
            stop_distance = stop_loss - entry_price
        
        stop_distance = abs(stop_distance)
        risk_info["stop_distance"] = stop_distance
        
        if stop_distance <= 0:
            risk_info["warnings"].append("Invalid stop loss: no stop distance")
            return 0.0, risk_info
        
        # Calculate position size based on method
        if self.position_sizing_method == "fixed_fractional":
            risk_amount = self.current_capital * self.risk_per_trade
            position_size = safe_divide(risk_amount, stop_distance)
            
        elif self.position_sizing_method == "fixed_amount":
            position_size = safe_divide(self.fixed_amount, entry_price)
            risk_amount = position_size * stop_distance
            
        elif self.position_sizing_method == "atr_based":
            if atr is None or atr <= 0:
                risk_info["warnings"].append("ATR required for ATR-based sizing")
                return 0.0, risk_info
            
            risk_amount = self.current_capital * self.risk_per_trade
            atr_stop_distance = atr * 2.0  # Assume 2x ATR stop
            position_size = safe_divide(risk_amount, atr_stop_distance)
            
        elif self.position_sizing_method == "volatility_adjusted":
            if atr is None or atr <= 0:
                risk_info["warnings"].append("ATR required for volatility-adjusted sizing")
                return 0.0, risk_info
            
            # Adjust position size based on volatility
            vol_factor = atr / entry_price  # ATR as % of price
            base_risk = self.current_capital * self.risk_per_trade
            adjusted_risk = base_risk * (0.5 / max(vol_factor, 0.005))  # Inverse vol scaling
            position_size = safe_divide(adjusted_risk, stop_distance)
            
        else:
            # Default to fixed fractional
            risk_amount = self.current_capital * self.risk_per_trade
            position_size = safe_divide(risk_amount, stop_distance)
        
        # Apply risk limits
        position_size, limit_info = self._apply_position_limits(
            symbol, position_size, entry_price, risk_amount
        )
        
        risk_info.update(limit_info)
        risk_info["risk_amount"] = position_size * stop_distance
        
        return max(0.0, position_size), risk_info
    
    def _apply_position_limits(
        self,
        symbol: str,
        position_size: float,
        entry_price: float,
        risk_amount: float
    ) -> Tuple[float, Dict]:
        """Apply position size limits."""
        limit_info = {"limits_applied": [], "final_size": position_size}
        original_size = position_size
        
        # Maximum position value limit
        position_value = position_size * entry_price
        max_position_value = self.current_capital * self.max_risk_per_symbol
        
        if position_value > max_position_value:
            position_size = safe_divide(max_position_value, entry_price)
            limit_info["limits_applied"].append("max_position_value")
        
        # Check existing exposure to symbol
        existing_position = self.positions.get(symbol)
        if existing_position:
            existing_value = existing_position.market_value
            total_value = existing_value + (position_size * entry_price)
            
            if total_value > max_position_value:
                allowed_additional = max_position_value - existing_value
                position_size = max(0, safe_divide(allowed_additional, entry_price))
                limit_info["limits_applied"].append("existing_exposure")
        
        # Daily risk limit
        if risk_amount > self.current_capital * self.max_daily_risk:
            max_risk = self.current_capital * self.max_daily_risk
            risk_ratio = safe_divide(max_risk, risk_amount)
            position_size *= risk_ratio
            limit_info["limits_applied"].append("daily_risk_limit")
        
        # Maximum number of positions
        if len(self.positions) >= self.max_positions and symbol not in self.positions:
            position_size = 0.0
            limit_info["limits_applied"].append("max_positions")
        
        # Log significant reductions
        if position_size < original_size * 0.8:
            size_reduction = (1 - position_size / original_size) * 100
            logger.warning(f"Position size reduced by {size_reduction:.1f}% due to risk limits")
        
        limit_info["final_size"] = position_size
        return position_size, limit_info
    
    def calculate_stop_take_levels(
        self,
        entry_price: float,
        atr: float,
        side: str,
        stop_atr_mult: float = 2.0,
        take_atr_mult: float = 3.0
    ) -> Tuple[float, float]:
        """
        Calculate stop-loss and take-profit levels.
        
        Args:
            entry_price: Entry price
            atr: Average True Range
            side: Position side ('long' or 'short')
            stop_atr_mult: ATR multiplier for stop loss
            take_atr_mult: ATR multiplier for take profit
            
        Returns:
            Tuple of (stop_loss, take_profit)
        """
        atr_stop = atr * stop_atr_mult
        atr_take = atr * take_atr_mult
        
        if side == 'long':
            stop_loss = entry_price - atr_stop
            take_profit = entry_price + atr_take
        else:  # short
            stop_loss = entry_price + atr_stop
            take_profit = entry_price - atr_take
        
        return stop_loss, take_profit
    
    def add_position(
        self,
        symbol: str,
        side: str,
        size: float,
        entry_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        atr: Optional[float] = None
    ) -> bool:
        """
        Add a new position to the portfolio.
        
        Args:
            symbol: Trading symbol
            side: Position side ('long' or 'short')
            size: Position size
            entry_price: Entry price
            stop_loss: Stop loss level
            take_profit: Take profit level
            atr: ATR at entry
            
        Returns:
            True if position was added successfully
        """
        # Check if trading is enabled
        if not self.trading_enabled:
            logger.warning("Trading is disabled due to risk limits")
            return False
        
        # Check position limits
        if len(self.positions) >= self.max_positions:
            logger.warning(f"Maximum positions limit reached: {self.max_positions}")
            return False
        
        # Create position
        position = Position(
            symbol=symbol,
            side=side,
            size=size,
            entry_price=entry_price,
            entry_time=datetime.now(),
            stop_loss=stop_loss,
            take_profit=take_profit,
            atr_at_entry=atr,
            risk_amount=size * abs(entry_price - (stop_loss or entry_price))
        )
        
        # Add to positions
        self.positions[symbol] = position
        
        # Update capital (assume immediate execution)
        position_value = size * entry_price
        self.current_capital -= position_value  # Reduce available capital
        
        logger.info(f"Added {side} position: {symbol} @ ${entry_price:.4f}, size: {size:.4f}")
        return True
    
    def close_position(
        self,
        symbol: str,
        exit_price: float,
        exit_reason: str = 'signal',
        fees: float = 0.0
    ) -> Optional[Trade]:
        """
        Close a position and record the trade.
        
        Args:
            symbol: Trading symbol
            exit_price: Exit price
            exit_reason: Reason for exit
            fees: Trading fees
            
        Returns:
            Trade object if position was closed
        """
        if symbol not in self.positions:
            logger.warning(f"No position found for {symbol}")
            return None
        
        position = self.positions[symbol]
        
        # Calculate P&L
        pnl = position.unrealized_pnl(exit_price) - fees
        pnl_pct = position.unrealized_pnl_pct(exit_price)
        
        # Create trade record
        holding_period = (datetime.now() - position.entry_time).total_seconds() / 3600
        
        trade = Trade(
            symbol=symbol,
            side=position.side,
            size=position.size,
            entry_price=position.entry_price,
            exit_price=exit_price,
            entry_time=position.entry_time,
            exit_time=datetime.now(),
            pnl=pnl,
            pnl_pct=pnl_pct,
            fees=fees,
            exit_reason=exit_reason,
            holding_period_hours=holding_period
        )
        
        # Update capital
        self.current_capital += position.size * exit_price  # Return capital + P&L
        self.daily_pnl += pnl
        
        # Track consecutive losses
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        
        # Update peak capital
        if self.current_capital > self.peak_capital:
            self.peak_capital = self.current_capital
        
        # Add to trades history
        self.trades.append(trade)
        
        # Remove position
        del self.positions[symbol]
        
        logger.info(
            f"Closed {position.side} position: {symbol} @ ${exit_price:.4f}, "
            f"P&L: ${pnl:.2f} ({pnl_pct*100:.2f}%), reason: {exit_reason}"
        )
        
        return trade
    
    def update_trailing_stops(self, market_data: Dict[str, Dict]) -> List[str]:
        """
        Update trailing stop levels for all positions.
        
        Args:
            market_data: Dictionary with current market data for each symbol
            
        Returns:
            List of symbols with updated stops
        """
        updated_symbols = []
        
        for symbol, position in self.positions.items():
            if symbol not in market_data:
                continue
            
            current_price = market_data[symbol].get('close')
            atr = market_data[symbol].get('atr', position.atr_at_entry)
            
            if current_price is None or atr is None:
                continue
            
            # Calculate new trailing stop
            trailing_distance = atr * self.risk_config.get("trailing_stop_atr_mult", 1.0)
            
            if position.side == 'long':
                new_stop = current_price - trailing_distance
                if position.trailing_stop is None or new_stop > position.trailing_stop:
                    position.trailing_stop = new_stop
                    updated_symbols.append(symbol)
                    
            else:  # short
                new_stop = current_price + trailing_distance
                if position.trailing_stop is None or new_stop < position.trailing_stop:
                    position.trailing_stop = new_stop
                    updated_symbols.append(symbol)
        
        return updated_symbols
    
    def check_risk_limits(self) -> Dict[str, bool]:
        """
        Check all risk limit conditions.
        
        Returns:
            Dictionary with risk limit status
        """
        risk_status = {
            "trading_enabled": self.trading_enabled,
            "daily_loss_limit": False,
            "max_drawdown": False,
            "consecutive_losses": False,
            "max_positions": False
        }
        
        # Daily loss limit
        daily_loss_pct = safe_divide(abs(self.daily_pnl), self.initial_capital)
        if self.daily_pnl < 0 and daily_loss_pct > self.daily_loss_limit:
            risk_status["daily_loss_limit"] = True
            logger.warning(f"Daily loss limit exceeded: {daily_loss_pct*100:.2f}%")
        
        # Maximum drawdown
        current_drawdown = safe_divide(self.peak_capital - self.current_capital, self.peak_capital)
        if current_drawdown > self.max_drawdown:
            risk_status["max_drawdown"] = True
            logger.warning(f"Maximum drawdown exceeded: {current_drawdown*100:.2f}%")
        
        # Consecutive losses
        if self.consecutive_losses >= self.consecutive_loss_limit:
            risk_status["consecutive_losses"] = True
            logger.warning(f"Consecutive loss limit exceeded: {self.consecutive_losses}")
        
        # Maximum positions
        if len(self.positions) >= self.max_positions:
            risk_status["max_positions"] = True
        
        # Disable trading if any critical limit is breached
        critical_limits = ["daily_loss_limit", "max_drawdown", "consecutive_losses"]
        if any(risk_status[limit] for limit in critical_limits) and not self.risk_override:
            self.trading_enabled = False
            logger.error("Trading disabled due to risk limit breach")
        
        return risk_status
    
    def get_portfolio_metrics(self) -> Dict:
        """
        Calculate current portfolio risk metrics.
        
        Returns:
            Dictionary with portfolio metrics
        """
        if not self.trades:
            return {"error": "No trades to analyze"}
        
        # Calculate equity curve
        equity = [self.initial_capital]
        running_capital = self.initial_capital
        
        for trade in self.trades:
            running_capital += trade.pnl
            equity.append(running_capital)
        
        equity_series = pd.Series(equity)
        returns = equity_series.pct_change().dropna()
        
        # Basic metrics
        total_return = (self.current_capital - self.initial_capital) / self.initial_capital
        n_trades = len(self.trades)
        
        if n_trades == 0:
            return {"error": "No completed trades"}
        
        # Win rate
        winning_trades = [t for t in self.trades if t.pnl > 0]
        win_rate = len(winning_trades) / n_trades
        
        # Profit factor
        total_wins = sum(t.pnl for t in winning_trades)
        total_losses = abs(sum(t.pnl for t in self.trades if t.pnl < 0))
        profit_factor = safe_divide(total_wins, total_losses)
        
        # Expectancy
        avg_win = safe_divide(total_wins, len(winning_trades)) if winning_trades else 0
        avg_loss = safe_divide(total_losses, n_trades - len(winning_trades))
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        
        # Risk metrics
        if len(returns) > 1:
            sharpe_ratio = safe_divide(returns.mean(), returns.std()) * np.sqrt(252)
            max_dd = (equity_series.cummax() - equity_series).max() / equity_series.cummax().max()
        else:
            sharpe_ratio = 0
            max_dd = 0
        
        # Current drawdown
        current_dd = safe_divide(self.peak_capital - self.current_capital, self.peak_capital)
        
        return {
            "total_return": total_return,
            "total_return_pct": total_return * 100,
            "current_capital": self.current_capital,
            "peak_capital": self.peak_capital,
            "current_drawdown": current_dd,
            "current_drawdown_pct": current_dd * 100,
            "max_drawdown": max_dd,
            "max_drawdown_pct": max_dd * 100,
            "n_trades": n_trades,
            "win_rate": win_rate,
            "win_rate_pct": win_rate * 100,
            "profit_factor": profit_factor,
            "expectancy": expectancy,
            "sharpe_ratio": sharpe_ratio,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "consecutive_losses": self.consecutive_losses,
            "daily_pnl": self.daily_pnl,
            "open_positions": len(self.positions),
            "trading_enabled": self.trading_enabled
        }
    
    def reset_daily_pnl(self) -> None:
        """Reset daily P&L counter (call at end of each trading day)."""
        self.daily_pnl = 0.0
        logger.info("Daily P&L reset")
    
    def enable_risk_override(self, override: bool = True) -> None:
        """
        Enable/disable risk override (for emergency situations).
        
        Args:
            override: True to override risk limits
        """
        self.risk_override = override
        if override:
            self.trading_enabled = True
            logger.warning("Risk override ENABLED - trading limits bypassed")
        else:
            logger.info("Risk override disabled")
    
    def get_position_summary(self) -> pd.DataFrame:
        """
        Get summary of current positions.
        
        Returns:
            DataFrame with position details
        """
        if not self.positions:
            return pd.DataFrame()
        
        position_data = []
        for symbol, pos in self.positions.items():
            position_data.append({
                'symbol': symbol,
                'side': pos.side,
                'size': pos.size,
                'entry_price': pos.entry_price,
                'market_value': pos.market_value,
                'stop_loss': pos.stop_loss,
                'take_profit': pos.take_profit,
                'trailing_stop': pos.trailing_stop,
                'entry_time': pos.entry_time,
                'risk_amount': pos.risk_amount
            })
        
        return pd.DataFrame(position_data)
    
    def get_trades_summary(self) -> pd.DataFrame:
        """
        Get summary of completed trades.
        
        Returns:
            DataFrame with trade details
        """
        if not self.trades:
            return pd.DataFrame()
        
        trade_data = []
        for trade in self.trades:
            trade_data.append({
                'symbol': trade.symbol,
                'side': trade.side,
                'size': trade.size,
                'entry_price': trade.entry_price,
                'exit_price': trade.exit_price,
                'pnl': trade.pnl,
                'pnl_pct': trade.pnl_pct,
                'fees': trade.fees,
                'entry_time': trade.entry_time,
                'exit_time': trade.exit_time,
                'holding_hours': trade.holding_period_hours,
                'exit_reason': trade.exit_reason
            })
        
        return pd.DataFrame(trade_data)