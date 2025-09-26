import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import json
import os
from datetime import datetime, timedelta
import time
import random
import requests

# Technical Analysis
import ta
import talib

# Set page config
st.set_page_config(
    page_title="Trading Insight Pro",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        color: #1E88E5;
        text-align: center;
        margin-bottom: 2rem;
        background: linear-gradient(90deg, #1E88E5, #FF5722);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        margin: 0.5rem 0;
    }
    .signal-long {
        background: linear-gradient(135deg, #4CAF50, #45a049);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin: 1rem 0;
    }
    .signal-short {
        background: linear-gradient(135deg, #f44336, #da190b);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin: 1rem 0;
    }
    .signal-neutral {
        background: linear-gradient(135deg, #9E9E9E, #616161);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'signals_history' not in st.session_state:
    st.session_state.signals_history = []

class TradingGUI:
    def __init__(self):
        self.supported_symbols = [
            "BTC/USDT", "ETH/USDT", "BNB/USDT", "ADA/USDT", "XRP/USDT",
            "SOL/USDT", "DOT/USDT", "DOGE/USDT", "AVAX/USDT", "MATIC/USDT",
            "LINK/USDT", "UNI/USDT", "LTC/USDT", "BCH/USDT", "ATOM/USDT",
            "FTM/USDT", "ALGO/USDT", "VET/USDT", "ICP/USDT", "NEAR/USDT"
        ]
        self.timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]
        
        # Binance API setup
        self.binance_base_url = "https://api.binance.com/api/v3"
        self.symbols_map = {
            "BTC/USDT": "BTCUSDT", "ETH/USDT": "ETHUSDT", "BNB/USDT": "BNBUSDT",
            "ADA/USDT": "ADAUSDT", "XRP/USDT": "XRPUSDT", "SOL/USDT": "SOLUSDT",
            "DOT/USDT": "DOTUSDT", "DOGE/USDT": "DOGEUSDT", "AVAX/USDT": "AVAXUSDT",
            "MATIC/USDT": "MATICUSDT", "LINK/USDT": "LINKUSDT", "UNI/USDT": "UNIUSDT",
            "LTC/USDT": "LTCUSDT", "BCH/USDT": "BCHUSDT", "ATOM/USDT": "ATOMUSDT",
            "FTM/USDT": "FTMUSDT", "ALGO/USDT": "ALGOUSDT", "VET/USDT": "VETUSDT",
            "ICP/USDT": "ICPUSDT", "NEAR/USDT": "NEARUSDT"
        }
        self.timeframe_map = {"1h": "1h", "4h": "4h", "1d": "1d"}
        
    def get_current_prices(self):
        """Get REAL current market prices từ Binance API"""
        try:
            url = f"{self.binance_base_url}/ticker/price"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            all_prices = response.json()
            current_prices = {}
            
            for symbol, binance_symbol in self.symbols_map.items():
                for price_data in all_prices:
                    if price_data['symbol'] == binance_symbol:
                        current_prices[symbol] = float(price_data['price'])
                        break
                        
            return current_prices
            
        except Exception as e:
            st.error(f"❌ Error fetching real prices: {e}")
            st.error("🌐 Please check your internet connection - No fallback data available")
            return {}
    
    def load_market_data(self, symbol, timeframe):
        """Load REAL market data từ Binance API"""
        try:
            # Construct URL for kline data
            binance_symbol = self.symbols_map.get(symbol, symbol.replace('/', ''))
            
            # Map timeframe to Binance format
            tf_map = {
                "1m": "1m",
                "5m": "5m", 
                "15m": "15m",
                "1h": "1h",
                "4h": "4h", 
                "1d": "1d"
            }
            
            binance_tf = tf_map.get(timeframe, "1h")
            
            # Get 500 candles for analysis
            url = f"{self.binance_base_url}/klines"
            params = {
                'symbol': binance_symbol,
                'interval': binance_tf,
                'limit': 500
            }
            
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            
            klines = response.json()
            
            # Convert to DataFrame
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'count', 'taker_buy_volume',
                'taker_buy_quote_volume', 'ignore'
            ])
            
            # Convert to proper types
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])
            
            # Convert timestamp to datetime
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            df = df[['datetime', 'open', 'high', 'low', 'close', 'volume']]
            df.set_index('datetime', inplace=True)
            
            return df
            
        except Exception as e:
            st.error(f"❌ Error loading real data for {symbol}: {e}")
            # Return None to show error state instead of fake data
            return None
    
    def calculate_indicators(self, df):
        """Tính toán technical indicators"""
        # Moving Averages
        df['sma_20'] = df['close'].rolling(20).mean()
        df['sma_50'] = df['close'].rolling(50).mean()
        df['ema_12'] = df['close'].ewm(span=12).mean()
        df['ema_26'] = df['close'].ewm(span=26).mean()
        df['ema_200'] = df['close'].ewm(span=200).mean()
        
        # MACD
        df['macd'] = df['ema_12'] - df['ema_26']
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['macd_histogram'] = df['macd'] - df['macd_signal']
        
        # RSI
        df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
        
        # Bollinger Bands
        bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
        df['bb_upper'] = bb.bollinger_hband()
        df['bb_middle'] = bb.bollinger_mavg()
        df['bb_lower'] = bb.bollinger_lband()
        
        # ATR
        df['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range()
        df['atr_percent'] = (df['atr'] / df['close']) * 100
        
        # Stochastic
        stoch = ta.momentum.StochasticOscillator(df['high'], df['low'], df['close'])
        df['stoch_k'] = stoch.stoch()
        df['stoch_d'] = stoch.stoch_signal()
        
        # Volume indicators
        if 'volume' in df.columns:
            df['volume_sma'] = df['volume'].rolling(20).mean()
            df['volume_ratio'] = df['volume'] / df['volume_sma']
        
        return df
    
    def analyze_market(self, df):
        """Phân tích market conditions"""
        current = df.iloc[-1]
        prev = df.iloc[-2]
        
        analysis = {
            'price': current['close'],
            'trend': 'NEUTRAL',
            'trend_strength': 0,
            'momentum': 'NEUTRAL',
            'volatility': 'NORMAL',
            'market_strength': 5.0,
            'signals': [],
            'rsi': current['rsi'],
            'macd': current['macd'],
            'atr_percent': current['atr_percent']
        }
        
        # Trend Analysis
        if current['close'] > current['ema_200'] and current['ema_12'] > current['ema_26']:
            if current['close'] > current['sma_50'] > current['sma_20']:
                analysis['trend'] = 'STRONG_BULLISH'
                analysis['trend_strength'] = 3
            else:
                analysis['trend'] = 'BULLISH'
                analysis['trend_strength'] = 2
        elif current['close'] < current['ema_200'] and current['ema_12'] < current['ema_26']:
            if current['close'] < current['sma_50'] < current['sma_20']:
                analysis['trend'] = 'STRONG_BEARISH'
                analysis['trend_strength'] = -3
            else:
                analysis['trend'] = 'BEARISH'
                analysis['trend_strength'] = -2
        
        # Momentum signals
        if current['macd'] > current['macd_signal'] and prev['macd'] <= prev['macd_signal']:
            analysis['signals'].append('MACD_BULLISH_CROSS')
            analysis['market_strength'] += 1.5
        elif current['macd'] < current['macd_signal'] and prev['macd'] >= prev['macd_signal']:
            analysis['signals'].append('MACD_BEARISH_CROSS')
            analysis['market_strength'] -= 1.5
        
        # RSI signals
        if current['rsi'] > 70:
            analysis['momentum'] = 'OVERBOUGHT'
            analysis['signals'].append('RSI_OVERBOUGHT')
            analysis['market_strength'] -= 1
        elif current['rsi'] < 30:
            analysis['momentum'] = 'OVERSOLD'
            analysis['signals'].append('RSI_OVERSOLD')
            analysis['market_strength'] += 1.5
        
        # Volatility
        avg_atr = df['atr_percent'].rolling(50).mean().iloc[-1]
        if current['atr_percent'] > avg_atr * 1.5:
            analysis['volatility'] = 'HIGH'
        elif current['atr_percent'] < avg_atr * 0.7:
            analysis['volatility'] = 'LOW'
        
        analysis['market_strength'] = max(0, min(10, analysis['market_strength']))
        
        return analysis
    
    def generate_signal(self, symbol, timeframe, balance, selected_leverage, min_safety, tp_percent=None, sl_percent=None):
        """Generate trading signal với logic cải thiện cho multi-timeframe và custom TP/SL"""
        df = self.load_market_data(symbol, timeframe)
        if df is None:
            return None
        
        df = self.calculate_indicators(df)
        market = self.analyze_market(df)
        current_data = df.iloc[-1]
        
        # Timeframe-specific adjustments
        is_short_tf = timeframe in ["1m", "5m"]  # Timeframes ngắn
        is_scalping_tf = timeframe in ["1m", "5m", "15m"]  # Scalping timeframes
        
        # Signal logic được cải thiện theo timeframe
        signal_direction = None
        safety_score = 5
        confidence = "MEDIUM"
        
        # Lấy indicators
        rsi = current_data['rsi']
        macd = current_data['macd']
        macd_signal = current_data['macd_signal']
        price = current_data['close']
        sma_20 = current_data['sma_20']
        ema_200 = current_data['ema_200']
        
        # Adaptive thresholds dựa trên timeframe
        if is_short_tf:
            # Timeframes 1m, 5m: More sensitive
            rsi_long_max = 75  # Cho phép RSI cao hơn
            rsi_short_min = 25  # Cho phép RSI thấp hơn
            price_tolerance = 0.002  # 0.2% tolerance
        elif is_scalping_tf:
            # Timeframe 15m: Medium sensitivity
            rsi_long_max = 70
            rsi_short_min = 30
            price_tolerance = 0.005  # 0.5% tolerance
        else:
            # Timeframes 1h, 4h, 1d: Less sensitive
            rsi_long_max = 65
            rsi_short_min = 35
            price_tolerance = 0.01  # 1% tolerance
        
        # LONG conditions với adaptive logic
        if (rsi < rsi_long_max and  
            macd > macd_signal and  
            price > sma_20 * (1 - price_tolerance)):
            signal_direction = "LONG"
            
            # Tính safety score dựa trên timeframe và điều kiện
            safety_score = 6 if is_short_tf else 7
            
            if rsi < 30:  # Oversold
                safety_score += 1
            if price > ema_200:  # Above long-term trend
                safety_score += 1
            if market['trend_strength'] > 0:
                confidence = "HIGH"
                safety_score += 1
                
        # SHORT conditions với adaptive logic  
        elif (rsi > rsi_short_min and  
              macd < macd_signal and  
              price < sma_20 * (1 + price_tolerance)):
            signal_direction = "SHORT"
            
            # Tính safety score
            safety_score = 6 if is_short_tf else 7
            
            if rsi > 70:  # Overbought
                safety_score += 1
            if price < ema_200:  # Below long-term trend
                safety_score += 1
            if market['trend_strength'] < 0:
                confidence = "HIGH"
                safety_score += 1
        
        # Extreme conditions (áp dụng cho tất cả timeframes)
        elif rsi < 20:  # Very oversold
            signal_direction = "LONG"
            safety_score = 8
            confidence = "HIGH"
        elif rsi > 80:  # Very overbought
            signal_direction = "SHORT"
            safety_score = 8
            confidence = "HIGH"
            
        # Momentum-based signals for short timeframes
        elif is_short_tf:
            # Additional conditions cho 1m, 5m
            if (rsi < 40 and macd > macd_signal and 
                current_data['close'] > current_data['open']):  # Green candle
                signal_direction = "LONG"
                safety_score = 6
                confidence = "MEDIUM"
            elif (rsi > 60 and macd < macd_signal and 
                  current_data['close'] < current_data['open']):  # Red candle
                signal_direction = "SHORT"
                safety_score = 6
                confidence = "MEDIUM"
                
        # Check minimum safety
        if safety_score < min_safety:
            signal_direction = None
        
        if not signal_direction:
            return None
        
        # Calculate entry, SL, TP với custom percentages hoặc ATR-based
        entry_price = price
        
        if tp_percent is not None and sl_percent is not None:
            # Tính TP/SL theo ROI trên margin (đúng cách futures)
            # TP/SL % là ROI trên margin, không phải % thay đổi giá coin
            
            # Với leverage, % thay đổi giá = ROI% / leverage
            price_change_tp = tp_percent / selected_leverage
            price_change_sl = sl_percent / selected_leverage
            
            if signal_direction == "LONG":
                stop_loss = entry_price * (1 - price_change_sl / 100)
                take_profit_1 = entry_price * (1 + price_change_tp / 100)
                take_profit_2 = entry_price * (1 + price_change_tp * 1.2 / 100)
                take_profit_3 = entry_price * (1 + price_change_tp * 1.5 / 100)
            else:
                # For SHORT positions
                stop_loss = entry_price * (1 + price_change_sl / 100)
                take_profit_1 = entry_price * (1 - price_change_tp / 100)
                take_profit_2 = entry_price * (1 - price_change_tp * 1.2 / 100)
                take_profit_3 = entry_price * (1 - price_change_tp * 1.5 / 100)
                
                # Ensure TP values don't go below 10% of entry price
                min_price = entry_price * 0.1
                take_profit_1 = max(take_profit_1, min_price)
                take_profit_2 = max(take_profit_2, min_price)
                take_profit_3 = max(take_profit_3, min_price)
        else:
            # Use ATR-based calculation (logic cũ)
            atr = current_data['atr']
            
            # Timeframe-specific multipliers
            if is_short_tf:  # 1m, 5m
                if market['volatility'] == 'HIGH':
                    sl_multiplier = 1.0
                    tp_multiplier = 3.0
                else:
                    sl_multiplier = 0.8
                    tp_multiplier = 2.5
            elif timeframe == "15m":  # 15m
                if market['volatility'] == 'HIGH':
                    sl_multiplier = 1.5
                    tp_multiplier = 4.0
                else:
                    sl_multiplier = 1.2
                    tp_multiplier = 3.5
            else:  # 1h, 4h, 1d - giữ nguyên logic cũ
                if market['volatility'] == 'HIGH':
                    sl_multiplier = 2.0
                    tp_multiplier = 5.0
                elif market['volatility'] == 'LOW':
                    sl_multiplier = 1.0
                    tp_multiplier = 3.0
                else:
                    sl_multiplier = 1.5
                    tp_multiplier = 4.0
            
            if signal_direction == "LONG":
                stop_loss = entry_price - (atr * sl_multiplier)
                take_profit_1 = entry_price + (atr * tp_multiplier)
                take_profit_2 = entry_price + (atr * tp_multiplier * 1.5)
                take_profit_3 = entry_price + (atr * tp_multiplier * 2.0)
            else:
                stop_loss = entry_price + (atr * sl_multiplier)
                take_profit_1 = entry_price - (atr * tp_multiplier)
                take_profit_2 = entry_price - (atr * tp_multiplier * 1.5)
                take_profit_3 = entry_price - (atr * tp_multiplier * 2.0)
        
        # Position sizing theo chuẩn Binance Futures
        risk_percent = 0.02  # 2% risk per trade
        if safety_score >= 8:
            risk_percent = 0.03  # 3% for high confidence
        elif safety_score <= 5:
            risk_percent = 0.01  # 1% for low confidence
        
        # Tính toán theo công thức Binance Futures
        risk_amount = balance * risk_percent
        
        # Distance từ entry đến SL (tính theo %)
        if signal_direction == "LONG":
            sl_distance_percent = ((entry_price - stop_loss) / entry_price) * 100
        else:
            sl_distance_percent = ((stop_loss - entry_price) / entry_price) * 100
        
        # Position size theo Binance formula
        # Position Size (USDT) = (Account Balance * Risk%) * Leverage / (SL Distance%)
        if sl_distance_percent > 0:
            position_size_usdt = (risk_amount * selected_leverage) / (sl_distance_percent / 100)
        else:
            position_size_usdt = risk_amount * selected_leverage
        
        # Position size trong coin
        position_size_coin = position_size_usdt / entry_price
        
        # Margin required
        margin_required = position_size_usdt / selected_leverage
        
        # Position size as percentage of balance
        position_size_percent = (margin_required / balance) * 100
        
        # Tính liquidation price (approximate)
        maintenance_margin_rate = 0.004  # 0.4% maintenance margin (BTCUSDT standard)
        if signal_direction == "LONG":
            liquidation_price = entry_price * (1 - (1/selected_leverage) + maintenance_margin_rate)
        else:
            liquidation_price = entry_price * (1 + (1/selected_leverage) + maintenance_margin_rate)
        
        # Use selected leverage directly
        leverage = selected_leverage
        
        # Risk/Reward calculation
        risk_reward = abs(take_profit_1 - entry_price) / abs(entry_price - stop_loss)
        
        signal = {
            'timestamp': datetime.now().isoformat(),
            'symbol': symbol,
            'timeframe': timeframe,
            'direction': signal_direction,
            'entry_price': round(entry_price, 4),
            'stop_loss': round(stop_loss, 4),
            'take_profit': [
                round(take_profit_1, 4),
                round(take_profit_2, 4),
                round(take_profit_3, 4)
            ],
            'position_size_usdt': round(position_size_usdt, 2),
            'position_size_coin': round(position_size_coin, 6),
            'margin_required': round(margin_required, 2),
            'position_size_percent': round(position_size_percent, 1),
            'leverage': leverage,
            'liquidation_price': round(liquidation_price, 4),
            'sl_distance_percent': round(sl_distance_percent, 2),
            'safety_score': safety_score,
            'confidence': confidence,
            'risk_reward': round(risk_reward, 2),
            'market_analysis': market
        }
        
        return signal
    
    def create_price_chart(self, df, symbol):
        """Tạo candlestick chart với indicators"""
        fig = make_subplots(
            rows=4, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            subplot_titles=('Price & Moving Averages', 'MACD', 'RSI', 'Volume'),
            row_heights=[0.5, 0.2, 0.2, 0.1]
        )
        
        # Candlestick
        fig.add_trace(go.Candlestick(
            x=df.index,
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name='Price'
        ), row=1, col=1)
        
        # Moving Averages
        fig.add_trace(go.Scatter(
            x=df.index, y=df['sma_20'],
            name='SMA 20', line=dict(color='orange')
        ), row=1, col=1)
        
        fig.add_trace(go.Scatter(
            x=df.index, y=df['sma_50'],
            name='SMA 50', line=dict(color='red')
        ), row=1, col=1)
        
        fig.add_trace(go.Scatter(
            x=df.index, y=df['ema_200'],
            name='EMA 200', line=dict(color='purple')
        ), row=1, col=1)
        
        # Bollinger Bands
        fig.add_trace(go.Scatter(
            x=df.index, y=df['bb_upper'],
            name='BB Upper', line=dict(color='gray', dash='dot')
        ), row=1, col=1)
        
        fig.add_trace(go.Scatter(
            x=df.index, y=df['bb_lower'],
            name='BB Lower', line=dict(color='gray', dash='dot'),
            fill='tonexty', fillcolor='rgba(128,128,128,0.1)'
        ), row=1, col=1)
        
        # MACD
        fig.add_trace(go.Scatter(
            x=df.index, y=df['macd'],
            name='MACD', line=dict(color='blue')
        ), row=2, col=1)
        
        fig.add_trace(go.Scatter(
            x=df.index, y=df['macd_signal'],
            name='MACD Signal', line=dict(color='red')
        ), row=2, col=1)
        
        fig.add_trace(go.Bar(
            x=df.index, y=df['macd_histogram'],
            name='MACD Histogram', marker_color='gray'
        ), row=2, col=1)
        
        # RSI
        fig.add_trace(go.Scatter(
            x=df.index, y=df['rsi'],
            name='RSI', line=dict(color='purple')
        ), row=3, col=1)
        
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)
        
        # Volume
        if 'volume' in df.columns:
            fig.add_trace(go.Bar(
                x=df.index, y=df['volume'],
                name='Volume', marker_color='lightblue'
            ), row=4, col=1)
        
        fig.update_layout(
            title=f'{symbol} Technical Analysis',
            height=800,
            showlegend=True,
            xaxis_rangeslider_visible=False
        )
        
        return fig

def main():
    gui = TradingGUI()
    
    # Header
    st.markdown('<h1 class="main-header">📈 Trading Insight Pro GUI</h1>', unsafe_allow_html=True)
    
    # Sidebar
    st.sidebar.markdown("## ⚙️ Trading Parameters")
    
    # Symbol selection
    selected_symbols = st.sidebar.multiselect(
        "🪙 Select Cryptocurrencies",
        gui.supported_symbols,
        default=[],  # Không chọn coin nào mặc định
        help="Để trống để scan tất cả coins với signals có độ an toàn cao. Chọn specific coins để focus analysis."
    )
    
    # Timeframe
    timeframe = st.sidebar.selectbox(
        "⏰ Timeframe",
        gui.timeframes,
        index=2,  # Default to 15m
        help="1m/5m: Scalping, 15m: Swing entries, 1h+: Position trading"
    )
    
    # Trading parameters
    balance = st.sidebar.number_input(
        "💰 Account Balance ($)",
        min_value=0,
        max_value=10000000,
        value=0,
        step=500,
        help="Your trading account balance - can be any amount"
    )
    
    # Leverage selection (direct choice)
    leverage_options = [5, 10, 15, 20, 25, 30, 50, 75, 100]
    selected_leverage = st.sidebar.selectbox(
        "⚡ Leverage",
        leverage_options,
        index=3,  # Default x20
        help="Choose your desired leverage multiplier"
    )
    
    min_safety = st.sidebar.slider(
        "🛡️ Minimum Safety Score",
        min_value=1,
        max_value=10,
        value=5,  # Lower default for more signals
        help="Lower values = More signals (higher risk)"
    )
    
    # Risk/Reward customization
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📊 Risk/Reward Settings")
    
    use_custom_rr = st.sidebar.checkbox(
        "🎯 Custom TP/SL Percentages", 
        value=False,
        help="Enable to set custom Take Profit and Stop Loss percentages"
    )
    
    if use_custom_rr:
        take_profit_percent = st.sidebar.slider(
            "💹 Take Profit (%)",
            min_value=5.0,
            max_value=200.0,
            value=100.0,  # Default 100% như user yêu cầu
            step=5.0,
            help="ROI % trên margin (không phải % thay đổi giá coin). VD: 100% = 100% lợi nhuận trên margin với leverage"
        )
        
        stop_loss_percent = st.sidebar.slider(
            "🛑 Stop Loss (%)",
            min_value=1.0,
            max_value=50.0,
            value=15.0,  # Default 15%
            step=1.0,
            help="ROI % lỗ trên margin. VD: 15% = mất 15% margin với leverage"
        )
        
        custom_rr_ratio = take_profit_percent / stop_loss_percent
        
        # Color-coded R/R display
        if custom_rr_ratio >= 3.0:
            rr_color = "🟢"  # Green - Excellent
            rr_quality = "Excellent"
        elif custom_rr_ratio >= 2.0:
            rr_color = "🟡"  # Yellow - Good  
            rr_quality = "Good"
        else:
            rr_color = "🔴"  # Red - Poor
            rr_quality = "Poor"
            
        st.sidebar.markdown(f"⚖️ **Risk/Reward: 1:{custom_rr_ratio:.2f}**")
        st.sidebar.markdown(f"{rr_color} **{rr_quality}** R/R Ratio")
    else:
        take_profit_percent = None
        stop_loss_percent = None
    
    auto_scan = st.sidebar.checkbox("🔄 Auto Scan (30s)")
    
    # Determine auto-scan mode
    if not selected_symbols:
        auto_scan_mode = True
        symbols_for_analysis = gui.supported_symbols
    else:
        auto_scan_mode = False
        symbols_for_analysis = selected_symbols
    
    # Main content
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Market Dashboard", "🎯 Trading Signals", "📈 Charts", "📋 Signal History"])
    
    with tab1:
        st.markdown("## 📊 Multi-Market Dashboard")
        
        if auto_scan_mode:
            st.info("🔍 **Auto-Scanning Mode**: Analyzing all coins for high-safety signals...")
        
        # Use the determined symbols for display
        selected_symbols = symbols_for_analysis
        
        # Create metrics for each symbol
        num_cols = min(len(selected_symbols), 4) if selected_symbols else 1
        cols = st.columns(num_cols)
        
        for idx, symbol in enumerate(selected_symbols):
            df = gui.load_market_data(symbol, timeframe)
            if df is not None:
                df = gui.calculate_indicators(df)
                market = gui.analyze_market(df)
                current = df.iloc[-1]
                
                with cols[idx % 4]:
                    # Price info
                    price_change = (current['close'] - df['close'].iloc[-2]) / df['close'].iloc[-2] * 100
                    
                    st.markdown(f"""
                    <div class="metric-card">
                        <h3>{symbol}</h3>
                        <h2>${current['close']:,.2f}</h2>
                        <p>Change: {price_change:+.2f}%</p>
                        <p>RSI: {current['rsi']:.1f}</p>
                        <p>Trend: {market['trend']}</p>
                        <p>Volatility: {market['volatility']}</p>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                with cols[idx % 4]:
                    st.error(f"❌ {symbol} - Error loading data")
        
        # Market summary
        st.markdown("### 📈 Market Summary")
        available_data = []
        
        for symbol in selected_symbols:
            df = gui.load_market_data(symbol, timeframe)
            if df is not None:
                df = gui.calculate_indicators(df)
                market = gui.analyze_market(df)
                current = df.iloc[-1]
                
                available_data.append({
                    'Symbol': symbol,
                    'Price': f"${current['close']:,.2f}",
                    'RSI': f"{current['rsi']:.1f}",
                    'MACD': f"{current['macd']:.2f}",
                    'Trend': market['trend'],
                    'Volatility': market['volatility'],
                    'Strength': f"{market['market_strength']:.1f}/10"
                })
        
        if available_data:
            df_summary = pd.DataFrame(available_data)
            st.dataframe(df_summary, width="stretch")
    
    with tab2:
        st.markdown("## 🎯 Real-Time Trading Signals")
        
        if st.button("🔍 Generate Signals", type="primary"):
            st.info("🔄 Analyzing market data and generating signals...")
            signals_found = 0
            high_safety_signals = []  # Store high safety signals for auto-scan mode
            debug_info = []
            
            # Determine symbols to process
            symbols_to_process = gui.supported_symbols if not selected_symbols else selected_symbols
            
            for symbol in symbols_to_process:
                # Generate signal first
                signal = gui.generate_signal(symbol, timeframe, balance, selected_leverage, min_safety, take_profit_percent, stop_loss_percent)
                
                # If auto-scan mode, only collect high safety signals
                if auto_scan_mode and signal and signal['safety_score'] >= 8:
                    high_safety_signals.append((symbol, signal))
                elif not auto_scan_mode:  # Normal mode - show all signals
                    with st.expander(f"📊 {symbol} Analysis", expanded=True):
                        # Add debug information
                        df = gui.load_market_data(symbol, timeframe)
                        if df is not None:
                            df = gui.calculate_indicators(df)
                            current = df.iloc[-1]
                            
                            # Show current market data
                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                st.metric("💰 Current Price", f"${current['close']:,.2f}")
                            with col2:
                                st.metric("📊 RSI", f"{current['rsi']:.1f}")
                            with col3:
                                st.metric("📈 MACD", f"{current['macd']:.3f}")
                            with col4:
                                st.metric("⚡ ATR", f"{current['atr']:.2f}")
                            
                            # Debug conditions
                            st.write("🔍 **Signal Conditions Check:**")
                            rsi_ok = current['rsi'] < 70 or current['rsi'] > 30
                            macd_trend = "Bullish" if current['macd'] > current['macd_signal'] else "Bearish"
                            
                            debug_info.append(f"• {symbol}: RSI={current['rsi']:.1f}, MACD={macd_trend}")
                            
                            st.write(f"• RSI condition: {'✅' if rsi_ok else '❌'} (Current: {current['rsi']:.1f})")
                            st.write(f"• MACD trend: {macd_trend}")
                            st.write(f"• Price vs SMA20: {'Above' if current['close'] > current['sma_20'] else 'Below'}")
                        
                        if signal:
                            signals_found += 1
                    if df is not None:
                        df = gui.calculate_indicators(df)
                        current = df.iloc[-1]
                        
                        # Show current market data
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("💰 Current Price", f"${current['close']:,.2f}")
                        with col2:
                            st.metric("📊 RSI", f"{current['rsi']:.1f}")
                        with col3:
                            st.metric("📈 MACD", f"{current['macd']:.3f}")
                        with col4:
                            st.metric("⚡ ATR", f"{current['atr']:.2f}")
                        
                        # Debug conditions
                        st.write("🔍 **Signal Conditions Check:**")
                        rsi_ok = current['rsi'] < 70 or current['rsi'] > 30
                        macd_trend = "Bullish" if current['macd'] > current['macd_signal'] else "Bearish"
                        
                        debug_info.append(f"• {symbol}: RSI={current['rsi']:.1f}, MACD={macd_trend}")
                        
                        st.write(f"• RSI condition: {'✅' if rsi_ok else '❌'} (Current: {current['rsi']:.1f})")
                        st.write(f"• MACD trend: {macd_trend}")
                        st.write(f"• Price vs SMA20: {'Above' if current['close'] > current['sma_20'] else 'Below'}")
                    
                    signal = gui.generate_signal(symbol, timeframe, balance, selected_leverage, min_safety, take_profit_percent, stop_loss_percent)
                    
                    if signal:
                        signals_found += 1
                        
                        # Signal display
                        signal_class = "signal-long" if signal['direction'] == "LONG" else "signal-short"
                        
                        st.markdown(f"""
                        <div class="{signal_class}">
                            <h2>🚨 {signal['direction']} SIGNAL</h2>
                            <h3>{symbol}</h3>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Signal details - Binance Futures Format
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.metric("💰 Entry Price", f"${signal['entry_price']:,.4f}")
                            st.metric("🛑 Stop Loss", f"${signal['stop_loss']:,.4f}")
                            st.metric("🎯 Take Profit 1", f"${signal['take_profit'][0]:,.4f}")
                            st.metric("⚡ Liquidation", f"${signal['liquidation_price']:,.4f}")
                        
                        with col2:
                            st.metric("📈 Leverage", f"{signal['leverage']}x")
                            st.metric("💵 Position Size", f"${signal['position_size_usdt']:,.2f}")
                            st.metric("🪙 Coin Amount", f"{signal['position_size_coin']:.6f}")
                            st.metric("💳 Margin Required", f"${signal['margin_required']:,.2f}")
                        
                        with col3:
                            st.metric("📊 Account %", f"{signal['position_size_percent']:.1f}%")
                            st.metric("🔒 Safety Score", f"{signal['safety_score']}/10")
                            st.metric("💪 Confidence", signal['confidence'])
                            st.metric("⚖️ Risk/Reward", f"1:{signal['risk_reward']:.2f}")
                        
                        # SL Distance info
                        st.info(f"📏 **SL Distance**: {signal['sl_distance_percent']:.2f}% from entry price")
                        
                        # Trading parameters cho Binance Futures
                        st.markdown("### 📋 Copy to Binance Futures")
                        
                        futures_code = f"""
🎯 FUTURES TRADE SETUP
Symbol: {symbol}
Direction: {signal['direction']} ({'Market BUY' if signal['direction'] == 'LONG' else 'Market SELL'})
Leverage: {signal['leverage']}x

💰 Entry: ${signal['entry_price']:,.4f}
🛑 Stop Loss: ${signal['stop_loss']:,.4f} ({signal['sl_distance_percent']:.2f}%)
🎯 TP1: ${signal['take_profit'][0]:,.4f}
🎯 TP2: ${signal['take_profit'][1]:,.4f}
🎯 TP3: ${signal['take_profit'][2]:,.4f}

📊 Position: ${signal['position_size_usdt']:,.2f} USDT
🪙 Quantity: {signal['position_size_coin']:.6f} {symbol.replace('USDT', '')}
💳 Margin: ${signal['margin_required']:,.2f} ({signal['position_size_percent']:.1f}% of balance)
⚡ Liquidation: ${signal['liquidation_price']:,.4f}

⚖️ Risk/Reward: 1:{signal['risk_reward']:.2f}
🔒 Safety: {signal['safety_score']}/10 ({signal['confidence']})
"""
                        
                        st.code(futures_code)
                        
                        # Add to history
                        signal['generated_at'] = datetime.now()
                        st.session_state.signals_history.append(signal)
                        
                    else:
                        st.markdown(f"""
                        <div class="signal-neutral">
                            <h3>⏳ No Signal - {symbol}</h3>
                            <p>Market conditions not optimal</p>
                        </div>
                        """, unsafe_allow_html=True)
            
            # Display high safety signals for auto-scan mode
            if auto_scan_mode:
                if high_safety_signals:
                    st.success(f"🎯 Found {len(high_safety_signals)} high-safety signals (Score ≥ 8)!")
                    
                    # Sort by safety score descending
                    high_safety_signals.sort(key=lambda x: x[1]['safety_score'], reverse=True)
                    
                    for symbol, signal in high_safety_signals:
                        signals_found += 1
                        
                        # Signal display
                        signal_class = "signal-long" if signal['direction'] == "LONG" else "signal-short"
                        
                        with st.expander(f"🚨 {signal['direction']} SIGNAL - {symbol} (Safety: {signal['safety_score']}/10)", expanded=True):
                            
                            # Signal details - Binance Futures Format
                            col1, col2, col3 = st.columns(3)
                            
                            with col1:
                                st.metric("💰 Entry Price", f"${signal['entry_price']:,.4f}")
                                st.metric("🛑 Stop Loss", f"${signal['stop_loss']:,.4f}")
                                st.metric("🎯 Take Profit 1", f"${signal['take_profit'][0]:,.4f}")
                                st.metric("⚡ Liquidation", f"${signal['liquidation_price']:,.4f}")
                            
                            with col2:
                                st.metric("📈 Leverage", f"{signal['leverage']}x")
                                st.metric("💵 Position Size", f"${signal['position_size_usdt']:,.2f}")
                                st.metric("🪙 Coin Amount", f"{signal['position_size_coin']:.6f}")
                                st.metric("💳 Margin Required", f"${signal['margin_required']:,.2f}")
                            
                            with col3:
                                st.metric("📊 Account %", f"{signal['position_size_percent']:.1f}%")
                                st.metric("🔒 Safety Score", f"{signal['safety_score']}/10")
                                st.metric("💪 Confidence", signal['confidence'])
                                st.metric("⚖️ Risk/Reward", f"1:{signal['risk_reward']:.2f}")
                            
                            # SL Distance info
                            st.info(f"📏 **SL Distance**: {signal['sl_distance_percent']:.2f}% from entry price")
                            
                            # Trading parameters cho Binance Futures
                            st.markdown("### 📋 Copy to Binance Futures")
                            
                            futures_code = f"""🎯 FUTURES TRADE SETUP
Symbol: {symbol}
Direction: {signal['direction']} ({'Market BUY' if signal['direction'] == 'LONG' else 'Market SELL'})
Leverage: {signal['leverage']}x

💰 Entry: ${signal['entry_price']:,.4f}
🛑 Stop Loss: ${signal['stop_loss']:,.4f} ({signal['sl_distance_percent']:.2f}%)
🎯 TP1: ${signal['take_profit'][0]:,.4f}
🎯 TP2: ${signal['take_profit'][1]:,.4f}
🎯 TP3: ${signal['take_profit'][2]:,.4f}

📊 Position: ${signal['position_size_usdt']:,.2f} USDT
🪙 Quantity: {signal['position_size_coin']:.6f} {symbol.replace('USDT', '')}
💳 Margin: ${signal['margin_required']:,.2f} ({signal['position_size_percent']:.1f}% of balance)
⚡ Liquidation: ${signal['liquidation_price']:,.4f}

⚖️ Risk/Reward: 1:{signal['risk_reward']:.2f}
🔒 Safety: {signal['safety_score']}/10 ({signal['confidence']})
"""
                            
                            st.code(futures_code)
                            
                            # Add to history
                            signal['generated_at'] = datetime.now()
                            st.session_state.signals_history.append(signal)
                else:
                    st.warning("⏳ No high-safety signals found. Market conditions may not be optimal for high-confidence trades.")
                    st.info("💡 **Tip**: High-safety signals require Safety Score ≥ 8. You can lower the minimum safety score in sidebar to see more signals.")
            
            if signals_found == 0 and not auto_scan_mode:
                st.warning("⏳ No trading signals generated. Try lowering the safety score or different timeframes.")
                
                # Show debug summary
                with st.expander("🔍 Debug Information", expanded=False):
                    st.write("**Market Analysis Summary:**")
                    for info in debug_info:
                        st.write(info)
                    st.write("\n**Tips to get more signals:**")
                    st.write("• Lower the minimum safety score to 3-4")
                    st.write("• Try different timeframes (15m for more signals)")
                    st.write("• Check during high volatility periods")
            else:
                st.success(f"✅ Generated {signals_found} trading signals!")
        
        # Auto-scan feature
        if auto_scan:
            placeholder = st.empty()
            countdown = st.empty()
            
            for i in range(30, 0, -1):
                countdown.markdown(f"🔄 Next auto-scan in: **{i}s**")
                time.sleep(1)
            
            countdown.empty()
            st.rerun()
    
    with tab3:
        st.markdown("## 📈 Technical Analysis Charts")
        
        chart_symbol = st.selectbox("Select Symbol for Chart", gui.supported_symbols)
        
        if chart_symbol:
            df = gui.load_market_data(chart_symbol, timeframe)
            if df is not None:
                df = gui.calculate_indicators(df)
                
                # Display chart
                fig = gui.create_price_chart(df, chart_symbol)
                st.plotly_chart(fig, width="stretch")
                
                # Current market analysis
                market = gui.analyze_market(df)
                current = df.iloc[-1]
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Current Price", f"${current['close']:,.2f}")
                    st.metric("RSI", f"{current['rsi']:.1f}")
                
                with col2:
                    st.metric("MACD", f"{current['macd']:.2f}")
                    st.metric("ATR %", f"{current['atr_percent']:.2f}%")
                
                with col3:
                    st.metric("Market Trend", market['trend'])
                    st.metric("Volatility", market['volatility'])
                
                with col4:
                    st.metric("Market Strength", f"{market['market_strength']:.1f}/10")
                    st.metric("Signals", str(len(market['signals'])))
    
    with tab4:
        st.markdown("## 📋 Signal History")
        
        if st.session_state.signals_history:
            # Display recent signals
            for i, signal in enumerate(reversed(st.session_state.signals_history[-10:])):
                with st.expander(f"{signal['symbol']} {signal['direction']} - {signal['generated_at'].strftime('%H:%M:%S')}", expanded=i<3):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**Entry:** ${signal['entry_price']:,.2f}")
                        st.write(f"**Stop Loss:** ${signal['stop_loss']:,.2f}")
                        st.write(f"**Take Profit:** ${signal['take_profit'][0]:,.2f}")
                        st.write(f"**Leverage:** {signal['leverage']}x")
                    
                    with col2:
                        st.write(f"**Safety Score:** {signal['safety_score']}/10")
                        st.write(f"**Confidence:** {signal['confidence']}")
                        st.write(f"**Risk/Reward:** 1:{signal['risk_reward']:.2f}")
                        st.write(f"**Position Size:** {signal['position_size_percent']:.1f}%")
            
            # Clear history button
            if st.button("🗑️ Clear History"):
                st.session_state.signals_history = []
                st.rerun()
        else:
            st.info("📝 No signals generated yet. Use the Trading Signals tab to generate signals.")
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #666;">
        <p>⚠️ <strong>Risk Warning:</strong> Trading cryptocurrencies involves substantial risk. Never risk more than you can afford to lose.</p>
        <p>💡 This tool is for educational purposes. Always do your own research before making trading decisions.</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()