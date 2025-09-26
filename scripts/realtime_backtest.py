#!/usr/bin/env python3
"""
Real-Time Backtesting & Performance Monitoring
Simulates live trading with continuous backtesting and monitoring.
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

# Add src to path
sys.path.append('src')

from utils import get_logger, ensure_directory
from data import DataLoader
from backtest import BacktestEngine, BacktestConfig
from strategy.rule_based import create_strategy

logger = get_logger(__name__)


class RealtimeBacktester:
    """Real-time backtesting engine with live monitoring."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.data_loader = DataLoader(config.get('data', {}))
        self.backtest_engine = BacktestEngine(BacktestConfig(**config.get('backtest', {})))
        
        # Monitoring state
        self.is_running = False
        self.last_update = None
        self.performance_history = []
        self.current_positions = {}
        
        # Results directory
        self.results_dir = Path("realtime_results")
        ensure_directory(self.results_dir)
        
    def start_monitoring(self, 
                        strategy_name: str,
                        symbols: List[str],
                        timeframe: str = "1h",
                        lookback_hours: int = 168,  # 1 week
                        update_interval: int = 3600,  # 1 hour in seconds
                        max_duration: int = 86400):  # 24 hours
        """Start real-time backtesting monitoring."""
        
        logger.info(f"🚀 Starting real-time backtest monitoring")
        logger.info(f"   Strategy: {strategy_name}")
        logger.info(f"   Symbols: {', '.join(symbols)}")
        logger.info(f"   Timeframe: {timeframe}")
        logger.info(f"   Update interval: {update_interval}s")
        
        self.is_running = True
        start_time = datetime.now()
        
        # Create strategy
        strategy_params = self.config.get('strategy_params', {}).get(strategy_name, {})
        strategy = create_strategy(strategy_name, strategy_params)
        
        iteration = 0
        
        try:
            while self.is_running and (datetime.now() - start_time).seconds < max_duration:
                iteration += 1
                current_time = datetime.now()
                
                print(f"\n{'='*80}")
                print(f"📊 REAL-TIME BACKTEST ITERATION #{iteration}")
                print(f"⏰ Time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"{'='*80}")
                
                # Run backtests for all symbols
                iteration_results = {}
                
                for symbol in symbols:
                    try:
                        result = self._run_single_backtest(
                            strategy, strategy_name, symbol, timeframe, lookback_hours
                        )
                        iteration_results[symbol] = result
                        
                    except Exception as e:
                        logger.error(f"Error backtesting {symbol}: {e}")
                        iteration_results[symbol] = None
                
                # Analyze and save results
                self._analyze_iteration(iteration_results, current_time, strategy_name)
                
                # Update monitoring state
                self.last_update = current_time
                
                # Wait for next iteration
                if self.is_running:
                    logger.info(f"⏳ Waiting {update_interval}s for next iteration...")
                    time.sleep(update_interval)
                
        except KeyboardInterrupt:
            logger.info("🛑 Monitoring stopped by user")
            
        except Exception as e:
            logger.error(f"❌ Monitoring error: {e}")
            
        finally:
            self.is_running = False
            self._generate_final_report(strategy_name)
            
        logger.info("✅ Real-time monitoring completed")
        
    def _run_single_backtest(self, 
                           strategy,
                           strategy_name: str, 
                           symbol: str, 
                           timeframe: str,
                           lookback_hours: int) -> Optional[Dict]:
        """Run backtest for single symbol with current data."""
        
        # Calculate date range
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=lookback_hours)
        
        start_date = start_time.strftime('%Y-%m-%d')
        end_date = end_time.strftime('%Y-%m-%d')
        
        try:
            # Load fresh data
            df = self.data_loader.load_ohlcv(symbol, timeframe, start_date, end_date)
            
            if len(df) < 50:  # Minimum data requirement
                logger.warning(f"Insufficient data for {symbol}: {len(df)} candles")
                return None
                
            # Run backtest
            results = self.backtest_engine.run_backtest(df, strategy, start_date, end_date)
            
            # Extract key metrics
            metrics = {
                'timestamp': datetime.now().isoformat(),
                'symbol': symbol,
                'strategy': strategy_name,
                'timeframe': timeframe,
                'data_points': len(df),
                'total_trades': len(results.trades),
                'win_rate': results.metrics.get('win_rate', 0),
                'profit_factor': results.metrics.get('profit_factor', 0),
                'total_return_pct': results.metrics.get('total_return_pct', 0),
                'max_drawdown_pct': results.metrics.get('max_drawdown_pct', 0),
                'sharpe_ratio': self._calculate_sharpe(results.trades),
                'last_price': df['close'].iloc[-1] if len(df) > 0 else 0,
                'current_position': self._get_current_position(results.trades),
                'recent_trades': results.trades[-5:] if len(results.trades) >= 5 else results.trades
            }
            
            return metrics
            
        except Exception as e:
            logger.error(f"Backtest error for {symbol}: {e}")
            return None
            
    def _calculate_sharpe(self, trades: List[Dict]) -> float:
        """Calculate Sharpe ratio from trades."""
        if len(trades) < 2:
            return 0
            
        returns = [t['pnl'] / t.get('entry_price', 1) for t in trades if t.get('entry_price', 0) > 0]
        
        if not returns:
            return 0
            
        returns_array = np.array(returns)
        if returns_array.std() == 0:
            return 0
            
        return (returns_array.mean() / returns_array.std()) * np.sqrt(252)
        
    def _get_current_position(self, trades: List[Dict]) -> str:
        """Determine current position from trades."""
        if not trades:
            return "flat"
            
        # Find last trade
        last_trade = trades[-1]
        
        # Simple logic: if last trade was a buy, we're long, if sell, we're short
        if last_trade.get('side') == 'buy':
            return "long"
        elif last_trade.get('side') == 'sell':
            return "short"
        else:
            return "flat"
            
    def _analyze_iteration(self, 
                          results: Dict, 
                          timestamp: datetime, 
                          strategy_name: str):
        """Analyze and report results for current iteration."""
        
        valid_results = {k: v for k, v in results.items() if v is not None}
        
        if not valid_results:
            print("❌ No valid backtest results this iteration")
            return
            
        print(f"\n📊 ITERATION RESULTS:")
        print(f"{'='*50}")
        
        # Per-symbol results
        for symbol, metrics in valid_results.items():
            print(f"\n🔹 {symbol}")
            print(f"   💰 Total Return: {metrics['total_return_pct']:.2f}%")
            print(f"   🎯 Win Rate: {metrics['win_rate']*100:.1f}%")
            print(f"   ⚖️ Profit Factor: {metrics['profit_factor']:.2f}")
            print(f"   📊 Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
            print(f"   📉 Max Drawdown: {metrics['max_drawdown_pct']:.2f}%")
            print(f"   🔢 Total Trades: {metrics['total_trades']}")
            print(f"   💵 Last Price: ${metrics['last_price']:.2f}")
            print(f"   📍 Position: {metrics['current_position'].upper()}")
            
        # Overall performance
        avg_return = np.mean([m['total_return_pct'] for m in valid_results.values()])
        avg_sharpe = np.mean([m['sharpe_ratio'] for m in valid_results.values()])
        avg_win_rate = np.mean([m['win_rate'] for m in valid_results.values()])
        
        print(f"\n🏆 OVERALL PERFORMANCE:")
        print(f"   📈 Avg Return: {avg_return:.2f}%")
        print(f"   📊 Avg Sharpe: {avg_sharpe:.2f}")
        print(f"   🎯 Avg Win Rate: {avg_win_rate*100:.1f}%")
        
        # Trading alerts
        self._check_trading_alerts(valid_results)
        
        # Save to history
        iteration_summary = {
            'timestamp': timestamp.isoformat(),
            'strategy': strategy_name,
            'results': valid_results,
            'summary': {
                'avg_return': avg_return,
                'avg_sharpe': avg_sharpe,
                'avg_win_rate': avg_win_rate,
                'symbols_count': len(valid_results)
            }
        }
        
        self.performance_history.append(iteration_summary)
        
        # Save iteration results
        filename = f"iteration_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.results_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(iteration_summary, f, indent=2, default=str)
            
    def _check_trading_alerts(self, results: Dict):
        """Check for trading alerts and signals."""
        
        alerts = []
        
        for symbol, metrics in results.items():
            # High performance alert
            if metrics['total_return_pct'] > 5 and metrics['sharpe_ratio'] > 1.5:
                alerts.append(f"🚀 STRONG PERFORMANCE: {symbol} showing {metrics['total_return_pct']:.2f}% return")
                
            # Position change alert  
            current_pos = metrics['current_position']
            if current_pos != 'flat':
                alerts.append(f"📍 POSITION ALERT: {symbol} currently {current_pos.upper()}")
                
            # Recent trade activity
            if len(metrics['recent_trades']) > 0:
                last_trade = metrics['recent_trades'][-1]
                last_pnl = last_trade.get('pnl', 0)
                if abs(last_pnl) > 50:  # Significant P&L
                    alerts.append(f"💰 SIGNIFICANT TRADE: {symbol} last trade P&L: ${last_pnl:.2f}")
                    
            # High drawdown warning
            if metrics['max_drawdown_pct'] > 8:
                alerts.append(f"⚠️ HIGH DRAWDOWN: {symbol} drawdown at {metrics['max_drawdown_pct']:.2f}%")
                
        if alerts:
            print(f"\n🔔 TRADING ALERTS:")
            for alert in alerts:
                print(f"   {alert}")
        else:
            print(f"\n✅ No significant alerts this iteration")
            
    def _generate_final_report(self, strategy_name: str):
        """Generate final performance report."""
        
        if not self.performance_history:
            logger.warning("No performance history to report")
            return
            
        print(f"\n{'='*80}")
        print(f"📋 FINAL PERFORMANCE REPORT")
        print(f"{'='*80}")
        
        # Time range
        start_time = self.performance_history[0]['timestamp']
        end_time = self.performance_history[-1]['timestamp']
        
        print(f"📅 Monitoring Period: {start_time} to {end_time}")
        print(f"🔄 Total Iterations: {len(self.performance_history)}")
        print(f"⚙️ Strategy: {strategy_name}")
        
        # Aggregate performance metrics
        all_returns = []
        all_sharpes = []
        all_win_rates = []
        
        for iteration in self.performance_history:
            summary = iteration['summary']
            all_returns.append(summary['avg_return'])
            all_sharpes.append(summary['avg_sharpe'])
            all_win_rates.append(summary['avg_win_rate'])
            
        print(f"\n📊 AGGREGATE METRICS:")
        print(f"   💰 Average Return: {np.mean(all_returns):.2f}% (std: {np.std(all_returns):.2f}%)")
        print(f"   📊 Average Sharpe: {np.mean(all_sharpes):.2f} (std: {np.std(all_sharpes):.2f})")
        print(f"   🎯 Average Win Rate: {np.mean(all_win_rates)*100:.1f}% (std: {np.std(all_win_rates)*100:.1f}%)")
        print(f"   📈 Best Return: {max(all_returns):.2f}%")
        print(f"   📉 Worst Return: {min(all_returns):.2f}%")
        
        # Symbol-specific performance
        symbol_performance = {}
        
        for iteration in self.performance_history:
            for symbol, metrics in iteration['results'].items():
                if symbol not in symbol_performance:
                    symbol_performance[symbol] = []
                symbol_performance[symbol].append(metrics['total_return_pct'])
                
        print(f"\n🔹 SYMBOL PERFORMANCE:")
        for symbol, returns in symbol_performance.items():
            avg_return = np.mean(returns)
            std_return = np.std(returns)
            print(f"   {symbol}: {avg_return:.2f}% ± {std_return:.2f}%")
            
        # Save final report
        final_report = {
            'strategy': strategy_name,
            'monitoring_period': {
                'start': start_time,
                'end': end_time,
                'iterations': len(self.performance_history)
            },
            'aggregate_metrics': {
                'avg_return': float(np.mean(all_returns)),
                'avg_sharpe': float(np.mean(all_sharpes)),
                'avg_win_rate': float(np.mean(all_win_rates)),
                'return_std': float(np.std(all_returns)),
                'sharpe_std': float(np.std(all_sharpes)),
                'best_return': float(max(all_returns)),
                'worst_return': float(min(all_returns))
            },
            'symbol_performance': {
                symbol: {
                    'avg_return': float(np.mean(returns)),
                    'std_return': float(np.std(returns)),
                    'iterations': len(returns)
                }
                for symbol, returns in symbol_performance.items()
            },
            'full_history': self.performance_history
        }
        
        report_file = self.results_dir / f"final_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(final_report, f, indent=2, default=str)
            
        print(f"\n💾 Final report saved to: {report_file}")
        print(f"✅ Real-time monitoring completed successfully!")
        
    def stop_monitoring(self):
        """Stop the monitoring process."""
        self.is_running = False
        logger.info("🛑 Monitoring stop requested")


def main():
    """Main function to run real-time backtesting."""
    
    # Configuration
    config = {
        'data': {
            'source': 'binance_spot',
            'cache_enabled': True
        },
        'backtest': {
            'initial_capital': 10000,
            'fee_rate': 0.001,
            'slippage_bps': 2.0
        },
        'strategy_params': {
            'StrategyMomo': {
                'ema_short': 12,
                'ema_long': 26,
                'rsi_period': 14,
                'rsi_overbought': 70,
                'rsi_oversold': 30,
                'risk_per_trade': 0.02
            }
        }
    }
    
    # Create backtester
    backtester = RealtimeBacktester(config)
    
    try:
        # Start monitoring
        backtester.start_monitoring(
            strategy_name='StrategyMomo',
            symbols=['BTC/USDT', 'ETH/USDT'],
            timeframe='1h',
            lookback_hours=168,     # 1 week of data
            update_interval=1800,   # Update every 30 minutes  
            max_duration=7200       # Run for 2 hours max
        )
        
    except KeyboardInterrupt:
        print("\n🛑 Stopping real-time backtesting...")
        backtester.stop_monitoring()


if __name__ == "__main__":
    main()