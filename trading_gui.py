import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import json
import os
import re
from datetime import datetime, timedelta
import time
import random
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Optional

# Technical Analysis
import ta
import talib

# New Professional Modules
from src.atr_risk_manager import ATRRiskManager
from src.futures_data_provider import BinanceFuturesDataProvider
from src.professional_momentum import ProfessionalMomentumStrategy
from src.robust_backtester import RobustBacktester
from src.portfolio_risk_manager import PortfolioRiskManager
from src.circuit_breaker import CircuitBreakerManager

# Import constants for v4.2.1 standardization
from constants import MIN_RR, get_regime_strength, safe_get_signal_field

# Analytics Integration
try:
    from src.analytics_integration import (
        analytics_integrator, 
        track_generated_signal, 
        show_analytics_summary_widget,
        add_analytics_integration_to_main_gui
    )
    from src.trading_analytics import auth, trade_tracker, dashboard
    ANALYTICS_AVAILABLE = True
except ImportError:
    ANALYTICS_AVAILABLE = False
    print("⚠️ Analytics module not available - running in basic mode")

def render_analytics_tab():
    """Render analytics tab with real trading data"""
    st.markdown("## 📊 Trading Analytics Dashboard")
    
    # Check if user is logged in to analytics
    if not analytics_integrator.initialize_user_session():
        st.warning("🔐 Please login to access your trading performance data.")
        st.info("Use the credentials form on the main screen to sign in.")
        return
    
    # Get current user info
    user_info = st.session_state.get('analytics_user')
    if not user_info:
        st.error("Analytics session expired. Please re-login.")
        return
    
    user_id = user_info['id']
    
    st.success(f"✅ Analytics Active: {user_info['username']} ({user_info['subscription_tier']})")
    
    # Date range selector
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("From", value=datetime.now().date() - timedelta(days=30))
    with col2:
        end_date = st.date_input("To", value=datetime.now().date())
    
    # Get trades data
    trades_df = trade_tracker.get_user_trades(user_id, limit=1000)
    
    if trades_df.empty:
        st.info("📊 No trading data found. Start generating signals to build your analytics.")
        return
    
    # Filter by date range
    trades_df['entry_date'] = pd.to_datetime(trades_df['entry_time']).dt.date
    period_trades = trades_df[
        (trades_df['entry_date'] >= start_date) & 
        (trades_df['entry_date'] <= end_date)
    ]
    
    if period_trades.empty:
        st.warning("📅 No trades found in selected date range")
        return
    
    # Key Performance Metrics
    st.markdown("### 🎯 Performance Overview")
    
    col1, col2, col3, col4 = st.columns(4)
    
    total_trades = len(period_trades)
    closed_trades = period_trades[period_trades['status'] == 'closed']
    
    with col1:
        st.metric("Total Signals", total_trades)
    
    with col2:
        open_positions = len(period_trades[period_trades['status'] == 'open'])
        st.metric("Open Positions", open_positions)
    
    with col3:
        if not closed_trades.empty:
            winning_trades = len(closed_trades[closed_trades['pnl_usdt'] > 0])
            win_rate = (winning_trades / len(closed_trades) * 100) if len(closed_trades) > 0 else 0
            st.metric("Win Rate", f"{win_rate:.1f}%")
        else:
            st.metric("Win Rate", "0.0%")
    
    with col4:
        if not closed_trades.empty:
            total_pnl = closed_trades['pnl_usdt'].sum()
            st.metric("Total P&L", f"${total_pnl:.2f}")
        else:
            st.metric("Total P&L", "$0.00")
    
    # Performance Charts
    if not closed_trades.empty:
        st.markdown("### 📈 Performance Charts")
        
        # Daily PnL
        daily_pnl = closed_trades.groupby('entry_date')['pnl_usdt'].sum().reset_index()
        daily_pnl['cumulative_pnl'] = daily_pnl['pnl_usdt'].cumsum()
        
        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=('Daily P&L', 'Cumulative P&L'),
            vertical_spacing=0.1
        )
        
        # Daily bars
        colors = ['green' if pnl >= 0 else 'red' for pnl in daily_pnl['pnl_usdt']]
        fig.add_trace(
            go.Bar(x=daily_pnl['entry_date'], y=daily_pnl['pnl_usdt'], 
                   marker_color=colors, name='Daily P&L'),
            row=1, col=1
        )
        
        # Cumulative line
        fig.add_trace(
            go.Scatter(x=daily_pnl['entry_date'], y=daily_pnl['cumulative_pnl'],
                      mode='lines+markers', name='Cumulative P&L', 
                      line=dict(color='blue', width=2)),
            row=2, col=1
        )
        
        fig.update_layout(height=600, showlegend=False)
        fig.update_xaxes(title_text="Date")
        fig.update_yaxes(title_text="P&L (USDT)", row=1, col=1)
        fig.update_yaxes(title_text="Cumulative P&L (USDT)", row=2, col=1)
        
        st.plotly_chart(fig, use_container_width=True)
    
    # Safety Score Analysis
    st.markdown("### 🎯 Safety Score Performance")
    
    if not closed_trades.empty:
        # Group by safety score
        safety_stats = closed_trades.groupby('safety_score').agg({
            'pnl_usdt': ['count', 'mean', lambda x: len(x[x > 0]) / len(x) * 100]
        }).round(2)
        
        safety_stats.columns = ['Trade Count', 'Avg P&L', 'Win Rate %']
        safety_stats = safety_stats.reset_index()
        
        # Safety score chart
        fig = px.bar(
            safety_stats,
            x='safety_score',
            y='Win Rate %',
            title='Win Rate by Safety Score',
            color='Win Rate %',
            color_continuous_scale='RdYlGn',
            text='Trade Count'
        )
        fig.update_traces(textposition='outside')
        st.plotly_chart(fig, use_container_width=True)
        
        # Safety stats table
        st.dataframe(safety_stats, use_container_width=True, hide_index=True)
    
    # Recent Trades Table
    st.markdown("### 📋 Recent Trading Activity")
    
    # Display recent trades
    display_cols = ['symbol', 'direction', 'entry_price', 'exit_price', 'pnl_usdt', 
                   'safety_score', 'status', 'outcome', 'entry_time']
    
    recent_trades = period_trades[display_cols].tail(20).copy()
    
    if not recent_trades.empty:
        # Format the data
        recent_trades['entry_price'] = recent_trades['entry_price'].round(6)
        recent_trades['exit_price'] = recent_trades['exit_price'].fillna(0).round(6)
        recent_trades['pnl_usdt'] = recent_trades['pnl_usdt'].fillna(0).round(2)
        recent_trades['entry_time'] = pd.to_datetime(recent_trades['entry_time']).dt.strftime('%Y-%m-%d %H:%M')
        
        # Style the dataframe
        def highlight_pnl(val):
            if pd.isna(val) or val == 0:
                return ''
            elif val > 0:
                return 'background-color: #d4f6d4'
            else:
                return 'background-color: #f6d4d4'
        
        styled_df = recent_trades.style.applymap(highlight_pnl, subset=['pnl_usdt'])
        st.dataframe(styled_df, use_container_width=True, hide_index=True)
        
        # Export option
        if st.button("📊 Export Trading Data"):
            csv = trades_df.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"trading_data_{user_id}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
    
    # Link to analytics refresh info
    st.markdown("---")
    st.caption("Analytics data updates automatically when you track new signals from this app.")

def chandelier_exit(df: pd.DataFrame, n: int = 22, k: float = 3.0, side: str = "LONG") -> float:
    """
    Calculate proper LeBeau Chandelier Exit
    
    Args:
        df: DataFrame with OHLCV data
        n: Period for ATR and highest high/lowest low (default 22)
        k: ATR multiplier (default 3.0)
        side: "LONG" or "SHORT"
        
    Returns:
        Chandelier Exit level
    """
    try:
        atr = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=n).average_true_range()
        if side == "LONG":
            hh = df['high'].rolling(n).max()
            return float(hh.iloc[-1] - k * atr.iloc[-1])
        else:
            ll = df['low'].rolling(n).min()
            return float(ll.iloc[-1] + k * atr.iloc[-1])
    except Exception as e:
        # Fallback calculation
        atr_simple = df['close'].rolling(n).std() * 2.0  # Simplified ATR
        if side == "LONG":
            hh = df['high'].rolling(n).max()
            return float(hh.iloc[-1] - k * atr_simple.iloc[-1])
        else:
            ll = df['low'].rolling(n).min()
            return float(ll.iloc[-1] + k * atr_simple.iloc[-1])

def get_symbol_cluster(symbol: str) -> str:
    """Get cluster classification for symbol (v4.2.1 stub)"""
    # Simple clustering based on symbol patterns
    if symbol.startswith(('BTC', 'ETH')):
        return 'major'
    elif symbol in ['BNB', 'ADA', 'XRP', 'SOL', 'DOT', 'AVAX', 'MATIC']:
        return 'altcoin'
    elif symbol in ['DOGE', 'SHIB', 'PEPE', 'FLOKI']:
        return 'meme'
    else:
        return 'defi'

def check_cluster_limits(positions: list, new_symbol: str, max_correlated_risk: float = 0.03) -> tuple:
    """Check if adding position violates cluster limits (v4.2.1 stub)"""
    new_cluster = get_symbol_cluster(new_symbol)
    cluster_risk = sum(pos.get('risk_percent', 0) for pos in positions 
                      if get_symbol_cluster(pos.get('symbol', '')) == new_cluster)
    
    if cluster_risk > max_correlated_risk * 100:  # Convert to percentage
        return False, f"Cluster {new_cluster} risk too high: {cluster_risk:.1f}%"
    return True, "Cluster limits OK"

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

# Initialize session state - v4.2.1: Use setdefault pattern
st.session_state.setdefault('signals_history', [])
st.session_state.setdefault('selected_signals', [])
st.session_state.setdefault('tracked_trades', [])


def _normalize_streamlit_key(value: str) -> str:
    """Convert arbitrary strings to safe Streamlit widget keys."""
    return re.sub(r"[^0-9a-zA-Z_]+", "_", value or "")


def _store_authenticated_user(user_info: Dict):
    """Persist authenticated user details in the Streamlit session."""
    st.session_state.authenticated_user = user_info
    st.session_state.analytics_user = user_info

    if ANALYTICS_AVAILABLE:
        try:
            session_token = auth.create_session(user_info['id'])
            st.session_state.auth_session_token = session_token
        except Exception:
            st.session_state.auth_session_token = None

    if 'signals_history' in st.session_state:
        st.session_state.signals_history = []
    st.session_state.pop('tracked_trades', None)
    st.session_state.pop('selected_signals', None)
    st.session_state.pop('auth_error', None)
    st.session_state.pop('auth_notice', None)


def logout_user():
    """Reset authentication-related session state and return to login screen."""
    st.session_state.pop('authenticated_user', None)
    st.session_state.pop('analytics_user', None)
    st.session_state.pop('auth_session_token', None)
    st.session_state.pop('tracked_trades', None)
    if 'signals_history' in st.session_state:
        st.session_state.signals_history = []

    st.session_state.auth_mode_selection = 'Login'
    st.session_state.auth_notice = "Bạn đã đăng xuất thành công."  # You have logged out successfully.
    st.rerun()


def ensure_user_logged_in() -> Optional[Dict]:
    """Render authentication flow and return user info when logged in."""
    if not ANALYTICS_AVAILABLE:
        st.error("Authentication system unavailable. Please ensure analytics components are installed.")
        return None

    user = st.session_state.get('authenticated_user')
    if user:
        return user

    st.markdown("## 🔐 Đăng nhập để tiếp tục")

    notice = st.session_state.pop('auth_notice', None)
    if notice:
        st.info(notice)

    error = st.session_state.pop('auth_error', None)
    if error:
        st.error(error)

    if 'auth_mode_selection' not in st.session_state:
        st.session_state.auth_mode_selection = 'Login'

    mode_label = st.radio(
        "Authentication Mode",
        options=("Login", "Create Account"),
        horizontal=True,
        key="auth_mode_selection"
    )
    mode = 'login' if mode_label == "Login" else 'signup'

    if mode == 'login':
        with st.form("login_form"):
            username = st.text_input("Username", placeholder="Enter username")
            password = st.text_input("Password", type="password", placeholder="Enter password")
            submitted = st.form_submit_button("Login", type="primary", use_container_width=True)

        if submitted:
            if not username or not password:
                st.session_state.auth_error = "Please enter both username and password."
                st.rerun()

            user_info = auth.authenticate_user(username.strip(), password)
            if user_info:
                _store_authenticated_user(user_info)
                st.rerun()
            else:
                st.session_state.auth_error = "Invalid username or password."
                st.rerun()

        st.caption("Chưa có tài khoản? Chọn **Create Account** để đăng ký.")
    else:
        with st.form("signup_form"):
            username = st.text_input("Username", placeholder="Choose a username")
            email = st.text_input("Email", placeholder="name@example.com")
            password = st.text_input("Password", type="password", placeholder="Create a password")
            confirm_password = st.text_input("Confirm Password", type="password", placeholder="Repeat password")
            submitted = st.form_submit_button("Create Account", type="primary", use_container_width=True)

        if submitted:
            if not username or not email or not password or not confirm_password:
                st.session_state.auth_error = "All fields are required."
                st.rerun()

            if password != confirm_password:
                st.session_state.auth_error = "Passwords do not match."
                st.rerun()

            success, message = auth.register_user(username.strip(), email.strip(), password)
            if success:
                st.session_state.auth_notice = "Account created successfully. Please log in."
                st.session_state.auth_mode_selection = 'Login'
                st.rerun()
            else:
                st.session_state.auth_error = message
                st.rerun()

        st.caption("Đã có tài khoản? Chọn lại **Login** để đăng nhập.")

    return None


class TradingGUI:
    def __init__(self):
        # Error tracking and telemetry (silent monitoring)
        self.error_counters = {
            'api_errors': 0,
            'data_parse_errors': 0,
            'signal_generation_errors': 0,
            'batch_loading_errors': 0
        }
        self.error_details = []  # Store recent error details for debugging
        
        self.supported_symbols = [
            # Major Coins (Top 10)
            "BTC/USDT", "ETH/USDT", "BNB/USDT", "XRP/USDT", "ADA/USDT",
            "SOL/USDT", "DOGE/USDT", "TRX/USDT", "AVAX/USDT", "DOT/USDT",
            
            # Layer 1 & Infrastructure
            "MATIC/USDT", "ATOM/USDT", "NEAR/USDT", "ALGO/USDT", "ICP/USDT",
            "FTM/USDT", "ONE/USDT", "HBAR/USDT", "EGLD/USDT", "FLOW/USDT",
            "ROSE/USDT", "KSM/USDT", "KAVA/USDT", "MINA/USDT", "OSMO/USDT",
            
            # DeFi Ecosystem
            "UNI/USDT", "LINK/USDT", "AAVE/USDT", "MKR/USDT", "COMP/USDT",
            "SNX/USDT", "CRV/USDT", "1INCH/USDT", "SUSHI/USDT", "YFI/USDT",
            "CAKE/USDT", "GMX/USDT", "DYDX/USDT", "LDO/USDT", "RPL/USDT",
            
            # Legacy Coins
            "LTC/USDT", "BCH/USDT", "ETC/USDT", "XMR/USDT", "ZEC/USDT",
            "DASH/USDT", "XLM/USDT", "VET/USDT", "THETA/USDT", "FIL/USDT",
            
            # Gaming & NFT
            "AXS/USDT", "SAND/USDT", "MANA/USDT", "ENJ/USDT", "GALA/USDT",
            "APE/USDT", "IMX/USDT", "GMT/USDT", "CHZ/USDT",
            
            # Meme Coins
            "SHIB/USDT", "FLOKI/USDT", "PEPE/USDT", "BONK/USDT", "WIF/USDT",
            
            # AI & Innovation
            "FET/USDT", "OCEAN/USDT", "AGIX/USDT", "GRT/USDT", "RENDER/USDT",
            
            # Additional Popular Coins
            "LUNC/USDT", "USTC/USDT", "ARB/USDT", "OP/USDT", "RNDR/USDT",
            "BLUR/USDT", "SUI/USDT", "APT/USDT", "JTO/USDT", "PYTH/USDT",
            
            # Exchange Tokens
            "FTT/USDT"
        ]
        self.timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]
        
        # Binance API setup
        self.binance_base_url = "https://api.binance.com/api/v3"
        self.symbols_map = {
            # Major Coins
            "BTC/USDT": "BTCUSDT", "ETH/USDT": "ETHUSDT", "BNB/USDT": "BNBUSDT",
            "XRP/USDT": "XRPUSDT", "ADA/USDT": "ADAUSDT", "SOL/USDT": "SOLUSDT",
            "DOGE/USDT": "DOGEUSDT", "TRX/USDT": "TRXUSDT", "AVAX/USDT": "AVAXUSDT",
            "DOT/USDT": "DOTUSDT",
            
            # Layer 1 & Infrastructure  
            "MATIC/USDT": "MATICUSDT", "ATOM/USDT": "ATOMUSDT", "NEAR/USDT": "NEARUSDT",
            "ALGO/USDT": "ALGOUSDT", "ICP/USDT": "ICPUSDT", "FTM/USDT": "FTMUSDT",
            "ONE/USDT": "ONEUSDT", "HBAR/USDT": "HBARUSDT", "EGLD/USDT": "EGLDUSDT",
            "FLOW/USDT": "FLOWUSDT", "ROSE/USDT": "ROSEUSDT", "KSM/USDT": "KSMUSDT",
            "KAVA/USDT": "KAVAUSDT", "MINA/USDT": "MINAUSDT", "OSMO/USDT": "OSMOUSDT",
            
            # DeFi Ecosystem
            "UNI/USDT": "UNIUSDT", "LINK/USDT": "LINKUSDT", "AAVE/USDT": "AAVEUSDT",
            "MKR/USDT": "MKRUSDT", "COMP/USDT": "COMPUSDT", "SNX/USDT": "SNXUSDT",
            "CRV/USDT": "CRVUSDT", "1INCH/USDT": "1INCHUSDT", "SUSHI/USDT": "SUSHIUSDT",
            "YFI/USDT": "YFIUSDT", "CAKE/USDT": "CAKEUSDT", "GMX/USDT": "GMXUSDT",
            "DYDX/USDT": "DYDXUSDT", "LDO/USDT": "LDOUSDT", "RPL/USDT": "RPLUSDT",
            
            # Legacy Coins
            "LTC/USDT": "LTCUSDT", "BCH/USDT": "BCHUSDT", "ETC/USDT": "ETCUSDT",
            "XMR/USDT": "XMRUSDT", "ZEC/USDT": "ZECUSDT", "DASH/USDT": "DASHUSDT",
            "XLM/USDT": "XLMUSDT", "VET/USDT": "VETUSDT", "THETA/USDT": "THETAUSDT",
            "FIL/USDT": "FILUSDT",
            
            # Gaming & NFT
            "AXS/USDT": "AXSUSDT", "SAND/USDT": "SANDUSDT", "MANA/USDT": "MANAUSDT",
            "ENJ/USDT": "ENJUSDT", "GALA/USDT": "GALAUSDT", "APE/USDT": "APEUSDT",
            "IMX/USDT": "IMXUSDT", "GMT/USDT": "GMTUSDT", "CHZ/USDT": "CHZUSDT",
            
            # Meme Coins
            "SHIB/USDT": "SHIBUSDT", "FLOKI/USDT": "FLOKIUSDT", "PEPE/USDT": "PEPEUSDT",
            "BONK/USDT": "BONKUSDT", "WIF/USDT": "WIFUSDT",
            
            # AI & Innovation  
            "FET/USDT": "FETUSDT", "OCEAN/USDT": "OCEANUSDT", "AGIX/USDT": "AGIXUSDT",
            "GRT/USDT": "GRTUSDT", "RENDER/USDT": "RENDERUSDT",
            
            # Additional Popular Coins
            "LUNC/USDT": "LUNCUSDT", "USTC/USDT": "USTCUSDT", "ARB/USDT": "ARBUSDT",
            "OP/USDT": "OPUSDT", "RNDR/USDT": "RNDRUSDT", "BLUR/USDT": "BLURUSDT",
            "SUI/USDT": "SUIUSDT", "APT/USDT": "APTUSDT", "JTO/USDT": "JTOUSDT",
            "PYTH/USDT": "PYTHUSDT",
            
            # Exchange Tokens (only available ones)
            "FTT/USDT": "FTTUSDT"
        }
        self.timeframe_map = {"1h": "1h", "4h": "4h", "1d": "1d"}
        
        # Initialize Professional Trading Modules
        self.atr_risk_manager = ATRRiskManager()
        self.futures_data_provider = BinanceFuturesDataProvider()
        self.momentum_strategy = ProfessionalMomentumStrategy()
        self.robust_backtester = RobustBacktester()
        self.portfolio_risk_manager = PortfolioRiskManager()
        self.circuit_breaker = CircuitBreakerManager()
        
        # Conservative Risk Settings
        self.base_risk_per_trade = 0.01  # 1% instead of 2%
        self.max_exposure_per_trade = 0.25  # 25% instead of 50%
        self.max_concurrent_positions = 3  # Max 3 positions
        self.circuit_breaker_enabled = True
        
        # Initialize circuit breaker in session state
        if 'circuit_breaker_state' not in st.session_state:
            st.session_state.circuit_breaker_state = self.circuit_breaker.get_status_summary()
        
        # Initialize market data caching
        st.session_state.setdefault('market_data_cache', {})
        st.session_state.setdefault('cache_timestamps', {})
            
        # Cache TTL (3 minutes for faster updates during scanning)
        self.cache_ttl = 180
        
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
            self._track_error('api_errors', f"Failed to get current prices: {str(e)}")
            return {}

    def _track_error(self, error_type: str, error_detail: str, symbol: str = None):
        """Silent error tracking for monitoring - does not display to user"""
        self.error_counters[error_type] = self.error_counters.get(error_type, 0) + 1
        
        # Keep only recent 50 errors to prevent memory issues
        if len(self.error_details) > 50:
            self.error_details = self.error_details[-25:]  # Keep last 25
        
        self.error_details.append({
            'type': error_type,
            'detail': error_detail,
            'symbol': symbol,
            'timestamp': datetime.now().isoformat()
        })

    def get_error_telemetry(self) -> Dict:
        """Get error telemetry for debugging (not shown in UI)"""
        return {
            'counters': self.error_counters.copy(),
            'recent_errors': self.error_details[-10:] if self.error_details else [],
            'total_errors': sum(self.error_counters.values()),
            'error_rate': sum(self.error_counters.values()) / max(1, len(self.supported_symbols))
        }
    
    def load_market_data(self, symbol, timeframe, limit=None, use_cache=True):
        """Load REAL market data từ Binance API với caching"""
        try:
            # Default limit - ít hơn cho performance
            if limit is None:
                limit = 200  # Giảm từ 500 xuống 200 cho performance
            
            # Check cache first
            cache_key = f"{symbol}_{timeframe}_{limit}"
            current_time = time.time()
            
            if (use_cache and 
                cache_key in st.session_state.market_data_cache and
                cache_key in st.session_state.cache_timestamps and
                current_time - st.session_state.cache_timestamps[cache_key] < self.cache_ttl):
                return st.session_state.market_data_cache[cache_key].copy()
            
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
            
            # Get candles for analysis
            url = f"{self.binance_base_url}/klines"
            params = {
                'symbol': binance_symbol,
                'interval': binance_tf,
                'limit': limit
            }
            
            response = requests.get(url, params=params, timeout=10)  # Giảm timeout
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
            
            # Cache the result
            if use_cache:
                st.session_state.market_data_cache[cache_key] = df.copy()
                st.session_state.cache_timestamps[cache_key] = current_time
            
            return df
            
        except Exception as e:
            self._track_error('api_errors', f"Load market data failed for {symbol}: {str(e)}", symbol)
            return None
            if use_cache:  # This means we're in normal UI mode, not batch mode
                try:
                    # Check if we're in Streamlit context
                    if 'st' in globals() and hasattr(st, 'error'):
                        st.error(f"❌ Error loading real data for {symbol}: {e}")
                except:
                    pass
            # Return None to show error state instead of fake data
            return None
    
    def batch_load_market_data(self, symbols, timeframe, limit=100):
        """Parallel loading of market data for multiple symbols"""
        def load_single(symbol):
            try:
                # Bypass cache in batch mode để tránh Streamlit session state issues
                return symbol, self.load_market_data(symbol, timeframe, limit=limit, use_cache=False)
            except Exception as e:
                self._track_error('batch_loading_errors', f"Batch load failed for {symbol}: {str(e)}", symbol)
                return symbol, None
        
        # Use ThreadPoolExecutor for parallel API calls
        results = {}
        with ThreadPoolExecutor(max_workers=4) as executor:  # Reduce workers to avoid rate limit
            future_to_symbol = {executor.submit(load_single, symbol): symbol for symbol in symbols}
            
            for future in as_completed(future_to_symbol):
                try:
                    symbol, data = future.result()
                    if data is not None and len(data) > 0:
                        results[symbol] = data
                except Exception as e:
                    pass
        
        return results
    
    def generate_signal_from_data(self, symbol, df, timeframe, balance, leverage, min_safety, tp_percent, sl_percent):
        """Generate signal from pre-loaded data - optimized for batch processing"""
        try:
            if df is None or len(df) < 50:
                return None
            
            # Skip circuit breaker and UI in batch mode for performance
            # Calculate indicators
            df = self.calculate_indicators(df)
            
            # Use professional momentum strategy
            signals = self.momentum_strategy.generate_signals(df)
            if not signals:
                return None
            
            # Get the latest signal
            latest_signal = signals[-1]
            signal_direction = latest_signal['direction']
            
            # Quick futures check without UI
            futures_approved, futures_reason = self.futures_data_provider.get_futures_signal_filter(symbol, signal_direction)
            if not futures_approved:
                return None
                
            entry_price = latest_signal['entry_price']
            
            # Quick TP/SL calculation for batch mode
            if tp_percent is not None and sl_percent is not None:
                price_change_tp = tp_percent / leverage
                price_change_sl = sl_percent / leverage
                
                if signal_direction == "LONG":
                    stop_loss = entry_price * (1 - price_change_sl / 100)
                    take_profit_1 = entry_price * (1 + price_change_tp / 100)
                    take_profit_2 = entry_price * (1 + price_change_tp * 1.3 / 100)  # 30% more than TP1
                else:
                    stop_loss = entry_price * (1 + price_change_sl / 100)
                    take_profit_1 = entry_price * (1 - price_change_tp / 100)
                    take_profit_2 = entry_price * (1 - price_change_tp * 1.3 / 100)  # 30% more than TP1
                
                atr_value = entry_price * 0.02  # Estimated 2% ATR for custom calculations
            else:
                # Use ATR-based calculation
                risk_result = self.atr_risk_manager.calculate_atr_stops(
                    df=df, 
                    entry_price=entry_price, 
                    direction=signal_direction,
                    risk_level='MODERATE'
                )
                stop_loss = risk_result['stop_loss']
                take_profit_1 = risk_result['take_profit_1']
                take_profit_2 = risk_result.get('take_profit_2', take_profit_1 * 1.05)  # Fallback TP2
                atr_value = risk_result.get('atr_value', entry_price * 0.02)  # Fallback ATR
            
            # Quick R/R check
            if signal_direction == "LONG":
                risk = entry_price - stop_loss
                reward = take_profit_1 - entry_price
            else:
                risk = stop_loss - entry_price
                reward = entry_price - take_profit_1
                
            risk_reward_ratio = reward / risk if risk > 0 else 0
            if risk_reward_ratio < MIN_RR:  # Use consistent constant - minimum 1:2.0 R/R
                return None  # R/R too low for institutional trading
            
            # Quick safety score
            confidence_score = latest_signal.get('confidence', 0.5)
            regime = latest_signal.get('regime')
            # v4.2.1: Use safe regime access helper
            regime_strength = get_regime_strength(regime)
            
            # v4.2.1: Use only enhanced safety score calculation
            market_analysis = self.analyze_market(df)
            safety_score = self.calculate_enhanced_safety_score(
                confidence_score, regime_strength, risk_reward_ratio, market_analysis, 
                futures_approved=True  # Assume approved for batch mode
            )
            
            if safety_score < min_safety:
                return None
            
            # Calculate real values for UI display instead of placeholders
            # Position sizing (simplified for batch mode)
            base_position_percent = 0.02  # 2% of balance base
            position_size_usdt = balance * base_position_percent
            margin_required = position_size_usdt / leverage
            
            # Calculate percentage metrics for GUI display  
            if signal_direction == "LONG":
                price_change_tp_percent = ((take_profit_1 - entry_price) / entry_price) * 100
                price_change_sl_percent = ((entry_price - stop_loss) / entry_price) * 100
            else:  # SHORT
                price_change_tp_percent = ((entry_price - take_profit_1) / entry_price) * 100
                price_change_sl_percent = ((stop_loss - entry_price) / entry_price) * 100
            
            # ROI percentages on margin with leverage
            tp1_roi_percent = abs(price_change_tp_percent * leverage)
            sl_risk_percent = abs(price_change_sl_percent * leverage)
            
            # Return simple result for generate_signal_from_data 
            # Full signal building happens in _internal_generate_signal
            # Include basic UI keys for batch mode compatibility
            return {
                'symbol': symbol,
                'direction': signal_direction,
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'take_profit_1': take_profit_1,
                'take_profit_2': take_profit_2,
                'safety_score': safety_score,
                'risk_reward_ratio': risk_reward_ratio,
                'confidence': confidence_score,
                'regime': regime_strength,
                # Real calculated UI compatibility keys (not placeholders)
                'leverage': leverage,
                'position_size_usdt': position_size_usdt,
                'margin_required': margin_required,
                'tp1_roi_percent': tp1_roi_percent,
                'sl_risk_percent': sl_risk_percent,
                'price_change_tp_percent': price_change_tp_percent,
                'price_change_sl_percent': price_change_sl_percent,
                'timeframe': timeframe,
                'timestamp': datetime.now(),
                'breakeven_trigger': entry_price,
                'partial_tp_size': 0.5,
                'time_stop_candles': 'N/A',
                'market_regime': 'Batch Mode',
                'confidence': 'Medium',
                'futures_analysis': 'Quick batch analysis'
            }
            
        except Exception as e:
            self._track_error('signal_generation_errors', f"Signal generation failed for {symbol}: {str(e)}", symbol)
            return None
    
    def generate_signal(self, symbol, timeframe, balance, selected_leverage, min_safety, tp_percent=None, sl_percent=None):
        """Generate professional trading signal với ATR risk management và futures filtering"""
        
        # Step 0: ❌ CIRCUIT BREAKER CHECK - CRITICAL FIRST STEP
        cb_status = self.circuit_breaker.check_circuit_breakers(balance)
        if not cb_status['allowed']:
            st.error("🚨 TRADING SUSPENDED - Circuit Breaker Activated")
            for suspension in cb_status['suspensions']:
                st.error(f"❌ {suspension}")
            st.warning("⚠️ Auto-scan disabled until limits reset or admin override")
            return None
            
        # Display warnings if any
        if cb_status['warnings']:
            for warning in cb_status['warnings']:
                st.warning(f"⚠️ {warning}")
        
        # Load market data and calculate indicators
        df = self.load_market_data(symbol, timeframe)
        if df is None:
            return None
        
        # Calculate all technical indicators before analysis
        df = self.calculate_indicators(df)
        
        return self._internal_generate_signal(symbol, df, timeframe, balance, selected_leverage, min_safety, tp_percent, sl_percent)
    
    def _internal_generate_signal(self, symbol, df, timeframe, balance, selected_leverage, min_safety, tp_percent=None, sl_percent=None):
        """Internal signal generation logic - shared by both methods"""
    
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
            'trend_strength': 0.0,
            'momentum': 'NEUTRAL',
            'volatility': 'NORMAL',
            'volume_profile': 'MEDIUM',
            'market_strength': 5.0,
            'signals': [],
            'rsi': current.get('rsi', 50),  # Safe access with default
            'macd': current.get('macd', 0),  # Safe access with default
            'atr_percent': current.get('atr_percent', 2.0),  # Safe access with default
            'sr_proximity': 0.5  # Default S/R proximity
        }
        
        # Enhanced Trend Analysis with safe access and normalized strength (0.0-1.0)
        ema_200 = current.get('ema_200')
        ema_12 = current.get('ema_12')
        ema_26 = current.get('ema_26')
        sma_50 = current.get('sma_50')
        sma_20 = current.get('sma_20')
        
        if all([ema_200, ema_12, ema_26, sma_50, sma_20]):  # All indicators available
            if current['close'] > ema_200 and ema_12 > ema_26:
                if current['close'] > sma_50 > sma_20:
                    analysis['trend'] = 'STRONG_BULLISH'
                    analysis['trend_strength'] = 0.9  # Very strong bullish
                else:
                    analysis['trend'] = 'BULLISH'
                    analysis['trend_strength'] = 0.7  # Strong bullish
            elif current['close'] < ema_200 and ema_12 < ema_26:
                if current['close'] < sma_50 < sma_20:
                    analysis['trend'] = 'STRONG_BEARISH'
                    analysis['trend_strength'] = 0.9  # Very strong bearish (absolute)
                else:
                    analysis['trend'] = 'BEARISH'
                    analysis['trend_strength'] = 0.7  # Strong bearish (absolute)
            else:
                # Sideways or weak trend
                price_vs_ema200 = abs(current['close'] - ema_200) / ema_200
                if price_vs_ema200 < 0.02:  # Within 2% of EMA200
                    analysis['trend_strength'] = 0.3  # Weak trend
                else:
                    analysis['trend_strength'] = 0.5  # Medium trend
        else:
            # Fallback when indicators not available
            analysis['trend_strength'] = 0.5  # Default medium strength
        
        # Momentum signals with safe access
        macd = current.get('macd', 0)
        macd_signal = current.get('macd_signal', 0)
        prev_macd = prev.get('macd', 0)
        prev_macd_signal = prev.get('macd_signal', 0)
        
        if macd > macd_signal and prev_macd <= prev_macd_signal:
            analysis['signals'].append('MACD_BULLISH_CROSS')
            analysis['market_strength'] += 1.5
        elif macd < macd_signal and prev_macd >= prev_macd_signal:
            analysis['signals'].append('MACD_BEARISH_CROSS')
            analysis['market_strength'] -= 1.5
        
        # RSI signals with safe access
        rsi = current.get('rsi', 50)
        if rsi > 70:
            analysis['momentum'] = 'OVERBOUGHT'
            analysis['signals'].append('RSI_OVERBOUGHT')
            analysis['market_strength'] -= 1
        elif rsi < 30:
            analysis['momentum'] = 'OVERSOLD'
            analysis['signals'].append('RSI_OVERSOLD')
            analysis['market_strength'] += 1.5
        
        # Enhanced Volume Analysis with safe access
        if 'volume' in df.columns and 'volume_ratio' in df.columns:
            volume_ratio = current.get('volume_ratio', 1.0)
            if volume_ratio > 1.5:
                analysis['volume_profile'] = 'HIGH'
            elif volume_ratio > 1.2:
                analysis['volume_profile'] = 'MEDIUM'
            else:
                analysis['volume_profile'] = 'LOW'
        
        # Volatility with safe access
        if 'atr_percent' in df.columns:
            avg_atr = df['atr_percent'].rolling(50).mean().iloc[-1]
            atr_percent = current.get('atr_percent', 2.0)
            if pd.notna(avg_atr) and avg_atr > 0:
                if atr_percent > avg_atr * 1.5:
                    analysis['volatility'] = 'HIGH'
                elif atr_percent < avg_atr * 0.7:
                    analysis['volatility'] = 'LOW'
        
        # Simple S/R proximity with safe access
        # For now, use distance from key moving averages as proxy
        if sma_20 and sma_50:  # Only if indicators are available
            distance_to_sma20 = abs(current['close'] - sma_20) / current['close']
            distance_to_sma50 = abs(current['close'] - sma_50) / current['close']
            
            min_distance = min(distance_to_sma20, distance_to_sma50)
            if min_distance < 0.01:  # Within 1%
                analysis['sr_proximity'] = 0.9
            elif min_distance < 0.02:  # Within 2%
                analysis['sr_proximity'] = 0.7
            elif min_distance < 0.05:  # Within 5%
                analysis['sr_proximity'] = 0.5
            else:
                analysis['sr_proximity'] = 0.3
        
        analysis['market_strength'] = max(0, min(10, analysis['market_strength']))
        
        return analysis
    
    def generate_signal(self, symbol, timeframe, balance, selected_leverage, min_safety, tp_percent=None, sl_percent=None):
        """Generate professional trading signal với ATR risk management và futures filtering"""
        
        # Step 0: ❌ CIRCUIT BREAKER CHECK - CRITICAL FIRST STEP
        cb_status = self.circuit_breaker.check_circuit_breakers(balance)
        if not cb_status['allowed']:
            st.error("🚨 TRADING SUSPENDED - Circuit Breaker Activated")
            for suspension in cb_status['suspensions']:
                st.error(f"❌ {suspension}")
            st.warning("⚠️ Auto-scan disabled until limits reset or admin override")
            return None
            
        # Display warnings if any
        if cb_status['warnings']:
            for warning in cb_status['warnings']:
                st.warning(f"⚠️ {warning}")
        
        # Load market data and calculate indicators
        df = self.load_market_data(symbol, timeframe)
        if df is None:
            return None
        
        # Calculate all technical indicators before analysis
        df = self.calculate_indicators(df)
        
        # Step 1: Check futures market conditions first
        futures_approved, futures_message = self.futures_data_provider.get_futures_signal_filter(symbol, "LONG")
        
        # Step 2: Use professional momentum strategy
        signals = self.momentum_strategy.generate_signals(df)
        if not signals:
            return None
        
        # Get the latest signal
        latest_signal = signals[-1]
        signal_direction = latest_signal['direction']
        regime = latest_signal['regime']
        
        # Step 3: Check futures approval for this specific direction
        if not self.futures_data_provider.get_futures_signal_filter(symbol, signal_direction)[0]:
            return None
        
        entry_price = latest_signal['entry_price']
        
        # Step 4: Calculate TP/SL - Ưu tiên custom values trước
        if tp_percent is not None and sl_percent is not None:
            # USER CUSTOM TP/SL - Tính theo ROI trên margin với leverage
            price_change_tp = tp_percent / selected_leverage
            price_change_sl = sl_percent / selected_leverage
            
            if signal_direction == "LONG":
                stop_loss = entry_price * (1 - price_change_sl / 100)
                take_profit_1 = entry_price * (1 + price_change_tp / 100)
                take_profit_2 = entry_price * (1 + price_change_tp * 1.2 / 100)
                # Proper LeBeau Chandelier Exit
                chandelier_stop = chandelier_exit(df, n=22, k=3.0, side="LONG")
            else:
                # For SHORT positions
                stop_loss = entry_price * (1 + price_change_sl / 100)
                take_profit_1 = entry_price * (1 - price_change_tp / 100)
                take_profit_2 = entry_price * (1 - price_change_tp * 1.2 / 100)
                # Proper LeBeau Chandelier Exit
                chandelier_stop = chandelier_exit(df, n=22, k=3.0, side="SHORT")
                
                # Ensure TP values don't go below 10% of entry price for SHORT
                min_price = entry_price * 0.1
                take_profit_1 = max(take_profit_1, min_price)
                take_profit_2 = max(take_profit_2, min_price)
            
            # Custom R/R calculation
            if signal_direction == "LONG":
                risk = entry_price - stop_loss
                reward = take_profit_1 - entry_price
            else:
                risk = stop_loss - entry_price
                reward = entry_price - take_profit_1
            
            risk_reward_ratio = reward / risk if risk > 0 else 1.0
            
            # ATR-based values for reference only
            risk_level = 'CONSERVATIVE'
            market_analysis = self.analyze_market(df)
            atr_data = self.atr_risk_manager.calculate_atr_stops(df, entry_price, signal_direction, risk_level, market_analysis)
            atr_value = atr_data['atr_value']
            
            # Custom trade management plan
            trade_plan = f"Custom TP: {tp_percent}% ROI, SL: {sl_percent}% risk. Partial exit at TP1, full exit at TP2."
            breakeven_trigger = entry_price + (take_profit_1 - entry_price) * 0.5  # 50% to TP1
            partial_tp_size = 0.5  # 50% partial TP
            
            # Get time stop from unified manager
            from src.unified_time_stop_manager import get_time_stop_manager
            
            time_stop_manager = get_time_stop_manager()
            time_stop_candles = time_stop_manager.calculate_time_stop_candles(
                timeframe=timeframe,
                strategy_type='momentum',  # Default strategy type
                market_condition='trending',  # Could be derived from regime analysis
                safety_score=safety_score,
                confidence=confidence_score
            )
            
        else:
            # PROFESSIONAL ATR-based TP/SL with dynamic R/R
            # Handle both object and dict regime types
            # v4.2.1: Use safe regime access helper
            regime_strength = get_regime_strength(regime)
                
            risk_level = 'CONSERVATIVE' if regime_strength < 0.6 else 'MODERATE'
            if regime_strength > 0.8:
                risk_level = 'AGGRESSIVE'
            
            # Prepare market analysis for dynamic R/R calculation
            market_analysis = self.analyze_market(df)
            atr_data = self.atr_risk_manager.calculate_atr_stops(
                df, entry_price, signal_direction, risk_level, market_analysis
            )
            
            stop_loss = atr_data['stop_loss']
            take_profit_1 = atr_data['take_profit_1']
            take_profit_2 = atr_data['take_profit_2']
            chandelier_stop = atr_data['chandelier_stop']
            risk_reward_ratio = atr_data['rr_ratio_1']
            atr_value = atr_data['atr_value']
            
            # Professional trade management plan
            trade_plan = self.atr_risk_manager.generate_trade_management_plan(atr_data, entry_price, signal_direction)
            breakeven_trigger = atr_data['breakeven_trigger']
            partial_tp_size = atr_data['partial_tp_size']
            time_stop_candles = atr_data['time_stop_candles']
        
        # Step 5: Calculate leverage first (needed for leveraged returns calculation)
        if tp_percent is None:  # ATR mode - sử dụng leverage thông minh
            # v4.2.1: Use safe regime access helper
            regime_strength = get_regime_strength(regime)
            
            # Cho phép leverage cao hơn trong ATR mode vì đã có risk management tốt
            if regime_strength > 0.7 and latest_signal['confidence'] > 0.7:
                max_leverage = min(selected_leverage, 25)  # High confidence = higher leverage
            elif regime_strength > 0.5:
                max_leverage = min(selected_leverage, 20)  # Medium confidence = default leverage
            else:
                max_leverage = min(selected_leverage, 15)  # Low confidence = lower leverage
        else:  # Custom mode - sử dụng leverage user chọn
            max_leverage = min(selected_leverage, 50)  # Allow higher leverage for custom mode
        
        # Calculate leveraged returns for ATR mode
        if tp_percent is None:
            leveraged_returns = self.atr_risk_manager.calculate_leveraged_returns(
                entry_price, take_profit_1, stop_loss, max_leverage, signal_direction
            )
        
        # Step 6: ❌ CRITICAL R/R VALIDATION - REJECT if natural R/R < MIN_RR (Compliance)
        if risk_reward_ratio < MIN_RR:
            st.error(f"❌ SIGNAL REJECTED: Natural Risk/Reward ratio {risk_reward_ratio:.2f} below compliance minimum {MIN_RR}")
            st.warning("⚠️ Compliance Rule: We never force TP adjustments. Natural market conditions must provide adequate R/R.")
            st.info("💡 This protects you from unrealistic profit targets that may not be achievable.")
            return None
        
        # Step 7: v4.2.1 - Use only enhanced safety score calculation (single method)
        confidence_score = latest_signal.get('confidence', 0.5)
        # v4.2.1: Use safe regime access helper
        regime_strength = get_regime_strength(regime)
        
        # Step 8: Calculate enhanced safety score using single method (v4.2.1)
        safety_score = self.calculate_enhanced_safety_score(
            confidence_score, regime_strength, risk_reward_ratio, market_analysis, futures_approved
        )
        
        # Step 9: Calculate intelligent position sizing (now with safety_score available)
        from src.intelligent_position_sizer import get_position_sizer
        
        position_sizer = get_position_sizer()
        position_sizing_result = position_sizer.calculate_intelligent_position_size(
            balance=balance,
            entry_price=entry_price,
            stop_loss=stop_loss,
            leverage=max_leverage,
            safety_score=safety_score,
            confidence=confidence_score,
            max_leverage_override=selected_leverage
        )
        
        if not position_sizing_result:
            st.error("❌ SIGNAL REJECTED: Position sizing calculation failed")
            return None
        
        # Extract calculated values
        position_size_usdt = position_sizing_result['position_size_usdt']
        margin_required = position_sizing_result['margin_required']
        effective_leverage = position_sizing_result['leverage_used']
        
        # Step 10: PORTFOLIO RISK CHECK - Professional institutional controls
        can_open, portfolio_message = self.portfolio_risk_manager.can_open_position(
            symbol=symbol,
            direction=signal_direction,
            position_size_usdt=position_size_usdt,
            leverage=max_leverage,
            stop_loss=stop_loss,
            entry_price=entry_price,
            portfolio_balance=balance,
            safety_score=safety_score
        )
        
        if not can_open:
            # Calculate real values for error scenario display
            base_position_percent = 0.02  # 2% of balance base
            position_size_usdt = balance * base_position_percent
            margin_required = position_size_usdt / max_leverage
            
            # Calculate percentage metrics for GUI display  
            if signal_direction == "LONG":
                price_change_tp_percent = ((take_profit_1 - entry_price) / entry_price) * 100
                price_change_sl_percent = ((entry_price - stop_loss) / entry_price) * 100
            else:  # SHORT
                price_change_tp_percent = ((entry_price - take_profit_1) / entry_price) * 100
                price_change_sl_percent = ((stop_loss - entry_price) / entry_price) * 100
            
            # ROI percentages on margin with leverage
            tp1_roi_percent = abs(price_change_tp_percent * max_leverage)
            sl_risk_percent = abs(price_change_sl_percent * max_leverage)
                
            return {
                'symbol': symbol,
                'direction': signal_direction,
                'entry_price': entry_price,
                'portfolio_blocked': True,
                'portfolio_reason': portfolio_message,
                'safety_score': safety_score,
                'timestamp': datetime.now(),
                # Add real calculated UI keys instead of 0s
                'leverage': max_leverage,
                'position_size_usdt': position_size_usdt,
                'margin_required': margin_required,
                'risk_reward_ratio': 0,  # Keep as 0 since blocked
                'tp1_roi_percent': tp1_roi_percent,
                'sl_risk_percent': sl_risk_percent,
                'price_change_tp_percent': price_change_tp_percent,
                'price_change_sl_percent': price_change_sl_percent,
                'stop_loss': stop_loss,
                'take_profit_1': take_profit_1,
                'breakeven_trigger': entry_price,
                'partial_tp_size': 0.5,
                'time_stop_candles': 'N/A',
                'market_regime': 'Not Available',
                'confidence': 'Medium',
                'futures_analysis': 'Analysis not completed'
            }
        
        # Step 9: LIQUIDATION SAFETY CHECK - Ensure SL is far from liquidation
        liquidation_price = self._calculate_liquidation_price(entry_price, max_leverage, signal_direction)
        
        # Check if SL is safe distance from liquidation (minimum 2x ATR buffer)
        atr_buffer_required = atr_value * 2.0  # 2 ATR safety buffer
        
        if signal_direction == "LONG":
            liq_to_entry_distance = abs(entry_price - liquidation_price)
            sl_to_liq_distance = abs(stop_loss - liquidation_price)
            
            if sl_to_liq_distance < atr_buffer_required:
                return {
                    'symbol': symbol,
                    'direction': signal_direction,
                    'entry_price': entry_price,
                    'liquidation_blocked': True,
                    'liquidation_reason': f"SL too close to liquidation. Distance: {sl_to_liq_distance:.6f}, Required: {atr_buffer_required:.6f}",
                    'liquidation_price': liquidation_price,
                    'safety_score': safety_score,
                    'timestamp': datetime.now(),
                    'mmr_mode': 'approx',  # v4.2.1: Indicate liquidation calculations are approximate
                    # Add missing UI keys with defaults
                    'leverage': max_leverage,
                    'position_size_usdt': 0,
                    'margin_required': 0,
                    'risk_reward_ratio': 0,
                    'tp1_roi_percent': 0,
                    'sl_risk_percent': 0,
                    'price_change_tp_percent': 0,
                    'price_change_sl_percent': 0,
                    'stop_loss': stop_loss,
                    'take_profit_1': take_profit_1
                }
        else:  # SHORT
            sl_to_liq_distance = abs(liquidation_price - stop_loss)
            
            if sl_to_liq_distance < atr_buffer_required:
                # Calculate real values for error scenario display
                base_position_percent = 0.02  # 2% of balance base
                position_size_usdt = balance * base_position_percent
                margin_required = position_size_usdt / max_leverage
                
                # Calculate percentage metrics for GUI display  
                if signal_direction == "LONG":
                    price_change_tp_percent = ((take_profit_1 - entry_price) / entry_price) * 100
                    price_change_sl_percent = ((entry_price - stop_loss) / entry_price) * 100
                else:  # SHORT
                    price_change_tp_percent = ((entry_price - take_profit_1) / entry_price) * 100
                    price_change_sl_percent = ((stop_loss - entry_price) / entry_price) * 100
                
                # ROI percentages on margin with leverage
                tp1_roi_percent = abs(price_change_tp_percent * max_leverage)
                sl_risk_percent = abs(price_change_sl_percent * max_leverage)
                    
                return {
                    'symbol': symbol,
                    'direction': signal_direction,
                    'entry_price': entry_price,
                    'liquidation_blocked': True,
                    'liquidation_reason': f"SL too close to liquidation. Distance: {sl_to_liq_distance:.6f}, Required: {atr_buffer_required:.6f}",
                    'liquidation_price': liquidation_price,
                    'safety_score': safety_score,
                    'timestamp': datetime.now(),
                    'mmr_mode': 'approx',  # v4.2.1: Indicate liquidation calculations are approximate
                    # Add real calculated UI keys instead of 0s
                    'leverage': max_leverage,
                    'position_size_usdt': position_size_usdt,
                    'margin_required': margin_required,
                    'risk_reward_ratio': 0,  # Keep as 0 since blocked
                    'tp1_roi_percent': tp1_roi_percent,
                    'sl_risk_percent': sl_risk_percent,
                    'price_change_tp_percent': price_change_tp_percent,
                    'price_change_sl_percent': price_change_sl_percent,
                    'stop_loss': stop_loss,
                    'take_profit_1': take_profit_1,
                    'breakeven_trigger': entry_price,
                    'partial_tp_size': 0.5,
                    'time_stop_candles': 'N/A',
                    'market_regime': 'Not Available',
                    'confidence': 'Medium',
                    'futures_analysis': 'Analysis not completed'
                }
        
        # Step 10: Calculate percentage metrics for GUI display
        # Price movement percentages (how much price needs to change)
        if entry_price > 0:  # Safety check
            if signal_direction == "LONG":
                price_change_tp_percent = ((take_profit_1 - entry_price) / entry_price) * 100
                price_change_sl_percent = ((entry_price - stop_loss) / entry_price) * 100
            else:  # SHORT
                price_change_tp_percent = ((entry_price - take_profit_1) / entry_price) * 100
                price_change_sl_percent = ((stop_loss - entry_price) / entry_price) * 100
            
            # ROI percentages on margin with leverage (what trader gains/loses)
            tp1_roi_percent = abs(price_change_tp_percent * max_leverage)
            sl_risk_percent = abs(price_change_sl_percent * max_leverage)
        else:
            # Fallback values if price data is invalid
            price_change_tp_percent = 0
            price_change_sl_percent = 0
            tp1_roi_percent = 0
            sl_risk_percent = 0
        
        # Generate final successful signal
        return {
            'symbol': symbol,
            'direction': signal_direction,
            'entry_price': entry_price,
            'current_market_price': df['close'].iloc[-1],  # Add current price for Binance reference
            'stop_loss': stop_loss,
            'take_profit_1': take_profit_1,
            'take_profit_2': take_profit_2,
            'chandelier_stop': chandelier_stop,
            'safety_score': safety_score,
            'confidence': regime.get('confidence_level', 'MEDIUM') if isinstance(regime, dict) else (regime.confidence_level if hasattr(regime, 'confidence_level') else 'MEDIUM'),
            'leverage': effective_leverage,
            'position_size_usdt': position_size_usdt,
            'margin_required': margin_required,
            'risk_reward_ratio': risk_reward_ratio,
            'timeframe': timeframe,
            'timestamp': datetime.now(),
            'market_regime': (f"{regime.get('trend_regime', 'UNKNOWN')} | {regime.get('volatility_regime', 'UNKNOWN')} | Strength: {regime_strength:.2f}" 
                           if isinstance(regime, dict) 
                           else f"{regime.trend_regime} | {regime.volatility_regime} | Strength: {regime.regime_strength:.2f}" 
                           if hasattr(regime, 'trend_regime') 
                           else f"UNKNOWN | UNKNOWN | Strength: {regime_strength:.2f}"),
            'atr_value': atr_value,
            'trade_management_plan': trade_plan,
            'futures_analysis': futures_message,
            'signals_conditions': latest_signal.get('conditions_met', []),
            'breakeven_trigger': breakeven_trigger,
            'partial_tp_size': partial_tp_size,
            'time_stop_candles': time_stop_candles,
            'custom_mode': tp_percent is not None and sl_percent is not None,
            'liquidation_price': liquidation_price,
            'mmr_mode': 'approx',  # Indicate liquidation calculations are approximate
            'portfolio_approved': True,
            'portfolio_message': portfolio_message,
            # GUI display metrics
            'price_change_tp_percent': price_change_tp_percent,
            'price_change_sl_percent': price_change_sl_percent,
            'tp1_roi_percent': tp1_roi_percent,
            'sl_risk_percent': sl_risk_percent,
            # Position sizing details
            'position_percent': position_sizing_result['position_percent'],
            'margin_percent': position_sizing_result['margin_percent'],
            'risk_percent': position_sizing_result['risk_percent'],
            'max_loss_usdt': position_sizing_result['max_loss_usdt']
        }

    def _calculate_liquidation_price(self, entry_price: float, leverage: float, direction: str) -> float:
        """Calculate approximate liquidation price for Binance Futures (not bracket-based)"""
        # Binance maintenance margin rates (approximate - simplified model)
        # Note: Real Binance uses complex bracket system based on position notional value
        if leverage <= 10:
            maintenance_margin_rate = 0.005  # 0.5%
        elif leverage <= 20:
            maintenance_margin_rate = 0.01   # 1%
        elif leverage <= 50:
            maintenance_margin_rate = 0.025  # 2.5%
        else:
            maintenance_margin_rate = 0.05   # 5%
        
        if direction == "LONG":
            # Long liquidation: entry_price * (1 - (1/leverage) + maintenance_margin)
            liquidation_price = entry_price * (1 - (1/leverage) + maintenance_margin_rate)
        else:
            # Short liquidation: entry_price * (1 + (1/leverage) + maintenance_margin)
            liquidation_price = entry_price * (1 + (1/leverage) + maintenance_margin_rate)
        
        return liquidation_price
    
    def calculate_enhanced_safety_score(self, confidence_score: float, regime_strength: float, 
                                      risk_reward_ratio: float, market_analysis: dict, 
                                      futures_approved: bool = True) -> int:
        """
        Calculate enhanced safety score using institutional-grade components (v4.2.1)
        Single source of truth for all safety scoring
        """
        safety_score = 0  # Start from zero
        
        # CONFIDENCE COMPONENT (max 3 points)
        if confidence_score >= 0.9:
            safety_score += 3  # Excellent confidence
        elif confidence_score >= 0.8:
            safety_score += 2  # Good confidence
        elif confidence_score >= 0.7:
            safety_score += 1  # Fair confidence
        
        # REGIME STRENGTH COMPONENT (max 3 points)
        if regime_strength >= 0.9:
            safety_score += 3  # Very strong regime
        elif regime_strength >= 0.8:
            safety_score += 2  # Strong regime
        elif regime_strength >= 0.7:
            safety_score += 1  # Medium regime
        
        # RISK/REWARD COMPONENT (max 2 points)
        if risk_reward_ratio >= 3.0:
            safety_score += 2  # Excellent R/R
        elif risk_reward_ratio >= 2.5:
            safety_score += 1  # Good R/R
            
        # FUTURES APPROVAL (max 1 point)
        if futures_approved:
            safety_score += 1
            
        # VOLUME PROFILE (max 1 point)
        if market_analysis.get('volume_profile') == 'HIGH':
            safety_score += 1
            
        # PENALTIES
        rsi = market_analysis.get('rsi', 50)
        if rsi > 75 or rsi < 25:  # Extreme RSI = risky
            safety_score -= 1
            
        volatility = market_analysis.get('volatility', 'NORMAL')
        if volatility == 'HIGH':  # High volatility = more risk
            safety_score -= 1
            
        # EXCEPTIONAL BONUSES (for scores 9-10)
        exceptional_bonus = 0
        if (regime_strength >= 0.9 and confidence_score >= 0.9 and 
            risk_reward_ratio >= 3.5 and market_analysis.get('volume_profile') == 'HIGH'):
            exceptional_bonus += 1  # Can reach score 10
        elif (regime_strength >= 0.85 and confidence_score >= 0.85 and 
              risk_reward_ratio >= 3.0):
            exceptional_bonus += 0.5  # Can reach score 9
            
        safety_score += exceptional_bonus
        
        # Clamp to 1-10 range
        return max(1, min(10, round(safety_score)))

    def select_signal_for_trade(self, signal: dict):
        """Track the chosen signal in analytics"""
        symbol = safe_get_signal_field(signal, 'symbol', 'UNKNOWN')

        if signal.get('portfolio_blocked') or signal.get('liquidation_blocked'):
            st.warning("⚠️ Setup này đang bị đánh dấu rủi ro cao, hãy kiểm tra lại trước khi đặt lệnh.")

        analytics_ready = False
        if ANALYTICS_AVAILABLE:
            analytics_ready = analytics_integrator.initialize_user_session()
            if not analytics_ready:
                st.warning("🔐 Vui lòng đăng nhập analytics để đồng bộ dữ liệu. Lệnh vẫn được lưu cục bộ.")

        entry_price = safe_get_signal_field(signal, 'entry_price', 0.0)
        position_size_usdt = safe_get_signal_field(signal, 'position_size_usdt', 1000.0)
        leverage = safe_get_signal_field(signal, 'leverage', 20)
        stop_loss = safe_get_signal_field(signal, 'stop_loss', entry_price * 0.98)

        analytics_payload = {
            'symbol': symbol,
            'direction': safe_get_signal_field(signal, 'direction', 'LONG'),
            'entry_price': entry_price,
            'position_size_usdt': position_size_usdt,
            'leverage': leverage,
            'stop_loss': stop_loss,
            'take_profit_1': safe_get_signal_field(signal, 'take_profit_1', entry_price * 1.04),
            'take_profit_2': safe_get_signal_field(signal, 'take_profit_2', None),
            'take_profit_3': safe_get_signal_field(signal, 'take_profit_3', None),
            'risk_reward_ratio': safe_get_signal_field(signal, 'risk_reward_ratio', 2.0),
            'safety_score': safe_get_signal_field(signal, 'safety_score', 5),
            'margin_required': signal.get('margin_required', position_size_usdt / leverage if leverage else position_size_usdt),
            'liquidation_price': signal.get('liquidation_price'),
            'timeframe': safe_get_signal_field(signal, 'timeframe', '1h'),
            'market_regime': safe_get_signal_field(signal, 'market_regime', 'N/A'),
            'volatility_level': safe_get_signal_field(signal, 'volatility_level', 'normal'),
            'signal_source': 'trading_insight',
            'strategy_version': signal.get('strategy_version', '4.2.1')
        }

        selected_entry = {
            'symbol': symbol,
            'direction': analytics_payload['direction'],
            'entry_price': entry_price,
            'take_profit_1': analytics_payload.get('take_profit_1'),
            'stop_loss': analytics_payload.get('stop_loss'),
            'timeframe': analytics_payload.get('timeframe'),
            'timestamp': datetime.now().isoformat(),
            'status': 'open'
        }

        updated_selected = list(st.session_state.get('selected_signals', []))
        updated_selected.append(selected_entry)
        st.session_state['selected_signals'] = updated_selected
        st.success(f"📌 Đã chọn lệnh {symbol}. Theo dõi trong mục 'Trades đã chọn'.")

        if analytics_ready:
            trade_id = track_generated_signal(analytics_payload)
            if trade_id:
                st.success(f"✅ Đã lưu lệnh {symbol} vào analytics (ID: {trade_id})")
                selected_entry['analytics_trade_id'] = trade_id

                tracked_entry = {
                    'trade_id': trade_id,
                    'symbol': symbol,
                    'direction': analytics_payload['direction'],
                    'entry_price': entry_price,
                    'take_profit_1': analytics_payload.get('take_profit_1'),
                    'stop_loss': analytics_payload.get('stop_loss'),
                    'timeframe': analytics_payload.get('timeframe'),
                    'timestamp': datetime.now().isoformat(),
                    'status': 'open'
                }

                tracked_list = list(st.session_state.get('tracked_trades', []))
                if not any(trade.get('trade_id') == trade_id for trade in tracked_list):
                    tracked_list.append(tracked_entry)
                    st.session_state['tracked_trades'] = tracked_list
            else:
                st.warning("⚠️ Không thể lưu trade vào analytics. Kiểm tra kết nối analytics.")
        else:
            st.info("ℹ️ Lệnh được lưu cục bộ. Đồng bộ analytics sau khi đăng nhập.")

    def auto_update_selected_trades(self):
        """Automatically evaluate open trades and mark outcomes when TP/SL is reached."""
        selected_trades = st.session_state.get('selected_signals', [])
        if not selected_trades:
            return

        current_prices = self.get_current_prices()
        if not current_prices:
            return

        notifications = []

        for trade in selected_trades:
            if trade.get('status') != 'open':
                continue

            symbol = trade.get('symbol')
            if not symbol:
                continue

            current_price = current_prices.get(symbol)
            if current_price is None:
                continue

            direction = trade.get('direction', 'LONG')
            take_profit = trade.get('take_profit_1')
            stop_loss = trade.get('stop_loss')

            if take_profit is None or stop_loss is None:
                continue

            outcome = None
            if direction == 'LONG':
                if current_price >= take_profit:
                    outcome = 'tp1_hit'
                elif current_price <= stop_loss:
                    outcome = 'sl_hit'
            else:  # SHORT
                if current_price <= take_profit:
                    outcome = 'tp1_hit'
                elif current_price >= stop_loss:
                    outcome = 'sl_hit'

            if not outcome:
                continue

            trade['status'] = 'closed'
            trade['outcome'] = outcome
            trade['exit_price'] = current_price
            trade['closed_at'] = datetime.now().isoformat()

            trade_id = trade.get('analytics_trade_id')
            if ANALYTICS_AVAILABLE and trade_id:
                analytics_integrator.update_trade_outcome_by_id(trade_id, current_price, outcome)

            tracked_list = st.session_state.get('tracked_trades', [])
            for tracked in tracked_list:
                if tracked.get('trade_id') == trade_id:
                    tracked.update({
                        'status': 'closed',
                        'outcome': outcome,
                        'exit_price': current_price,
                        'closed_at': trade['closed_at']
                    })
                    break

            if not trade.get('auto_notified'):
                notifications.append(f"✅ {symbol}: {outcome.replace('_', ' ')} @ {current_price:,.4f}")
                trade['auto_notified'] = True

        for note in notifications:
            st.success(note)

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
    user = ensure_user_logged_in()
    if not user:
        return

    gui = TradingGUI()

    if ANALYTICS_AVAILABLE:
        analytics_integrator.initialize_user_session()

    gui.auto_update_selected_trades()

    # Header
    st.markdown('<h1 class="main-header">📈 Trading Insight Pro GUI</h1>', unsafe_allow_html=True)
    
    # Sidebar
    st.sidebar.markdown("## 👤 Account")
    st.sidebar.success(f"Đang đăng nhập: {user['username']}")
    if user.get('subscription_tier'):
        st.sidebar.caption(f"Tier: {user['subscription_tier']}")
    if user.get('email'):
        st.sidebar.caption(user['email'])
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        logout_user()
    st.sidebar.markdown("---")
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
        min_value=100,
        max_value=10000000,
        value=10000,  # Default $10,000 balance
        step=500,
        help="Your trading account balance - can be any amount"
    )
    
    # Circuit Breaker Status Display
    cb_status = gui.circuit_breaker.check_circuit_breakers(balance)
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🚨 Circuit Breaker Status")
    
    if cb_status['risk_level'] == 'SUSPENDED':
        st.sidebar.error("🚨 TRADING SUSPENDED")
        for suspension in cb_status['suspensions']:
            st.sidebar.error(f"❌ {suspension}")
        
        # Admin override button
        if st.sidebar.button("🔓 Admin Override (Risky)", type="secondary"):
            gui.circuit_breaker.admin_override_enable()
            st.sidebar.success("✅ Override activated - Trade carefully!")
            st.rerun()
            
    elif cb_status['risk_level'] == 'DANGER':
        st.sidebar.warning("⚠️ DANGER ZONE")
        for warning in cb_status['warnings']:
            st.sidebar.warning(f"⚠️ {warning}")
            
    elif cb_status['risk_level'] == 'WARNING':
        st.sidebar.warning("⚠️ WARNING")
        for warning in cb_status['warnings']:
            st.sidebar.warning(f"⚠️ {warning}")
    else:
        st.sidebar.success("✅ Normal Trading")
    
    # Display current limits
    with st.sidebar.expander("📊 Current Limits"):
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Daily P&L", f"${cb_status['daily_pnl']:.2f}")
            st.metric("Daily Trades", cb_status['daily_trades'])
        with col2:
            st.metric("Weekly P&L", f"${cb_status['weekly_pnl']:.2f}")  
            st.metric("Consecutive Loss", str(cb_status['consecutive_losses']))
    
    st.sidebar.markdown("---")
    
    # Leverage selection (direct choice)
    leverage_options = [5, 10, 15, 20, 25, 30, 50, 75, 100]
    selected_leverage = st.sidebar.selectbox(
        "⚡ Leverage",
        leverage_options,
        index=3,  # Default x20 (index 3 = 20)
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
    
    st.sidebar.info("💡 **Chế độ tính toán:**\n- ❌ **ATR Mode**: Professional stops dựa trên volatility\n- ✅ **Custom Mode**: Bạn tự định % lợi nhuận và rủi ro")
    
    use_custom_rr = st.sidebar.checkbox(
        "🎯 Custom TP/SL Percentages", 
        value=False,
        help="Bật để tự chọn % Take Profit và Stop Loss theo ý muốn"
    )
    
    if use_custom_rr:
        st.sidebar.markdown("**🎯 Custom Mode:**")
        
        take_profit_percent = st.sidebar.slider(
            "💹 Take Profit (% ROI)",
            min_value=5.0,
            max_value=500.0,  # Allow higher TP
            value=100.0,  # Default 100% như user yêu cầu
            step=5.0,
            help="% lợi nhuận trên MARGIN (có tính leverage). VD: 100% = gấp đôi margin với leverage x20"
        )
        
        stop_loss_percent = st.sidebar.slider(
            "🛑 Stop Loss (% Risk)",
            min_value=1.0,
            max_value=50.0,
            value=15.0,  # Default 15%
            step=1.0,
            help="% rủi ro trên MARGIN (có tính leverage). VD: 15% = mất 15% margin với leverage x20"
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
            rr_quality = "Risky"
        
        st.sidebar.metric(
            f"{rr_color} Risk/Reward",
            f"1:{custom_rr_ratio:.2f}",
            f"{rr_quality} ratio"
        )
        
        # Show how this translates to price movement with leverage
        st.sidebar.info(f"""
**💡 Với leverage x{selected_leverage}:**
• TP đạt khi giá coin thay đổi: {take_profit_percent/selected_leverage:.1f}%
• SL trigger khi giá coin thay đổi: {stop_loss_percent/selected_leverage:.1f}%
        """)
    else:
        st.sidebar.markdown("**⚙️ ATR Mode:** Professional stops dựa trên volatility")
        take_profit_percent = None
        stop_loss_percent = None
    
    auto_scan = st.sidebar.checkbox("🔄 Auto Scan (0-5 Signals)", help="Scan all coins and show up to 5 highest safety score signals (may return 0-5 depending on quality bars)")
    
    # Determine auto-scan mode
    if not selected_symbols:
        auto_scan_mode = True
        symbols_for_analysis = gui.supported_symbols
    else:
        auto_scan_mode = False
        symbols_for_analysis = selected_symbols
    
    # Main content
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Market Dashboard", "🎯 Trading Signals", "📈 Charts", "📋 Signal History", "📈 Analytics"])
    
    with tab1:
        st.markdown("## 📊 Multi-Market Dashboard")
        
        if auto_scan_mode:
            st.info("🏆 **Quality Signals Mode**: Analyzing all coins for highest safety score signals (0-5 depending on quality bars)...")
        
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
            # Determine symbols to process
            symbols_to_process = gui.supported_symbols if not selected_symbols else selected_symbols
            
            # Show different progress for auto-scan vs manual
            if auto_scan_mode:
                st.info(f"� **Fast Batch Analysis**: Processing {len(symbols_to_process)} symbols in parallel...")
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Batch load data for all symbols (parallel)
                status_text.text("📊 Loading market data in parallel...")
                batch_data = gui.batch_load_market_data(symbols_to_process, timeframe, limit=100)
                
                # Debug batch loading result
                st.info(f"📊 **Batch Load Result:** {len(batch_data)} out of {len(symbols_to_process)} symbols loaded successfully")
                
                # If batch loading fails, try sequential loading for first few symbols
                if len(batch_data) == 0:
                    st.warning("⚠️ **Batch loading failed, trying sequential loading for first 10 symbols...**")
                    status_text.text("🔄 Sequential fallback loading...")
                    
                    test_symbols = symbols_to_process[:10]  # Try first 10 only
                    for i, symbol in enumerate(test_symbols):
                        try:
                            df = gui.load_market_data(symbol, timeframe, limit=100, use_cache=False)
                            if df is not None and len(df) > 0:
                                batch_data[symbol] = df
                            progress_bar.progress(10 + (i / len(test_symbols)) * 20)
                        except Exception as e:
                            st.error(f"Failed to load {symbol}: {e}")
                    
                    st.info(f"📊 **Sequential Load Result:** {len(batch_data)} symbols loaded")
                
                # Final check
                if len(batch_data) == 0:
                    st.error("❌ **No market data loaded!** This could be due to:")
                    st.markdown("""
                    - Network connectivity issues
                    - Binance API rate limiting  
                    - All symbols currently unavailable
                    - Streamlit session state conflicts
                    """)
                    progress_bar.empty()
                    status_text.empty()
                    return
                
                progress_bar.progress(30)
                
                # Process signals in parallel
                status_text.text("🔍 Generating signals...")
                all_signals = []
                
                # Generate signals for all symbols
                for symbol in symbols_to_process:
                    if symbol in batch_data:
                        df = batch_data[symbol]
                        try:
                            signal = gui.generate_signal_from_data(symbol, df, timeframe, 
                                                               balance, selected_leverage, min_safety, 
                                                               take_profit_percent, stop_loss_percent)
                            if signal and 'entry_price' in signal:  # Valid signal
                                all_signals.append((symbol, signal))
                        except Exception as e:
                            pass  # Silent error handling
                
                def process_symbol(symbol):
                    if symbol in batch_data:
                        return symbol, gui.generate_signal_from_data(symbol, batch_data[symbol], timeframe, 
                                                           balance, selected_leverage, min_safety, 
                                                           take_profit_percent, stop_loss_percent)
                    return symbol, None
                
                with ThreadPoolExecutor(max_workers=8) as executor:
                    futures = {executor.submit(process_symbol, symbol): symbol for symbol in symbols_to_process}
                    
                    completed = 0
                    for future in as_completed(futures):
                        symbol, signal = future.result()
                        
                        if signal and not signal.get('portfolio_blocked') and not signal.get('liquidation_blocked'):
                            all_signals.append((symbol, signal))
                        
                        completed += 1
                        progress = 30 + (completed / len(symbols_to_process)) * 60
                        progress_bar.progress(int(progress))
                        status_text.text(f"🔍 Processed {completed}/{len(symbols_to_process)} symbols...")
                
                progress_bar.progress(100)
                status_text.text(f"✅ Found {len(all_signals)} signals from {len(batch_data)} symbols with data")
                time.sleep(2)  # Show debug info longer
                progress_bar.empty()
                status_text.empty()
                
            else:
                st.info("🔄 Analyzing market data and generating signals...")
                all_signals = []
                debug_info = []
                
                for symbol in symbols_to_process:
                    # Generate signal first
                    signal = gui.generate_signal(symbol, timeframe, balance, selected_leverage, min_safety, take_profit_percent, stop_loss_percent)
                    
                    # Store all valid signals for ranking
                    if signal and not signal.get('portfolio_blocked') and not signal.get('liquidation_blocked'):
                        all_signals.append((symbol, signal))
            
            # Persist signals for reuse on rerun
            stored_signals_payload = []
            for sym, sig in all_signals:
                if not sig:
                    continue
                sig_copy = dict(sig)
                sig_copy['symbol'] = sym
                stored_signals_payload.append(sig_copy)
            st.session_state['latest_signals_data'] = stored_signals_payload

            # Process detailed analysis for non-auto-scan mode
            signals_found = 0
            if not auto_scan_mode:
                debug_info = []
                for symbol in symbols_to_process:
                    signal = gui.generate_signal(symbol, timeframe, balance, selected_leverage, min_safety, take_profit_percent, stop_loss_percent)
                
                # For normal mode (specific symbols selected), show detailed analysis
                if not auto_scan_mode:
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
                            # Check if signal was blocked by portfolio or liquidation rules
                            if signal.get('portfolio_blocked'):
                                st.error(f"""
                                🚫 **PORTFOLIO BLOCKED - {symbol}**
                                
                                **Reason:** {signal['portfolio_reason']}
                                
                                **Signal Details:**
                                • Direction: {signal['direction']} 
                                • Entry: ${signal['entry_price']:,.6f}
                                • Safety Score: {signal['safety_score']}/10
                                
                                💡 **Solutions:**
                                - Close existing positions to free up risk budget
                                - Wait for better setup with higher safety score  
                                - Reduce position size (coming in future update)
                                """)
                                
                            elif signal.get('liquidation_blocked'):
                                st.warning(f"""
                                ⚡ **LIQUIDATION RISK - {symbol}**
                                
                                **Issue:** {signal['liquidation_reason']}
                                
                                **Signal Details:**
                                • Direction: {signal['direction']}
                                • Entry: ${signal['entry_price']:,.6f}
                                • Liquidation Price: ${signal['liquidation_price']:,.6f}
                                • Safety Score: {signal['safety_score']}/10
                                
                                💡 **Solutions:**
                                - Reduce leverage to increase liquidation buffer
                                - Wait for better entry with wider stop loss
                                - Use lower timeframe for tighter entry
                                """)
                                
                            else:
                                # Valid signal - proceed with display
                                signals_found += 1
                                
                                # Signal display
                                signal_class = "signal-long" if signal['direction'] == "LONG" else "signal-short"
                                
                                st.markdown(f"""
                                <div class="{signal_class}">
                                    <h2>🚨 {signal['direction']} SIGNAL</h2>
                                    <h3>{symbol}</h3>
                                </div>
                                """, unsafe_allow_html=True)
                            
                            # Professional Signal Display - New Format
                            col1, col2, col3 = st.columns(3)
                            
                            with col1:
                                st.metric("💰 Entry Price", f"${signal['entry_price']:,.6f}")
                                current_price = signal.get('current_market_price', signal['entry_price'])
                                price_diff = abs(current_price - signal['entry_price'])
                                st.metric("📊 Current Market", f"${current_price:,.6f}", 
                                         delta=f"±{price_diff:.6f}" if price_diff > 0 else None,
                                         help="Live market price when signal generated")
                                st.metric("🛑 ATR Stop Loss", f"${signal['stop_loss']:,.6f}")
                                st.metric("🎯 TP1 Price", f"${signal['take_profit_1']:,.6f}")
                            
                            with col2:
                                st.metric("📈 Leverage", f"{signal['leverage']}x")
                                st.metric("💵 Position Size", f"${signal['position_size_usdt']:,.2f}")
                                st.metric("💳 Margin Required", f"${signal['margin_required']:,.2f}")
                                st.metric("⚖️ Risk/Reward", f"1:{signal['risk_reward_ratio']:.2f}")
                                
                            with col3:
                                st.metric("🎯 TP1 ROI", f"+{signal.get('tp1_roi_percent', 0):.1f}%", help="Lợi nhuận trên margin với leverage")
                                st.metric("🛑 SL Risk", f"-{signal.get('sl_risk_percent', 0):.1f}%", help="Rủi ro trên margin với leverage")
                                st.metric("📊 Price Move TP", f"+{signal.get('price_change_tp_percent', 0):.2f}%", help="% thay đổi giá coin cần thiết")
                                st.metric("📊 Price Move SL", f"-{signal.get('price_change_sl_percent', 0):.2f}%", help="% thay đổi giá coin tới SL")
                            
                            # Additional info row
                            col4, col5, col6 = st.columns(3)
                            with col4:
                                st.metric("🛡️ Safety Score", f"{signal['safety_score']}/10")
                            with col5:
                                st.metric("🔮 Confidence", signal['confidence'])
                            with col6:
                                st.metric("📈 ATR Value", f"${signal.get('atr_value', signal['entry_price'] * 0.02):,.6f}")
                            
                            # Professional Trade Management Info
                            st.info(f"🎯 **Trade Management**: Breakeven at ${signal.get('breakeven_trigger', signal['entry_price']):,.6f}, {signal.get('partial_tp_size', 0.5):.1%} partial TP at TP1")
                            
                            # Trading parameters cho Binance Futures - New Professional Format
                            st.markdown("### 📋 Copy to Binance Futures")
                            
                            mode_text = "CUSTOM" if signal.get('custom_mode', False) else "PROFESSIONAL ATR"
                            
                            # Get current market price and add SHORT-specific instructions
                            current_price = signal.get('current_market_price', signal['entry_price'])
                            
                            if signal['direction'] == 'SHORT':
                                binance_instructions = f"""
⚠️  SHORT ORDER BINANCE SETUP:
1. Market SELL at current price (~${current_price:,.6f})
2. Set Stop Loss (BUY) at ${signal['stop_loss']:,.6f} (HIGHER than entry)
3. Set Take Profit (BUY) at ${signal['take_profit_1']:,.6f} (LOWER than entry)

🎯 Order Types:
• Entry: Market Order (SELL)  
• Stop Loss: Stop Market (BUY when price reaches ${signal['stop_loss']:,.6f})
• Take Profit: Limit Order (BUY at ${signal['take_profit_1']:,.6f})
"""
                            else:
                                binance_instructions = f"""
📈 LONG ORDER BINANCE SETUP:
1. Market BUY at current price (~${current_price:,.6f})
2. Set Stop Loss (SELL) at ${signal['stop_loss']:,.6f} (LOWER than entry)
3. Set Take Profit (SELL) at ${signal['take_profit_1']:,.6f} (HIGHER than entry)

🎯 Order Types:
• Entry: Market Order (BUY)
• Stop Loss: Stop Market (SELL when price reaches ${signal['stop_loss']:,.6f})  
• Take Profit: Limit Order (SELL at ${signal['take_profit_1']:,.6f})
"""
                            
                            futures_code = f"""
🎯 {mode_text} FUTURES TRADE SETUP
Symbol: {symbol}
Direction: {signal['direction']} ({'Market BUY' if signal['direction'] == 'LONG' else 'Market SELL'})
Leverage: {signal['leverage']}x

💰 Entry: ${signal['entry_price']:,.6f}
📊 Current Market: ${current_price:,.6f}
🛑 Stop Loss: ${signal['stop_loss']:,.6f}
🎯 TP1 (50%): ${signal['take_profit_1']:,.6f}
🎯 TP2 (Full): ${signal.get('take_profit_2', signal['take_profit_1'] * 1.05):,.6f}
🎯 Chandelier Stop: ${signal.get('chandelier_stop', signal['stop_loss']):,.6f}

📊 Position: ${signal['position_size_usdt']:,.2f} USDT
💳 Margin: ${signal['margin_required']:,.2f}
⚖️ Risk/Reward: 1:{signal['risk_reward_ratio']:.2f}

{binance_instructions}

🎯 Trade Management:
• Mode: {mode_text}
• Breakeven Trigger: ${signal.get('breakeven_trigger', signal['entry_price']):,.6f}
• Partial TP: {signal.get('partial_tp_size', 0.5):.1%} at TP1
• Time Stop: {signal.get('time_stop_candles', 20)} candles
• ATR Value: ${signal.get('atr_value', signal['entry_price'] * 0.02):,.6f}

📈 Market Analysis:
• Regime: {signal.get('market_regime', 'Unknown')}
• Confidence: {signal['confidence']}
• Futures Filter: {signal['futures_analysis'][:50]}...

🔒 Safety: {signal['safety_score']}/10
"""
                            
                            st.code(futures_code)

                            select_key = f"select_trade_{_normalize_streamlit_key(symbol)}_{_normalize_streamlit_key(signal['direction'])}_{idx}"
                            if st.button("📌 Chọn lệnh này", key=select_key, type="primary"):
                                gui.select_signal_for_trade(signal)

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
            
            # Display top signals for auto-scan mode
            if auto_scan_mode:
                if all_signals:
                    # Sort by safety score descending and take up to 5 (may be fewer)
                    top_signals = sorted(all_signals, key=lambda x: x[1]['safety_score'], reverse=True)[:5]
                    
                    st.success(f"🎯 **Top {len(top_signals)} Highest Safety Signals** (from {len(all_signals)} analyzed)")
                    
                    for rank, (symbol, signal) in enumerate(top_signals, 1):
                        signals_found += 1
                        
                        # Signal display with ranking
                        signal_class = "signal-long" if signal['direction'] == "LONG" else "signal-short"
                        
                        with st.expander(f"#{rank} 🚨 {signal['direction']} SIGNAL - {symbol} (Safety: {signal['safety_score']}/10)", expanded=True):
                            
                            # Professional Signal Display for Auto-scan
                            col1, col2, col3 = st.columns(3)
                            
                            with col1:
                                st.metric("💰 Entry Price", f"${signal['entry_price']:,.6f}")
                                st.metric("🛑 ATR Stop Loss", f"${signal['stop_loss']:,.6f}")
                                st.metric("🎯 TP1 Price", f"${signal['take_profit_1']:,.6f}")
                                if 'take_profit_2' in signal:
                                    st.metric("🎯 TP2 Price", f"${signal['take_profit_2']:,.6f}")
                                else:
                                    st.metric("🎯 TP2 Price", f"${signal['take_profit_1'] * 1.05:,.6f}")  # Fallback
                            
                            with col2:
                                st.metric("📈 Leverage", f"{signal.get('leverage', 'N/A')}x" if 'leverage' in signal else "N/A")
                                st.metric("💵 Position Size", f"${signal.get('position_size_usdt', 0):,.2f}" if 'position_size_usdt' in signal else "N/A")
                                st.metric("💳 Margin Required", f"${signal.get('margin_required', 0):,.2f}" if 'margin_required' in signal else "N/A")
                                st.metric("⚖️ Risk/Reward", f"1:{signal['risk_reward_ratio']:.2f}")
                            
                            with col3:
                                st.metric("🎯 TP1 ROI", f"+{signal.get('tp1_roi_percent', 0):.1f}%", help="Lợi nhuận trên margin với leverage")
                                st.metric("🛑 SL Risk", f"-{signal.get('sl_risk_percent', 0):.1f}%", help="Rủi ro trên margin với leverage")
                                st.metric("📊 Price Move TP", f"+{signal.get('price_change_tp_percent', 0):.2f}%", help="% thay đổi giá coin cần thiết")
                                st.metric("📊 Price Move SL", f"-{signal.get('price_change_sl_percent', 0):.2f}%", help="% thay đổi giá coin tới SL")
                            
                            # Additional info row for auto-scan with ranking
                            col4, col5, col6 = st.columns(3)
                            with col4:
                                # Add rank indicator and color coding
                                rank_color = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else "🏅"
                                st.metric("🏆 Rank", f"{rank_color} #{rank}")
                            with col5:
                                st.metric("🛡️ Safety Score", f"{signal['safety_score']}/10")
                                st.metric("🔮 Confidence", signal['confidence'])
                            with col6:
                                st.metric("📈 ATR Value", f"${signal.get('atr_value', signal['entry_price'] * 0.02):,.6f}")
                            
                            # Professional Market Analysis
                            st.info(f"🔍 **Market Regime**: {signal.get('market_regime', 'Trending')}")
                            st.info(f"🔍 **Futures Filter**: {signal.get('futures_analysis', 'Analysis completed')[:100]}...")
                            
                            # Trading parameters cho Binance Futures
                            st.markdown("### 📋 Copy to Binance Futures")
                            
                            mode_text = "CUSTOM" if signal.get('custom_mode', False) else "PROFESSIONAL ATR"
                            
                            futures_code = f"""🎯 {mode_text} FUTURES TRADE SETUP
Symbol: {symbol}
Direction: {signal['direction']} ({'Market BUY' if signal['direction'] == 'LONG' else 'Market SELL'})
Leverage: {signal.get('leverage', 'N/A')}x

💰 Entry: ${signal['entry_price']:,.6f}
🛑 Stop Loss: ${signal['stop_loss']:,.6f}
🎯 TP1 (50%): ${signal['take_profit_1']:,.6f}
🎯 TP2 (Full): ${signal.get('take_profit_2', signal['take_profit_1'] * 1.05):,.6f}
🎯 Chandelier Stop: ${signal.get('chandelier_stop', signal['stop_loss']):,.6f}

📊 Position: ${signal.get('position_size_usdt', 0):,.2f} USDT
💳 Margin: ${signal.get('margin_required', 0):,.2f}
⚖️ Risk/Reward: 1:{signal['risk_reward_ratio']:.2f}

🎯 Trade Management:
• Mode: {mode_text}
• Breakeven Trigger: ${signal.get('breakeven_trigger', signal['entry_price']):,.6f}
• Partial TP: {signal.get('partial_tp_size', 0.5):.1%} at TP1
• Time Stop: {signal.get('time_stop_candles', 'N/A')} candles

📈 Market Analysis:
• Regime: {signal.get('market_regime', 'Not Available')}
• Confidence: {signal.get('confidence', 'Medium')}

🔒 Safety: {signal['safety_score']}/10
"""
                            
                            st.code(futures_code)

                            select_key = f"select_trade_{_normalize_streamlit_key(symbol)}_{_normalize_streamlit_key(signal['direction'])}_{rank}"
                            if st.button("📌 Chọn lệnh này", key=select_key, type="primary"):
                                gui.select_signal_for_trade(signal)
                            
                            # Add to history
                            signal['generated_at'] = datetime.now()
                            st.session_state.signals_history.append(signal)
                else:
                    st.warning("⏳ No signals found in current market scan.")
                    st.info(f"💡 **Analyzed {len(gui.supported_symbols)} coins** - Try again in a few minutes as market conditions change.")
            
            # v4.2.1: Auto-scan can return 0 valid signals (no forced top 5)
            if signals_found == 0:
                if auto_scan_mode:
                    st.info("🔍 **Auto-scan complete**: No signals meet current quality standards. Try again as market conditions change.")
                else:
                    st.warning("⏳ No trading signals generated. Try lowering the safety score or different timeframes.")
                    
                    # Show debug summary for manual mode only
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

        stored_signals = st.session_state.get('latest_signals_data', [])
        if stored_signals:
            st.markdown("### 📌 Generated Signals (Session)")
            for idx, signal in enumerate(stored_signals):
                symbol = signal.get('symbol', 'UNKNOWN')
                direction = signal.get('direction', 'LONG')
                entry_price = signal.get('entry_price', 0.0)
                stop_loss = signal.get('stop_loss', 0.0)
                take_profit_1 = signal.get('take_profit_1', 0.0)
                safety_score = signal.get('safety_score', 0)
                leverage = signal.get('leverage', 1)
                margin_required = signal.get('margin_required', 0.0)
                position_size = signal.get('position_size_usdt', 0.0)

                with st.container():
                    st.markdown(f"**{symbol}** · {direction} · Entry ${entry_price:,.6f}")
                    info_cols = st.columns(3)
                    with info_cols[0]:
                        st.write(f"Stop Loss: ${stop_loss:,.6f}")
                        st.write(f"TP1: ${take_profit_1:,.6f}")
                    with info_cols[1]:
                        st.write(f"Safety: {safety_score}/10")
                        st.write(f"Leverage: {leverage}x")
                    with info_cols[2]:
                        st.write(f"Margin: ${margin_required:,.2f}")
                        st.write(f"Position: ${position_size:,.2f}")

                    button_key = f"select_saved_signal_{_normalize_streamlit_key(symbol)}_{idx}"
                    if st.button("📌 Chọn lệnh này", key=button_key):
                        gui.select_signal_for_trade(signal)
    
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
                        st.write(f"**Entry:** ${signal['entry_price']:,.6f}")
                        st.write(f"**ATR Stop:** ${signal['stop_loss']:,.6f}")
                        st.write(f"**Take Profit 1:** ${signal['take_profit_1']:,.6f}")
                        st.write(f"**Leverage:** {signal['leverage']}x")
                    
                    with col2:
                        st.write(f"**Safety Score:** {signal['safety_score']}/10")
                        st.write(f"**Confidence:** {signal['confidence']}")
                        st.write(f"**Risk/Reward:** 1:{signal['risk_reward_ratio']:.2f}")
                        st.write(f"**Position Size:** ${signal['position_size_usdt']:,.2f}")
                        
                    # Show market regime and trade management
                    st.info(f"**Regime:** {signal.get('market_regime', 'N/A')}")
                    st.info(f"**Breakeven:** ${signal.get('breakeven_trigger', 0):,.6f} | **Partial TP:** {signal.get('partial_tp_size', 0.5):.1%}")
            
            # Clear history button
            if st.button("🗑️ Clear History"):
                st.session_state.signals_history = []
                st.success("✅ Signal history cleared!")
                st.rerun()
        else:
            st.info("📝 No signals generated yet. Use the Trading Signals tab to generate signals.")

        st.markdown("---")
        st.markdown("### 📌 Trades đã chọn")

        selected_trades = st.session_state.get('selected_signals', [])
        if selected_trades:
            for idx, trade in enumerate(reversed(selected_trades[-10:])):
                trade_symbol = trade.get('symbol', 'UNKNOWN')
                status = trade.get('status', 'open')
                header = f"{trade_symbol} {trade.get('direction', 'LONG')} @ {trade.get('entry_price', 0):,.4f}"
                analytics_id = trade.get('analytics_trade_id')
                if status == 'closed':
                    header += " ✅"

                with st.expander(header, expanded=status != 'closed'):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**Analytics ID:** {analytics_id if analytics_id else 'Chưa đồng bộ'}")
                        st.write(f"**Được chọn lúc:** {trade.get('timestamp', '')[:19]}")
                        st.write(f"**Trạng thái:** {status}")
                    with col2:
                        st.write(f"**TP1:** {trade.get('take_profit_1', 'N/A')}")
                        st.write(f"**Stop Loss:** {trade.get('stop_loss', 'N/A')}")
                        st.write(f"**Timeframe:** {trade.get('timeframe', 'N/A')}")
                        if status == 'closed':
                            st.write(f"**Outcome:** {trade.get('outcome', 'N/A')}")
                            st.write(f"**Exit Price:** {trade.get('exit_price', 'N/A')}")

                    if status != 'closed':
                        if analytics_id:
                            form_key = f"close_trade_{_normalize_streamlit_key(str(analytics_id))}_{idx}"
                            with st.form(form_key):
                                exit_price = st.number_input(
                                    "Exit Price",
                                    min_value=0.0,
                                    value=float(trade.get('take_profit_1') or trade.get('entry_price') or 0.0),
                                    key=f"exit_price_input_{analytics_id}_{idx}"
                                )
                                outcome = st.selectbox(
                                    "Outcome",
                                    options=["tp1_hit", "tp2_hit", "tp3_hit", "sl_hit", "manual_close"],
                                    index=0,
                                    key=f"outcome_select_{analytics_id}_{idx}"
                                )
                                submit = st.form_submit_button("✅ Đánh dấu đã đóng", use_container_width=True)

                            if submit:
                                if exit_price <= 0:
                                    st.warning("⚠️ Exit price phải lớn hơn 0")
                                else:
                                    success = analytics_integrator.update_trade_outcome_by_id(analytics_id, exit_price, outcome)
                                    if success:
                                        trade['status'] = 'closed'
                                        trade['outcome'] = outcome
                                        trade['exit_price'] = exit_price
                                        trade['closed_at'] = datetime.now().isoformat()

                                        # Sync tracked trades list if present
                                        for stored in st.session_state.get('tracked_trades', []):
                                            if stored.get('trade_id') == analytics_id:
                                                stored.update({
                                                    'status': 'closed',
                                                    'outcome': outcome,
                                                    'exit_price': exit_price,
                                                    'closed_at': trade['closed_at']
                                                })
                                                break

                                        st.success("✅ Đã cập nhật kết quả trade vào analytics")
                                        st.rerun()
                                    else:
                                        st.warning("❌ Không thể cập nhật analytics. Thử lại sau.")
                        else:
                            st.info("ℹ️ Lệnh chưa đồng bộ với analytics nên chưa thể cập nhật kết quả tự động.")
        else:
            st.info("Chưa có lệnh nào được chọn từ tab Trading.")
    
    # Analytics Tab
    with tab5:
        if ANALYTICS_AVAILABLE:
            render_analytics_tab()
        else:
            st.error("📊 Analytics module not available")
            st.info("Install analytics module to access performance tracking features")
    
    # Analytics Integration
    if ANALYTICS_AVAILABLE:
        add_analytics_integration_to_main_gui()
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #666;">
        <p>⚠️ <strong>Risk Warning:</strong> Trading cryptocurrencies involves substantial risk. Never risk more than you can afford to lose.</p>
        <p>💡 This tool is for educational purposes. Always do your own research before making trading decisions.</p>
        <p><small><strong>Last Updated:</strong> Sep 27, 2025 – <strong>Version:</strong> 4.2.1</small></p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
