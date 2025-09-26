"""
Reporting Module for Trading Insight.
Provides comprehensive reporting, visualizations, and analytics for backtest results.
"""

import base64
import io
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

import numpy as np
import pandas as pd

try:
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.patches import Rectangle
    import seaborn as sns
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    plt = None
    sns = None

try:
    import plotly.graph_objects as go
    import plotly.express as px
    from plotly.subplots import make_subplots
    import plotly.offline as pyo
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    go = None
    px = None

from .utils import get_logger, ensure_dir
from .backtest import BacktestResults

logger = get_logger(__name__)

# Suppress warnings
warnings.filterwarnings("ignore", category=UserWarning)
if MATPLOTLIB_AVAILABLE:
    plt.style.use('default')


@dataclass
class ReportConfig:
    """Configuration for report generation."""
    
    # Output settings
    output_dir: str = "reports"
    report_name: Optional[str] = None
    include_plots: bool = True
    plot_format: str = "html"  # html, png, svg
    
    # Plot settings
    plot_width: int = 1200
    plot_height: int = 600
    dpi: int = 100
    color_scheme: str = "default"  # default, dark, colorblind
    
    # Content settings
    include_trades: bool = True
    include_drawdown: bool = True
    include_monthly_returns: bool = True
    include_correlations: bool = False
    max_trades_display: int = 50
    
    # Export settings
    export_csv: bool = True
    export_html: bool = True
    export_pdf: bool = False
    
    # Template settings
    template: str = "default"  # default, minimal, detailed
    
    def __post_init__(self):
        """Post-initialization setup."""
        # Set color scheme
        self.colors = self._get_color_scheme()
        
    def _get_color_scheme(self) -> Dict[str, str]:
        """Get color scheme for plots."""
        if self.color_scheme == "dark":
            return {
                'background': '#1e1e1e',
                'text': '#ffffff',
                'grid': '#444444',
                'positive': '#00ff00',
                'negative': '#ff0000',
                'neutral': '#0080ff',
                'accent': '#ffa500'
            }
        elif self.color_scheme == "colorblind":
            return {
                'background': '#ffffff',
                'text': '#000000',
                'grid': '#cccccc',
                'positive': '#0173B2',
                'negative': '#DE8F05',
                'neutral': '#029E73',
                'accent': '#CC78BC'
            }
        else:  # default
            return {
                'background': '#ffffff',
                'text': '#000000',
                'grid': '#cccccc',
                'positive': '#2E8B57',
                'negative': '#DC143C',
                'neutral': '#4682B4',
                'accent': '#FF6347'
            }


@dataclass 
class ReportSummary:
    """Summary statistics for the report."""
    
    # Performance metrics
    total_return: float
    cagr: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    max_drawdown_duration: int
    volatility: float
    skewness: float
    kurtosis: float
    
    # Trade statistics
    n_trades: int
    n_winning_trades: int
    n_losing_trades: int
    win_rate: float
    profit_factor: float
    expectancy: float
    avg_win: float
    avg_loss: float
    best_trade: float
    worst_trade: float
    
    # Time-based metrics
    trading_days: int
    avg_trades_per_day: float
    avg_hold_time: float
    
    # Risk metrics
    var_95: float
    cvar_95: float
    beta: Optional[float] = None
    alpha: Optional[float] = None
    
    @classmethod
    def from_backtest_results(cls, results: BacktestResults) -> 'ReportSummary':
        """Create summary from backtest results."""
        metrics = results.metrics
        
        # Calculate additional metrics
        returns = results.returns if hasattr(results, 'returns') else pd.Series([])
        var_95 = returns.quantile(0.05) if len(returns) > 0 else 0
        cvar_95 = returns[returns <= var_95].mean() if len(returns) > 0 and var_95 != 0 else 0
        
        trade_durations = []
        if results.trades:
            for trade in results.trades:
                if hasattr(trade, 'duration') and trade.duration:
                    trade_durations.append(trade.duration)
        
        avg_hold_time = np.mean(trade_durations) if trade_durations else 0
        
        return cls(
            total_return=metrics.get('total_return', 0),
            cagr=metrics.get('cagr', 0),
            sharpe_ratio=metrics.get('sharpe_ratio', 0),
            sortino_ratio=metrics.get('sortino_ratio', 0),
            max_drawdown=metrics.get('max_drawdown', 0),
            max_drawdown_duration=metrics.get('max_drawdown_duration', 0),
            volatility=metrics.get('volatility', 0),
            skewness=metrics.get('skewness', 0),
            kurtosis=metrics.get('kurtosis', 0),
            n_trades=metrics.get('n_trades', 0),
            n_winning_trades=metrics.get('n_winning_trades', 0),
            n_losing_trades=metrics.get('n_losing_trades', 0),
            win_rate=metrics.get('win_rate', 0),
            profit_factor=metrics.get('profit_factor', 0),
            expectancy=metrics.get('expectancy', 0),
            avg_win=metrics.get('avg_win', 0),
            avg_loss=metrics.get('avg_loss', 0),
            best_trade=metrics.get('best_trade', 0),
            worst_trade=metrics.get('worst_trade', 0),
            trading_days=metrics.get('trading_days', 0),
            avg_trades_per_day=metrics.get('avg_trades_per_day', 0),
            avg_hold_time=avg_hold_time,
            var_95=var_95,
            cvar_95=cvar_95
        )


class ReportGenerator:
    """Generate comprehensive trading reports."""
    
    def __init__(self, config: ReportConfig):
        self.config = config
        
        # Check dependencies
        if self.config.include_plots and not (MATPLOTLIB_AVAILABLE or PLOTLY_AVAILABLE):
            logger.warning("No plotting library available. Plots will be disabled.")
            self.config.include_plots = False
            
        # Create output directory
        ensure_dir(Path(self.config.output_dir))
        
    def generate_report(self, 
                       results: BacktestResults,
                       strategy_name: str,
                       symbol: str,
                       timeframe: str,
                       additional_data: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """Generate comprehensive trading report."""
        logger.info(f"Generating report for {strategy_name} on {symbol} {timeframe}")
        
        # Create report summary
        summary = ReportSummary.from_backtest_results(results)
        
        # Create report name
        if self.config.report_name:
            report_name = self.config.report_name
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            symbol_clean = symbol.replace("/", "_")
            report_name = f"{strategy_name}_{symbol_clean}_{timeframe}_{timestamp}"
        
        # Create report directory
        report_dir = Path(self.config.output_dir) / report_name
        ensure_dir(report_dir)
        
        generated_files = {}
        
        # Generate plots
        plots = {}
        if self.config.include_plots:
            plots = self._generate_plots(results, summary, report_dir)
            
        # Generate CSV exports
        if self.config.export_csv:
            csv_files = self._export_csv(results, report_dir)
            generated_files.update(csv_files)
            
        # Generate HTML report
        if self.config.export_html:
            html_file = self._generate_html_report(
                results, summary, strategy_name, symbol, timeframe, 
                plots, report_dir, additional_data
            )
            generated_files['html'] = html_file
            
        # Generate PDF report
        if self.config.export_pdf:
            # PDF generation would require additional dependencies
            logger.warning("PDF export not implemented yet")
            
        logger.info(f"Report generated: {report_dir}")
        return generated_files
        
    def _generate_plots(self, 
                       results: BacktestResults, 
                       summary: ReportSummary,
                       output_dir: Path) -> Dict[str, str]:
        """Generate all plots for the report."""
        plots = {}
        
        try:
            # 1. Equity curve
            if hasattr(results, 'equity_curve') and len(results.equity_curve) > 0:
                plot_file = self._plot_equity_curve(results.equity_curve, output_dir)
                if plot_file:
                    plots['equity_curve'] = plot_file
                    
            # 2. Drawdown chart
            if self.config.include_drawdown and hasattr(results, 'drawdown') and len(results.drawdown) > 0:
                plot_file = self._plot_drawdown(results.drawdown, output_dir)
                if plot_file:
                    plots['drawdown'] = plot_file
                    
            # 3. Monthly returns heatmap
            if self.config.include_monthly_returns and hasattr(results, 'returns'):
                plot_file = self._plot_monthly_returns(results.returns, output_dir)
                if plot_file:
                    plots['monthly_returns'] = plot_file
                    
            # 4. Trade analysis
            if self.config.include_trades and results.trades:
                plot_file = self._plot_trade_analysis(results.trades, output_dir)
                if plot_file:
                    plots['trade_analysis'] = plot_file
                    
            # 5. Returns distribution
            if hasattr(results, 'returns') and len(results.returns) > 0:
                plot_file = self._plot_returns_distribution(results.returns, output_dir)
                if plot_file:
                    plots['returns_distribution'] = plot_file
                    
        except Exception as e:
            logger.warning(f"Error generating plots: {e}")
            
        return plots
        
    def _plot_equity_curve(self, equity_curve: pd.Series, output_dir: Path) -> Optional[str]:
        """Plot equity curve."""
        try:
            if PLOTLY_AVAILABLE and self.config.plot_format == "html":
                fig = go.Figure()
                
                fig.add_trace(go.Scatter(
                    x=equity_curve.index,
                    y=equity_curve.values,
                    mode='lines',
                    name='Portfolio Value',
                    line=dict(color=self.config.colors['positive'], width=2)
                ))
                
                fig.update_layout(
                    title='Portfolio Equity Curve',
                    xaxis_title='Date',
                    yaxis_title='Portfolio Value ($)',
                    width=self.config.plot_width,
                    height=self.config.plot_height,
                    template='plotly_white'
                )
                
                filename = output_dir / "equity_curve.html"
                fig.write_html(filename)
                return str(filename)
                
            elif MATPLOTLIB_AVAILABLE:
                fig, ax = plt.subplots(figsize=(12, 6))
                
                ax.plot(equity_curve.index, equity_curve.values, 
                       color=self.config.colors['positive'], linewidth=2)
                
                ax.set_title('Portfolio Equity Curve', fontsize=14, fontweight='bold')
                ax.set_xlabel('Date')
                ax.set_ylabel('Portfolio Value ($)')
                ax.grid(True, alpha=0.3)
                
                # Format x-axis
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
                ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
                plt.xticks(rotation=45)
                
                plt.tight_layout()
                
                filename = output_dir / "equity_curve.png"
                plt.savefig(filename, dpi=self.config.dpi, bbox_inches='tight')
                plt.close()
                
                return str(filename)
                
        except Exception as e:
            logger.warning(f"Error plotting equity curve: {e}")
            
        return None
        
    def _plot_drawdown(self, drawdown: pd.Series, output_dir: Path) -> Optional[str]:
        """Plot drawdown chart."""
        try:
            if PLOTLY_AVAILABLE and self.config.plot_format == "html":
                fig = go.Figure()
                
                fig.add_trace(go.Scatter(
                    x=drawdown.index,
                    y=drawdown.values * 100,
                    fill='tozeroy',
                    mode='lines',
                    name='Drawdown',
                    line=dict(color=self.config.colors['negative'], width=1),
                    fillcolor=f"rgba(220, 20, 60, 0.3)"
                ))
                
                fig.update_layout(
                    title='Portfolio Drawdown',
                    xaxis_title='Date',
                    yaxis_title='Drawdown (%)',
                    width=self.config.plot_width,
                    height=self.config.plot_height,
                    template='plotly_white'
                )
                
                filename = output_dir / "drawdown.html"
                fig.write_html(filename)
                return str(filename)
                
            elif MATPLOTLIB_AVAILABLE:
                fig, ax = plt.subplots(figsize=(12, 4))
                
                ax.fill_between(drawdown.index, drawdown.values * 100, 0,
                               color=self.config.colors['negative'], alpha=0.3)
                ax.plot(drawdown.index, drawdown.values * 100,
                       color=self.config.colors['negative'], linewidth=1)
                
                ax.set_title('Portfolio Drawdown', fontsize=14, fontweight='bold')
                ax.set_xlabel('Date')
                ax.set_ylabel('Drawdown (%)')
                ax.grid(True, alpha=0.3)
                
                # Format x-axis
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
                ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
                plt.xticks(rotation=45)
                
                plt.tight_layout()
                
                filename = output_dir / "drawdown.png"
                plt.savefig(filename, dpi=self.config.dpi, bbox_inches='tight')
                plt.close()
                
                return str(filename)
                
        except Exception as e:
            logger.warning(f"Error plotting drawdown: {e}")
            
        return None
        
    def _plot_monthly_returns(self, returns: pd.Series, output_dir: Path) -> Optional[str]:
        """Plot monthly returns heatmap."""
        try:
            # Calculate monthly returns
            monthly_returns = returns.resample('M').apply(lambda x: (1 + x).prod() - 1)
            monthly_returns.index = monthly_returns.index.strftime('%Y-%m')
            
            if len(monthly_returns) < 2:
                return None
                
            # Create pivot table for heatmap
            monthly_df = pd.DataFrame({
                'date': monthly_returns.index,
                'return': monthly_returns.values * 100
            })
            monthly_df['year'] = pd.to_datetime(monthly_df['date']).dt.year
            monthly_df['month'] = pd.to_datetime(monthly_df['date']).dt.month
            
            pivot_table = monthly_df.pivot(index='year', columns='month', values='return')
            
            if MATPLOTLIB_AVAILABLE:
                fig, ax = plt.subplots(figsize=(12, 6))
                
                # Create heatmap
                im = ax.imshow(pivot_table.values, cmap='RdYlGn', aspect='auto')
                
                # Set ticks and labels
                ax.set_xticks(range(len(pivot_table.columns)))
                ax.set_xticklabels([f"M{i}" for i in pivot_table.columns])
                ax.set_yticks(range(len(pivot_table.index)))
                ax.set_yticklabels(pivot_table.index)
                
                # Add colorbar
                cbar = plt.colorbar(im, ax=ax)
                cbar.set_label('Monthly Return (%)')
                
                # Add text annotations
                for i in range(len(pivot_table.index)):
                    for j in range(len(pivot_table.columns)):
                        if not pd.isna(pivot_table.iloc[i, j]):
                            text = ax.text(j, i, f'{pivot_table.iloc[i, j]:.1f}%',
                                         ha="center", va="center", color="black", fontsize=8)
                
                ax.set_title('Monthly Returns Heatmap', fontsize=14, fontweight='bold')
                plt.tight_layout()
                
                filename = output_dir / "monthly_returns.png"
                plt.savefig(filename, dpi=self.config.dpi, bbox_inches='tight')
                plt.close()
                
                return str(filename)
                
        except Exception as e:
            logger.warning(f"Error plotting monthly returns: {e}")
            
        return None
        
    def _plot_trade_analysis(self, trades: List, output_dir: Path) -> Optional[str]:
        """Plot trade analysis charts."""
        try:
            if not trades:
                return None
                
            # Extract trade data
            trade_data = []
            for trade in trades:
                trade_data.append({
                    'pnl': getattr(trade, 'pnl', 0),
                    'pnl_pct': getattr(trade, 'pnl_pct', 0) * 100,
                    'duration': getattr(trade, 'duration', 0),
                    'side': getattr(trade, 'side', 'long')
                })
                
            df = pd.DataFrame(trade_data)
            
            if MATPLOTLIB_AVAILABLE:
                fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))
                
                # 1. P&L distribution
                ax1.hist(df['pnl'], bins=30, alpha=0.7, 
                        color=self.config.colors['neutral'], edgecolor='black')
                ax1.set_title('Trade P&L Distribution')
                ax1.set_xlabel('P&L ($)')
                ax1.set_ylabel('Frequency')
                ax1.grid(True, alpha=0.3)
                
                # 2. Win/Loss streak
                df['cumulative'] = df['pnl'].cumsum()
                ax2.plot(df.index, df['cumulative'], color=self.config.colors['positive'])
                ax2.fill_between(df.index, 0, df['cumulative'], 
                                where=df['cumulative'] >= 0, 
                                color=self.config.colors['positive'], alpha=0.3)
                ax2.fill_between(df.index, 0, df['cumulative'], 
                                where=df['cumulative'] < 0, 
                                color=self.config.colors['negative'], alpha=0.3)
                ax2.set_title('Cumulative Trade P&L')
                ax2.set_xlabel('Trade Number')
                ax2.set_ylabel('Cumulative P&L ($)')
                ax2.grid(True, alpha=0.3)
                
                # 3. Trade duration vs P&L
                colors = [self.config.colors['positive'] if pnl >= 0 else self.config.colors['negative'] 
                         for pnl in df['pnl']]
                ax3.scatter(df['duration'], df['pnl_pct'], c=colors, alpha=0.6)
                ax3.set_title('Trade Duration vs Returns')
                ax3.set_xlabel('Duration (periods)')
                ax3.set_ylabel('Return (%)')
                ax3.grid(True, alpha=0.3)
                
                # 4. Long vs Short performance
                if 'side' in df.columns:
                    long_pnl = df[df['side'] == 'long']['pnl_pct']
                    short_pnl = df[df['side'] == 'short']['pnl_pct']
                    
                    ax4.boxplot([long_pnl, short_pnl], labels=['Long', 'Short'])
                    ax4.set_title('Long vs Short Performance')
                    ax4.set_ylabel('Return (%)')
                    ax4.grid(True, alpha=0.3)
                else:
                    ax4.text(0.5, 0.5, 'No side data available', 
                            transform=ax4.transAxes, ha='center', va='center')
                
                plt.tight_layout()
                
                filename = output_dir / "trade_analysis.png"
                plt.savefig(filename, dpi=self.config.dpi, bbox_inches='tight')
                plt.close()
                
                return str(filename)
                
        except Exception as e:
            logger.warning(f"Error plotting trade analysis: {e}")
            
        return None
        
    def _plot_returns_distribution(self, returns: pd.Series, output_dir: Path) -> Optional[str]:
        """Plot returns distribution."""
        try:
            if len(returns) < 10:
                return None
                
            if MATPLOTLIB_AVAILABLE:
                fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
                
                # 1. Histogram with normal distribution overlay
                ax1.hist(returns * 100, bins=50, density=True, alpha=0.7,
                        color=self.config.colors['neutral'], edgecolor='black')
                
                # Normal distribution overlay
                mu, sigma = returns.mean() * 100, returns.std() * 100
                x = np.linspace(returns.min() * 100, returns.max() * 100, 100)
                y = (1 / (sigma * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - mu) / sigma) ** 2)
                ax1.plot(x, y, 'r--', linewidth=2, label=f'Normal (μ={mu:.2f}, σ={sigma:.2f})')
                
                ax1.set_title('Returns Distribution')
                ax1.set_xlabel('Daily Returns (%)')
                ax1.set_ylabel('Density')
                ax1.legend()
                ax1.grid(True, alpha=0.3)
                
                # 2. Q-Q plot
                from scipy import stats
                stats.probplot(returns, dist="norm", plot=ax2)
                ax2.set_title('Q-Q Plot vs Normal Distribution')
                ax2.grid(True, alpha=0.3)
                
                plt.tight_layout()
                
                filename = output_dir / "returns_distribution.png"
                plt.savefig(filename, dpi=self.config.dpi, bbox_inches='tight')
                plt.close()
                
                return str(filename)
                
        except Exception as e:
            logger.warning(f"Error plotting returns distribution: {e}")
            
        return None
        
    def _export_csv(self, results: BacktestResults, output_dir: Path) -> Dict[str, str]:
        """Export data to CSV files."""
        csv_files = {}
        
        try:
            # 1. Export equity curve
            if hasattr(results, 'equity_curve') and len(results.equity_curve) > 0:
                filename = output_dir / "equity_curve.csv"
                results.equity_curve.to_csv(filename)
                csv_files['equity_curve'] = str(filename)
                
            # 2. Export trades
            if results.trades:
                trades_data = []
                for trade in results.trades:
                    trade_dict = {
                        'symbol': getattr(trade, 'symbol', ''),
                        'side': getattr(trade, 'side', ''),
                        'entry_time': getattr(trade, 'entry_time', ''),
                        'exit_time': getattr(trade, 'exit_time', ''),
                        'entry_price': getattr(trade, 'entry_price', 0),
                        'exit_price': getattr(trade, 'exit_price', 0),
                        'quantity': getattr(trade, 'quantity', 0),
                        'pnl': getattr(trade, 'pnl', 0),
                        'pnl_pct': getattr(trade, 'pnl_pct', 0),
                        'fees': getattr(trade, 'fees', 0),
                        'exit_reason': getattr(trade, 'exit_reason', '')
                    }
                    trades_data.append(trade_dict)
                    
                trades_df = pd.DataFrame(trades_data)
                filename = output_dir / "trades.csv"
                trades_df.to_csv(filename, index=False)
                csv_files['trades'] = str(filename)
                
            # 3. Export daily returns
            if hasattr(results, 'returns') and len(results.returns) > 0:
                filename = output_dir / "daily_returns.csv"
                results.returns.to_csv(filename)
                csv_files['returns'] = str(filename)
                
        except Exception as e:
            logger.warning(f"Error exporting CSV files: {e}")
            
        return csv_files
        
    def _generate_html_report(self, 
                             results: BacktestResults,
                             summary: ReportSummary,
                             strategy_name: str,
                             symbol: str,
                             timeframe: str,
                             plots: Dict[str, str],
                             output_dir: Path,
                             additional_data: Optional[Dict] = None) -> str:
        """Generate HTML report."""
        
        # HTML template
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Trading Strategy Report - {strategy_name}</title>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
                .header {{ text-align: center; border-bottom: 2px solid #333; padding-bottom: 20px; margin-bottom: 30px; }}
                .section {{ margin-bottom: 30px; }}
                .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; }}
                .metric-card {{ border: 1px solid #ddd; padding: 15px; border-radius: 5px; background: #f9f9f9; }}
                .metric-title {{ font-weight: bold; color: #333; }}
                .metric-value {{ font-size: 1.2em; color: #007acc; }}
                .positive {{ color: #2E8B57; }}
                .negative {{ color: #DC143C; }}
                .plot-container {{ text-align: center; margin: 20px 0; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; font-weight: bold; }}
                .disclaimer {{ background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin-top: 30px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Trading Strategy Report</h1>
                <h2>{strategy_name} on {symbol} ({timeframe})</h2>
                <p>Generated on {timestamp}</p>
            </div>
            
            {performance_section}
            
            {plots_section}
            
            {trades_section}
            
            {disclaimer_section}
        </body>
        </html>
        """
        
        # Generate sections
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        performance_section = self._generate_performance_section(summary)
        plots_section = self._generate_plots_section(plots, output_dir)
        trades_section = self._generate_trades_section(results.trades) if results.trades else ""
        disclaimer_section = self._generate_disclaimer_section()
        
        # Fill template
        html_content = html_template.format(
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            timestamp=timestamp,
            performance_section=performance_section,
            plots_section=plots_section,
            trades_section=trades_section,
            disclaimer_section=disclaimer_section
        )
        
        # Save HTML file
        filename = output_dir / "report.html"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        return str(filename)
        
    def _generate_performance_section(self, summary: ReportSummary) -> str:
        """Generate performance metrics section."""
        return f"""
        <div class="section">
            <h3>Performance Metrics</h3>
            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-title">Total Return</div>
                    <div class="metric-value {'positive' if summary.total_return >= 0 else 'negative'}">
                        {summary.total_return*100:.2f}%
                    </div>
                </div>
                <div class="metric-card">
                    <div class="metric-title">CAGR</div>
                    <div class="metric-value {'positive' if summary.cagr >= 0 else 'negative'}">
                        {summary.cagr*100:.2f}%
                    </div>
                </div>
                <div class="metric-card">
                    <div class="metric-title">Sharpe Ratio</div>
                    <div class="metric-value">{summary.sharpe_ratio:.2f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-title">Max Drawdown</div>
                    <div class="metric-value negative">{summary.max_drawdown*100:.2f}%</div>
                </div>
                <div class="metric-card">
                    <div class="metric-title">Win Rate</div>
                    <div class="metric-value">{summary.win_rate*100:.1f}%</div>
                </div>
                <div class="metric-card">
                    <div class="metric-title">Profit Factor</div>
                    <div class="metric-value">{summary.profit_factor:.2f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-title">Number of Trades</div>
                    <div class="metric-value">{summary.n_trades}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-title">Volatility</div>
                    <div class="metric-value">{summary.volatility*100:.2f}%</div>
                </div>
            </div>
        </div>
        """
        
    def _generate_plots_section(self, plots: Dict[str, str], output_dir: Path) -> str:
        """Generate plots section."""
        if not plots:
            return ""
            
        plots_html = '<div class="section"><h3>Charts</h3>'
        
        for plot_name, plot_path in plots.items():
            plot_file = Path(plot_path)
            
            if plot_file.suffix == '.html':
                # Embed HTML plot
                with open(plot_path, 'r') as f:
                    plot_content = f.read()
                plots_html += f'<div class="plot-container">{plot_content}</div>'
            elif plot_file.suffix in ['.png', '.jpg', '.svg']:
                # Embed image
                relative_path = plot_file.relative_to(output_dir)
                plots_html += f'<div class="plot-container"><img src="{relative_path}" style="max-width: 100%; height: auto;"></div>'
                
        plots_html += '</div>'
        return plots_html
        
    def _generate_trades_section(self, trades: List) -> str:
        """Generate trades section."""
        if not trades:
            return ""
            
        # Show recent trades (up to max_trades_display)
        recent_trades = trades[-self.config.max_trades_display:] if len(trades) > self.config.max_trades_display else trades
        
        trades_html = f"""
        <div class="section">
            <h3>Recent Trades (Last {len(recent_trades)})</h3>
            <table>
                <tr>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Entry Time</th>
                    <th>Exit Time</th>
                    <th>Entry Price</th>
                    <th>Exit Price</th>
                    <th>P&L</th>
                    <th>P&L %</th>
                    <th>Exit Reason</th>
                </tr>
        """
        
        for trade in recent_trades:
            pnl_class = "positive" if getattr(trade, 'pnl', 0) >= 0 else "negative"
            trades_html += f"""
                <tr>
                    <td>{getattr(trade, 'symbol', '')}</td>
                    <td>{getattr(trade, 'side', '')}</td>
                    <td>{getattr(trade, 'entry_time', '')}</td>
                    <td>{getattr(trade, 'exit_time', '')}</td>
                    <td>${getattr(trade, 'entry_price', 0):.4f}</td>
                    <td>${getattr(trade, 'exit_price', 0):.4f}</td>
                    <td class="{pnl_class}">${getattr(trade, 'pnl', 0):.2f}</td>
                    <td class="{pnl_class}">{getattr(trade, 'pnl_pct', 0)*100:.2f}%</td>
                    <td>{getattr(trade, 'exit_reason', '')}</td>
                </tr>
            """
            
        trades_html += "</table></div>"
        return trades_html
        
    def _generate_disclaimer_section(self) -> str:
        """Generate disclaimer section."""
        return """
        <div class="disclaimer">
            <h4>⚠️ IMPORTANT DISCLAIMER</h4>
            <p><strong>This is for educational and research purposes only. Past performance does not guarantee future results.</strong></p>
            <ul>
                <li>These results are based on historical data and may not reflect future market conditions</li>
                <li>Real trading involves additional costs, slippage, and market impact not fully captured in backtests</li>
                <li>Always perform your own due diligence before making investment decisions</li>
                <li>Consider paper trading before risking real capital</li>
                <li>Past performance is not indicative of future results</li>
            </ul>
            <p><em>Generated by Trading Insight Framework</em></p>
        </div>
        """


def create_report_generator(config: Dict[str, Any]) -> ReportGenerator:
    """Factory function to create report generator from config."""
    report_config = ReportConfig(**config)
    return ReportGenerator(report_config)


def generate_quick_report(results: BacktestResults,
                         strategy_name: str,
                         symbol: str,
                         timeframe: str,
                         output_dir: str = "reports") -> Dict[str, str]:
    """Generate a quick report with default settings."""
    config = ReportConfig(output_dir=output_dir)
    generator = ReportGenerator(config)
    
    return generator.generate_report(
        results=results,
        strategy_name=strategy_name,
        symbol=symbol,
        timeframe=timeframe
    )