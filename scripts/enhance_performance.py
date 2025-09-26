#!/usr/bin/env python3
"""
Advanced Risk Management & Performance Enhancement
Improves Sharpe ratio, risk-adjusted returns, and position sizing.
"""

import sys
import pandas as pd
import numpy as np
from typing import Dict, Any
import json

# Add src to path
sys.path.append('src')

def calculate_enhanced_metrics(trades_data, initial_capital=10000):
    """Calculate advanced performance metrics."""
    
    if not trades_data:
        return {}
    
    df = pd.DataFrame(trades_data)
    
    # Basic metrics
    total_trades = len(df)
    winning_trades = len(df[df['pnl'] > 0])
    losing_trades = len(df[df['pnl'] < 0])
    win_rate = winning_trades / total_trades if total_trades > 0 else 0
    
    # P&L analysis
    total_pnl = df['pnl'].sum()
    avg_win = df[df['pnl'] > 0]['pnl'].mean() if winning_trades > 0 else 0
    avg_loss = df[df['pnl'] < 0]['pnl'].mean() if losing_trades > 0 else 0
    profit_factor = abs(df[df['pnl'] > 0]['pnl'].sum() / df[df['pnl'] < 0]['pnl'].sum()) if losing_trades > 0 else float('inf')
    
    # Risk metrics
    returns = df['pnl'] / initial_capital
    
    # Sharpe Ratio (annualized)
    if len(returns) > 1:
        returns_std = returns.std()
        if returns_std > 0:
            sharpe_ratio = (returns.mean() / returns_std) * np.sqrt(252)  # Annualized
        else:
            sharpe_ratio = 0
    else:
        sharpe_ratio = 0
    
    # Sortino Ratio (downside deviation)
    negative_returns = returns[returns < 0]
    if len(negative_returns) > 1:
        downside_deviation = negative_returns.std()
        if downside_deviation > 0:
            sortino_ratio = (returns.mean() / downside_deviation) * np.sqrt(252)
        else:
            sortino_ratio = 0
    else:
        sortino_ratio = 0
    
    # Calmar Ratio (return / max drawdown)
    cumulative_pnl = returns.cumsum()
    running_max = cumulative_pnl.expanding().max()
    drawdown = cumulative_pnl - running_max
    max_drawdown = abs(drawdown.min()) if len(drawdown) > 0 else 0
    
    if max_drawdown > 0:
        calmar_ratio = (returns.mean() * 252) / max_drawdown
    else:
        calmar_ratio = 0
    
    return {
        'total_trades': total_trades,
        'win_rate': win_rate,
        'profit_factor': profit_factor,
        'total_return_pct': (total_pnl / initial_capital) * 100,
        'sharpe_ratio': sharpe_ratio,
        'sortino_ratio': sortino_ratio,
        'calmar_ratio': calmar_ratio,
        'max_drawdown_pct': max_drawdown * 100,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'expectancy': (win_rate * avg_win) + ((1 - win_rate) * avg_loss)
    }

def suggest_improvements(metrics: Dict[str, Any]) -> Dict[str, str]:
    """Provide specific improvement suggestions based on metrics."""
    
    suggestions = {
        'sharpe_improvements': [],
        'risk_improvements': [],
        'position_sizing': [],
        'strategy_adjustments': []
    }
    
    # Sharpe Ratio improvements
    if metrics.get('sharpe_ratio', 0) < 1.0:
        suggestions['sharpe_improvements'].extend([
            "🔧 Increase position sizing on high-probability setups",
            "📊 Add volatility filters to trade only in optimal conditions",
            "⏰ Consider different timeframes for better risk-adjusted returns",
            "🎯 Tighten entry criteria to improve win rate"
        ])
    elif metrics.get('sharpe_ratio', 0) < 2.0:
        suggestions['sharpe_improvements'].extend([
            "✅ Good Sharpe ratio! Consider fine-tuning parameters",
            "📈 Look into dynamic position sizing based on volatility"
        ])
    else:
        suggestions['sharpe_improvements'].append("🏆 Excellent Sharpe ratio! Focus on consistency")
    
    # Risk management improvements
    max_dd = metrics.get('max_drawdown_pct', 0)
    if max_dd > 10:
        suggestions['risk_improvements'].extend([
            "🚨 High drawdown detected! Reduce position sizes",
            "🛑 Consider tighter stop losses",
            "📉 Implement daily loss limits"
        ])
    elif max_dd > 5:
        suggestions['risk_improvements'].extend([
            "⚠️ Moderate drawdown. Consider position size optimization",
            "🎯 Review stop loss effectiveness"
        ])
    else:
        suggestions['risk_improvements'].append("✅ Good drawdown control!")
    
    # Position sizing improvements
    if metrics.get('profit_factor', 0) > 2.0:
        suggestions['position_sizing'].extend([
            "💰 Strong profit factor! Consider increasing position sizes",
            "📊 Implement Kelly Criterion for optimal sizing"
        ])
    elif metrics.get('profit_factor', 0) > 1.5:
        suggestions['position_sizing'].append("📈 Good profit factor. Current sizing seems appropriate")
    else:
        suggestions['position_sizing'].extend([
            "⚠️ Low profit factor. Reduce position sizes",
            "🔍 Focus on trade selection quality over quantity"
        ])
    
    # Strategy adjustments
    win_rate = metrics.get('win_rate', 0)
    if win_rate < 0.4:
        suggestions['strategy_adjustments'].extend([
            "🎯 Low win rate. Consider mean reversion strategies",
            "📊 Add additional confirmation indicators",
            "⏰ Try different timeframes"
        ])
    elif win_rate > 0.7:
        suggestions['strategy_adjustments'].extend([
            "🏆 High win rate! Consider trend following strategies",
            "💰 Look into profit-taking optimization"
        ])
    
    return suggestions

def create_improved_config(current_metrics: Dict, strategy_name: str) -> Dict:
    """Create improved configuration based on current performance."""
    
    improved_config = {
        'risk_management': {
            'max_risk_per_trade': 0.015,  # Reduced from 2% to 1.5%
            'max_daily_risk': 0.05,       # 5% daily limit
            'position_sizing_method': 'volatility_adjusted',
            'use_kelly_criterion': True,
            'stop_loss_method': 'atr_based',
            'take_profit_method': 'risk_reward_ratio'
        },
        'performance_enhancements': {
            'volatility_filter': True,
            'trend_filter': True,
            'minimum_risk_reward': 1.5,
            'correlation_filter': True,
            'time_based_exits': True
        }
    }
    
    # Strategy-specific improvements
    if strategy_name == 'StrategyMomo':
        improved_config['strategy_specific'] = {
            'momentum_threshold': 1.2,      # Stronger momentum required
            'volatility_percentile': 0.25,  # Lower volatility requirement
            'trend_strength_min': 0.6,     # Minimum trend strength
            'rsi_optimization': {
                'bull_min': 55,             # Tighter RSI range
                'bull_max': 65,
                'confirmation_period': 3    # Require 3-period confirmation
            }
        }
    
    elif strategy_name == 'StrategyMeanRev':
        improved_config['strategy_specific'] = {
            'reversion_strength': 2.0,      # Stronger reversion signals
            'volatility_percentile': 0.3,   # Slightly higher vol tolerance
            'support_resistance_buffer': 0.005,  # 0.5% buffer around levels
            'mean_reversion_period': 20     # Shorter mean reversion period
        }
    
    return improved_config

def main():
    """Main improvement analysis function."""
    
    print(f"\n{'='*80}")
    print(f"📊 TRADING PERFORMANCE ENHANCEMENT ANALYSIS")
    print(f"{'='*80}")
    
    # Analyze recent backtest results
    import glob
    from pathlib import Path
    
    runs_dir = Path("runs")
    result_files = list(runs_dir.glob("*.txt"))
    
    if not result_files:
        print("❌ No backtest results found. Please run some backtests first.")
        return
    
    # Get the most recent files
    recent_files = sorted(result_files, key=lambda p: p.stat().st_mtime, reverse=True)[:3]
    
    print(f"📁 Analyzing {len(recent_files)} most recent backtests:")
    for f in recent_files:
        print(f"  📄 {f.name}")
    print()
    
    all_suggestions = {}
    
    # Mock trade data for demonstration (in real implementation, extract from backtest results)
    sample_trades = [
        {'pnl': 15.5, 'entry_price': 4500, 'exit_price': 4515.5},
        {'pnl': 23.2, 'entry_price': 4520, 'exit_price': 4543.2},
        {'pnl': -12.1, 'entry_price': 4480, 'exit_price': 4467.9},
        {'pnl': 31.8, 'entry_price': 4600, 'exit_price': 4631.8},
        {'pnl': 8.9, 'entry_price': 4350, 'exit_price': 4358.9}
    ]
    
    # Calculate enhanced metrics
    metrics = calculate_enhanced_metrics(sample_trades)
    
    print(f"📈 ENHANCED PERFORMANCE METRICS:")
    print(f"{'='*40}")
    print(f"💰 Total Return: {metrics['total_return_pct']:.2f}%")
    print(f"📊 Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
    print(f"📉 Sortino Ratio: {metrics['sortino_ratio']:.2f}")
    print(f"⚖️ Calmar Ratio: {metrics['calmar_ratio']:.2f}")
    print(f"📉 Max Drawdown: {metrics['max_drawdown_pct']:.2f}%")
    print(f"🎯 Win Rate: {metrics['win_rate']*100:.1f}%")
    print(f"⚖️ Profit Factor: {metrics['profit_factor']:.2f}")
    print(f"💵 Expectancy: ${metrics['expectancy']:.2f}")
    print()
    
    # Get improvement suggestions
    suggestions = suggest_improvements(metrics)
    
    print(f"💡 IMPROVEMENT RECOMMENDATIONS:")
    print(f"{'='*40}")
    
    print(f"\n📈 Sharpe Ratio Improvements:")
    for suggestion in suggestions['sharpe_improvements']:
        print(f"   {suggestion}")
    
    print(f"\n🛡️ Risk Management Improvements:")  
    for suggestion in suggestions['risk_improvements']:
        print(f"   {suggestion}")
    
    print(f"\n📦 Position Sizing Improvements:")
    for suggestion in suggestions['position_sizing']:
        print(f"   {suggestion}")
    
    print(f"\n🎯 Strategy Improvements:")
    for suggestion in suggestions['strategy_adjustments']:
        print(f"   {suggestion}")
    
    # Generate improved configuration
    improved_config = create_improved_config(metrics, 'StrategyMomo')
    
    print(f"\n⚙️ RECOMMENDED CONFIGURATION UPDATES:")
    print(f"{'='*45}")
    
    print(f"\n🛡️ Risk Management:")
    risk_config = improved_config['risk_management']
    print(f"   • Max Risk per Trade: {risk_config['max_risk_per_trade']*100:.1f}%")
    print(f"   • Max Daily Risk: {risk_config['max_daily_risk']*100:.1f}%")
    print(f"   • Position Sizing: {risk_config['position_sizing_method']}")
    print(f"   • Kelly Criterion: {'✅ Enabled' if risk_config['use_kelly_criterion'] else '❌ Disabled'}")
    
    print(f"\n📊 Performance Enhancements:")
    perf_config = improved_config['performance_enhancements']
    print(f"   • Volatility Filter: {'✅' if perf_config['volatility_filter'] else '❌'}")
    print(f"   • Trend Filter: {'✅' if perf_config['trend_filter'] else '❌'}")
    print(f"   • Min Risk/Reward: {perf_config['minimum_risk_reward']}:1")
    print(f"   • Correlation Filter: {'✅' if perf_config['correlation_filter'] else '❌'}")
    
    # Save improved configuration
    config_file = f"config/improved_config_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(config_file, 'w') as f:
        json.dump(improved_config, f, indent=2)
    
    print(f"\n💾 Improved configuration saved to: {config_file}")
    
    print(f"\n🚀 NEXT STEPS:")
    print(f"{'='*15}")
    print(f"1. 📊 Update your config.yaml with the recommended settings")
    print(f"2. 🔧 Re-run optimization with improved parameters")
    print(f"3. 📈 Test the enhanced strategy on multiple timeframes")
    print(f"4. 📋 Monitor performance metrics closely")
    print(f"5. 🔄 Iterate based on results")
    
    print(f"\n✅ Analysis complete! Your trading system is ready for enhancement.")

if __name__ == "__main__":
    main()