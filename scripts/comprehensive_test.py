#!/usr/bin/env python3
"""
Comprehensive Backtesting Suite
Tests strategies across multiple symbols, timeframes, and configurations to get robust results.
"""

import sys
import subprocess
import time
from datetime import datetime
import pandas as pd
import json

def comprehensive_backtest():
    """Run comprehensive backtesting across multiple scenarios."""
    
    print(f"\n{'='*80}")
    print(f"🚀 COMPREHENSIVE BACKTESTING SUITE")
    print(f"{'='*80}")
    print(f"🕐 Started: {datetime.now()}")
    print()
    
    # Define test scenarios
    strategies = ["StrategyMomo", "StrategyMeanRev"]
    symbols = ["BTC/USDT", "ETH/USDT"]
    timeframes = ["1h", "4h"]
    
    results = []
    total_tests = len(strategies) * len(symbols) * len(timeframes)
    current_test = 0
    
    print(f"📊 Running {total_tests} backtest scenarios...")
    print(f"{'='*50}")
    
    for strategy in strategies:
        for symbol in symbols:
            for timeframe in timeframes:
                current_test += 1
                test_name = f"{strategy}_{symbol.replace('/', '_')}_{timeframe}"
                
                print(f"\n📈 Test {current_test}/{total_tests}: {test_name}")
                print(f"{'='*40}")
                
                # Run backtest
                cmd = f"python main.py backtest {strategy} --symbol {symbol} --timeframe {timeframe}"
                
                try:
                    start_time = time.time()
                    result = subprocess.run(cmd.split(), capture_output=True, text=True, cwd='.')
                    end_time = time.time()
                    
                    if result.returncode == 0:
                        # Parse results
                        output = result.stdout
                        metrics = parse_backtest_output(output)
                        metrics.update({
                            'strategy': strategy,
                            'symbol': symbol,
                            'timeframe': timeframe,
                            'test_name': test_name,
                            'execution_time': round(end_time - start_time, 2),
                            'status': 'success'
                        })
                        
                        # Display quick summary
                        print(f"✅ Success | Trades: {metrics.get('trades', 0)} | Win Rate: {metrics.get('win_rate', 'N/A')} | P&L: {metrics.get('total_return', 'N/A')}")
                        
                    else:
                        print(f"❌ Failed: {result.stderr}")
                        metrics = {
                            'strategy': strategy,
                            'symbol': symbol,
                            'timeframe': timeframe,
                            'test_name': test_name,
                            'status': 'failed',
                            'error': result.stderr
                        }
                    
                    results.append(metrics)
                    
                    # Brief pause between tests
                    time.sleep(0.5)
                    
                except Exception as e:
                    print(f"❌ Error: {e}")
                    results.append({
                        'strategy': strategy,
                        'symbol': symbol,
                        'timeframe': timeframe,
                        'test_name': test_name,
                        'status': 'error',
                        'error': str(e)
                    })
    
    # Analyze and display comprehensive results
    print(f"\n\n{'='*80}")
    print(f"📊 COMPREHENSIVE ANALYSIS RESULTS")
    print(f"{'='*80}")
    
    # Filter successful results
    successful_results = [r for r in results if r.get('status') == 'success']
    
    if not successful_results:
        print("❌ No successful backtests to analyze")
        return
    
    # Convert to DataFrame for analysis
    df = pd.DataFrame(successful_results)
    
    # 1. Best performers by different metrics
    print(f"\n🏆 TOP PERFORMERS:")
    print(f"{'='*30}")
    
    # Best by Total Return
    if 'total_return' in df.columns:
        df['return_num'] = pd.to_numeric(df['total_return'].str.replace('%', ''), errors='coerce')
        best_return = df.loc[df['return_num'].idxmax()]
        print(f"💰 Highest Return: {best_return['test_name']}")
        print(f"   📈 Return: {best_return['total_return']}")
        print(f"   🎯 Win Rate: {best_return.get('win_rate', 'N/A')}")
        print()
    
    # Best by Win Rate
    if 'win_rate' in df.columns:
        df['win_rate_num'] = pd.to_numeric(df['win_rate'].str.replace('%', ''), errors='coerce')
        best_winrate = df.loc[df['win_rate_num'].idxmax()]
        print(f"🎯 Highest Win Rate: {best_winrate['test_name']}")
        print(f"   🎯 Win Rate: {best_winrate['win_rate']}")
        print(f"   📈 Return: {best_winrate.get('total_return', 'N/A')}")
        print()
    
    # Best by Profit Factor
    if 'profit_factor' in df.columns:
        df['pf_num'] = pd.to_numeric(df['profit_factor'], errors='coerce')
        best_pf = df.loc[df['pf_num'].idxmax()]
        print(f"⚖️ Best Profit Factor: {best_pf['test_name']}")
        print(f"   ⚖️ Profit Factor: {best_pf['profit_factor']}")
        print(f"   📈 Return: {best_pf.get('total_return', 'N/A')}")
        print()
    
    # 2. Strategy comparison
    print(f"📊 STRATEGY COMPARISON:")
    print(f"{'='*30}")
    
    strategy_stats = df.groupby('strategy').agg({
        'return_num': ['mean', 'std', 'count'],
        'win_rate_num': ['mean', 'std'],
        'trades': ['mean', 'sum']
    }).round(2)
    
    for strategy in strategies:
        strategy_data = df[df['strategy'] == strategy]
        if len(strategy_data) > 0:
            avg_return = strategy_data['return_num'].mean()
            avg_winrate = strategy_data['win_rate_num'].mean()
            total_trades = strategy_data['trades'].sum()
            
            print(f"🎯 {strategy}:")
            print(f"   📈 Avg Return: {avg_return:.2f}%")
            print(f"   🎯 Avg Win Rate: {avg_winrate:.1f}%")
            print(f"   📊 Total Trades: {total_trades}")
            print()
    
    # 3. Symbol comparison
    print(f"💰 SYMBOL COMPARISON:")
    print(f"{'='*25}")
    
    for symbol in symbols:
        symbol_data = df[df['symbol'] == symbol]
        if len(symbol_data) > 0:
            avg_return = symbol_data['return_num'].mean()
            avg_winrate = symbol_data['win_rate_num'].mean()
            total_trades = symbol_data['trades'].sum()
            
            print(f"📊 {symbol}:")
            print(f"   📈 Avg Return: {avg_return:.2f}%")
            print(f"   🎯 Avg Win Rate: {avg_winrate:.1f}%")
            print(f"   📊 Total Trades: {total_trades}")
            print()
    
    # 4. Timeframe comparison
    print(f"⏰ TIMEFRAME COMPARISON:")
    print(f"{'='*25}")
    
    for tf in timeframes:
        tf_data = df[df['timeframe'] == tf]
        if len(tf_data) > 0:
            avg_return = tf_data['return_num'].mean()
            avg_winrate = tf_data['win_rate_num'].mean()
            total_trades = tf_data['trades'].sum()
            
            print(f"⏰ {tf}:")
            print(f"   📈 Avg Return: {avg_return:.2f}%")
            print(f"   🎯 Avg Win Rate: {avg_winrate:.1f}%")
            print(f"   📊 Total Trades: {total_trades}")
            print()
    
    # 5. Recommendations
    print(f"💡 RECOMMENDATIONS:")
    print(f"{'='*20}")
    
    # Find best overall combination
    if 'return_num' in df.columns and 'win_rate_num' in df.columns:
        # Create composite score (return * winrate)
        df['composite_score'] = df['return_num'] * df['win_rate_num'] / 100
        best_overall = df.loc[df['composite_score'].idxmax()]
        
        print(f"🏆 RECOMMENDED SETUP:")
        print(f"   🎯 Strategy: {best_overall['strategy']}")
        print(f"   📊 Symbol: {best_overall['symbol']}")
        print(f"   ⏰ Timeframe: {best_overall['timeframe']}")
        print(f"   📈 Return: {best_overall['total_return']}")
        print(f"   🎯 Win Rate: {best_overall['win_rate']}")
        print(f"   📊 Trades: {best_overall['trades']}")
        print()
    
    # Save detailed results
    results_file = f"runs/comprehensive_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"💾 Detailed results saved to: {results_file}")
    print(f"✅ Analysis complete!")

def parse_backtest_output(output):
    """Parse backtest output to extract metrics."""
    metrics = {}
    
    lines = output.split('\n')
    
    for line in lines:
        line = line.strip()
        
        # Parse table format: │ Metric │ Value │
        if '│' in line and '┃' not in line and '━' not in line and '┏' not in line:
            parts = [p.strip() for p in line.split('│') if p.strip()]
            if len(parts) == 2:
                metric_name = parts[0].lower().replace(' ', '_')
                metric_value = parts[1]
                
                # Clean up common metrics
                if 'total_return' in metric_name:
                    metrics['total_return'] = metric_value
                elif 'win_rate' in metric_name:
                    metrics['win_rate'] = metric_value
                elif 'profit_factor' in metric_name:
                    metrics['profit_factor'] = metric_value.replace(',', '')
                elif 'number_of_trades' in metric_name:
                    metrics['trades'] = int(metric_value) if metric_value.isdigit() else 0
                elif 'sharpe_ratio' in metric_name:
                    metrics['sharpe_ratio'] = metric_value
                elif 'max_drawdown' in metric_name:
                    metrics['max_drawdown'] = metric_value
    
    return metrics

if __name__ == "__main__":
    comprehensive_backtest()