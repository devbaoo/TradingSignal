#!/usr/bin/env python3
"""
Trading Analytics GUI - Production Dashboard
Streamlit interface for trading analytics with authentication
Version 1.0.0 - September 27, 2025
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime, date, timedelta
import time

# Import analytics components
from trading_analytics import db, auth, trade_tracker, dashboard

def init_session_state():
    """Initialize analytics session state"""
    if 'analytics_user' not in st.session_state:
        st.session_state.analytics_user = None
    if 'analytics_session_token' not in st.session_state:
        st.session_state.analytics_session_token = None
    if 'show_registration' not in st.session_state:
        st.session_state.show_registration = False

def login_page():
    """Display login/registration page"""
    st.markdown("# 🔐 Trading Analytics - Login")
    st.markdown("---")
    
    # Toggle between login and registration
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Login", type="primary", use_container_width=True):
            st.session_state.show_registration = False
    with col2:
        if st.button("Register New Account", use_container_width=True):
            st.session_state.show_registration = True
    
    st.markdown("---")
    
    if st.session_state.show_registration:
        registration_form()
    else:
        login_form()

def login_form():
    """Display login form"""
    st.markdown("### Login to Your Analytics Dashboard")
    
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login", type="primary")
        
        if submit:
            if username and password:
                user_info = auth.authenticate_user(username, password)
                if user_info:
                    # Create session
                    session_token = auth.create_session(user_info['id'])
                    if session_token:
                        st.session_state.analytics_user = user_info
                        st.session_state.analytics_session_token = session_token
                        st.success("✅ Login successful! Redirecting...")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Failed to create session")
                else:
                    st.error("❌ Invalid username or password")
            else:
                st.error("Please enter both username and password")

def registration_form():
    """Display registration form"""
    st.markdown("### Create New Account")
    
    with st.form("registration_form"):
        username = st.text_input("Username", help="Choose a unique username")
        email = st.text_input("Email", help="Valid email address required")
        password = st.text_input("Password", type="password", help="Minimum 8 characters")
        password_confirm = st.text_input("Confirm Password", type="password")
        
        terms_accepted = st.checkbox("I agree to the Terms of Service and Privacy Policy")
        
        submit = st.form_submit_button("Create Account", type="primary")
        
        if submit:
            # Validation
            errors = []
            if not username or len(username) < 3:
                errors.append("Username must be at least 3 characters")
            if not email or '@' not in email:
                errors.append("Valid email address required")
            if not password or len(password) < 8:
                errors.append("Password must be at least 8 characters")
            if password != password_confirm:
                errors.append("Passwords do not match")
            if not terms_accepted:
                errors.append("You must accept the Terms of Service")
            
            if errors:
                for error in errors:
                    st.error(f"❌ {error}")
            else:
                success, message = auth.register_user(username, email, password)
                if success:
                    st.success("✅ Registration successful! You can now login.")
                    st.session_state.show_registration = False
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error(f"❌ {message}")

def validate_session():
    """Validate current session"""
    if st.session_state.analytics_session_token:
        user_info = auth.validate_session(st.session_state.analytics_session_token)
        if user_info:
            st.session_state.analytics_user = user_info
            return True
        else:
            # Session expired
            st.session_state.analytics_user = None
            st.session_state.analytics_session_token = None
            return False
    return False

def logout():
    """Logout user"""
    st.session_state.analytics_user = None
    st.session_state.analytics_session_token = None
    st.rerun()

def dashboard_header():
    """Display dashboard header with user info"""
    col1, col2, col3 = st.columns([3, 2, 1])
    
    with col1:
        st.markdown("# 📊 Trading Analytics Dashboard")
        st.markdown(f"Welcome back, **{st.session_state.analytics_user['username']}**!")
    
    with col2:
        tier = st.session_state.analytics_user['subscription_tier']
        tier_emoji = "🆓" if tier == "free" else "⭐" if tier == "pro" else "💎"
        st.markdown(f"**Subscription:** {tier_emoji} {tier.title()}")
        st.markdown(f"**User ID:** #{st.session_state.analytics_user['id']}")
    
    with col3:
        if st.button("🚪 Logout", type="secondary"):
            logout()

def overview_dashboard():
    """Main overview dashboard"""
    user_id = st.session_state.analytics_user['id']
    
    # Date range selector
    st.markdown("## 📈 Performance Overview")
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("From", value=date.today() - timedelta(days=30))
    with col2:
        end_date = st.date_input("To", value=date.today())
    
    # Get trades for the period
    trades_df = trade_tracker.get_user_trades(user_id, limit=500)
    
    if not trades_df.empty:
        # Filter by date range
        trades_df['entry_date'] = pd.to_datetime(trades_df['entry_time']).dt.date
        period_trades = trades_df[
            (trades_df['entry_date'] >= start_date) & 
            (trades_df['entry_date'] <= end_date)
        ]
        
        # Key metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_trades = len(period_trades)
            st.metric("Total Trades", total_trades)
        
        with col2:
            closed_trades = period_trades[period_trades['status'] == 'closed']
            if not closed_trades.empty:
                winning_trades = len(closed_trades[closed_trades['pnl_usdt'] > 0])
                win_rate = (winning_trades / len(closed_trades) * 100) if len(closed_trades) > 0 else 0
                st.metric("Win Rate", f"{win_rate:.1f}%")
            else:
                st.metric("Win Rate", "0.0%")
        
        with col3:
            if not closed_trades.empty:
                total_pnl = closed_trades['pnl_usdt'].sum()
                st.metric("Total P&L", f"${total_pnl:.2f}")
            else:
                st.metric("Total P&L", "$0.00")
        
        with col4:
            open_trades = len(period_trades[period_trades['status'] == 'open'])
            st.metric("Open Positions", open_trades)
        
        # Charts
        if not closed_trades.empty:
            # Daily PnL chart
            st.markdown("### Daily P&L Performance")
            daily_pnl = closed_trades.groupby('entry_date')['pnl_usdt'].sum().reset_index()
            daily_pnl['cumulative_pnl'] = daily_pnl['pnl_usdt'].cumsum()
            
            fig = make_subplots(
                rows=2, cols=1,
                subplot_titles=('Daily P&L', 'Cumulative P&L'),
                vertical_spacing=0.1
            )
            
            # Daily P&L bar chart
            colors = ['green' if pnl >= 0 else 'red' for pnl in daily_pnl['pnl_usdt']]
            fig.add_trace(
                go.Bar(
                    x=daily_pnl['entry_date'],
                    y=daily_pnl['pnl_usdt'],
                    marker_color=colors,
                    name='Daily P&L'
                ),
                row=1, col=1
            )
            
            # Cumulative P&L line chart
            fig.add_trace(
                go.Scatter(
                    x=daily_pnl['entry_date'],
                    y=daily_pnl['cumulative_pnl'],
                    mode='lines+markers',
                    line=dict(color='blue', width=2),
                    name='Cumulative P&L'
                ),
                row=2, col=1
            )
            
            fig.update_layout(height=500, showlegend=False)
            fig.update_xaxes(title_text="Date")
            fig.update_yaxes(title_text="P&L (USDT)", row=1, col=1)
            fig.update_yaxes(title_text="Cumulative P&L (USDT)", row=2, col=1)
            
            st.plotly_chart(fig, use_container_width=True)
        
    else:
        st.info("📝 No trades found. Start trading to see your analytics!")

def trade_history_page():
    """Trade history and details page"""
    st.markdown("## 📋 Trade History")
    
    user_id = st.session_state.analytics_user['id']
    
    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        status_filter = st.selectbox("Status", ["All", "open", "closed", "cancelled"])
    with col2:
        symbol_filter = st.text_input("Symbol (optional)", placeholder="e.g., BTCUSDT")
    with col3:
        limit = st.number_input("Max Records", min_value=10, max_value=500, value=100)
    
    # Get trades
    trades_df = trade_tracker.get_user_trades(
        user_id, 
        limit=limit,
        status=status_filter if status_filter != "All" else None
    )
    
    # Apply symbol filter
    if symbol_filter and not trades_df.empty:
        trades_df = trades_df[trades_df['symbol'].str.contains(symbol_filter, case=False, na=False)]
    
    if not trades_df.empty:
        # Display summary
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Records", len(trades_df))
        with col2:
            closed_count = len(trades_df[trades_df['status'] == 'closed'])
            st.metric("Closed Trades", closed_count)
        with col3:
            if closed_count > 0:
                closed_trades = trades_df[trades_df['status'] == 'closed']
                avg_pnl = closed_trades['pnl_usdt'].mean()
                st.metric("Avg P&L", f"${avg_pnl:.2f}")
            else:
                st.metric("Avg P&L", "$0.00")
        with col4:
            open_count = len(trades_df[trades_df['status'] == 'open'])
            st.metric("Open Trades", open_count)
        
        # Trade table
        st.markdown("### Trade Details")
        
        # Select columns to display
        display_columns = [
            'symbol', 'direction', 'entry_price', 'exit_price', 'position_size_usdt',
            'leverage', 'pnl_usdt', 'pnl_percent', 'safety_score', 'status',
            'outcome', 'entry_time', 'exit_time'
        ]
        
        display_df = trades_df[display_columns].copy()
        
        # Format columns
        if not display_df.empty:
            display_df['entry_price'] = display_df['entry_price'].round(6)
            display_df['exit_price'] = display_df['exit_price'].fillna(0).round(6)
            display_df['pnl_usdt'] = display_df['pnl_usdt'].fillna(0).round(2)
            display_df['pnl_percent'] = display_df['pnl_percent'].fillna(0).round(2)
            display_df['entry_time'] = pd.to_datetime(display_df['entry_time']).dt.strftime('%Y-%m-%d %H:%M')
            display_df['exit_time'] = pd.to_datetime(display_df['exit_time'], errors='coerce').dt.strftime('%Y-%m-%d %H:%M')
            display_df['exit_time'] = display_df['exit_time'].fillna('-')
        
        # Color code P&L
        def color_pnl(val):
            if pd.isna(val) or val == 0:
                return ''
            elif val > 0:
                return 'background-color: #d4edda'
            else:
                return 'background-color: #f8d7da'
        
        styled_df = display_df.style.applymap(color_pnl, subset=['pnl_usdt'])
        st.dataframe(styled_df, use_container_width=True, hide_index=True)
        
        # Export option
        if st.button("📊 Export to CSV"):
            csv = trades_df.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"trades_{user_id}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
    else:
        st.info("No trades match your filters.")

def sl_tp_statistics_page():
    """SL/TP statistics and success rate analysis"""
    st.markdown("## 🎯 Stop Loss & Take Profit Statistics")
    
    user_id = st.session_state.analytics_user['id']
    
    # Time period selector
    period_options = {
        "Last 7 Days": 7,
        "Last 30 Days": 30,
        "Last 90 Days": 90,
        "Last 365 Days": 365
    }
    
    selected_period = st.selectbox("Analysis Period", list(period_options.keys()), index=1)
    days = period_options[selected_period]
    
    # Get statistics
    stats = dashboard.get_sl_tp_statistics(user_id, days)
    
    if stats['total_closed_trades'] > 0:
        # Overview metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Closed Trades", stats['total_closed_trades'])
        
        with col2:
            st.metric("Success Rate", f"{stats['success_rate']:.1f}%")
        
        with col3:
            st.metric("SL Hits", stats['sl_hits'])
        
        with col4:
            st.metric("TP Hits", stats['tp_hits'])
        
        # Success rate by safety score
        st.markdown("### Success Rate by Safety Score")
        
        if stats['by_safety_score']:
            safety_data = []
            for score, data in stats['by_safety_score'].items():
                safety_data.append({
                    'Safety Score': score,
                    'Trades': data['trades'],
                    'Success Rate (%)': data['success_rate']
                })
            
            safety_df = pd.DataFrame(safety_data)
            
            # Chart
            fig = px.bar(
                safety_df,
                x='Safety Score',
                y='Success Rate (%)',
                title='Success Rate by Safety Score',
                color='Success Rate (%)',
                color_continuous_scale='RdYlGn',
                text='Trades'
            )
            
            fig.update_traces(textposition='outside')
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
            
            # Table
            st.dataframe(safety_df, use_container_width=True, hide_index=True)
        
        # Success rate by timeframe
        st.markdown("### Success Rate by Timeframe")
        
        if stats['by_timeframe']:
            tf_data = []
            for tf, data in stats['by_timeframe'].items():
                tf_data.append({
                    'Timeframe': tf,
                    'Trades': data['trades'],
                    'Success Rate (%)': data['success_rate']
                })
            
            tf_df = pd.DataFrame(tf_data)
            
            # Chart
            fig = px.pie(
                tf_df,
                values='Trades',
                names='Timeframe',
                title='Trade Distribution by Timeframe'
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Success rate table
            st.dataframe(tf_df, use_container_width=True, hide_index=True)
        
        # Detailed outcome breakdown
        st.markdown("### Detailed Outcome Analysis")
        
        # Get detailed outcomes
        trades_df = trade_tracker.get_user_trades(user_id, limit=1000, status='closed')
        if not trades_df.empty:
            # Filter by time period
            trades_df['entry_date'] = pd.to_datetime(trades_df['entry_time']).dt.date
            cutoff_date = date.today() - timedelta(days=days)
            period_trades = trades_df[trades_df['entry_date'] >= cutoff_date]
            
            if not period_trades.empty:
                outcome_counts = period_trades['outcome'].value_counts()
                
                fig = px.pie(
                    values=outcome_counts.values,
                    names=outcome_counts.index,
                    title='Trade Outcomes Distribution'
                )
                st.plotly_chart(fig, use_container_width=True)
                
                # Outcome details table
                outcome_df = pd.DataFrame({
                    'Outcome': outcome_counts.index,
                    'Count': outcome_counts.values,
                    'Percentage': (outcome_counts.values / outcome_counts.sum() * 100).round(1)
                })
                st.dataframe(outcome_df, use_container_width=True, hide_index=True)
    
    else:
        st.info(f"📊 No closed trades found in the last {days} days.")

def monthly_performance_page():
    """Monthly performance analysis"""
    st.markdown("## 📅 Monthly Performance Analysis")
    
    user_id = st.session_state.analytics_user['id']
    
    # Month/year selector
    col1, col2 = st.columns(2)
    with col1:
        current_year = datetime.now().year
        year = st.selectbox("Year", range(current_year - 2, current_year + 1), index=2)
    with col2:
        month = st.selectbox("Month", range(1, 13), index=datetime.now().month - 1, 
                           format_func=lambda x: datetime(2024, x, 1).strftime('%B'))
    
    # Get monthly data
    monthly_df = dashboard.get_monthly_performance(user_id, year, month)
    
    if not monthly_df.empty:
        # Monthly summary
        total_trades = monthly_df['total_trades'].sum()
        total_pnl = monthly_df['daily_pnl'].sum()
        avg_win_rate = monthly_df['win_rate'].mean()
        best_day = monthly_df.loc[monthly_df['daily_pnl'].idxmax()]
        worst_day = monthly_df.loc[monthly_df['daily_pnl'].idxmin()]
        
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Trades", total_trades)
        
        with col2:
            st.metric("Monthly P&L", f"${total_pnl:.2f}")
        
        with col3:
            st.metric("Avg Win Rate", f"{avg_win_rate:.1f}%")
        
        with col4:
            profitable_days = len(monthly_df[monthly_df['daily_pnl'] > 0])
            st.metric("Profitable Days", f"{profitable_days}/{len(monthly_df)}")
        
        # Daily performance chart
        st.markdown(f"### Daily Performance - {datetime(year, month, 1).strftime('%B %Y')}")
        
        fig = make_subplots(
            rows=3, cols=1,
            subplot_titles=('Daily P&L', 'Cumulative P&L', 'Daily Trade Count'),
            vertical_spacing=0.1
        )
        
        # Daily P&L
        colors = ['green' if pnl >= 0 else 'red' for pnl in monthly_df['daily_pnl']]
        fig.add_trace(
            go.Bar(
                x=monthly_df['trade_date'],
                y=monthly_df['daily_pnl'],
                marker_color=colors,
                name='Daily P&L'
            ),
            row=1, col=1
        )
        
        # Cumulative P&L
        fig.add_trace(
            go.Scatter(
                x=monthly_df['trade_date'],
                y=monthly_df['cumulative_pnl'],
                mode='lines+markers',
                line=dict(color='blue', width=2),
                name='Cumulative P&L'
            ),
            row=2, col=1
        )
        
        # Trade count
        fig.add_trace(
            go.Bar(
                x=monthly_df['trade_date'],
                y=monthly_df['total_trades'],
                marker_color='lightblue',
                name='Trade Count'
            ),
            row=3, col=1
        )
        
        fig.update_layout(height=800, showlegend=False)
        fig.update_xaxes(title_text="Date")
        fig.update_yaxes(title_text="P&L (USDT)", row=1, col=1)
        fig.update_yaxes(title_text="Cumulative P&L (USDT)", row=2, col=1)
        fig.update_yaxes(title_text="Number of Trades", row=3, col=1)
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Best and worst days
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 🏆 Best Trading Day")
            st.metric("Date", best_day['trade_date'])
            st.metric("P&L", f"${best_day['daily_pnl']:.2f}")
            st.metric("Trades", int(best_day['total_trades']))
            st.metric("Win Rate", f"{best_day['win_rate']:.1f}%")
        
        with col2:
            st.markdown("#### 📉 Worst Trading Day")
            st.metric("Date", worst_day['trade_date'])
            st.metric("P&L", f"${worst_day['daily_pnl']:.2f}")
            st.metric("Trades", int(worst_day['total_trades']))
            st.metric("Win Rate", f"{worst_day['win_rate']:.1f}%")
        
        # Detailed daily table
        st.markdown("### Daily Breakdown")
        
        display_df = monthly_df.copy()
        display_df['daily_pnl'] = display_df['daily_pnl'].round(2)
        display_df['cumulative_pnl'] = display_df['cumulative_pnl'].round(2)
        display_df['avg_trade_pnl'] = display_df['avg_trade_pnl'].round(2)
        display_df['best_trade'] = display_df['best_trade'].round(2)
        display_df['worst_trade'] = display_df['worst_trade'].round(2)
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    else:
        st.info(f"📊 No trades found for {datetime(year, month, 1).strftime('%B %Y')}.")

def main():
    """Main analytics application"""
    st.set_page_config(
        page_title="Trading Analytics",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Initialize session state
    init_session_state()
    
    # Check authentication
    if not st.session_state.analytics_user or not validate_session():
        login_page()
        return
    
    # Display dashboard
    dashboard_header()
    
    # Sidebar navigation
    st.sidebar.markdown("## 🧭 Navigation")
    
    pages = {
        "📈 Overview": overview_dashboard,
        "📋 Trade History": trade_history_page,
        "🎯 SL/TP Statistics": sl_tp_statistics_page,
        "📅 Monthly Performance": monthly_performance_page
    }
    
    selected_page = st.sidebar.radio("Select Page", list(pages.keys()))
    
    # Display selected page
    pages[selected_page]()
    
    # Footer
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Trading Analytics v1.0.0**")
    st.sidebar.markdown("Integrated with TradingInsight v4.2.1")
    st.sidebar.markdown(f"Session: {st.session_state.analytics_user['username']}")

if __name__ == "__main__":
    main()