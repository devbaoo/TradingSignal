"""
Command Line Interface for Trading Insight.
Provides commands for data downloading, backtesting, optimization, and live trading.
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import typer
    from rich.console import Console
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
    from rich import print as rprint
except ImportError:
    print("Please install required CLI dependencies:")
    print("pip install typer[all] rich")
    sys.exit(1)

from .utils import load_config, setup_logging, set_random_seed, get_logger
from .data import DataLoader
from .strategy.rule_based import create_strategy
from .backtest import BacktestEngine, BacktestConfig

app = typer.Typer(
    name="trading-insight",
    help="Trading Insight - Robust trading strategy development and testing framework",
    add_completion=False
)
console = Console()
logger = get_logger(__name__)


def load_system_config(config_path: str = "config/config.yaml") -> dict:
    """Load and validate system configuration."""
    try:
        config = load_config(config_path)
        
        # Setup logging
        log_config = config.get("logging", {})
        setup_logging(
            level=log_config.get("level", "INFO"),
            log_file=log_config.get("file"),
            include_timestamp=log_config.get("include_timestamp", True)
        )
        
        # Set random seed for reproducibility
        seed = config.get("system", {}).get("random_seed", 42)
        set_random_seed(seed)
        
        return config
        
    except Exception as e:
        console.print(f"[red]Error loading configuration: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def download(
    symbol: str = typer.Argument(..., help="Trading symbol (e.g., BTC/USDT)"),
    timeframe: str = typer.Option("1h", "--timeframe", "-t", help="Timeframe (e.g., 1h, 4h, 1d)"),
    since: str = typer.Option("2021-01-01", "--since", "-s", help="Start date (YYYY-MM-DD)"),
    to: Optional[str] = typer.Option(None, "--to", help="End date (YYYY-MM-DD)"),
    exchange: str = typer.Option("binance", "--exchange", "-e", help="Exchange name"),
    config_path: str = typer.Option("config/config.yaml", "--config", "-c", help="Config file path"),
    force: bool = typer.Option(False, "--force", "-f", help="Force reload (ignore cache)")
):
    """Download historical market data."""
    console.print(f"[bold blue]Downloading {symbol} data...[/bold blue]")
    
    try:
        config = load_system_config(config_path)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True
        ) as progress:
            task = progress.add_task(
                f"Downloading {symbol} {timeframe} data from {exchange}...", 
                total=None
            )
            
            loader = DataLoader(config)
            df = loader.load_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                since=since,
                to=to,
                exchange=exchange,
                force_reload=force
            )
            
            progress.update(task, completed=True)
        
        # Display results
        table = Table(title=f"{symbol} Data Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Symbol", symbol)
        table.add_row("Exchange", exchange)
        table.add_row("Timeframe", timeframe)
        table.add_row("Periods", str(len(df)))
        table.add_row("Date Range", f"{df.index[0].strftime('%Y-%m-%d')} to {df.index[-1].strftime('%Y-%m-%d')}")
        table.add_row("Price Range", f"${df['low'].min():.2f} - ${df['high'].max():.2f}")
        
        console.print(table)
        console.print(f"[green]✓ Data downloaded successfully![/green]")
        
    except Exception as e:
        console.print(f"[red]Error downloading data: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def backtest(
    strategy: str = typer.Argument(..., help="Strategy name (e.g., StrategyMomo)"),
    symbol: str = typer.Option("BTC/USDT", "--symbol", "-s", help="Trading symbol"),
    timeframe: str = typer.Option("1h", "--timeframe", "-t", help="Timeframe"),
    start: Optional[str] = typer.Option(None, "--start", help="Start date (YYYY-MM-DD)"),
    end: Optional[str] = typer.Option(None, "--end", help="End date (YYYY-MM-DD)"),
    initial_capital: float = typer.Option(10000, "--capital", "-k", help="Initial capital"),
    config_path: str = typer.Option("config/config.yaml", "--config", "-c", help="Config file path"),
):
    """Run strategy backtest."""
    console.print(f"[bold blue]Running backtest: {strategy} on {symbol} {timeframe}[/bold blue]")
    
    try:
        config = load_system_config(config_path)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True
        ) as progress:
            # Load data
            data_task = progress.add_task("Loading data...", total=None)
            
            loader = DataLoader(config)
            df = loader.load_ohlcv(symbol, timeframe, start, end)
            
            progress.update(data_task, completed=True)
            
            # Initialize strategy
            strategy_task = progress.add_task("Initializing strategy...", total=None)
            
            strategy_config = config.get("strategies", {}).get(strategy, {})
            strategy_instance = create_strategy(strategy, strategy_config)
            
            progress.update(strategy_task, completed=True)
            
            # Run backtest
            backtest_task = progress.add_task("Running backtest...", total=None)
            
            backtest_config = BacktestConfig(
                initial_capital=initial_capital,
                fee_rate=config.get("backtest", {}).get("fee_rate", 0.001),
                slippage_bps=config.get("backtest", {}).get("slippage_bps", 2.0)
            )
            
            engine = BacktestEngine(backtest_config)
            results = engine.run_backtest(df, strategy_instance, start, end)
            
            progress.update(backtest_task, completed=True)
        
        # Display results
        display_backtest_results(results)
        
        # Save results
        save_backtest_results(results, strategy, symbol, timeframe)
        
    except Exception as e:
        console.print(f"[red]Error running backtest: {e}[/red]")
        logger.exception("Backtest error")
        raise typer.Exit(1)


@app.command() 
def optimize(
    strategy: str = typer.Argument(..., help="Strategy name"),
    symbol: str = typer.Option("BTC/USDT", "--symbol", "-s", help="Trading symbol"),
    timeframe: str = typer.Option("1h", "--timeframe", "-t", help="Timeframe"),
    trials: int = typer.Option(100, "--trials", "-n", help="Number of optimization trials"),
    config_path: str = typer.Option("config/config.yaml", "--config", "-c", help="Config file path"),
):
    """Optimize strategy parameters."""
    console.print(f"[bold blue]Optimizing {strategy} on {symbol} {timeframe}[/bold blue]")
    console.print(f"[dim]Running {trials} trials...[/dim]")
    
    try:
        config = load_system_config(config_path)
        
        # Check if optuna is available
        try:
            from src.optimize import optimize_strategy_simple
        except ImportError as import_err:
            console.print(f"[red]Error: Optimization requires 'optuna'. Install with: pip install optuna[/red]")
            console.print(f"[dim]Import error: {import_err}[/dim]")
            raise typer.Exit(1)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
        ) as progress:
            
            task = progress.add_task("Optimizing parameters...", total=trials)
            
            # Run optimization
            try:
                results = optimize_strategy_simple(
                    strategy_name=strategy,
                    symbol=symbol,
                    timeframe=timeframe,
                    n_trials=trials
                )
                
                progress.update(task, completed=trials)
                
                # Display results
                console.print(f"\n[bold green]✅ Optimization completed![/bold green]")
                console.print(f"\n[bold]Best Parameters:[/bold]")
                
                best_params = results.best_params
                if best_params:
                    for param, value in best_params.items():
                        console.print(f"  {param}: {value}")
                
                console.print(f"\n[bold]Best Performance:[/bold]")
                console.print(f"  Objective Value: {results.best_value:.4f}")
                console.print(f"  Total Trials: {results.n_trials}")
                
                if hasattr(results, 'best_trial_metrics') and results.best_trial_metrics:
                    metrics = results.best_trial_metrics
                    console.print(f"  Total Return: {metrics.get('total_return', 'N/A')}")
                    console.print(f"  Win Rate: {metrics.get('win_rate', 'N/A')}")
                    console.print(f"  Profit Factor: {metrics.get('profit_factor', 'N/A')}")
                    console.print(f"  Max Drawdown: {metrics.get('max_drawdown', 'N/A')}")
                
                # Save results
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                results_file = f"runs/optimization_{strategy}_{symbol.replace('/', '_')}_{timeframe}_{timestamp}.json"
                
                results_dict = {
                    'strategy': strategy,
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'trials': trials,
                    'best_params': best_params,
                    'best_value': results.best_value,
                    'timestamp': timestamp
                }
                
                import json
                with open(results_file, 'w') as f:
                    json.dump(results_dict, f, indent=2, default=str)
                
                console.print(f"\n[dim]Results saved to: {results_file}[/dim]")
                
            except Exception as opt_error:
                progress.update(task, completed=trials)
                console.print(f"[red]Optimization failed: {opt_error}[/red]")
                raise typer.Exit(1)
                
    except Exception as e:
        console.print(f"[red]Error running optimization: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def signal(
    symbol: str = typer.Option("BTC/USDT", "--symbol", "-s", help="Trading symbol"),
    timeframe: str = typer.Option("1h", "--timeframe", "-t", help="Timeframe"),
    strategy: str = typer.Option("StrategyMomo", "--strategy", help="Strategy name"),
    account_balance: float = typer.Option(10000, "--balance", "-b", help="Account balance in USDT"),
    min_safety: int = typer.Option(6, "--min-safety", help="Minimum safety score (1-10)"),
    config_path: str = typer.Option("config/config.yaml", "--config", "-c", help="Config file path"),
):
    """Generate live trading signal with specific parameters."""
    
    console.print(f"[bold blue]Generating Trading Signal[/bold blue]")
    console.print(f"[dim]{symbol} {timeframe} using {strategy}[/dim]")
    
    try:
        config = load_system_config(config_path)
        config['account_balance'] = account_balance
        
        # Import signal generator
        try:
            from src.signals import TradingSignalGenerator
        except ImportError as e:
            console.print(f"[red]Error importing signal generator: {e}[/red]")
            raise typer.Exit(1)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
        ) as progress:
            
            # Initialize signal generator
            init_task = progress.add_task("Initializing signal generator...", total=None)
            generator = TradingSignalGenerator(config)
            progress.update(init_task, completed=True)
            
            # Generate signal
            signal_task = progress.add_task("Analyzing market and generating signal...", total=None)
            signal = generator.generate_signal(symbol, timeframe, strategy)
            progress.update(signal_task, completed=True)
        
        if signal and signal.safety_score >= min_safety:
            # Display the signal
            console.print(f"\n[bold green]🎯 TRADING SIGNAL GENERATED![/bold green]")
            console.print(signal.trading_command)
            
            # Save signal to file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            signal_file = f"trading_signals/signal_{symbol.replace('/', '_')}_{timestamp}.json"
            
            from pathlib import Path
            from src.utils import ensure_directory
            
            signals_dir = Path("trading_signals")
            ensure_directory(signals_dir)
            
            # Convert signal to dict for JSON
            signal_dict = {
                'symbol': signal.symbol,
                'direction': signal.direction,
                'timestamp': signal.timestamp.isoformat(),
                'strategy': signal.strategy_name,
                'timeframe': signal.timeframe,
                'entry_price': signal.entry_price,
                'entry_range': signal.entry_price_range,
                'stop_loss': signal.stop_loss,
                'take_profit': signal.take_profit,
                'recommended_leverage': signal.recommended_leverage,
                'position_size_usdt': signal.position_size_usdt,
                'position_size_percent': signal.position_size_percent,
                'safety_score': signal.safety_score,
                'confidence_level': signal.confidence_level,
                'risk_level': signal.risk_level,
                'risk_reward_ratio': signal.risk_reward_ratio,
                'execution_notes': signal.execution_notes,
                'validity_period': signal.validity_period
            }
            
            import json
            with open(signal_file, 'w') as f:
                json.dump(signal_dict, f, indent=2, default=str)
            
            console.print(f"\n[green]💾 Signal saved to: {signal_file}[/green]")
            
            # Quick copy-paste format
            console.print(f"\n[bold yellow]📋 QUICK COPY-PASTE FORMAT:[/bold yellow]")
            console.print(f"[cyan]{signal.symbol} {signal.direction}[/cyan]")
            console.print(f"[cyan]Entry: ${signal.entry_price:,.4f}[/cyan]") 
            console.print(f"[cyan]SL: ${signal.stop_loss:,.4f}[/cyan]")
            console.print(f"[cyan]TP1: ${signal.take_profit[0]:,.4f}[/cyan]")
            console.print(f"[cyan]Leverage: {signal.recommended_leverage}x[/cyan]")
            console.print(f"[cyan]Size: ${signal.position_size_usdt:,.0f} ({signal.position_size_percent:.1f}%)[/cyan]")
            
        elif signal:
            console.print(f"\n[yellow]⚠️ Signal generated but safety score too low[/yellow]")
            console.print(f"[dim]Safety score: {signal.safety_score}/{min_safety} (minimum required)[/dim]")
            console.print(f"[dim]Try lowering --min-safety parameter or wait for better conditions[/dim]")
        else:
            console.print(f"\n[red]❌ No trading signal generated[/red]")
            console.print(f"[dim]Market conditions may not meet strategy criteria[/dim]")
        
    except Exception as e:
        console.print(f"[red]Error generating signal: {e}[/red]")
        logger.exception("Signal generation error")
        raise typer.Exit(1)


@app.command()
def live(
    strategy: str = typer.Argument(..., help="Strategy name"),
    symbol: str = typer.Option("BTC/USDT", "--symbol", "-s", help="Trading symbol"),
    timeframe: str = typer.Option("15m", "--timeframe", "-t", help="Timeframe"),
    exchange: str = typer.Option("binance", "--exchange", "-e", help="Exchange"),
    paper: bool = typer.Option(True, "--paper", help="Paper trading mode"),
    config_path: str = typer.Option("config/config.yaml", "--config", "-c", help="Config file path"),
):
    """Run live/paper trading."""
    console.print(f"[bold yellow]Live trading not yet implemented[/bold yellow]")
    console.print("This feature will be available in a future update.")
    
    if not paper:
        console.print("[red]WARNING: Live trading with real money is not yet supported![/red]")


@app.command()
def report(
    run_id: Optional[str] = typer.Argument(None, help="Backtest run ID"),
    config_path: str = typer.Option("config/config.yaml", "--config", "-c", help="Config file path"),
):
    """Generate detailed backtest report."""
    console.print(f"[bold yellow]Reporting not yet implemented[/bold yellow]")
    console.print("This feature will be available in a future update.")


@app.command()
def list_strategies(
    config_path: str = typer.Option("config/config.yaml", "--config", "-c", help="Config file path"),
):
    """List available strategies."""
    console.print("[bold blue]Available Strategies[/bold blue]")
    
    try:
        config = load_system_config(config_path)
        strategies = config.get("strategies", {})
        
        table = Table()
        table.add_column("Strategy", style="cyan")
        table.add_column("Description", style="white")
        table.add_column("Allow Short", style="yellow")
        table.add_column("Risk/Trade", style="green")
        
        strategy_descriptions = {
            "StrategyMomo": "Momentum strategy using EMA, RSI, and MACD signals",
            "StrategyMeanRev": "Mean reversion using Bollinger Bands and RSI"
        }
        
        for strategy_name, strategy_config in strategies.items():
            description = strategy_descriptions.get(strategy_name, "Custom strategy")
            allow_short = "Yes" if strategy_config.get("allow_short", False) else "No"
            risk_per_trade = f"{strategy_config.get('risk_per_trade', 0.02)*100:.1f}%"
            
            table.add_row(strategy_name, description, allow_short, risk_per_trade)
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]Error listing strategies: {e}[/red]")


@app.command()
def validate_config(
    config_path: str = typer.Option("config/config.yaml", "--config", "-c", help="Config file path"),
):
    """Validate configuration file."""
    console.print(f"[bold blue]Validating configuration: {config_path}[/bold blue]")
    
    try:
        config = load_system_config(config_path)
        
        # Check required sections
        required_sections = ["data_dir", "exchanges", "strategies", "backtest", "risk"]
        missing_sections = []
        
        for section in required_sections:
            if section not in config:
                missing_sections.append(section)
        
        if missing_sections:
            console.print(f"[red]Missing required sections: {', '.join(missing_sections)}[/red]")
        else:
            console.print("[green]✓ All required sections present[/green]")
        
        # Validate strategy configurations
        strategies = config.get("strategies", {})
        if not strategies:
            console.print("[yellow]⚠ No strategies configured[/yellow]")
        else:
            console.print(f"[green]✓ {len(strategies)} strategies configured[/green]")
        
        # Validate exchange configurations
        exchanges = config.get("exchanges", {})
        if not exchanges:
            console.print("[yellow]⚠ No exchanges configured[/yellow]")
        else:
            console.print(f"[green]✓ {len(exchanges)} exchanges configured[/green]")
        
        console.print("[green]Configuration validation completed[/green]")
        
    except Exception as e:
        console.print(f"[red]Configuration validation failed: {e}[/red]")
        raise typer.Exit(1)


def display_backtest_results(results):
    """Display backtest results in a formatted table."""
    metrics = results.metrics
    
    # Performance metrics table
    perf_table = Table(title="Performance Metrics")
    perf_table.add_column("Metric", style="cyan")
    perf_table.add_column("Value", style="green")
    
    perf_table.add_row("Total Return", f"{metrics.get('total_return', 0)*100:.2f}%")
    perf_table.add_row("CAGR", f"{metrics.get('cagr', 0)*100:.2f}%")
    perf_table.add_row("Sharpe Ratio", f"{metrics.get('sharpe_ratio', 0):.2f}")
    perf_table.add_row("Sortino Ratio", f"{metrics.get('sortino_ratio', 0):.2f}")
    perf_table.add_row("Max Drawdown", f"{metrics.get('max_drawdown', 0)*100:.2f}%")
    perf_table.add_row("Volatility", f"{metrics.get('volatility', 0)*100:.2f}%")
    
    console.print(perf_table)
    
    # Trade statistics table
    trade_table = Table(title="Trade Statistics")
    trade_table.add_column("Metric", style="cyan")
    trade_table.add_column("Value", style="green")
    
    trade_table.add_row("Number of Trades", str(metrics.get('n_trades', 0)))
    trade_table.add_row("Win Rate", f"{metrics.get('win_rate', 0)*100:.2f}%")
    trade_table.add_row("Profit Factor", f"{metrics.get('profit_factor', 0):.2f}")
    trade_table.add_row("Expectancy", f"${metrics.get('expectancy', 0):.2f}")
    trade_table.add_row("Average Win", f"${metrics.get('avg_win', 0):.2f}")
    trade_table.add_row("Average Loss", f"${metrics.get('avg_loss', 0):.2f}")
    trade_table.add_row("Total Fees", f"${metrics.get('total_fees', 0):.2f}")
    
    console.print(trade_table)
    
    # Recent trades (last 5)
    if results.trades:
        recent_trades = results.trades[-5:]
        trades_table = Table(title="Recent Trades (Last 5)")
        trades_table.add_column("Symbol")
        trades_table.add_column("Side") 
        trades_table.add_column("Entry")
        trades_table.add_column("Exit")
        trades_table.add_column("P&L")
        trades_table.add_column("P&L %")
        trades_table.add_column("Exit Reason")
        
        for trade in recent_trades:
            pnl_color = "green" if trade.pnl > 0 else "red"
            trades_table.add_row(
                trade.symbol,
                trade.side,
                f"${trade.entry_price:.4f}",
                f"${trade.exit_price:.4f}",
                f"[{pnl_color}]${trade.pnl:.2f}[/{pnl_color}]",
                f"[{pnl_color}]{trade.pnl_pct*100:.2f}%[/{pnl_color}]",
                trade.exit_reason
            )
        
        console.print(trades_table)


def save_backtest_results(results, strategy: str, symbol: str, timeframe: str):
    """Save backtest results to file."""
    try:
        # Create runs directory
        runs_dir = Path("runs")
        runs_dir.mkdir(exist_ok=True)
        
        # Generate timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create filename
        symbol_clean = symbol.replace("/", "_")
        filename = f"{strategy}_{symbol_clean}_{timeframe}_{timestamp}.txt"
        
        filepath = runs_dir / filename
        
        # Save summary to text file
        with open(filepath, 'w') as f:
            f.write(f"Trading Insight Backtest Results\n")
            f.write(f"================================\n\n")
            f.write(f"Strategy: {strategy}\n")
            f.write(f"Symbol: {symbol}\n")
            f.write(f"Timeframe: {timeframe}\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            # Performance metrics
            metrics = results.metrics
            f.write("Performance Metrics:\n")
            f.write(f"- Total Return: {metrics.get('total_return', 0)*100:.2f}%\n")
            f.write(f"- CAGR: {metrics.get('cagr', 0)*100:.2f}%\n")
            f.write(f"- Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}\n")
            f.write(f"- Max Drawdown: {metrics.get('max_drawdown', 0)*100:.2f}%\n")
            f.write(f"- Number of Trades: {metrics.get('n_trades', 0)}\n")
            f.write(f"- Win Rate: {metrics.get('win_rate', 0)*100:.2f}%\n")
            f.write(f"- Profit Factor: {metrics.get('profit_factor', 0):.2f}\n")
        
        console.print(f"[green]Results saved to: {filepath}[/green]")
        
    except Exception as e:
        logger.warning(f"Failed to save results: {e}")


def main():
    """Main entry point for the CLI."""
    try:
        app()
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user[/yellow]")
        raise typer.Exit(0)
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    main()