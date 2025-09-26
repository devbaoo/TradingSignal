#!/usr/bin/env python3
"""
Trade Analysis Helper
Runs a backtest and captures detailed trade information from the CLI output.
"""

import subprocess
import sys
import re
from datetime import datetime

def analyze_backtest_output(strategy: str, symbol: str, timeframe: str):
    """Run backtest and analyze the detailed output."""
    
    print(f"\n{'='*80}")
    print(f"🔍 DETAILED TRADE ANALYSIS")
    print(f"{'='*80}")
    print(f"🎯 Strategy: {strategy}")
    print(f"📊 Symbol: {symbol}")  
    print(f"⏰ Timeframe: {timeframe}")
    print(f"🕐 Analysis Time: {datetime.now()}")
    print()
    
    # Run the backtest command and capture output
    cmd = f"python main.py backtest {strategy} --symbol {symbol} --timeframe {timeframe}"
    
    print(f"🚀 Running: {cmd}")
    print(f"{'='*80}")
    
    try:
        result = subprocess.run(cmd.split(), capture_output=True, text=True, cwd='.')
        
        if result.returncode != 0:
            print(f"❌ Error running backtest: {result.stderr}")
            return
        
        output = result.stdout
        print(output)
        
        # Parse the table output for trade details
        print(f"\n{'='*80}")
        print(f"📊 TRADE ANALYSIS & INSIGHTS")
        print(f"{'='*80}")
        
        # Extract performance metrics from output
        metrics = {}
        
        # Look for the performance table
        lines = output.split('\n')
        performance_section = False
        trade_section = False
        
        for line in lines:
            line = line.strip()
            
            # Performance metrics section
            if "Performance Metrics" in line:
                performance_section = True
                continue
            elif performance_section and "│" in line and "┃" not in line:
                # Parse metric lines like: │ Total Return  │ 0.08%  │
                parts = [p.strip() for p in line.split('│') if p.strip()]
                if len(parts) == 2:
                    metric_name = parts[0]
                    metric_value = parts[1]
                    metrics[metric_name] = metric_value
            
            # Trade statistics section  
            elif "Trade Statistics" in line:
                performance_section = False
                trade_section = True
                continue
            elif trade_section and "│" in line and "┃" not in line:
                parts = [p.strip() for p in line.split('│') if p.strip()]
                if len(parts) == 2:
                    metric_name = parts[0]
                    metric_value = parts[1] 
                    metrics[metric_name] = metric_value
        
        # Display extracted metrics with analysis
        if metrics:
            print(f"📈 PERFORMANCE ANALYSIS:")
            print(f"{'='*40}")
            
            total_return = metrics.get('Total Return', 'N/A')
            num_trades = metrics.get('Number of Trades', 'N/A')
            win_rate = metrics.get('Win Rate', 'N/A')
            profit_factor = metrics.get('Profit Factor', 'N/A')
            
            print(f"💰 Total Return: {total_return}")
            print(f"📊 Number of Trades: {num_trades}")
            print(f"🎯 Win Rate: {win_rate}")
            print(f"⚖️ Profit Factor: {profit_factor}")
            print()
        
        # Strategy-specific insights
        print(f"🔍 STRATEGY INSIGHTS: {strategy}")
        print(f"{'='*40}")
        
        if 'Momo' in strategy:
            print(f"📋 MOMENTUM STRATEGY ANALYSIS:")
            print(f"  🎯 Entry Conditions:")
            print(f"     • Price above 200 EMA (bullish regime)")
            print(f"     • RSI: 50-70 for long entries") 
            print(f"     • MACD signal crossover")
            print(f"     • Low volatility filter active")
            print()
            print(f"  🛑 Stop Loss Strategy:")
            print(f"     • 2.0 × ATR below entry price")
            print(f"     • Adaptive based on volatility")
            print()
            print(f"  🎯 Take Profit Strategy:")
            print(f"     • 3.0 × ATR above entry price")
            print(f"     • Target Risk/Reward: 1.5:1")
            print()
            
        elif 'MeanRev' in strategy:
            print(f"📋 MEAN REVERSION STRATEGY ANALYSIS:")
            print(f"  🎯 Entry Conditions:")
            print(f"     • Price at Bollinger Band extremes")
            print(f"     • RSI < 30 (oversold) or > 70 (overbought)")
            print(f"     • Williams %R confirmation")
            print()
            print(f"  🛑 Stop Loss Strategy:")
            print(f"     • 1.5 × ATR from entry")
            print(f"     • Conservative approach")
            print()
            print(f"  🎯 Take Profit Strategy:")
            print(f"     • 2.0 × ATR toward mean")
            print(f"     • Target Risk/Reward: 1.33:1")
            print()
        
        # Timeframe analysis
        print(f"⏰ TIMEFRAME ANALYSIS: {timeframe}")
        print(f"{'='*30}")
        
        timeframe_insights = {
            '15m': {
                'duration': '30min - 4 hours',
                'trades_per_day': '2-8',
                'volatility': 'High',
                'best_for': 'Scalping, quick momentum'
            },
            '1h': {
                'duration': '2-12 hours', 
                'trades_per_day': '1-4',
                'volatility': 'Medium',
                'best_for': 'Intraday swings, trend following'
            },
            '4h': {
                'duration': '12 hours - 3 days',
                'trades_per_day': '0.5-2',
                'volatility': 'Medium-Low',
                'best_for': 'Swing trading, position building'
            },
            '1d': {
                'duration': '3-21 days',
                'trades_per_day': '0.1-0.5', 
                'volatility': 'Low',
                'best_for': 'Position trading, long-term trends'
            }
        }
        
        tf_info = timeframe_insights.get(timeframe, {})
        if tf_info:
            print(f"  ⏱️ Expected Trade Duration: {tf_info.get('duration', 'Variable')}")
            print(f"  📊 Typical Trades/Day: {tf_info.get('trades_per_day', 'Variable')}")
            print(f"  🌊 Volatility Level: {tf_info.get('volatility', 'Unknown')}")
            print(f"  🎯 Best For: {tf_info.get('best_for', 'General trading')}")
        print()
        
        # Risk analysis
        print(f"⚖️ RISK ANALYSIS:")
        print(f"{'='*20}")
        max_dd = metrics.get('Max Drawdown', 'N/A')
        volatility = metrics.get('Volatility', 'N/A')
        
        print(f"  📉 Max Drawdown: {max_dd}")
        print(f"  🌊 Volatility: {volatility}")
        
        if num_trades != 'N/A':
            try:
                trade_count = int(num_trades)
                if trade_count < 10:
                    print(f"  ⚠️ Warning: Low sample size ({trade_count} trades)")
                    print(f"     Consider longer backtest period")
                elif trade_count > 100:
                    print(f"  ✅ Good sample size ({trade_count} trades)")
                    print(f"     Results statistically meaningful")
            except ValueError:
                pass
        
        print()
        print(f"💡 ACTIONABLE INSIGHTS:")
        print(f"{'='*25}")
        
        if win_rate != 'N/A':
            try:
                wr = float(win_rate.replace('%', ''))
                if wr > 70:
                    print(f"  ✅ Excellent win rate ({win_rate})")
                    print(f"     Strategy shows strong edge")
                elif wr > 50:
                    print(f"  ✅ Good win rate ({win_rate})")
                    print(f"     Positive expectancy likely")
                else:
                    print(f"  ⚠️ Low win rate ({win_rate})")
                    print(f"     Ensure profit factor > 2.0")
            except ValueError:
                pass
        
        if profit_factor != 'N/A':
            try:
                pf = float(profit_factor)
                if pf > 2.0:
                    print(f"  ✅ Strong profit factor ({profit_factor})")
                    print(f"     Wins significantly outweigh losses")
                elif pf > 1.0:
                    print(f"  ✅ Positive profit factor ({profit_factor})")
                    print(f"     Strategy is profitable")
                else:
                    print(f"  ❌ Poor profit factor ({profit_factor})")
                    print(f"     Strategy loses money")
            except ValueError:
                pass
        
        print()
        print(f"🚀 NEXT STEPS:")
        print(f"{'='*15}")
        print(f"  1. 📊 Run longer backtest (more data)")
        print(f"  2. 🔧 Optimize parameters if needed")
        print(f"  3. 📈 Test on different symbols")
        print(f"  4. 💰 Consider position sizing")
        print(f"  5. 🔍 Monitor live performance")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) >= 4:
        strategy = sys.argv[1]
        symbol = sys.argv[2]
        timeframe = sys.argv[3]
    else:
        # Use best performing combo
        strategy = "StrategyMomo"
        symbol = "ETH/USDT" 
        timeframe = "1h"
    
    analyze_backtest_output(strategy, symbol, timeframe)