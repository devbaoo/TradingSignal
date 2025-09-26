"""
Backtesting engine with vectorized calculations.
Supports fees, slippage, walk-forward analysis, and realistic fill logic.
"""

import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .risk import RiskManager, Trade
from .strategy.rule_based import BaseStrategy
from .utils import get_logger, safe_divide, Timer

warnings.filterwarnings("ignore", category=RuntimeWarning)
logger = get_logger(__name__)


@dataclass
class BacktestConfig:
    """Backtest configuration parameters."""
    initial_capital: float = 10000.0
    fee_rate: float = 0.001  # 0.1% per side
    slippage_model: str = "fixed"  # "fixed", "bps", "adaptive"
    slippage_bps: float = 2.0  # Basis points
    slippage_fixed: float = 0.0005  # Fixed percentage
    fill_method: str = "next_open"  # "next_open", "next_close", "intrabar"
    intrabar_fill: bool = True  # Use high/low for stop/limit fills
    commission_per_share: float = 0.0  # Additional per-share commission


@dataclass
class BacktestResults:
    """Backtest results container."""
    trades: List[Trade]
    equity_curve: pd.Series
    metrics: Dict
    portfolio_stats: Dict
    drawdown_curve: pd.Series
    returns: pd.Series
    benchmark_returns: Optional[pd.Series] = None
    config: Optional[BacktestConfig] = None


class BacktestEngine:
    """
    Vectorized backtesting engine.
    
    Features:
    - Realistic fill logic with slippage and fees
    - Intrabar stop-loss and take-profit execution
    - Walk-forward analysis capability
    - Portfolio-level risk management
    - Benchmark comparison
    """
    
    def __init__(self, config: BacktestConfig = None):
        """
        Initialize backtest engine.
        
        Args:
            config: Backtest configuration
        """
        self.config = config or BacktestConfig()
        self.trades = []
        self.equity_curve = []
        self.positions = {}  # symbol -> position info
        self.cash = self.config.initial_capital
        self.initial_capital = self.config.initial_capital
        
        # Risk manager
        risk_config = {
            "risk": {
                "position_sizing": "fixed_fractional",
                "risk_per_trade": 0.02,
                "max_positions": 5,
                "max_drawdown": 0.25
            }
        }
        self.risk_manager = RiskManager(risk_config)
        self.risk_manager.set_initial_capital(self.config.initial_capital)
        
    def run_backtest(
        self,
        data: pd.DataFrame,
        strategy: BaseStrategy,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> BacktestResults:
        """
        Run backtest on data with given strategy.
        
        Args:
            data: OHLCV DataFrame with indicators
            strategy: Trading strategy instance
            start_date: Start date for backtest
            end_date: End date for backtest
            
        Returns:
            BacktestResults object
        """
        with Timer("Backtest execution", logger):
            # Filter data by date range
            if start_date or end_date:
                data = self._filter_data_by_date(data, start_date, end_date)
            
            if len(data) < 50:
                raise ValueError("Insufficient data for backtesting")
            
            logger.info(f"Running backtest on {len(data)} periods from {data.index[0]} to {data.index[-1]}")
            
            # Prepare data with strategy indicators
            data = strategy.prepare_data(data)
            
            # Generate signals
            data = strategy.generate_signals(data)
            
            # Execute trades
            self._execute_vectorized_backtest(data, strategy)
            
            # Calculate results
            results = self._calculate_results(data)
            
        logger.info(f"Backtest completed: {len(self.trades)} trades, final capital: ${self.cash:.2f}")
        return results
    
    def _filter_data_by_date(
        self, 
        data: pd.DataFrame, 
        start_date: Optional[str], 
        end_date: Optional[str]
    ) -> pd.DataFrame:
        """Filter data by date range."""
        if start_date:
            start_dt = pd.to_datetime(start_date)
            if data.index.tz is not None:
                start_dt = start_dt.tz_localize(data.index.tz)
            data = data[data.index >= start_dt]
        if end_date:
            end_dt = pd.to_datetime(end_date)
            if data.index.tz is not None:
                end_dt = end_dt.tz_localize(data.index.tz)
            data = data[data.index <= end_dt]
        return data
    
    def _execute_vectorized_backtest(self, data: pd.DataFrame, strategy: BaseStrategy) -> None:
        """Execute the main backtesting loop."""
        # Reset state
        self.trades = []
        self.equity_curve = [self.config.initial_capital]
        self.positions = {}
        self.cash = self.config.initial_capital
        
        # Track portfolio value over time
        portfolio_values = []
        
        for i, (timestamp, row) in enumerate(data.iterrows()):
            # Update risk manager
            current_portfolio_value = self.cash + sum(
                pos["size"] * row["close"] for pos in self.positions.values()
            )
            
            # Check for exit conditions first (stops and take profits)
            self._check_exit_conditions(i, row, data)
            
            # Check for new entry signals
            if row.get("Signal", 0) != 0 and len(self.positions) < 5:  # Max 5 positions
                self._handle_entry_signal(i, row, data, strategy)
            
            # Update trailing stops
            self._update_trailing_stops(row)
            
            # Record portfolio value
            portfolio_values.append(current_portfolio_value)
            
            # Log progress periodically
            if i % 1000 == 0:
                logger.debug(f"Processed {i}/{len(data)} periods")
        
        self.equity_curve = pd.Series(portfolio_values, index=data.index)
    
    def _check_exit_conditions(self, i: int, row: pd.Series, data: pd.DataFrame) -> None:
        """Check exit conditions for all open positions."""
        symbols_to_close = []
        
        for symbol, position in self.positions.items():
            # Intrabar stop/take profit check
            if self.config.intrabar_fill:
                exit_info = self._check_intrabar_exits(position, row)
                if exit_info:
                    price, reason = exit_info
                    self._close_position(symbol, price, reason, row)
                    symbols_to_close.append(symbol)
                    continue
            
            # Signal-based exit
            signal_exit = self._check_signal_exit(position, row, i, data)
            if signal_exit:
                exit_price = self._calculate_fill_price(row, "sell" if position["side"] == "long" else "buy")
                self._close_position(symbol, exit_price, "signal", row)
                symbols_to_close.append(symbol)
        
        # Remove closed positions
        for symbol in symbols_to_close:
            del self.positions[symbol]
    
    def _check_intrabar_exits(self, position: Dict, row: pd.Series) -> Optional[Tuple[float, str]]:
        """Check for intrabar stop-loss and take-profit execution."""
        if position["side"] == "long":
            # Check stop loss
            if position["stop_loss"] and row["low"] <= position["stop_loss"]:
                return position["stop_loss"], "stop_loss"
            
            # Check take profit
            if position["take_profit"] and row["high"] >= position["take_profit"]:
                return position["take_profit"], "take_profit"
                
            # Check trailing stop
            if position.get("trailing_stop") and row["low"] <= position["trailing_stop"]:
                return position["trailing_stop"], "trailing_stop"
        
        else:  # short position
            # Check stop loss
            if position["stop_loss"] and row["high"] >= position["stop_loss"]:
                return position["stop_loss"], "stop_loss"
            
            # Check take profit
            if position["take_profit"] and row["low"] <= position["take_profit"]:
                return position["take_profit"], "take_profit"
                
            # Check trailing stop
            if position.get("trailing_stop") and row["high"] >= position["trailing_stop"]:
                return position["trailing_stop"], "trailing_stop"
        
        return None
    
    def _check_signal_exit(self, position: Dict, row: pd.Series, i: int, data: pd.DataFrame) -> bool:
        """Check for signal-based exit conditions."""
        # Simple signal reversal exit
        current_signal = row.get("Signal", 0)
        
        if position["side"] == "long" and current_signal < 0:
            return True
        elif position["side"] == "short" and current_signal > 0:
            return True
        
        # Strategy-specific exit signals
        if position["side"] == "long" and row.get("Signal_Exit_Long", 0):
            return True
        elif position["side"] == "short" and row.get("Signal_Exit_Short", 0):
            return True
        
        return False
    
    def _handle_entry_signal(self, i: int, row: pd.Series, data: pd.DataFrame, strategy: BaseStrategy) -> None:
        """Handle entry signal and create new position."""
        signal = row["Signal"]
        
        if signal == 0:
            return
        
        symbol = "SYMBOL"  # Would be actual symbol in multi-asset backtest
        side = "long" if signal > 0 else "short"
        
        # Get entry price
        entry_price = self._calculate_fill_price(row, "buy" if side == "long" else "sell")
        
        # Calculate stop loss and take profit
        atr = row.get("ATR_14", row["close"] * 0.02)  # Default to 2% if no ATR
        
        if side == "long":
            stop_loss = entry_price - (atr * strategy.stop_loss_atr_mult)
            take_profit = entry_price + (atr * strategy.take_profit_atr_mult)
        else:
            stop_loss = entry_price + (atr * strategy.stop_loss_atr_mult)
            take_profit = entry_price - (atr * strategy.take_profit_atr_mult)
        
        # Calculate position size
        position_size, risk_info = self.risk_manager.calculate_position_size(
            symbol, entry_price, stop_loss, side, atr
        )
        
        if position_size <= 0:
            logger.debug(f"Position size too small or risk limits exceeded: {risk_info}")
            return
        
        # Calculate required capital
        required_capital = position_size * entry_price
        fees = self._calculate_fees(required_capital)
        slippage_cost = self._calculate_slippage(entry_price, required_capital)
        
        total_cost = required_capital + fees + slippage_cost
        
        if total_cost > self.cash:
            logger.debug(f"Insufficient capital for trade: required ${total_cost:.2f}, available ${self.cash:.2f}")
            return
        
        # Create position
        position = {
            "symbol": symbol,
            "side": side,
            "size": position_size,
            "entry_price": entry_price,
            "entry_time": row.name,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "trailing_stop": None,
            "atr_at_entry": atr,
            "fees_paid": fees,
            "slippage_cost": slippage_cost
        }
        
        # Update cash and add position
        self.cash -= total_cost
        self.positions[symbol] = position
        
        logger.debug(f"Opened {side} position at ${entry_price:.4f}, size: {position_size:.4f}")
    
    def _close_position(self, symbol: str, exit_price: float, exit_reason: str, row: pd.Series) -> None:
        """Close a position and record the trade."""
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        
        # Calculate proceeds
        proceeds = position["size"] * exit_price
        fees = self._calculate_fees(proceeds)
        slippage_cost = self._calculate_slippage(exit_price, proceeds)
        
        net_proceeds = proceeds - fees - slippage_cost
        
        # Calculate P&L
        if position["side"] == "long":
            gross_pnl = proceeds - (position["size"] * position["entry_price"])
        else:  # short
            gross_pnl = (position["size"] * position["entry_price"]) - proceeds
        
        total_fees = position["fees_paid"] + fees
        total_slippage = position["slippage_cost"] + slippage_cost
        net_pnl = gross_pnl - total_fees - total_slippage
        
        pnl_pct = safe_divide(net_pnl, position["size"] * position["entry_price"])
        
        # Create trade record
        holding_period = (row.name - position["entry_time"]).total_seconds() / 3600
        
        trade = Trade(
            symbol=symbol,
            side=position["side"],
            size=position["size"],
            entry_price=position["entry_price"],
            exit_price=exit_price,
            entry_time=position["entry_time"],
            exit_time=row.name,
            pnl=net_pnl,
            pnl_pct=pnl_pct,
            fees=total_fees,
            exit_reason=exit_reason,
            holding_period_hours=holding_period
        )
        
        self.trades.append(trade)
        
        # Update cash
        self.cash += net_proceeds
        
        logger.debug(f"Closed {position['side']} position at ${exit_price:.4f}, P&L: ${net_pnl:.2f}")
    
    def _update_trailing_stops(self, row: pd.Series) -> None:
        """Update trailing stops for all positions."""
        for position in self.positions.values():
            if not position.get("atr_at_entry"):
                continue
            
            trailing_distance = position["atr_at_entry"] * 1.0  # 1x ATR trailing
            current_price = row["close"]
            
            if position["side"] == "long":
                new_stop = current_price - trailing_distance
                if position["trailing_stop"] is None or new_stop > position["trailing_stop"]:
                    position["trailing_stop"] = new_stop
            else:  # short
                new_stop = current_price + trailing_distance
                if position["trailing_stop"] is None or new_stop < position["trailing_stop"]:
                    position["trailing_stop"] = new_stop
    
    def _calculate_fill_price(self, row: pd.Series, action: str) -> float:
        """Calculate realistic fill price based on fill method."""
        if self.config.fill_method == "next_open":
            # Would use next period's open in real implementation
            return row["open"]
        elif self.config.fill_method == "next_close":
            return row["close"]
        elif self.config.fill_method == "intrabar":
            # Use OHLC for more realistic fills
            if action == "buy":
                return row["close"] + (row["high"] - row["close"]) * 0.1  # Slightly worse fill
            else:
                return row["close"] - (row["close"] - row["low"]) * 0.1
        
        return row["close"]
    
    def _calculate_fees(self, trade_value: float) -> float:
        """Calculate trading fees."""
        return trade_value * self.config.fee_rate
    
    def _calculate_slippage(self, price: float, trade_value: float) -> float:
        """Calculate slippage cost."""
        if self.config.slippage_model == "fixed":
            return trade_value * self.config.slippage_fixed
        elif self.config.slippage_model == "bps":
            return trade_value * (self.config.slippage_bps / 10000.0)
        elif self.config.slippage_model == "adaptive":
            # Could use volume, volatility, etc. for adaptive slippage
            return trade_value * 0.0002  # 2 bps default
        
        return 0.0
    
    def _calculate_results(self, data: pd.DataFrame) -> BacktestResults:
        """Calculate backtest results and metrics."""
        # Final portfolio value
        final_value = self.cash + sum(
            pos["size"] * data["close"].iloc[-1] for pos in self.positions.values()
        )
        
        # Create equity curve
        equity_curve = self.equity_curve.copy()
        
        if len(equity_curve) != len(data):
            # Pad equity curve if needed
            while len(equity_curve) < len(data):
                equity_curve = pd.concat([equity_curve, pd.Series([equity_curve.iloc[-1]])])
            equity_curve.index = data.index
        
        # Calculate returns
        returns = equity_curve.pct_change().dropna()
        
        # Calculate drawdown
        peak = equity_curve.cummax()
        drawdown = (equity_curve - peak) / peak
        
        # Calculate metrics
        metrics = self._calculate_performance_metrics(equity_curve, returns, data)
        
        # Portfolio stats
        portfolio_stats = {
            "initial_capital": self.config.initial_capital,
            "final_value": final_value,
            "total_return": (final_value - self.config.initial_capital) / self.config.initial_capital,
            "n_trades": len(self.trades),
            "open_positions": len(self.positions),
            "cash_remaining": self.cash
        }
        
        return BacktestResults(
            trades=self.trades,
            equity_curve=equity_curve,
            metrics=metrics,
            portfolio_stats=portfolio_stats,
            drawdown_curve=drawdown,
            returns=returns,
            config=self.config
        )
    
    def _calculate_performance_metrics(
        self, 
        equity_curve: pd.Series, 
        returns: pd.Series, 
        data: pd.DataFrame
    ) -> Dict:
        """Calculate comprehensive performance metrics."""
        if len(self.trades) == 0:
            return {"error": "No trades to analyze"}
        
        # Basic metrics
        total_return = (equity_curve.iloc[-1] - equity_curve.iloc[0]) / equity_curve.iloc[0]
        
        # Annualized metrics
        days = (equity_curve.index[-1] - equity_curve.index[0]).days
        if days > 0:
            years = days / 365.25
            cagr = (equity_curve.iloc[-1] / equity_curve.iloc[0]) ** (1/years) - 1
        else:
            cagr = 0
        
        # Risk metrics
        if len(returns) > 1:
            annual_return = returns.mean() * 252
            annual_vol = returns.std() * np.sqrt(252)
            sharpe_ratio = safe_divide(annual_return, annual_vol) if annual_vol > 0 else 0
            
            # Downside deviation (Sortino)
            downside_returns = returns[returns < 0]
            downside_vol = downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 else 0
            sortino_ratio = safe_divide(annual_return, downside_vol) if downside_vol > 0 else 0
        else:
            sharpe_ratio = 0
            sortino_ratio = 0
            annual_vol = 0
        
        # Drawdown metrics
        peak = equity_curve.cummax()
        drawdown = (equity_curve - peak) / peak
        max_drawdown = drawdown.min()
        
        # Trade analysis
        winning_trades = [t for t in self.trades if t.pnl > 0]
        losing_trades = [t for t in self.trades if t.pnl < 0]
        
        win_rate = len(winning_trades) / len(self.trades)
        
        total_wins = sum(t.pnl for t in winning_trades)
        total_losses = abs(sum(t.pnl for t in losing_trades))
        profit_factor = safe_divide(total_wins, total_losses)
        
        avg_win = safe_divide(total_wins, len(winning_trades)) if winning_trades else 0
        avg_loss = safe_divide(total_losses, len(losing_trades)) if losing_trades else 0
        
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        
        # Risk-adjusted returns
        calmar_ratio = safe_divide(cagr, abs(max_drawdown)) if max_drawdown < 0 else 0
        
        return {
            "total_return": total_return,
            "cagr": cagr,
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "calmar_ratio": calmar_ratio,
            "max_drawdown": max_drawdown,
            "volatility": annual_vol,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "expectancy": expectancy,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "n_trades": len(self.trades),
            "avg_holding_period": np.mean([t.holding_period_hours for t in self.trades]) if self.trades else 0,
            "total_fees": sum(t.fees for t in self.trades),
        }
    
    def run_walk_forward_analysis(
        self,
        data: pd.DataFrame,
        strategy: BaseStrategy,
        train_periods: int = 252,
        test_periods: int = 63,
        step_size: int = 21
    ) -> Dict:
        """
        Run walk-forward analysis.
        
        Args:
            data: OHLCV DataFrame
            strategy: Trading strategy
            train_periods: Training window size
            test_periods: Test window size  
            step_size: Step size between windows
            
        Returns:
            Dictionary with walk-forward results
        """
        logger.info("Starting walk-forward analysis...")
        
        results = []
        total_periods = len(data)
        
        start_idx = 0
        while start_idx + train_periods + test_periods <= total_periods:
            # Define train and test windows
            train_end = start_idx + train_periods
            test_start = train_end
            test_end = test_start + test_periods
            
            train_data = data.iloc[start_idx:train_end]
            test_data = data.iloc[test_start:test_end]
            
            logger.info(f"Window {len(results)+1}: Train {train_data.index[0]} to {train_data.index[-1]}, "
                       f"Test {test_data.index[0]} to {test_data.index[-1]}")
            
            # Run backtest on test period
            # In practice, you might optimize parameters on train_data here
            test_result = self.run_backtest(test_data, strategy)
            
            results.append({
                "window": len(results) + 1,
                "train_start": train_data.index[0],
                "train_end": train_data.index[-1],
                "test_start": test_data.index[0],
                "test_end": test_data.index[-1],
                "test_result": test_result
            })
            
            start_idx += step_size
        
        # Aggregate results
        all_trades = []
        all_returns = []
        
        for result in results:
            all_trades.extend(result["test_result"].trades)
            all_returns.extend(result["test_result"].returns.tolist())
        
        # Calculate aggregate metrics
        if all_trades:
            win_rate = len([t for t in all_trades if t.pnl > 0]) / len(all_trades)
            total_pnl = sum(t.pnl for t in all_trades)
            avg_pnl_per_trade = total_pnl / len(all_trades)
        else:
            win_rate = 0
            total_pnl = 0
            avg_pnl_per_trade = 0
        
        summary = {
            "n_windows": len(results),
            "total_trades": len(all_trades),
            "overall_win_rate": win_rate,
            "total_pnl": total_pnl,
            "avg_pnl_per_trade": avg_pnl_per_trade,
            "windows": results
        }
        
        logger.info(f"Walk-forward analysis completed: {len(results)} windows, {len(all_trades)} total trades")
        
        return summary