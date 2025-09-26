#!/usr/bin/env python3
"""
Detailed Trade Analysis Tool
Analyzes backtest results in detail by parsing the saved trade logs.
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path
import glob
from datetime import datetime
import re

def analyze_latest_backtest(strategy_name: str = None, symbol: str = None, timeframe: str = None):
    """Analyze the most recent backtest results in detail."""
    
    runs_dir = Path("runs")
    if not runs_dir.exists():
        print("❌ No runs directory found. Please run a backtest first.")
        return
    
    # Find matching result files
    pattern = "*.txt"
    if strategy_name:
        pattern = f"{strategy_name}*{pattern}"
    if symbol:
        clean_symbol = symbol.replace("/", "_")
        pattern = f"*{clean_symbol}*{pattern}"
    if timeframe:
        pattern = f"*{timeframe}*{pattern}"
    
    result_files = list(runs_dir.glob(pattern))
    
    if not result_files:
        print(f"❌ No backtest results found matching: {pattern}")
        print("Available files:")
        for f in runs_dir.glob("*.txt"):
            print(f"  📁 {f.name}")
        return
    
    # Get the most recent file
    latest_file = max(result_files, key=lambda p: p.stat().st_mtime)
    
    print(f"\n{'='*80}")
    print(f"📊 ANALYZING BACKTEST RESULTS")
    print(f"{'='*80}")
    print(f"� File: {latest_file.name}")
    print(f"� Modified: {datetime.fromtimestamp(latest_file.stat().st_mtime)}")
    print()
    
    # Parse the result file
    content = latest_file.read_text()
    
    # Extract basic info
    strategy_match = re.search(r'Strategy: (.+)', content)
    symbol_match = re.search(r'Symbol: (.+)', content)
    timeframe_match = re.search(r'Timeframe: (.+)', content)
    
    strategy_name = strategy_match.group(1) if strategy_match else "Unknown"
    symbol = symbol_match.group(1) if symbol_match else "Unknown"  
    timeframe = timeframe_match.group(1) if timeframe_match else "Unknown"
    
    print(f"🎯 Strategy: {strategy_name}")
    print(f"📊 Symbol: {symbol}")
    print(f"⏰ Timeframe: {timeframe}")
    print()
    
    # Extract performance metrics
    metrics = {}
    metric_patterns = {
        'Total Return': r'Total Return: ([\d.-]+)%',
        'CAGR': r'CAGR: ([\d.-]+)%',
        'Sharpe Ratio': r'Sharpe Ratio: ([\d.-]+)',
        'Max Drawdown': r'Max Drawdown: -([\d.-]+)%',
        'Number of Trades': r'Number of Trades: (\d+)',
        'Win Rate': r'Win Rate: ([\d.-]+)%',
        'Profit Factor': r'Profit Factor: ([\d.-]+)'
    }
    
    for metric, pattern in metric_patterns.items():
        match = re.search(pattern, content)
        if match:
            try:
                value = float(match.group(1))
                metrics[metric] = value
            except ValueError:
                metrics[metric] = match.group(1)
    
    # Display performance summary
    print(f"📈 PERFORMANCE SUMMARY")
    print(f"{'='*40}")
    for metric, value in metrics.items():
        if isinstance(value, float):
            if 'Rate' in metric or 'Return' in metric or 'Drawdown' in metric:
                print(f"{metric:20}: {value:+6.2f}%")
            else:
                print(f"{metric:20}: {value:8.2f}")
        else:
            print(f"{metric:20}: {value}")
    print()
    
    # Now let's run a fresh backtest to get detailed trade info
    print(f"🔍 Running detailed analysis...")
    return analyze_trades_detailed_simple(strategy_name, symbol, timeframe)

def analyze_trades_detailed_simple(strategy_name: str, symbol: str, timeframe: str):
    """Run a simple analysis using the CLI backtest but capture more details."""
    
    import subprocess
    import tempfile
    import os
    
    # Create a temporary script to capture detailed backtest results
    temp_script = '''
import sys
sys.path.append("src")

from src.utils import load_config, setup_logging, get_logger
from src.data import DataLoader
from src.strategy.rule_based import create_strategy
from src.backtest import BacktestEngine
from src.risk import RiskManager

# Setup
setup_logging()
config = load_config("config/config.yaml")
data_loader = DataLoader(config)

# Load data
print("Loading data...")
data = data_loader.load_ohlcv("{symbol}", "{timeframe}")
print(f"Loaded {len(data)} periods from {data.index[0]} to {data.index[-1]}")

# Initialize components
strategy = create_strategy("{strategy_name}", config.get('strategies', {{}}).get('{strategy_name}', {{}}))
risk_manager = RiskManager(config)
risk_manager.set_initial_capital(10000.0)

# Run backtest
backtest_engine = BacktestEngine()
results = backtest_engine.run_backtest(
    data=data,
    strategy=strategy,
    risk_manager=risk_manager,
    symbol="{symbol}",
    initial_capital=10000.0
)

# Extract detailed trade info
trades = results.get('trades', [])
print(f"\\n📊 Found {len(trades)} trades")

for i, trade in enumerate(trades):
    print(f"\\n=== TRADE {i+1} ===")
    print(f"Entry: {trade.get('entry_time')} at ${trade.get('entry_price', 0):.4f}")
    print(f"Exit:  {trade.get('exit_time')} at ${trade.get('exit_price', 0):.4f}")
    print(f"P&L: ${trade.get('pnl', 0):.2f}")
    print(f"Duration: {trade.get('duration', 'N/A')}")
    print(f"Side: {trade.get('side', 'N/A')}")
    print(f"Quantity: {trade.get('quantity', 0):.6f}")
    print(f"Exit Reason: {trade.get('exit_reason', 'N/A')}")
'''.format(strategy_name=strategy_name, symbol=symbol, timeframe=timeframe)
    
    try:
        # Write and execute temporary script
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(temp_script)
            temp_file = f.name
        
        # Run the script
        result = subprocess.run([sys.executable, temp_file], 
                              capture_output=True, text=True, cwd='.')
        
        print(result.stdout)
        if result.stderr:
            print(f"Errors: {result.stderr}")
        
        # Clean up
        os.unlink(temp_file)
        
    except Exception as e:
        print(f"❌ Error running detailed analysis: {e}")
        
        # Fallback: Show what we can from existing data  
        print(f"\n📋 TRADE ANALYSIS RECOMMENDATIONS")
        print(f"{'='*50}")
        print(f"Based on the {strategy_name} strategy:")
        print()
        
        if 'Momo' in strategy_name:
            print(f"🎯 ENTRY CONDITIONS:")
            print(f"  • Price above 200 EMA (bullish regime)")
            print(f"  • RSI between 50-70 for long entries")
            print(f"  • MACD signal line crossing above")
            print(f"  • Low volatility environment")
            print()
            print(f"� STOP LOSS:")
            print(f"  • Typically 2.0 × ATR below entry")
            print(f"  • Dynamic based on market volatility")
            print()
            print(f"🎯 TAKE PROFIT:")
            print(f"  • Typically 3.0 × ATR above entry") 
            print(f"  • Risk/Reward ratio: ~1.5:1")
            print()
            
        elif 'MeanRev' in strategy_name:
            print(f"🎯 ENTRY CONDITIONS:")
            print(f"  • Price touching Bollinger Band extremes")
            print(f"  • RSI < 30 (oversold) or > 70 (overbought)")
            print(f"  • Williams %R confirming reversal")
            print(f"  • Low volatility preferred")
            print()
            print(f"🛑 STOP LOSS:")
            print(f"  • Typically 1.5 × ATR from entry")
            print(f"  • Conservative approach")
            print()
            print(f"🎯 TAKE PROFIT:")
            print(f"  • Typically 2.0 × ATR toward mean")
            print(f"  • Risk/Reward ratio: ~1.33:1")
            print()
        
        print(f"⏱️ TYPICAL TRADE DURATION:")
        print(f"  • {timeframe} timeframe: {get_expected_duration(timeframe)}")
        print()
        
        print(f"💡 TO GET DETAILED TRADE DATA:")
        print(f"  1. Check your backtest results in runs/")
        print(f"  2. Look at entry/exit prices in the CLI output") 
        print(f"  3. Use the backtest engine's debug mode")
        print(f"  4. Run: python main.py backtest {strategy_name} --symbol {symbol} --timeframe {timeframe}")

def get_expected_duration(timeframe):
    """Get expected trade duration based on timeframe."""
    duration_map = {
        '15m': '2-8 hours',
        '1h': '4-24 hours', 
        '4h': '1-7 days',
        '1d': '3-30 days'
    }
    return duration_map.get(timeframe, 'Variable')

if __name__ == "__main__":
    if len(sys.argv) >= 4:
        strategy_name = sys.argv[1]
        symbol = sys.argv[2]
        timeframe = sys.argv[3]
        analyze_latest_backtest(strategy_name, symbol, timeframe)
    else:
        # Analyze the most recent backtest
        analyze_latest_backtest()