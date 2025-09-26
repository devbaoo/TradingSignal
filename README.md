# 📈 Trading Insight Pro - Complete Futures Trading System# Trading Insight

## 🌟 OverviewA robust trading strategy development and testing framework for cryptocurrency (BTC, ETH) and commodities (XAUUSD) markets. This project focuses on **ROBUSTNESS** rather than promising high returns or win rates.

**Trading Insight Pro** là hệ thống giao dịch futures cryptocurrency hoàn chỉnh với GUI thân thiện, được thiết kế để tạo ra các tín hiệu giao dịch chính xác với đầy đủ thông số: **entry**, **stop loss**, **take profit**, **leverage**, **position size** dựa trên độ an toàn của lệnh.## Features

### ✨ Key Features- **Multi-Asset Support**: BTC/USDT, ETH/USDT (spot), XAUUSD (gold)

- **Multiple Timeframes**: 15m, 1h, 4h, 1D

🎯 **Tín hiệu giao dịch thực tế** - Entry, SL, TP, leverage, position size - **Comprehensive Technical Analysis**: 10+ indicators with proper implementation

📊 **Multi-coin analysis** - Hỗ trợ 20+ cryptocurrencies - **Risk Management**: Position sizing, stop-loss/take-profit, trailing stops

🖥️ **Beautiful GUI** - Streamlit interface với real-time charts - **Strategy Types**: Rule-based and ML-driven strategies

📈 **Technical Analysis** - 10+ indicators (RSI, MACD, Bollinger Bands, etc.) - **Robust Backtesting**: Vectorized engine with fees, slippage, walk-forward analysis

🛡️ **Safety Scoring** - Đánh giá độ rủi ro 1-10 cho mỗi signal - **Hyperparameter Optimization**: Bayesian optimization with Optuna

⚡ **Real-time monitoring** - Auto-scan every 30 seconds - **Paper Trading**: Live simulation with testnet exchanges

📋 **Signal history** - Lưu trữ và tracking performance - **Detailed Reporting**: HTML/CSV reports with comprehensive metrics

## 🚀 Quick Start## Installation

### 1. Setup Environment### Prerequisites

```bash

cd /Users/devbaoo/WorkSpace/TradingInsight- Python 3.10 or higher

source .venv/bin/activate- Git

```

### Quick Setup

### 2. Launch GUI

````bash**Option 1: Automated Setup (Recommended)**

# Option 1: Use quick start script

./start_gui.sh```bash

# Clone the repository

# Option 2: Manual launch  git clone <your-repo-url>

streamlit run trading_gui.py --server.port 8501cd TradingInsight

````

# Run the automated setup script

### 3. Access Applicationchmod +x scripts/setup.sh

- Open browser: `http://localhost:8501`./scripts/setup.sh

- Select coins, timeframe, and parameters```

- Generate real-time trading signals

**Option 2: Manual Setup**

## 🎛️ GUI Features

````bash

### 📊 Market Dashboard# Clone the repository

- **Real-time metrics** for multiple coinsgit clone <your-repo-url>

- **Price, RSI, MACD, trend analysis**cd TradingInsight

- **Market strength indicators**

- **Volatility assessment**# Create virtual environment

   python3 -m venv .venv

### 🎯 Trading Signals   source .venv/bin/activate  # On macOS/Linux

- **Generate signals** with one click```

- **Complete trading parameters**:

  - Entry Price3. **Install TA-Lib system dependency** (required for technical indicators):

  - Stop Loss

  - Take Profit (3 levels)   ```bash

  - Leverage recommendation   # On macOS using Homebrew

  - Position size (USDT + % of account)   brew install ta-lib

  - Safety score (1-10)

  - Risk/Reward ratio   # On Ubuntu/Debian

   sudo apt-get install libta-lib0-dev

### 📈 Interactive Charts

- **Candlestick charts** with technical indicators   # On Windows, download from: https://github.com/cgohlke/talib-build/releases

- **Multiple timeframes** (1h, 4h, 1d)   ```

- **Zoom, pan, hover** functionality

- **Bollinger Bands, moving averages, volume**4. **Install the project**:



### 📋 Signal History# Install dependencies

- **Track all generated signals**

- **Performance monitoring**pip install -e .

- **Export/clear functionality**

# Install development dependencies (optional)

## ⚙️ Configuration Options

pip install -e .[dev]

### 🪙 Supported Cryptocurrencies

```# Copy example configuration

BTC/USDT, ETH/USDT, BNB/USDT, ADA/USDT, XRP/USDT,

SOL/USDT, DOT/USDT, DOGE/USDT, AVAX/USDT, MATIC/USDT,cp config/config.example.yaml config/config.yaml

LINK/USDT, UNI/USDT, LTC/USDT, BCH/USDT, ATOM/USDT,

FTM/USDT, ALGO/USDT, VET/USDT, ICP/USDT, NEAR/USDT# Download sample data

````

*Currently BTC/USDT and ETH/USDT have cached data*python3 scripts/download_sample_data.py

### 📈 Leverage Options````

- **Conservative**: 2-5x

- **Moderate**: 5-10x ## Quick Start

- **Aggressive**: 10-25x

- **Expert**: 25-100x**Important**: Either activate the virtual environment first with `source .venv/bin/activate` or use the full path to Python as shown below.

### 🛡️ Safety Scoring System### 1. Download Data

- **9-10**: Very Safe - Strong trend, multiple confirmations

- **7-8**: Safe - Good market conditions```bash

- **5-6**: Moderate - Average risk# Using activated environment

- **3-4**: Risky - Use with cautionpython3 scripts/download_sample_data.py

- **1-2**: Very Risky - Not recommended

# Or using full path

## 💡 Trading Output Example.venv/bin/python scripts/download_sample_data.py

````

```

🚨 LONG SIGNAL - BTC/USDT### 2. Run Backtest



Entry Price: $43,250.00```bash

Stop Loss: $42,100.00# Using activated environment

Take Profit: $44,800.00python3 main.py backtest StrategyMomo --symbol BTC/USDT --timeframe 1h

Leverage: 5x

Position Size: $1,250.00 (2.5% of account)# Or using full path

Safety Score: 8/10.venv/bin/python main.py backtest StrategyMomo --symbol BTC/USDT --timeframe 1h

Confidence: HIGH```

Risk/Reward: 1:1.35

### 3. Optimize Strategy

Copy to Exchange:

Symbol: BTC/USDT```bash

Direction: LONG (BUY)# Using activated environment

Entry: $43,250.00python3 main.py optimize StrategyMomo --symbol BTC/USDT --timeframe 1h --trials 50

Stop Loss: $42,100.00

Take Profit: $44,800.00# Or using full path

Leverage: 5x.venv/bin/python main.py optimize StrategyMomo --symbol BTC/USDT --timeframe 1h --trials 50

Position Size: 2.5% of account```

```

### 4. Generate Report

## 🔧 Technical Architecture

```bash

### Core Components# Using activated environment

- **Signal Generation**: `src/signals.py` - Main trading logicpython3 main.py report

- **GUI Application**: `trading_gui.py` - Streamlit interface

- **Data Management**: Cached OHLCV data from Binance# Or using full path

- **Analysis Scripts**: Comprehensive backtesting and analysis tools.venv/bin/python main.py report

```

### Technical Indicators

- **Trend**: SMA (20, 50), EMA (12, 26, 200)### 5. Paper Trading

- **Momentum**: RSI, MACD, Stochastic

- **Volatility**: Bollinger Bands, ATR```bash

- **Volume**: Volume SMA, Volume Ratiopython3 main.py live StrategyMomo --paper --symbol BTC/USDT --timeframe 15m

```

### Data Sources

- **Exchange**: Binance (cached data)## Project Structure

- **Timeframes**: 1h, 4h, 1d

- **Coverage**: September 2023 - September 2025```

- **Symbols**: BTC/USDT, ETH/USDT (expandable)TradingInsight/

├── README.md

## 📁 Project Structure├── LICENSE

├── pyproject.toml

```├── Dockerfile

TradingInsight/├── Makefile

├── trading_gui.py           # Main GUI application├── config/

├── start_gui.sh            # Quick start script│   └── config.example.yaml

├── GUI_USER_GUIDE.md       # Detailed user guide├── data/

├── src/│   ├── raw/

│   ├── signals.py          # Core signal generation│   ├── processed/

│   ├── cli.py             # Command-line interface│   └── cache/

│   └── ...├── src/

├── scripts/│   ├── __init__.py

│   ├── generate_futures_signals.py  # Advanced signal generator│   ├── data.py              # Data loading and processing

│   ├── comprehensive_test.py        # System testing│   ├── indicators.py        # Technical indicators

│   └── ...│   ├── features.py          # Feature engineering

├── data/cache/             # Market data cache│   ├── strategy/

├── trading_signals/        # Generated signals (JSON)│   │   ├── __init__.py

├── config/                 # Configuration files│   │   ├── rule_based.py    # Rule-based strategies

└── requirements.txt        # Python dependencies│   │   └── ml.py           # ML-based strategies

```│   ├── risk.py             # Risk management

│   ├── backtest.py         # Backtesting engine

## 🎯 Usage Scenarios│   ├── optimize.py         # Hyperparameter optimization

│   ├── report.py           # Reporting and visualization

### Day Trading (1h timeframe)│   ├── live.py             # Live/paper trading

- **Higher leverage** (5-10x)│   ├── utils.py            # Utilities and logging

- **Tight stops** (1-2% risk)│   └── cli.py              # Command line interface

- **Quick profits** (1:1.5 R:R)├── tests/

- **High safety score** required (7+)│   ├── __init__.py

│   ├── test_indicators.py

### Swing Trading (4h timeframe)│   ├── test_backtest.py

- **Moderate leverage** (3-5x)│   ├── test_strategies.py

- **Wider stops** (2-3% risk)│   └── test_data.py

- **Larger profits** (1:2-3 R:R)└── runs/                   # Backtest results and artifacts

- **Medium safety score** (6+)```



### Position Trading (1d timeframe)## Configuration

- **Low leverage** (2-3x)

- **Wide stops** (3-5% risk)The system is highly configurable through YAML files. Key configuration sections:

- **Large profits** (1:3-5 R:R)

- **Any safety score** (5+)- **Data**: Exchange settings, symbols, timeframes

- **Strategy**: Parameters for each strategy type

## 🛡️ Risk Management- **Risk**: Position sizing, stop-loss rules, max drawdown limits

- **Backtest**: Walk-forward windows, fees, slippage

### Position Sizing Formula- **ML**: Feature sets, model parameters, thresholds

```python

Risk Amount = Account Balance × Risk Percentage (1-3%)See `config/config.example.yaml` for detailed examples.

Price Risk = |Entry Price - Stop Loss| / Entry Price

Position Size = Risk Amount / Price Risk## Strategies

```

### Rule-Based Strategies

### Safety Guidelines

1. **Never risk more than 2-3%** per trade1. **Strategy_Momo (Momentum)**

2. **Always use stop losses**

3. **Take profits at planned levels**   - Long: Uptrend + RSI 50-70 rising + MACD histogram crossing up

4. **Adjust leverage based on safety score**   - Risk: 2×ATR stop, 3×ATR target, 1×ATR trailing

5. **Monitor market volatility**

2. **Strategy_MeanRev (Mean Reversion)**

## 📊 Performance & Testing   - Long: Price touches lower Bollinger Band + RSI < 30 + low volatility

   - Risk: 1.5×ATR stop, middle Bollinger Band target

### Systematic Testing

- **All core features validated**### ML-Based Strategies

- **Error handling tested**

- **Real market data integration**- Random Forest / XGBoost models for probability prediction

- **Signal generation accuracy**- Time-series cross-validation to prevent look-ahead bias

- **GUI functionality verified**- Multiple target labeling methods (return-based, triple-barrier, trend continuation)



### Quality Assurance## Risk Management

- **Modular, maintainable code**

- **Comprehensive error handling**- **Position Sizing**: Fixed fractional (0.5-2% risk per trade) or ATR-based

- **Real-time data validation**- **Risk Limits**: Max risk per symbol/day, max concurrent positions

- **User-friendly interface**- **Circuit Breakers**: Max drawdown limits with automatic shutdown

- **Fee & Slippage Modeling**: Configurable transaction costs

## 🔄 Auto-Features

## Backtesting Features

### Auto-Scan Mode

- **Scans all selected coins** every 30 seconds- **Vectorized Engine**: Fast backtesting with realistic fill logic

- **Automatic signal generation**- **Walk-Forward Analysis**: Time-based validation windows

- **Real-time market updates**- **Transaction Costs**: Configurable fees and slippage models

- **Background monitoring**- **Intrabar Logic**: Stop-loss and take-profit checking within bars



### Smart Defaults## Performance Metrics

- **Dynamic leverage adjustment**

- **Volatility-based stops**The system reports comprehensive metrics focusing on robustness:

- **Risk-adjusted position sizing**

- **Market condition awareness**- **Return Metrics**: CAGR, Sharpe/Sortino ratios

- **Risk Metrics**: Maximum drawdown, VaR/CVaR, volatility

## ⚠️ Important Disclaimers- **Trade Metrics**: Win rate, profit factor, expectancy

- **Stability**: Performance across different market regimes

### Risk Warnings

1. **Cryptocurrency trading involves substantial risk**## Paper Trading

2. **Never invest more than you can afford to lose**

3. **Past performance does not guarantee future results**- **Exchange Integration**: Binance/Bybit testnet support via CCXT

4. **This tool is for educational purposes**- **Risk Guards**: Real-time risk monitoring and position limits

5. **Always do your own research before trading**- **Logging**: Detailed trade logs and P&L tracking

- **Safety**: Paper-only by default, requires explicit flags for live trading

### Market Limitations

- **Crypto markets are highly volatile**## Testing

- **Leverage amplifies both gains and losses**

- **Market conditions can change rapidly**```bash

- **No trading system is 100% accurate**# Run all tests

pytest

## 🛠️ Development & Customization

# Run specific test categories

### Adding New Symbolspytest -m unit

1. Update `self.supported_symbols` in `trading_gui.py`pytest -m integration

2. Add data to `data/cache/` directory

3. Update `self.available_symbols` list# Run with coverage

pytest --cov=src --cov-report=html

### Modifying Indicators```

1. Edit `calculate_indicators()` method

2. Update signal logic in `analyze_market()`## Docker Support

3. Adjust thresholds in `generate_signal()`

```bash

### Custom Strategies# Build image

1. Modify signal conditions in `generate_signal()`docker build -t trading-insight .

2. Adjust safety scoring algorithm

3. Update position sizing formulas# Run container

docker run -v $(pwd)/data:/app/data -v $(pwd)/config:/app/config trading-insight

## 📞 Support & Updates```



### Getting Help## Important Disclaimers

- **Check GUI_USER_GUIDE.md** for detailed instructions

- **Review error messages** in terminal output⚠️ **Risk Warning**:

- **Test with small positions** first

- **Use paper trading** for practice- This software is for educational and research purposes

- Past performance does not guarantee future results

### Future Enhancements- Trading involves substantial risk of loss

- **More cryptocurrency pairs**- Never risk more than you can afford to lose

- **Additional timeframes**

- **Advanced order types**⚠️ **No Profit Guarantees**:

- **Portfolio management**

- **Performance analytics**- This system focuses on robustness, not profitability promises

- All strategies must be thoroughly tested before live use

---- Market conditions change and strategies may stop working



## 🎉 Success! ⚠️ **Data Dependencies**:



**Trading Insight Pro** is now ready for use! This comprehensive system provides everything you need for professional futures trading:- XAUUSD data requires external sources (CSV or free APIs)

- Crypto data depends on exchange availability

✅ **Real-time signal generation**  - Always validate data quality before backtesting

✅ **Complete trading parameters**

✅ **Risk management tools**  ## License

✅ **Beautiful, intuitive GUI**

✅ **Multi-coin analysis**  MIT License - see LICENSE file for details.

✅ **Safety scoring system**

## Contributing

**Happy Trading!** 🚀📈💰

1. Fork the repository

*Remember: Trade responsibly, manage your risk, and never invest more than you can afford to lose.*2. Create a feature branch
3. Make changes with proper tests
4. Submit a pull request

## Support

For questions and support:

- Check the documentation in this README
- Review example configurations
- Run tests to understand expected behavior
- Open issues for bugs or feature requests

---

**Remember**: This is a research and educational tool. Always paper trade extensively before considering live deployment.
````
