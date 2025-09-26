"""
Parameter Optimization Module for Trading Insight.
Provides Bayesian optimization using Optuna for hyperparameter tuning.
"""

import json
import warnings
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Union

import numpy as np
import pandas as pd

try:
    import optuna
    from optuna.samplers import TPESampler
    from optuna.pruners import MedianPruner
    from optuna.visualization import (
        plot_optimization_history,
        plot_param_importances,
        plot_parallel_coordinate
    )
    OPTUNA_AVAILABLE = True
except ImportError:
    OPTUNA_AVAILABLE = False
    optuna = None

from .utils import get_logger, ensure_directory as ensure_dir
from .backtest import BacktestEngine, BacktestConfig
from .strategy.rule_based import create_strategy
from .data import DataLoader

logger = get_logger(__name__)

# Suppress Optuna logging
if OPTUNA_AVAILABLE:
    optuna.logging.set_verbosity(optuna.logging.WARNING)


@dataclass
class OptimizationConfig:
    """Configuration for parameter optimization."""
    
    # Optimization settings
    n_trials: int = 100
    timeout: Optional[int] = None  # seconds
    n_jobs: int = 1  # -1 for all cores
    sampler: str = "tpe"  # tpe, random, cmaes
    pruner: str = "median"  # median, hyperband, none
    
    # Objective settings
    objective: str = "sharpe_ratio"  # sharpe_ratio, total_return, profit_factor, win_rate
    direction: str = "maximize"  # maximize, minimize
    
    # Cross-validation settings
    cv_method: str = "walk_forward"  # walk_forward, time_series_split
    n_splits: int = 5
    test_size: float = 0.2
    
    # Parameter search space
    parameter_ranges: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # Study settings
    study_name: Optional[str] = None
    storage: Optional[str] = None  # sqlite:///example.db
    load_if_exists: bool = True
    
    # Output settings
    results_dir: str = "optimization_results"
    save_plots: bool = True
    save_study: bool = True
    
    def __post_init__(self):
        """Set default parameter ranges."""
        if not self.parameter_ranges:
            self.parameter_ranges = {
                "StrategyMomo": {
                    "ema_short": {"type": "int", "low": 5, "high": 20},
                    "ema_long": {"type": "int", "low": 20, "high": 100},
                    "rsi_period": {"type": "int", "low": 10, "high": 30},
                    "rsi_overbought": {"type": "float", "low": 65, "high": 85},
                    "rsi_oversold": {"type": "float", "low": 15, "high": 35},
                    "macd_fast": {"type": "int", "low": 8, "high": 16},
                    "macd_slow": {"type": "int", "low": 20, "high": 35},
                    "macd_signal": {"type": "int", "low": 5, "high": 12},
                    "risk_per_trade": {"type": "float", "low": 0.01, "high": 0.05},
                    "stop_loss_pct": {"type": "float", "low": 0.02, "high": 0.08},
                    "take_profit_pct": {"type": "float", "low": 0.04, "high": 0.15}
                },
                "StrategyMeanRev": {
                    "bb_period": {"type": "int", "low": 15, "high": 30},
                    "bb_std": {"type": "float", "low": 1.5, "high": 2.5},
                    "rsi_period": {"type": "int", "low": 10, "high": 25},
                    "rsi_overbought": {"type": "float", "low": 65, "high": 85},
                    "rsi_oversold": {"type": "float", "low": 15, "high": 35},
                    "volume_threshold": {"type": "float", "low": 1.0, "high": 2.0},
                    "risk_per_trade": {"type": "float", "low": 0.01, "high": 0.05},
                    "stop_loss_pct": {"type": "float", "low": 0.02, "high": 0.08},
                    "take_profit_pct": {"type": "float", "low": 0.04, "high": 0.15}
                }
            }


@dataclass
class OptimizationResults:
    """Results from parameter optimization."""
    
    study_name: str
    n_trials: int
    best_value: float
    best_params: Dict[str, Any]
    best_trial_number: int
    optimization_time: float
    
    # Study statistics
    completed_trials: int
    pruned_trials: int
    failed_trials: int
    
    # Parameter importance
    param_importances: Optional[Dict[str, float]] = None
    
    # Files created
    study_path: Optional[str] = None
    results_path: Optional[str] = None
    plots_dir: Optional[str] = None
    
    @property
    def summary(self) -> Dict[str, Any]:
        """Get summary of optimization results."""
        return {
            "study_name": self.study_name,
            "n_trials": self.n_trials,
            "best_value": self.best_value,
            "best_params": self.best_params,
            "completed_trials": self.completed_trials,
            "pruned_trials": self.pruned_trials,
            "failed_trials": self.failed_trials,
            "optimization_time": self.optimization_time
        }


class ParameterOptimizer:
    """Bayesian optimizer for trading strategy parameters."""
    
    def __init__(self, config: OptimizationConfig):
        if not OPTUNA_AVAILABLE:
            raise ImportError("Optuna is required for optimization. Install with: pip install optuna")
            
        self.config = config
        self.study = None
        self.data_loader = None
        self.backtest_engine = None
        
        # Initialize components
        self._initialize_study()
        
    def _initialize_study(self):
        """Initialize Optuna study."""
        # Create sampler
        if self.config.sampler == "tpe":
            sampler = TPESampler(seed=42)
        elif self.config.sampler == "random":
            sampler = optuna.samplers.RandomSampler(seed=42)
        elif self.config.sampler == "cmaes":
            sampler = optuna.samplers.CmaEsSampler(seed=42)
        else:
            raise ValueError(f"Unsupported sampler: {self.config.sampler}")
            
        # Create pruner
        if self.config.pruner == "median":
            pruner = MedianPruner(n_startup_trials=10, n_warmup_steps=5)
        elif self.config.pruner == "hyperband":
            pruner = optuna.pruners.HyperbandPruner()
        elif self.config.pruner == "none":
            pruner = optuna.pruners.NopPruner()
        else:
            raise ValueError(f"Unsupported pruner: {self.config.pruner}")
            
        # Create study
        study_name = self.config.study_name or f"optimization_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        self.study = optuna.create_study(
            study_name=study_name,
            direction=self.config.direction,
            sampler=sampler,
            pruner=pruner,
            storage=self.config.storage,
            load_if_exists=self.config.load_if_exists
        )
        
        logger.info(f"Initialized Optuna study: {study_name}")
        
    def optimize_strategy(self, 
                         strategy_name: str,
                         symbol: str, 
                         timeframe: str,
                         start_date: Optional[str] = None,
                         end_date: Optional[str] = None,
                         data_config: Optional[Dict] = None) -> OptimizationResults:
        """Optimize strategy parameters."""
        logger.info(f"Starting optimization for {strategy_name} on {symbol} {timeframe}")
        
        # Initialize data loader and backtest engine
        if data_config is None:
            data_config = {}
        self.data_loader = DataLoader(data_config)
        
        backtest_config = BacktestConfig(
            initial_capital=10000,
            fee_rate=0.001,
            slippage_bps=2.0
        )
        self.backtest_engine = BacktestEngine(backtest_config)
        
        # Load data
        logger.info("Loading market data...")
        df = self.data_loader.load_ohlcv(symbol, timeframe, start_date, end_date)
        
        # Get parameter ranges for strategy
        if strategy_name not in self.config.parameter_ranges:
            raise ValueError(f"No parameter ranges defined for strategy: {strategy_name}")
            
        param_ranges = self.config.parameter_ranges[strategy_name]
        
        # Define objective function
        def objective(trial):
            return self._objective_function(
                trial, df, strategy_name, param_ranges, start_date, end_date
            )
            
        # Run optimization
        start_time = pd.Timestamp.now()
        
        logger.info(f"Running optimization with {self.config.n_trials} trials...")
        self.study.optimize(
            objective,
            n_trials=self.config.n_trials,
            timeout=self.config.timeout,
            n_jobs=self.config.n_jobs,
            show_progress_bar=True
        )
        
        optimization_time = (pd.Timestamp.now() - start_time).total_seconds()
        
        # Analyze results
        results = self._analyze_results(optimization_time)
        
        # Save results
        if self.config.save_study or self.config.save_plots:
            self._save_results(results, strategy_name, symbol, timeframe)
            
        logger.info(f"Optimization completed in {optimization_time:.2f}s")
        logger.info(f"Best {self.config.objective}: {results.best_value:.4f}")
        logger.info(f"Best parameters: {results.best_params}")
        
        return results
        
    def _objective_function(self, 
                           trial, 
                           df: pd.DataFrame, 
                           strategy_name: str,
                           param_ranges: Dict,
                           start_date: Optional[str],
                           end_date: Optional[str]) -> float:
        """Objective function for optimization."""
        try:
            # Sample parameters
            params = {}
            for param_name, param_config in param_ranges.items():
                if param_config["type"] == "int":
                    params[param_name] = trial.suggest_int(
                        param_name, param_config["low"], param_config["high"]
                    )
                elif param_config["type"] == "float":
                    params[param_name] = trial.suggest_float(
                        param_name, param_config["low"], param_config["high"]
                    )
                elif param_config["type"] == "categorical":
                    params[param_name] = trial.suggest_categorical(
                        param_name, param_config["choices"]
                    )
                    
            # Create strategy with sampled parameters
            strategy = create_strategy(strategy_name, params)
            
            # Run cross-validation or single backtest
            if self.config.cv_method == "walk_forward":
                objective_value = self._walk_forward_cv(df, strategy, start_date, end_date)
            else:
                # Simple train-test split
                split_idx = int(len(df) * (1 - self.config.test_size))
                df_test = df.iloc[split_idx:].copy()
                
                results = self.backtest_engine.run_backtest(df_test, strategy, start_date, end_date)
                
                # Calculate objective value based on objective type
                if self.config.objective == "sharpe_ratio":
                    # Calculate Sharpe ratio manually if not in metrics
                    if 'sharpe_ratio' in results.metrics:
                        objective_value = results.metrics['sharpe_ratio']
                    else:
                        # Calculate from trades
                        trades = results.trades
                        if len(trades) > 1:
                            returns = [t['pnl'] / t['entry_price'] for t in trades if t.get('entry_price', 0) > 0]
                            if returns:
                                returns_array = np.array(returns)
                                if returns_array.std() > 0:
                                    objective_value = (returns_array.mean() / returns_array.std()) * np.sqrt(252)
                                else:
                                    objective_value = 0
                            else:
                                objective_value = 0
                        else:
                            objective_value = 0
                            
                elif self.config.objective == "total_return":
                    objective_value = results.metrics.get('total_return_pct', 0) / 100
                    
                elif self.config.objective == "profit_factor":
                    objective_value = results.metrics.get('profit_factor', 0)
                    
                elif self.config.objective == "win_rate":
                    objective_value = results.metrics.get('win_rate', 0)
                    
                else:
                    objective_value = results.metrics.get(self.config.objective, 0)
                
            # Handle invalid results
            if pd.isna(objective_value) or np.isinf(objective_value):
                return -10 if self.config.direction == "maximize" else 10
                
            # Ensure reasonable bounds
            if self.config.direction == "maximize":
                objective_value = max(objective_value, -10)  # Don't go too negative
            else:
                objective_value = min(objective_value, 10)   # Don't go too positive
                
            return float(objective_value)
            
        except Exception as e:
            logger.warning(f"Trial failed with error: {str(e)}")
            # Return worst possible value for failed trials
            return -10 if self.config.direction == "maximize" else 10
            
    def _walk_forward_cv(self, 
                        df: pd.DataFrame, 
                        strategy,
                        start_date: Optional[str], 
                        end_date: Optional[str]) -> float:
        """Perform walk-forward cross-validation."""
        scores = []
        
        # Calculate window size
        window_size = len(df) // (self.config.n_splits + 1)
        
        for i in range(self.config.n_splits):
            # Define train/test periods
            train_start = i * window_size
            train_end = (i + 1) * window_size
            test_end = min((i + 2) * window_size, len(df))
            
            if test_end <= train_end:
                break
                
            # Get test data
            df_test = df.iloc[train_end:test_end].copy()
            
            if len(df_test) < 100:  # Minimum periods for meaningful backtest
                continue
                
            # Run backtest
            try:
                results = self.backtest_engine.run_backtest(df_test, strategy, start_date, end_date)
                score = results.metrics.get(self.config.objective, 0)
                
                if not (pd.isna(score) or np.isinf(score)):
                    scores.append(score)
                    
            except Exception:
                continue
                
        # Return mean score
        return np.mean(scores) if scores else -10 if self.config.direction == "maximize" else 10
        
    def _analyze_results(self, optimization_time: float) -> OptimizationResults:
        """Analyze optimization results."""
        study = self.study
        
        # Get parameter importance
        param_importances = None
        try:
            param_importances = optuna.importance.get_param_importances(study)
        except Exception as e:
            logger.warning(f"Could not compute parameter importances: {e}")
            
        # Create results
        results = OptimizationResults(
            study_name=study.study_name,
            n_trials=len(study.trials),
            best_value=study.best_value,
            best_params=study.best_params,
            best_trial_number=study.best_trial.number,
            optimization_time=optimization_time,
            completed_trials=len([t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]),
            pruned_trials=len([t for t in study.trials if t.state == optuna.trial.TrialState.PRUNED]),
            failed_trials=len([t for t in study.trials if t.state == optuna.trial.TrialState.FAIL]),
            param_importances=param_importances
        )
        
        return results
        
    def _save_results(self, 
                     results: OptimizationResults,
                     strategy_name: str, 
                     symbol: str, 
                     timeframe: str):
        """Save optimization results to files."""
        # Create results directory
        results_dir = Path(self.config.results_dir)
        ensure_dir(results_dir)
        
        # Create timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create subdirectory for this optimization
        symbol_clean = symbol.replace("/", "_")
        subdir_name = f"{strategy_name}_{symbol_clean}_{timeframe}_{timestamp}"
        subdir = results_dir / subdir_name
        ensure_dir(subdir)
        
        # Save study
        if self.config.save_study:
            study_path = subdir / "study.pkl"
            import joblib
            joblib.dump(self.study, study_path)
            results.study_path = str(study_path)
            
        # Save results summary
        results_path = subdir / "results.json"
        with open(results_path, 'w') as f:
            json.dump(results.summary, f, indent=2, default=str)
        results.results_path = str(results_path)
        
        # Save detailed trial results
        trials_df = self.study.trials_dataframe()
        trials_path = subdir / "trials.csv"
        trials_df.to_csv(trials_path, index=False)
        
        # Save plots
        if self.config.save_plots:
            plots_dir = subdir / "plots"
            ensure_dir(plots_dir)
            results.plots_dir = str(plots_dir)
            
            try:
                # Optimization history
                fig = plot_optimization_history(self.study)
                fig.write_html(plots_dir / "optimization_history.html")
                
                # Parameter importance
                if results.param_importances:
                    fig = plot_param_importances(self.study)
                    fig.write_html(plots_dir / "param_importances.html")
                    
                # Parallel coordinate plot
                fig = plot_parallel_coordinate(self.study)
                fig.write_html(plots_dir / "parallel_coordinate.html")
                
                logger.info(f"Plots saved to {plots_dir}")
                
            except Exception as e:
                logger.warning(f"Could not save plots: {e}")
                
        logger.info(f"Results saved to {subdir}")
        
    def load_study(self, study_path: str):
        """Load a previously saved study."""
        import joblib
        self.study = joblib.load(study_path)
        logger.info(f"Study loaded from {study_path}")
        
    def continue_optimization(self, n_additional_trials: int):
        """Continue optimization with additional trials."""
        if self.study is None:
            raise ValueError("No study loaded")
            
        logger.info(f"Continuing optimization with {n_additional_trials} additional trials")
        
        # Note: This requires the same objective function setup as the original optimization
        # In practice, you'd need to store and reload the objective function context
        logger.warning("Continue optimization not fully implemented - requires objective function context")


def create_optimizer(config: Dict[str, Any]) -> ParameterOptimizer:
    """Factory function to create parameter optimizer from config."""
    opt_config = OptimizationConfig(**config)
    return ParameterOptimizer(opt_config)


def optimize_strategy_simple(strategy_name: str,
                           symbol: str,
                           timeframe: str,
                           n_trials: int = 50,
                           data_config: Optional[Dict] = None) -> OptimizationResults:
    """Simple optimization function with default settings."""
    config = OptimizationConfig(n_trials=n_trials)
    optimizer = ParameterOptimizer(config)
    
    return optimizer.optimize_strategy(
        strategy_name=strategy_name,
        symbol=symbol,
        timeframe=timeframe,
        data_config=data_config
    )