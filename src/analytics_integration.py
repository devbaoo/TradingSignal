#!/usr/bin/env python3
"""
Analytics Integration Utilities
Connect main trading system with analytics tracking
Version 1.0.0 - September 27, 2025
"""

import streamlit as st
from typing import Dict, Optional
from datetime import datetime
import json

# Import analytics components
try:
    from src.trading_analytics import trade_tracker, auth, db
except ImportError:
    # Fallback if analytics not available
    trade_tracker = None
    auth = None
    db = None

class AnalyticsIntegrator:
    """Integrate analytics with main trading system"""
    
    def __init__(self):
        self.enabled = trade_tracker is not None
        self.current_user_id = None
    
    def initialize_user_session(self):
        """Initialize analytics user session from main app"""
        if not self.enabled:
            return False
        
        # Check if user is logged into analytics
        if 'analytics_user' in st.session_state and st.session_state.analytics_user:
            self.current_user_id = st.session_state.analytics_user['id']
            return True
        
        return False
    
    def show_analytics_login_prompt(self):
        """Show prompt to login to analytics"""
        if not self.enabled:
            return
        
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 📊 Analytics Tracking")
        
        if not self.current_user_id:
            st.sidebar.warning("⚠️ Analytics not connected")
            st.sidebar.info("Đăng nhập ở màn hình chính để kích hoạt analytics.")
        else:
            user = st.session_state.analytics_user
            st.sidebar.success(f"✅ Connected: {user['username']}")
            st.sidebar.text(f"Tier: {user['subscription_tier']}")
            
            # Show recent tracking stats
            if 'tracked_trades' in st.session_state:
                recent_count = len(st.session_state.tracked_trades)
                st.sidebar.metric("Signals Tracked", recent_count)
    
    def track_signal_as_trade(self, signal_data: Dict) -> bool:
        """Track a generated signal as a potential trade"""
        if not self.enabled or not self.current_user_id:
            return False
        
        try:
            # Convert signal data to trade format
            direction = signal_data.get('direction') or signal_data.get('action')
            if direction:
                direction = direction.upper()

            position_size_usdt = signal_data.get('position_size_usdt')
            if position_size_usdt is None:
                position_size_usdt = signal_data.get('position_size')
            if position_size_usdt is None:
                position_size_usdt = 100.0

            regime_info = signal_data.get('market_regime')
            if not regime_info:
                raw_regime = signal_data.get('regime')
                if isinstance(raw_regime, dict):
                    trend = raw_regime.get('trend_regime', 'UNKNOWN')
                    vol = raw_regime.get('volatility_regime', 'UNKNOWN')
                    strength = raw_regime.get('strength', raw_regime.get('regime_strength', 0.5))
                    regime_info = f"{trend} | {vol} | Strength: {strength:.2f}"
                else:
                    regime_info = raw_regime

            trade_data = {
                'symbol': signal_data.get('symbol'),
                'direction': direction,
                'entry_price': signal_data.get('entry_price'),
                'position_size_usdt': position_size_usdt,
                'leverage': signal_data.get('leverage', 1),
                'stop_loss': signal_data.get('stop_loss'),
                'take_profit_1': signal_data.get('take_profit_1'),
                'take_profit_2': signal_data.get('take_profit_2'),
                'take_profit_3': signal_data.get('take_profit_3'),
                'risk_reward_ratio': signal_data.get('risk_reward_ratio'),
                'safety_score': signal_data.get('safety_score'),
                'margin_required': signal_data.get('margin_required'),
                'liquidation_price': signal_data.get('liquidation_price'),
                'timeframe': signal_data.get('timeframe'),
                'market_regime': regime_info,
                'volatility_level': signal_data.get('volatility_level'),
                'signal_source': 'trading_insight',
                'strategy_version': '4.2.1'
            }
            
            # Add trade to tracking
            trade_id = trade_tracker.add_trade(self.current_user_id, trade_data)
            
            if trade_id:
                # Store trade ID for potential updates
                if 'tracked_trades' not in st.session_state:
                    st.session_state.tracked_trades = []
                
                st.session_state.tracked_trades.append({
                    'trade_id': trade_id,
                    'symbol': trade_data['symbol'],
                    'direction': trade_data.get('direction'),
                    'entry_price': trade_data['entry_price'],
                    'take_profit_1': trade_data.get('take_profit_1'),
                    'stop_loss': trade_data.get('stop_loss'),
                    'timeframe': trade_data.get('timeframe'),
                    'timestamp': datetime.now().isoformat(),
                    'status': 'open'
                })
                
                # Show success message
                st.sidebar.success(f"📊 Signal tracked: {trade_data['symbol']}")
            
            return trade_id
            
        except Exception as e:
            st.sidebar.error(f"Failed to track signal: {str(e)}")
            return None
    
    def show_analytics_integration_ui(self):
        """Show analytics integration UI in main app"""
        if not self.enabled:
            return
        
        # Initialize user session
        self.initialize_user_session()
        
        # Show login prompt or user info
        self.show_analytics_login_prompt()
        
        # Show recent tracked trades
        if self.current_user_id and 'tracked_trades' in st.session_state:
            recent_trades = st.session_state.tracked_trades[-5:]  # Last 5 trades
            if recent_trades:
                st.sidebar.markdown("#### 📈 Recent Signals Tracked")
                for i, trade in enumerate(reversed(recent_trades)):
                    st.sidebar.text(f"{trade['symbol']} @ {trade['entry_price']}")
    
    def update_trade_outcome(self, 
                             symbol: str, 
                             entry_price: float, 
                             exit_price: float, 
                             outcome: str, 
                             closed_reason: Optional[str] = None) -> bool:
        """Update trade outcome (for manual use)."""
        if not self.enabled or not self.current_user_id:
            return False
        
        try:
            # Find trade by symbol and entry price (simplified matching)
            # In production, you'd want more robust trade matching
            conn = db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id FROM trades 
                WHERE user_id = ? AND symbol = ? AND entry_price = ? AND status = 'open'
                ORDER BY entry_time DESC
                LIMIT 1
            """, (self.current_user_id, symbol, entry_price))
            
            trade_row = cursor.fetchone()
            if trade_row:
                trade_id = trade_row[0]
                success = trade_tracker.update_trade_outcome(trade_id, exit_price, outcome, closed_reason)
                conn.close()
                return success
            
            conn.close()
            return False
            
        except Exception as e:
            st.error(f"Failed to update trade outcome: {str(e)}")
            return False

    def update_trade_outcome_by_id(self, 
                                   trade_id: int, 
                                   exit_price: float, 
                                   outcome: str, 
                                   closed_reason: Optional[str] = None) -> bool:
        """Update trade outcome directly by trade id."""
        if not self.enabled or not self.current_user_id:
            return False
        try:
            success = trade_tracker.update_trade_outcome(trade_id, exit_price, outcome, closed_reason)
            if success and 'tracked_trades' in st.session_state:
                for trade in st.session_state.tracked_trades:
                    if trade.get('trade_id') == trade_id:
                        trade['status'] = 'closed'
                        trade['closed_at'] = datetime.now().isoformat()
                        trade['outcome'] = outcome
                        trade['closed_reason'] = closed_reason or trade.get('closed_reason')
                        trade['exit_price'] = exit_price
                        break
            return success
        except Exception as e:
            st.error(f"Failed to update trade outcome: {str(e)}")
            return False

# Global integrator instance
analytics_integrator = AnalyticsIntegrator()

def show_analytics_modal():
    """Show analytics login/dashboard modal"""
    if 'show_analytics_login' in st.session_state and st.session_state.show_analytics_login:
        with st.container():
            st.markdown("### 🔐 Analytics Login Required")
            
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.info("Đăng nhập trực tiếp trong ứng dụng chính để bật analytics.")

                if st.button("Đã hiểu", type="primary", use_container_width=True):
                    st.session_state.show_analytics_login = False
                    st.rerun()

def add_analytics_integration_to_main_gui():
    """Add analytics integration components to main GUI"""
    # Show modal if needed
    show_analytics_modal()
    
    # Show integration UI in sidebar
    analytics_integrator.show_analytics_integration_ui()

def track_generated_signal(signal_data: Dict) -> bool:
    """Wrapper function to track generated signals"""
    return analytics_integrator.track_signal_as_trade(signal_data)

# Helper functions for portfolio integration
def sync_portfolio_with_analytics():
    """Sync portfolio positions with analytics tracking"""
    if not analytics_integrator.enabled or not analytics_integrator.current_user_id:
        return
    
    # Get portfolio positions from session state
    if 'portfolio_positions' in st.session_state:
        positions = st.session_state.portfolio_positions
        
        # Sync open positions with analytics
        for pos in positions:
            # Check if this position is already tracked
            # This is a simplified implementation
            pass

def show_analytics_summary_widget():
    """Show analytics summary widget in main GUI"""
    if not analytics_integrator.enabled:
        return
    
    if analytics_integrator.initialize_user_session():
        st.sidebar.markdown("#### 📊 Analytics Summary")
        
        # Get recent performance (simplified)
        user_id = analytics_integrator.current_user_id
        
        try:
            # Get recent trades count
            recent_trades = trade_tracker.get_user_trades(user_id, limit=10)
            if not recent_trades.empty:
                closed_trades = recent_trades[recent_trades['status'] == 'closed']
                if not closed_trades.empty:
                    total_pnl = closed_trades['pnl_usdt'].sum()
                    win_rate = (len(closed_trades[closed_trades['pnl_usdt'] > 0]) / len(closed_trades) * 100)
                    
                    st.sidebar.metric("Recent P&L", f"${total_pnl:.2f}")
                    st.sidebar.metric("Win Rate", f"{win_rate:.1f}%")
                else:
                    st.sidebar.info("No closed trades yet")
            else:
                st.sidebar.info("Start trading to see analytics")
                
        except Exception as e:
            st.sidebar.error("Analytics connection issue")

# Export main functions
__all__ = [
    'analytics_integrator',
    'add_analytics_integration_to_main_gui', 
    'track_generated_signal',
    'sync_portfolio_with_analytics',
    'show_analytics_summary_widget'
]
