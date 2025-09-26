"""
Advanced Backtesting with Walk-Forward Analysis and Purged Cross-Validation
Prevents overfitting and provides realistic performance estimates
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import warnings
from sklearn.model_selection import TimeSeriesSplit
import json


@dataclass
class BacktestConfig:
    """Enhanced backtest configuration"""
    initial_capital: float = 10000
    fee_rate: float = 0.0004  # 0.04% per side (Binance futures)
    slippage_bps: float = 2.0  # 2 basis points slippage
    order_rejection_rate: float = 0.02  # 2% order rejection
    partial_fill_rate: float = 0.05  # 5% partial fills
    max_drawdown_stop: float = 0.15  # Stop trading at 15% drawdown
    risk_free_rate: float = 0.02  # 2% annual risk-free rate
    
    # Walk-forward parameters
    train_periods: int = 252  # 252 days training
    test_periods: int = 63   # 63 days testing (3 months)
    reoptimization_frequency: int = 21  # Reoptimize every 21 days
    min_trades_per_period: int = 5  # Minimum trades needed
    
    # Purged CV parameters
    purge_days: int = 3  # Gap between train and test
    embargo_days: int = 1  # Embargo period after test


@dataclass
class WalkForwardResult:
    """Walk-forward analysis results"""
    period_start: datetime
    period_end: datetime
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    trades_count: int
    avg_trade_duration: float
    best_params: Dict[str, Any]
    is_profitable: bool


class RobustBacktester:
    """Professional backtesting with walk-forward analysis"""
    
    def __init__(self, config: BacktestConfig = None):
        self.config = config or BacktestConfig()
        self.results_history = []
        
    def run_walk_forward_analysis(self, 
                                 data: pd.DataFrame,
                                 strategy_class,
                                 param_grid: Dict[str, List]) -> List[WalkForwardResult]:
        """Run comprehensive walk-forward analysis"""
        
        results = []
        
        # Create time-based splits
        splits = self._create_purged_cv_splits(data)
        
        for i, (train_idx, test_idx) in enumerate(splits):
            print(f"Processing walk-forward period {i+1}/{len(splits)}")
            
            train_data = data.iloc[train_idx]
            test_data = data.iloc[test_idx]
            
            # Optimize parameters on training data
            best_params = self._optimize_parameters(
                train_data, strategy_class, param_grid
            )
            
            # Test on out-of-sample data
            strategy = strategy_class(**best_params)
            backtest_result = self._run_realistic_backtest(test_data, strategy)
            
            # Store results
            period_result = WalkForwardResult(
                period_start=test_data.index[0],
                period_end=test_data.index[-1],
                total_return=backtest_result['total_return'],
                sharpe_ratio=backtest_result['sharpe_ratio'],
                max_drawdown=backtest_result['max_drawdown'],
                win_rate=backtest_result['win_rate'],
                profit_factor=backtest_result['profit_factor'],
                trades_count=backtest_result['trades_count'],
                avg_trade_duration=backtest_result['avg_trade_duration'],
                best_params=best_params,
                is_profitable=backtest_result['total_return'] > 0
            )
            
            results.append(period_result)
            
        return results
    
    def _create_purged_cv_splits(self, data: pd.DataFrame) -> List[Tuple[np.ndarray, np.ndarray]]:
        """Create purged cross-validation splits to prevent data leakage"""
        
        splits = []
        n_samples = len(data)
        
        # Calculate split points
        train_size = self.config.train_periods
        test_size = self.config.test_periods
        purge_size = self.config.purge_days
        embargo_size = self.config.embargo_days
        
        start_idx = 0
        
        while start_idx + train_size + purge_size + test_size < n_samples:
            # Training period
            train_start = start_idx
            train_end = start_idx + train_size
            
            # Purge period (gap between train and test)
            purge_start = train_end
            purge_end = purge_start + purge_size
            
            # Test period
            test_start = purge_end
            test_end = test_start + test_size
            
            # Embargo period (after test)
            embargo_end = test_end + embargo_size
            
            train_idx = np.arange(train_start, train_end)
            test_idx = np.arange(test_start, test_end)
            
            splits.append((train_idx, test_idx))
            
            # Move window forward by reoptimization frequency
            start_idx += self.config.reoptimization_frequency
            
        return splits
    
    def _optimize_parameters(self, 
                           train_data: pd.DataFrame,
                           strategy_class,
                           param_grid: Dict[str, List]) -> Dict[str, Any]:
        """Optimize strategy parameters on training data"""
        
        best_params = None
        best_score = -np.inf
        
        # Generate parameter combinations
        param_combinations = self._generate_param_combinations(param_grid)
        
        for params in param_combinations:
            try:
                strategy = strategy_class(**params)
                result = self._run_realistic_backtest(train_data, strategy)
                
                # Use risk-adjusted return as optimization metric
                score = self._calculate_optimization_score(result)
                
                if score > best_score:
                    best_score = score
                    best_params = params
                    
            except Exception as e:
                print(f"Error testing params {params}: {e}")
                continue
        
        return best_params or param_grid  # Fallback to default params
    
    def _run_realistic_backtest(self, 
                               data: pd.DataFrame,
                               strategy) -> Dict[str, float]:
        """Run backtest with realistic market conditions"""
        
        trades = []
        equity_curve = [self.config.initial_capital]
        current_equity = self.config.initial_capital
        max_equity = self.config.initial_capital
        drawdown_start = 0
        max_drawdown = 0
        
        # Generate signals
        signals = strategy.generate_signals(data)
        
        for i, signal in enumerate(signals):
            if not signal:
                continue
                
            entry_price = signal.get('entry_price')
            exit_price = signal.get('exit_price')
            direction = signal.get('direction')
            
            if not all([entry_price, exit_price, direction]):
                continue
            
            # Apply realistic market conditions
            adjusted_entry = self._apply_market_impact(entry_price, 'entry')
            adjusted_exit = self._apply_market_impact(exit_price, 'exit')
            
            # Check for order rejection
            if np.random.random() < self.config.order_rejection_rate:
                continue  # Order rejected
            
            # Apply partial fills
            fill_ratio = 1.0
            if np.random.random() < self.config.partial_fill_rate:
                fill_ratio = np.random.uniform(0.7, 0.9)  # Partial fill
            
            # Calculate trade P&L
            if direction == 'LONG':
                raw_pnl = (adjusted_exit - adjusted_entry) / adjusted_entry
            else:  # SHORT
                raw_pnl = (adjusted_entry - adjusted_exit) / adjusted_entry
            
            # Apply fees and slippage
            total_fees = 2 * self.config.fee_rate  # Entry + exit fees
            slippage = self.config.slippage_bps / 10000  # Convert bps to decimal
            
            net_pnl = raw_pnl - total_fees - slippage
            
            # Calculate position size (2% risk per trade)
            position_size = current_equity * 0.02 * fill_ratio
            trade_pnl = position_size * net_pnl
            
            # Update equity
            current_equity += trade_pnl
            equity_curve.append(current_equity)
            
            # Track drawdown
            if current_equity > max_equity:
                max_equity = current_equity
                drawdown_start = len(equity_curve) - 1
            else:
                current_drawdown = (max_equity - current_equity) / max_equity
                max_drawdown = max(max_drawdown, current_drawdown)
            
            # Stop trading if max drawdown exceeded
            if max_drawdown >= self.config.max_drawdown_stop:
                print(f"Trading stopped due to max drawdown: {max_drawdown:.2%}")
                break
            
            # Store trade
            trades.append({
                'entry_price': adjusted_entry,
                'exit_price': adjusted_exit,
                'direction': direction,
                'pnl': trade_pnl,
                'pnl_pct': net_pnl,
                'fill_ratio': fill_ratio
            })
        
        # Calculate metrics
        if not trades:
            return self._empty_backtest_result()
        
        return self._calculate_backtest_metrics(trades, equity_curve)
    
    def _apply_market_impact(self, price: float, order_type: str) -> float:
        """Apply slippage and market impact"""
        
        # Market impact varies by order type
        impact_factor = self.config.slippage_bps / 10000
        
        if order_type == 'entry':
            # Worse fills on entry
            slippage = np.random.uniform(0.5, 1.5) * impact_factor
        else:
            # Slightly better fills on exit
            slippage = np.random.uniform(0.3, 1.0) * impact_factor
        
        # Random direction for slippage
        direction = np.random.choice([-1, 1])
        
        return price * (1 + direction * slippage)
    
    def _calculate_optimization_score(self, result: Dict) -> float:
        """Calculate score for parameter optimization"""
        
        # Penalize strategies with too few trades
        if result['trades_count'] < self.config.min_trades_per_period:
            return -999
        
        # Risk-adjusted score (Sharpe ratio with drawdown penalty)
        sharpe = result['sharpe_ratio']
        drawdown_penalty = result['max_drawdown'] * 2  # Heavy penalty for drawdown
        
        return sharpe - drawdown_penalty
    
    def _generate_param_combinations(self, param_grid: Dict[str, List]) -> List[Dict]:
        """Generate all parameter combinations"""
        
        if not param_grid:
            return [{}]
        
        combinations = []
        param_names = list(param_grid.keys())
        
        def backtrack(current_params, param_idx):
            if param_idx == len(param_names):
                combinations.append(current_params.copy())
                return
            
            param_name = param_names[param_idx]
            for value in param_grid[param_name]:
                current_params[param_name] = value
                backtrack(current_params, param_idx + 1)
                del current_params[param_name]
        
        backtrack({}, 0)
        return combinations
    
    def _calculate_backtest_metrics(self, 
                                   trades: List[Dict],
                                   equity_curve: List[float]) -> Dict[str, float]:
        """Calculate comprehensive backtest metrics"""
        
        if not trades:
            return self._empty_backtest_result()
        
        # Basic metrics
        total_return = (equity_curve[-1] - equity_curve[0]) / equity_curve[0]
        wins = [t for t in trades if t['pnl'] > 0]
        losses = [t for t in trades if t['pnl'] <= 0]
        
        win_rate = len(wins) / len(trades) if trades else 0
        
        avg_win = np.mean([t['pnl'] for t in wins]) if wins else 0
        avg_loss = abs(np.mean([t['pnl'] for t in losses])) if losses else 1
        profit_factor = (avg_win * len(wins)) / (avg_loss * len(losses)) if losses else 999
        
        # Calculate Sharpe ratio
        equity_returns = pd.Series(equity_curve).pct_change().dropna()
        excess_returns = equity_returns - (self.config.risk_free_rate / 252)  # Daily risk-free rate
        sharpe_ratio = np.sqrt(252) * excess_returns.mean() / excess_returns.std() if len(excess_returns) > 1 else 0
        
        # Calculate maximum drawdown
        equity_series = pd.Series(equity_curve)
        rolling_max = equity_series.expanding().max()
        drawdown = (equity_series - rolling_max) / rolling_max
        max_drawdown = abs(drawdown.min())
        
        # Average trade duration (assume daily data)
        avg_trade_duration = 1.0  # Placeholder for intraday strategies
        
        return {
            'total_return': total_return,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'trades_count': len(trades),
            'avg_trade_duration': avg_trade_duration,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'final_equity': equity_curve[-1]
        }
    
    def _empty_backtest_result(self) -> Dict[str, float]:
        """Return empty result when no trades"""
        return {
            'total_return': 0,
            'sharpe_ratio': 0,
            'max_drawdown': 0,
            'win_rate': 0,
            'profit_factor': 0,
            'trades_count': 0,
            'avg_trade_duration': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'final_equity': self.config.initial_capital
        }
    
    def generate_report(self, results: List[WalkForwardResult]) -> Dict:
        """Generate comprehensive walk-forward analysis report"""
        
        if not results:
            return {'error': 'No results to analyze'}
        
        # Aggregate metrics
        profitable_periods = [r for r in results if r.is_profitable]
        
        report = {
            'summary': {
                'total_periods': len(results),
                'profitable_periods': len(profitable_periods),
                'profitability_ratio': len(profitable_periods) / len(results),
                'avg_return': np.mean([r.total_return for r in results]),
                'avg_sharpe': np.mean([r.sharpe_ratio for r in results]),
                'avg_drawdown': np.mean([r.max_drawdown for r in results]),
                'avg_win_rate': np.mean([r.win_rate for r in results]),
                'total_trades': sum(r.trades_count for r in results)
            },
            'stability_metrics': {
                'return_volatility': np.std([r.total_return for r in results]),
                'sharpe_consistency': np.std([r.sharpe_ratio for r in results]),
                'worst_period_return': min(r.total_return for r in results),
                'best_period_return': max(r.total_return for r in results),
                'max_consecutive_losses': self._calculate_max_consecutive_losses(results)
            },
            'robustness_score': self._calculate_robustness_score(results),
            'recommendation': self._generate_recommendation(results)
        }
        
        return report
    
    def _calculate_max_consecutive_losses(self, results: List[WalkForwardResult]) -> int:
        """Calculate maximum consecutive losing periods"""
        consecutive_losses = 0
        max_consecutive = 0
        
        for result in results:
            if result.total_return <= 0:
                consecutive_losses += 1
                max_consecutive = max(max_consecutive, consecutive_losses)
            else:
                consecutive_losses = 0
        
        return max_consecutive
    
    def _calculate_robustness_score(self, results: List[WalkForwardResult]) -> float:
        """Calculate overall strategy robustness score (0-10)"""
        
        if not results:
            return 0
        
        # Component scores (0-1)
        profitability_score = len([r for r in results if r.is_profitable]) / len(results)
        avg_return = np.mean([r.total_return for r in results])
        return_score = min(1.0, max(0.0, avg_return * 10))  # 10% = score 1.0
        
        sharpe_scores = [max(0, min(1, r.sharpe_ratio / 2)) for r in results]  # Sharpe 2.0 = score 1.0
        avg_sharpe_score = np.mean(sharpe_scores)
        
        drawdown_scores = [max(0, 1 - r.max_drawdown * 5) for r in results]  # 20% DD = score 0
        avg_drawdown_score = np.mean(drawdown_scores)
        
        return_vol = np.std([r.total_return for r in results])
        consistency_score = max(0, 1 - return_vol * 5)  # 20% vol = score 0
        
        # Weighted average
        weights = [0.3, 0.2, 0.2, 0.2, 0.1]  # Profitability, return, sharpe, drawdown, consistency
        scores = [profitability_score, return_score, avg_sharpe_score, avg_drawdown_score, consistency_score]
        
        robustness = sum(w * s for w, s in zip(weights, scores)) * 10
        
        return round(robustness, 1)
    
    def _generate_recommendation(self, results: List[WalkForwardResult]) -> str:
        """Generate trading recommendation based on results"""
        
        robustness = self._calculate_robustness_score(results)
        profitability = len([r for r in results if r.is_profitable]) / len(results)
        
        if robustness >= 7.0 and profitability >= 0.7:
            return "STRONG BUY - Strategy shows consistent profitability and low risk"
        elif robustness >= 5.0 and profitability >= 0.6:
            return "BUY - Strategy is profitable but monitor risk management"
        elif robustness >= 3.0 and profitability >= 0.5:
            return "HOLD - Strategy shows mixed results, consider optimization"
        else:
            return "AVOID - Strategy shows poor performance and high risk"


def create_robust_backtester(config: BacktestConfig = None) -> RobustBacktester:
    """Factory function to create robust backtester"""
    return RobustBacktester(config)