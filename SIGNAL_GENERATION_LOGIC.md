# 🎯 Signal Generation Logic - Detailed Documentation

## 📋 **Table of Contents**

1. [Overview](#overview)
2. [Data Flow Architecture](#data-flow-architecture)
3. [Signal Generation Pipeline](#signal-generation-pipeline)
4. [Technical Analysis Engine](#technical-analysis-engine)
5. [Safety Scoring System](#safety-scoring-system)
6. [Position Sizing Algorithm](#position-sizing-algorithm)
7. [Risk Management Logic](#risk-management-logic)
8. [Auto-Scan Mode](#auto-scan-mode)
9. [Signal Output Format](#signal-output-format)
10. [Performance Optimization](#performance-optimization)

---

## 🏗️ **Overview**

TradingInsight Pro sử dụng một hệ thống phức tạp để tạo ra trading signals chất lượng cao cho futures trading. Hệ thống được thiết kế theo nguyên tắc **safety-first** với nhiều lớp validation và scoring.

### **Core Components:**

- **Data Fetcher**: Lấy dữ liệu real-time từ Binance API
- **Technical Analysis Engine**: Tính toán 20+ indicators
- **Signal Generator**: Logic tạo signals dựa trên multiple strategies
- **Safety Scorer**: Đánh giá độ an toàn của signals (1-10 scale)
- **Position Sizer**: Tính toán position size và leverage optimal
- **Risk Manager**: Tính toán TP/SL theo ROI-based approach

---

## 🔄 **Data Flow Architecture**

```mermaid
graph TD
    A[User Input] --> B{Auto-Scan Mode?}
    B -->|Yes| C[Scan All Coins]
    B -->|No| D[Selected Coins Only]
    C --> E[Binance API Data Fetcher]
    D --> E
    E --> F[OHLCV Data + Real Prices]
    F --> G[Technical Analysis Engine]
    G --> H[Strategy Logic Evaluation]
    H --> I[Market Structure Analysis]
    I --> J[Safety Score Calculation]
    J --> K{Safety >= Threshold?}
    K -->|Yes| L[Position Size Calculation]
    K -->|No| M[Reject Signal]
    L --> N[Risk Management (TP/SL)]
    N --> O[Signal Formatting]
    O --> P[GUI Display]
    P --> Q[Trading Signals JSON Export]
```

### **Data Sources:**

- **Primary**: Binance Spot API (`/api/v3/klines`)
- **Backup**: Cached historical data
- **Real-time**: Current prices via `/api/v3/ticker/price`

---

## 🎯 **Signal Generation Pipeline**

### **Step 1: Market Data Collection**

```python
def get_binance_data(symbol, timeframe, limit=500):
    """
    Fetch OHLCV data từ Binance API
    - symbol: BTCUSDT, ETHUSDT, etc.
    - timeframe: 1m, 5m, 15m, 1h, 4h, 1d
    - limit: Number of candles (max 1000)
    """
    url = f"{base_url}/klines"
    params = {
        'symbol': symbol,
        'interval': timeframe,
        'limit': limit
    }
    # Return: DataFrame with OHLCV + volume
```

### **Step 2: Technical Analysis Calculation**

```python
def calculate_indicators(df):
    """
    Tính toán 20+ technical indicators:

    TREND INDICATORS:
    - EMA 12, 26, 200
    - SMA 20, 50
    - MACD (line, signal, histogram)

    MOMENTUM INDICATORS:
    - RSI (14 period)
    - Stochastic %K, %D
    - Williams %R

    VOLATILITY INDICATORS:
    - Bollinger Bands (20, 2)
    - ATR (14 period)
    - ATR percentage

    VOLUME INDICATORS:
    - Volume SMA (20)
    - Volume ratio
    - On-Balance Volume (OBV)

    SUPPORT/RESISTANCE:
    - Dynamic S/R levels (20 period)
    - Pivot points
    """
```

### **Step 3: Market Structure Analysis**

```python
def analyze_market_structure(df):
    """
    Phân tích cấu trúc thị trường:

    TREND ANALYSIS:
    - Price vs EMA 200 (bullish/bearish)
    - EMA 12 vs EMA 26 (short-term trend)
    - Trend strength percentage

    MOMENTUM ANALYSIS:
    - RSI levels (overbought/oversold)
    - MACD crossovers
    - Stochastic signals

    VOLATILITY ANALYSIS:
    - ATR percentile ranking
    - Bollinger Band squeeze
    - Price range analysis

    VOLUME ANALYSIS:
    - Volume vs average
    - Volume confirmation
    - Accumulation/Distribution
    """
```

---

## ⚙️ **Technical Analysis Engine**

### **Multi-Timeframe Logic**

```python
# Timeframe-specific parameters
TIMEFRAME_CONFIGS = {
    '1m': {
        'rsi_period': 14,
        'ema_fast': 8,
        'ema_slow': 21,
        'bb_period': 10,
        'atr_period': 7,
        'min_signals': 3,
        'volatility_threshold': 0.5
    },
    '5m': {
        'rsi_period': 14,
        'ema_fast': 12,
        'ema_slow': 26,
        'bb_period': 20,
        'atr_period': 14,
        'min_signals': 4,
        'volatility_threshold': 0.8
    },
    '15m': {
        'rsi_period': 14,
        'ema_fast': 12,
        'ema_slow': 26,
        'bb_period': 20,
        'atr_period': 14,
        'min_signals': 4,
        'volatility_threshold': 1.0
    },
    # ... 1h, 4h, 1d configs
}
```

### **Strategy Logic (StrategyMomo)**

```python
def generate_momentum_signal(df, config):
    """
    Multi-factor momentum strategy:

    LONG CONDITIONS:
    1. RSI > 30 (not oversold)
    2. Price > EMA 200 (long-term uptrend)
    3. EMA 12 > EMA 26 (short-term momentum)
    4. MACD > MACD Signal (momentum confirmation)
    5. Close > Bollinger Middle (above mean)
    6. Volume > 1.2x average (volume confirmation)

    SHORT CONDITIONS:
    1. RSI < 70 (not overbought)
    2. Price < EMA 200 (long-term downtrend)
    3. EMA 12 < EMA 26 (short-term weakness)
    4. MACD < MACD Signal (momentum down)
    5. Close < Bollinger Middle (below mean)
    6. Volume > 1.2x average (volume confirmation)

    SIGNAL STRENGTH:
    - All 6 conditions = Strong signal (score 8-10)
    - 4-5 conditions = Medium signal (score 6-7)
    - 3 conditions = Weak signal (score 3-5)
    - < 3 conditions = No signal
    """
```

---

## 🛡️ **Safety Scoring System**

### **Scoring Components (Weighted)**

```python
SAFETY_WEIGHTS = {
    'trend_strength': 0.25,      # 25% - Xu hướng rõ ràng
    'volatility': 0.20,          # 20% - Volatility thấp = an toàn hơn
    'volume': 0.15,              # 15% - Volume xác nhận
    'risk_reward': 0.15,         # 15% - R/R ratio tốt
    'support_resistance': 0.15,   # 15% - Gần S/R levels
    'backtest_performance': 0.10  # 10% - Historical performance
}
```

### **Detailed Scoring Logic**

```python
def calculate_safety_score(signal_data):
    """
    1. TREND STRENGTH (0-10):
       - Trend > 5% = 10 points
       - Trend 3-5% = 8 points
       - Trend 1-3% = 6 points
       - Trend < 1% = 3 points

    2. VOLATILITY (0-10):
       - ATR < 25th percentile = 9 points (very stable)
       - ATR 25-50th percentile = 7 points (stable)
       - ATR 50-75th percentile = 5 points (moderate)
       - ATR > 75th percentile = 3 points (high vol)

    3. VOLUME (0-10):
       - High volume (>1.5x avg) = 9 points
       - Medium volume (0.8-1.5x) = 7 points
       - Low volume (<0.8x avg) = 4 points

    4. RISK/REWARD (0-10):
       - R/R >= 3.0 = 10 points
       - R/R >= 2.0 = 8 points
       - R/R >= 1.5 = 6 points
       - R/R < 1.5 = 3 points

    5. S/R PROXIMITY (0-10):
       - Very close to S/R (<2%) = 9 points
       - Close to S/R (2-5%) = 7 points
       - Far from S/R (>5%) = 4 points

    6. BACKTEST PERFORMANCE (0-10):
       - Win rate >70% + PF >1.5 = 10 points
       - Win rate >60% + PF >1.2 = 8 points
       - Win rate >50% + PF >1.0 = 6 points
       - Below average = 3 points
    """

    total_score = sum(component_score * weight)
    final_score = max(1, min(10, round(total_score)))

    # Confidence mapping
    if final_score >= 8: confidence = "HIGH"
    elif final_score >= 6: confidence = "MEDIUM"
    else: confidence = "LOW"

    return final_score, confidence
```

---

## 📊 **Position Sizing Algorithm**

### **Risk-Adjusted Position Sizing**

```python
def calculate_position_size(entry_price, stop_loss, safety_score,
                          account_balance=10000, base_risk=0.02):
    """
    Dynamic position sizing based on safety score:

    SAFETY MULTIPLIERS:
    - Score 10: 1.2x risk (safest trades)
    - Score 9: 1.1x risk
    - Score 8: 1.0x risk (normal)
    - Score 7: 0.9x risk
    - Score 6: 0.8x risk
    - Score 5: 0.6x risk
    - Score 4: 0.4x risk
    - Score 3: 0.3x risk
    - Score 2: 0.2x risk
    - Score 1: 0.1x risk (riskiest)

    LEVERAGE RECOMMENDATION:
    - Score 8-10: Max 10-15x leverage
    - Score 6-7: Max 5-10x leverage
    - Score 4-5: Max 3-7x leverage
    - Score 1-3: Max 1-3x leverage

    CALCULATION:
    adjusted_risk = base_risk * safety_multiplier
    risk_amount = account_balance * adjusted_risk
    price_diff = abs(entry_price - stop_loss)
    position_value = risk_amount / (price_diff / entry_price)
    position_size_usdt = position_value / recommended_leverage
    """
```

### **ROI-Based TP/SL Calculation**

```python
def calculate_tp_sl_roi(entry_price, direction, leverage, tp_percent, sl_percent):
    """
    Calculate TP/SL based on ROI on margin (not just price change):

    ROI FORMULA:
    ROI = (Exit_Price - Entry_Price) / Entry_Price * Leverage

    FOR LONG POSITIONS:
    TP_Price = Entry_Price * (1 + TP_ROI / Leverage)
    SL_Price = Entry_Price * (1 - SL_ROI / Leverage)

    FOR SHORT POSITIONS:
    TP_Price = Entry_Price * (1 - TP_ROI / Leverage)
    SL_Price = Entry_Price * (1 + SL_ROI / Leverage)

    EXAMPLE (100% ROI with 10x leverage):
    - Entry: $50,000
    - Leverage: 10x
    - Target ROI: 100%
    - TP Price: $50,000 * (1 + 1.0/10) = $55,000
    - Actual ROI: (55,000-50,000)/50,000 * 10 = 100% ✅
    """
```

---

## 🚨 **Risk Management Logic**

### **Multi-Level Risk Controls**

```python
class RiskManager:
    """
    1. POSITION LEVEL RISK:
       - Max 2% risk per trade (adjustable by safety)
       - Max 50% account exposure per trade
       - Min 1.5:1 risk/reward ratio

    2. PORTFOLIO LEVEL RISK:
       - Max 10% total risk across all positions
       - Max 5 concurrent positions
       - Correlation limits between positions

    3. LEVERAGE CONTROLS:
       - Dynamic leverage based on safety score
       - Max leverage caps per timeframe
       - Volatility-adjusted leverage

    4. TIME-BASED CONTROLS:
       - Signal validity period (4 hours default)
       - Market hours filtering
       - Weekend/holiday restrictions
    """

    def validate_signal(self, signal):
        """
        Pre-execution validation:
        - Check account balance sufficiency
        - Validate TP/SL prices are reasonable
        - Ensure leverage doesn't exceed limits
        - Confirm market is open/liquid
        """
```

---

## 🔍 **Auto-Scan Mode**

### **Smart Scanning Logic**

```python
def auto_scan_mode(gui_instance):
    """
    When no coins are selected:

    1. SCAN ALL SUPPORTED COINS:
       - BTC/USDT, ETH/USDT, BNB/USDT, etc. (20 coins)
       - Multiple timeframes if enabled

    2. GENERATE SIGNALS:
       - Run full analysis for each coin
       - Calculate safety scores
       - Apply filters

    3. FILTER HIGH-QUALITY SIGNALS:
       - Safety score >= 8 (High confidence only)
       - Risk/Reward >= 1.5
       - Valid market conditions

    4. RANK AND DISPLAY:
       - Sort by safety score (highest first)
       - Show max 10 best signals
       - Clean formatting for copy-paste

    BENEFITS:
    - No manual coin selection needed
    - Focus on only the best opportunities
    - Automated quality control
    - Time-efficient scanning
    """
```

---

## 📤 **Signal Output Format**

### **GUI Display Format**

```python
# Expandable Signal Cards
🚨 LONG SIGNAL - BTC/USDT (Safety: 9/10)
├── Entry: $63,420.50 (Range: $63,356 - $63,485)
├── Stop Loss: $61,127.30 (-3.62% | ROI: -36.2%)
├── Take Profit: $69,762.55 (+10.00% | ROI: +100.0%)
├── Leverage: 10x | Position: $1,200 (12.0% of account)
├── Risk/Reward: 2.76 | Timeframe: 1h
├── Indicators: RSI(45) | EMA(Bullish) | MACD(Buy)
└── Notes: High volume confirms signal strength
```

### **JSON Export Format**

```json
{
  "symbol": "BTC/USDT",
  "direction": "LONG",
  "timestamp": "2025-09-26T14:30:00Z",
  "entry_price": 63420.5,
  "stop_loss": 61127.3,
  "take_profit": 69762.55,
  "leverage": 10,
  "position_size_usdt": 1200.0,
  "safety_score": 9,
  "confidence": "HIGH",
  "risk_reward": 2.76,
  "timeframe": "1h",
  "strategy": "StrategyMomo",
  "indicators": {
    "rsi": 45.2,
    "ema_trend": "BULLISH",
    "macd_signal": "BUY",
    "volume_profile": "HIGH"
  },
  "execution_notes": "High volume confirms signal strength | Low volatility - Good for larger positions",
  "validity_minutes": 240
}
```

### **Binance Futures Command Format**

```bash
# Copy-paste ready for Binance Futures
Symbol: BTCUSDT
Side: BUY (LONG)
Type: MARKET
Quantity: 0.0189 BTC
Leverage: 10x
Stop Loss: 61127.30
Take Profit: 69762.55
```

---

## ⚡ **Performance Optimization**

### **Caching Strategy**

```python
# 1. Price Data Caching (Redis/Memory)
cache_key = f"{symbol}_{timeframe}_{timestamp}"
cache_duration = {
    '1m': 30,    # 30 seconds
    '5m': 120,   # 2 minutes
    '15m': 300,  # 5 minutes
    '1h': 1800,  # 30 minutes
    '4h': 3600,  # 1 hour
    '1d': 14400  # 4 hours
}

# 2. Indicator Calculation Caching
# Cache calculated indicators to avoid recalculation

# 3. Batch API Requests
# Fetch multiple symbols in single request where possible

# 4. Async Processing
# Use asyncio for concurrent signal generation
```

### **Error Handling & Fallbacks**

```python
def robust_signal_generation(symbol):
    """
    Multi-layer error handling:

    1. API FAILURES:
       - Retry with exponential backoff
       - Fallback to cached data
       - Alternative data sources

    2. CALCULATION ERRORS:
       - Graceful degradation
       - Default safety scores
       - Skip problematic indicators

    3. VALIDATION FAILURES:
       - Reject invalid signals
       - Log errors for debugging
       - Continue with other symbols
    """
```

---

## 🎯 **Signal Quality Metrics**

### **Success Metrics Tracking**

- **Accuracy Rate**: % of signals that hit TP before SL
- **Average R/R Achieved**: Actual vs predicted risk/reward
- **Safety Score Correlation**: How well safety scores predict success
- **Timeframe Performance**: Which timeframes perform best
- **Market Condition Success**: Performance in different market phases

### **Continuous Improvement**

- **A/B Testing**: Compare different indicator combinations
- **Parameter Optimization**: Fine-tune thresholds using backtest data
- **Machine Learning Integration**: Enhance safety scoring with ML models
- **User Feedback Loop**: Track user-reported signal outcomes

---

## 🚀 **Conclusion**

TradingInsight Pro's signal generation system là một **comprehensive, multi-layered approach** to futures trading signal creation. Key strengths:

✅ **Safety-First Design**: Multi-factor safety scoring
✅ **Real Data Only**: No simulation or fake data
✅ **ROI-Based Calculations**: Leverage-aware TP/SL
✅ **Auto-Quality Control**: Only high-confidence signals shown
✅ **Production Ready**: Robust error handling & performance optimization
✅ **User-Friendly**: Clean interface with actionable outputs

**The system prioritizes quality over quantity, focusing on high-probability setups that maximize trader success while minimizing risk.** 🎯
