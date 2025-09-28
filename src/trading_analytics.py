#!/usr/bin/env python3
"""
Trading Analytics Module - Production Ready
Full-stack analytics system with authentication, dashboards, and trade tracking
Version 1.0.0 - September 27, 2025
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import sqlite3
import hashlib
import uuid
from datetime import datetime, timedelta
import json
from typing import Dict, List, Optional, Tuple
import time

# Database schema and initialization
class TradingAnalyticsDB:
    def __init__(self, db_path: str = "trading_analytics.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database with all required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                subscription_tier TEXT DEFAULT 'free'
            )
        """)
        
        # Trading sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trading_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_token TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        
        # Trades table - comprehensive trade tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL, -- LONG/SHORT
                entry_price REAL NOT NULL,
                exit_price REAL,
                position_size_usdt REAL NOT NULL,
                leverage INTEGER NOT NULL,
                stop_loss REAL,
                take_profit_1 REAL,
                take_profit_2 REAL,
                take_profit_3 REAL,
                
                -- Status tracking
                status TEXT DEFAULT 'open', -- open/closed/cancelled
                outcome TEXT, -- win/loss/breakeven
                closed_reason TEXT, -- tp1/tp2/tp3/sl/manual
                
                -- Performance metrics
                pnl_usdt REAL DEFAULT 0,
                pnl_percent REAL DEFAULT 0,
                roi_percent REAL DEFAULT 0, -- ROI on margin
                
                -- Risk metrics
                risk_reward_ratio REAL,
                safety_score INTEGER,
                margin_required REAL,
                liquidation_price REAL,
                
                -- Time tracking
                entry_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                exit_time TIMESTAMP,
                duration_minutes INTEGER,
                
                -- Market data
                timeframe TEXT,
                market_regime TEXT,
                volatility_level TEXT,
                
                -- Source tracking
                signal_source TEXT DEFAULT 'trading_insight',
                strategy_version TEXT DEFAULT '4.2.1',
                
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        
        # Daily performance summary
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date DATE NOT NULL,
                
                -- Trade counts
                total_trades INTEGER DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,
                losing_trades INTEGER DEFAULT 0,
                
                -- PnL metrics
                gross_pnl_usdt REAL DEFAULT 0,
                net_pnl_usdt REAL DEFAULT 0, -- after fees
                best_trade_pnl REAL DEFAULT 0,
                worst_trade_pnl REAL DEFAULT 0,
                
                -- Performance ratios
                win_rate REAL DEFAULT 0,
                profit_factor REAL DEFAULT 0,
                sharpe_ratio REAL DEFAULT 0,
                max_drawdown REAL DEFAULT 0,
                
                -- Risk metrics
                total_risk_taken REAL DEFAULT 0,
                avg_risk_per_trade REAL DEFAULT 0,
                max_leverage_used INTEGER DEFAULT 1,
                
                -- Portfolio value
                starting_balance REAL,
                ending_balance REAL,
                balance_change REAL DEFAULT 0,
                
                UNIQUE(user_id, date),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        
        # System performance tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                
                -- Signal quality metrics
                total_signals_generated INTEGER DEFAULT 0,
                signals_with_outcome INTEGER DEFAULT 0,
                avg_safety_score REAL DEFAULT 0,
                
                -- Outcome distribution
                sl_hits INTEGER DEFAULT 0,
                tp1_hits INTEGER DEFAULT 0,
                tp2_hits INTEGER DEFAULT 0,
                tp3_hits INTEGER DEFAULT 0,
                manual_closes INTEGER DEFAULT 0,
                
                -- Success rates by safety score
                safety_1_3_success_rate REAL DEFAULT 0,
                safety_4_6_success_rate REAL DEFAULT 0,
                safety_7_8_success_rate REAL DEFAULT 0,
                safety_9_10_success_rate REAL DEFAULT 0,
                
                -- Performance by timeframe
                h1_success_rate REAL DEFAULT 0,
                h4_success_rate REAL DEFAULT 0,
                d1_success_rate REAL DEFAULT 0,
                
                UNIQUE(date)
            )
        """)
        
        conn.commit()
        
        # Ensure schema migrations for outcome normalization
        self._ensure_column(cursor, 'trades', 'closed_reason', 'TEXT')
        self._migrate_trade_outcomes(cursor)
        
        conn.commit()
        conn.close()
    
    def get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)

    def _ensure_column(self, cursor, table: str, column: str, definition: str) -> None:
        """Add a column to the table if it does not exist."""
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in cursor.fetchall()]
        if column not in columns:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _migrate_trade_outcomes(self, cursor) -> None:
        """Normalize existing outcome data to the new schema (idempotent)."""
        cursor.execute("PRAGMA table_info(trades)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'closed_reason' not in columns:
            return

        # Populate closed_reason where missing based on legacy outcome values
        cursor.execute(
            """
            UPDATE trades
            SET closed_reason = CASE
                WHEN (closed_reason IS NULL OR closed_reason = '') AND outcome IN ('tp1_hit', 'tp1') THEN 'tp1'
                WHEN (closed_reason IS NULL OR closed_reason = '') AND outcome IN ('tp2_hit', 'tp2') THEN 'tp2'
                WHEN (closed_reason IS NULL OR closed_reason = '') AND outcome IN ('tp3_hit', 'tp3') THEN 'tp3'
                WHEN (closed_reason IS NULL OR closed_reason = '') AND outcome IN ('sl_hit', 'sl') THEN 'sl'
                WHEN (closed_reason IS NULL OR closed_reason = '') AND outcome IN ('manual_close', 'manual', 'breakeven') THEN 'manual'
                ELSE closed_reason
            END
            """
        )

        # Normalize outcome column to win/loss/breakeven taxonomy
        cursor.execute(
            """
            UPDATE trades
            SET outcome = CASE
                WHEN outcome IN ('tp1_hit', 'tp2_hit', 'tp3_hit', 'tp1', 'tp2', 'tp3') THEN 'win'
                WHEN outcome IN ('sl_hit', 'sl') THEN 'loss'
                WHEN outcome IN ('manual_close', 'manual', 'breakeven') THEN 'breakeven'
                ELSE outcome
            END
            """
        )


class UserAuth:
    def __init__(self, db: TradingAnalyticsDB):
        self.db = db
    
    def hash_password(self, password: str, salt: str = None) -> Tuple[str, str]:
        """Hash password with salt"""
        if not salt:
            salt = uuid.uuid4().hex
        
        password_hash = hashlib.pbkdf2_hmac('sha256', 
                                          password.encode('utf-8'), 
                                          salt.encode('utf-8'), 
                                          100000)
        return password_hash.hex(), salt
    
    def register_user(self, username: str, email: str, password: str) -> bool:
        """Register new user"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # Check if user exists
            cursor.execute("SELECT id FROM users WHERE username = ? OR email = ?", 
                         (username, email))
            if cursor.fetchone():
                return False, "User already exists"
            
            # Hash password
            password_hash, salt = self.hash_password(password)
            
            # Insert user
            cursor.execute("""
                INSERT INTO users (username, email, password_hash, salt)
                VALUES (?, ?, ?, ?)
            """, (username, email, password_hash, salt))
            
            conn.commit()
            conn.close()
            return True, "Registration successful"
            
        except Exception as e:
            return False, f"Registration failed: {str(e)}"
    
    def authenticate_user(self, username: str, password: str) -> Optional[Dict]:
        """Authenticate user and return user info"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, username, email, password_hash, salt, subscription_tier
                FROM users 
                WHERE username = ? AND is_active = 1
            """, (username,))
            
            user_data = cursor.fetchone()
            if not user_data:
                return None
            
            user_id, username, email, stored_hash, salt, tier = user_data
            
            # Verify password
            password_hash, _ = self.hash_password(password, salt)
            if password_hash != stored_hash:
                return None
            
            # Update last login
            cursor.execute("""
                UPDATE users SET last_login = CURRENT_TIMESTAMP 
                WHERE id = ?
            """, (user_id,))
            
            conn.commit()
            conn.close()
            
            return {
                'id': user_id,
                'username': username,
                'email': email,
                'subscription_tier': tier
            }
            
        except Exception as e:
            st.error(f"Authentication error: {str(e)}")
            return None
    
    def create_session(self, user_id: int) -> str:
        """Create authenticated session"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            session_token = uuid.uuid4().hex
            expires_at = datetime.now() + timedelta(hours=24)  # 24 hour sessions
            
            cursor.execute("""
                INSERT INTO trading_sessions (user_id, session_token, expires_at)
                VALUES (?, ?, ?)
            """, (user_id, session_token, expires_at))
            
            conn.commit()
            conn.close()
            
            return session_token
            
        except Exception as e:
            st.error(f"Session creation failed: {str(e)}")
            return None
    
    def validate_session(self, session_token: str) -> Optional[Dict]:
        """Validate session and return user info"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT u.id, u.username, u.email, u.subscription_tier
                FROM trading_sessions s
                JOIN users u ON s.user_id = u.id
                WHERE s.session_token = ? 
                AND s.is_active = 1 
                AND s.expires_at > CURRENT_TIMESTAMP
            """, (session_token,))
            
            user_data = cursor.fetchone()
            conn.close()
            
            if user_data:
                return {
                    'id': user_data[0],
                    'username': user_data[1],
                    'email': user_data[2],
                    'subscription_tier': user_data[3]
                }
            return None
            
        except Exception as e:
            st.error(f"Session validation failed: {str(e)}")
            return None


class TradeTracker:
    def __init__(self, db: TradingAnalyticsDB):
        self.db = db
    
    @staticmethod
    def _normalize_outcome_inputs(outcome: Optional[str], 
                                  closed_reason: Optional[str], 
                                  pnl_percent: float) -> Tuple[str, str]:
        """Map legacy outcome values into standardized fields."""

        outcome_val = (outcome or '').strip().lower()
        closed_val = (closed_reason or '').strip().lower()

        closed_aliases = {
            'tp1_hit': 'tp1',
            'tp_1': 'tp1',
            'take_profit_1': 'tp1',
            'tp1': 'tp1',
            'tp2_hit': 'tp2',
            'tp_2': 'tp2',
            'take_profit_2': 'tp2',
            'tp2': 'tp2',
            'tp3_hit': 'tp3',
            'tp_3': 'tp3',
            'take_profit_3': 'tp3',
            'tp3': 'tp3',
            'sl_hit': 'sl',
            'stop_loss': 'sl',
            'sl': 'sl',
            'manual_close': 'manual',
            'manual': 'manual',
            'breakeven': 'manual',
        }

        detailed_outcomes = {
            'tp1_hit': ('tp1', 'win'),
            'tp2_hit': ('tp2', 'win'),
            'tp3_hit': ('tp3', 'win'),
            'tp1': ('tp1', 'win'),
            'tp2': ('tp2', 'win'),
            'tp3': ('tp3', 'win'),
            'sl_hit': ('sl', 'loss'),
            'sl': ('sl', 'loss'),
            'stop_loss': ('sl', 'loss'),
            'manual_close': ('manual', 'breakeven'),
            'manual': ('manual', 'breakeven'),
            'breakeven': ('manual', 'breakeven'),
        }

        allowed_closed = {'tp1', 'tp2', 'tp3', 'sl', 'manual'}

        if closed_val in closed_aliases:
            closed_val = closed_aliases[closed_val]
        elif closed_val and closed_val not in allowed_closed:
            closed_val = ''

        outcome_category = None

        if outcome_val in detailed_outcomes:
            mapped_closed, mapped_outcome = detailed_outcomes[outcome_val]
            closed_val = closed_val or mapped_closed
            outcome_category = mapped_outcome
        elif outcome_val in {'win', 'loss', 'breakeven'}:
            outcome_category = outcome_val

        if outcome_category is None:
            if closed_val in {'tp1', 'tp2', 'tp3'}:
                outcome_category = 'win'
            elif closed_val == 'sl':
                outcome_category = 'loss'
            elif closed_val == 'manual':
                # Manual closes depend on realised PnL
                if pnl_percent > 0:
                    outcome_category = 'win'
                elif pnl_percent < 0:
                    outcome_category = 'loss'
                else:
                    outcome_category = 'breakeven'

        if outcome_category is None:
            if pnl_percent > 0:
                outcome_category = 'win'
            elif pnl_percent < 0:
                outcome_category = 'loss'
            else:
                outcome_category = 'breakeven'

        if not closed_val:
            if outcome_category == 'win':
                closed_val = 'tp1'
            elif outcome_category == 'loss':
                closed_val = 'sl'
            else:
                closed_val = 'manual'

        return outcome_category, closed_val
    
    def add_trade(self, user_id: int, trade_data: Dict) -> Optional[int]:
        """Add new trade to tracking and return trade id"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO trades (
                    user_id, symbol, direction, entry_price, position_size_usdt,
                    leverage, stop_loss, take_profit_1, take_profit_2, take_profit_3,
                    risk_reward_ratio, safety_score, margin_required, liquidation_price,
                    timeframe, market_regime, volatility_level, signal_source, strategy_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                trade_data.get('symbol'),
                trade_data.get('direction'),
                trade_data.get('entry_price'),
                trade_data.get('position_size_usdt'),
                trade_data.get('leverage'),
                trade_data.get('stop_loss'),
                trade_data.get('take_profit_1'),
                trade_data.get('take_profit_2'),
                trade_data.get('take_profit_3'),
                trade_data.get('risk_reward_ratio'),
                trade_data.get('safety_score'),
                trade_data.get('margin_required'),
                trade_data.get('liquidation_price'),
                trade_data.get('timeframe'),
                trade_data.get('market_regime'),
                trade_data.get('volatility_level'),
                trade_data.get('signal_source', 'trading_insight'),
                trade_data.get('strategy_version', '4.2.1')
            ))
            
            conn.commit()
            trade_id = cursor.lastrowid
            conn.close()
            return trade_id
            
        except Exception as e:
            st.error(f"Failed to add trade: {str(e)}")
            return None
    
    def update_trade_outcome(self, 
                             trade_id: int, 
                             exit_price: float, 
                             outcome: str, 
                             closed_reason: Optional[str] = None, 
                             exit_time: datetime = None) -> bool:
        """Update trade with exit information."""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            if not exit_time:
                exit_time = datetime.now()
            
            # Get trade data for PnL calculation
            cursor.execute("""
                SELECT entry_price, position_size_usdt, leverage, direction, entry_time
                FROM trades WHERE id = ?
            """, (trade_id,))
            
            trade_data = cursor.fetchone()
            if not trade_data:
                return False
            
            entry_price, size, leverage, direction, entry_time_str = trade_data
            
            # Calculate PnL
            if direction == 'LONG':
                price_change_pct = (exit_price - entry_price) / entry_price
            else:
                price_change_pct = (entry_price - exit_price) / entry_price
            
            pnl_percent = price_change_pct * 100
            roi_percent = pnl_percent * leverage  # ROI on margin
            pnl_usdt = (size / leverage) * (roi_percent / 100)  # PnL on margin
            
            # Calculate duration
            entry_dt = datetime.fromisoformat(entry_time_str.replace('Z', '+00:00'))
            duration_minutes = int((exit_time - entry_dt).total_seconds() / 60)
            
            outcome_category, normalized_reason = self._normalize_outcome_inputs(outcome, closed_reason, pnl_percent)

            # Update trade
            cursor.execute("""
                UPDATE trades SET
                    exit_price = ?, outcome = ?, closed_reason = ?, status = 'closed',
                    pnl_usdt = ?, pnl_percent = ?, roi_percent = ?,
                    exit_time = ?, duration_minutes = ?
                WHERE id = ?
            """, (exit_price, outcome_category, normalized_reason, pnl_usdt, pnl_percent, roi_percent, 
                  exit_time, duration_minutes, trade_id))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            st.error(f"Failed to update trade: {str(e)}")
            return False
    
    def get_user_trades(self, user_id: int, limit: int = 100, status: str = None) -> pd.DataFrame:
        """Get user's trade history"""
        try:
            conn = self.db.get_connection()
            
            query = "SELECT * FROM trades WHERE user_id = ?"
            params = [user_id]
            
            if status:
                query += " AND status = ?"
                params.append(status)
            
            query += " ORDER BY entry_time DESC LIMIT ?"
            params.append(limit)
            
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()
            
            return df
            
        except Exception as e:
            st.error(f"Failed to get trades: {str(e)}")
            return pd.DataFrame()


class AnalyticsDashboard:
    def __init__(self, db: TradingAnalyticsDB, trade_tracker: TradeTracker):
        self.db = db
        self.trade_tracker = trade_tracker
    
    def calculate_daily_stats(self, user_id: int, date: datetime.date) -> Dict:
        """Calculate daily performance statistics"""
        try:
            conn = self.db.get_connection()
            
            # Get trades for the day
            query = """
                SELECT * FROM trades 
                WHERE user_id = ? 
                AND DATE(entry_time) = ?
                AND status = 'closed'
            """
            
            trades_df = pd.read_sql_query(query, conn, params=[user_id, date])
            conn.close()
            
            if trades_df.empty:
                return {
                    'date': date,
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'win_rate': 0,
                    'gross_pnl_usdt': 0,
                    'best_trade': 0,
                    'worst_trade': 0,
                    'profit_factor': 0
                }
            
            # Calculate statistics
            total_trades = len(trades_df)
            winning_trades = len(trades_df[trades_df['pnl_usdt'] > 0])
            losing_trades = len(trades_df[trades_df['pnl_usdt'] < 0])
            
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            gross_pnl = trades_df['pnl_usdt'].sum()
            
            best_trade = trades_df['pnl_usdt'].max() if not trades_df.empty else 0
            worst_trade = trades_df['pnl_usdt'].min() if not trades_df.empty else 0
            
            # Profit factor
            gross_profit = trades_df[trades_df['pnl_usdt'] > 0]['pnl_usdt'].sum()
            gross_loss = abs(trades_df[trades_df['pnl_usdt'] < 0]['pnl_usdt'].sum())
            profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')
            
            return {
                'date': date,
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'win_rate': win_rate,
                'gross_pnl_usdt': gross_pnl,
                'best_trade': best_trade,
                'worst_trade': worst_trade,
                'profit_factor': profit_factor,
                'avg_trade_pnl': gross_pnl / total_trades if total_trades > 0 else 0
            }
            
        except Exception as e:
            st.error(f"Failed to calculate daily stats: {str(e)}")
            return {}
    
    def get_monthly_performance(self, user_id: int, year: int, month: int) -> pd.DataFrame:
        """Get monthly performance breakdown"""
        try:
            conn = self.db.get_connection()
            
            query = """
                SELECT 
                    DATE(entry_time) as trade_date,
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END) as winning_trades,
                    SUM(pnl_usdt) as daily_pnl,
                    AVG(pnl_usdt) as avg_trade_pnl,
                    MAX(pnl_usdt) as best_trade,
                    MIN(pnl_usdt) as worst_trade
                FROM trades 
                WHERE user_id = ? 
                AND strftime('%Y', entry_time) = ?
                AND strftime('%m', entry_time) = ?
                AND status = 'closed'
                GROUP BY DATE(entry_time)
                ORDER BY trade_date
            """
            
            df = pd.read_sql_query(query, conn, params=[
                user_id, str(year), f"{month:02d}"
            ])
            conn.close()
            
            # Calculate win rate
            if not df.empty:
                df['win_rate'] = (df['winning_trades'] / df['total_trades'] * 100).round(1)
                df['cumulative_pnl'] = df['daily_pnl'].cumsum()
            
            return df
            
        except Exception as e:
            st.error(f"Failed to get monthly performance: {str(e)}")
            return pd.DataFrame()
    
    def get_sl_tp_statistics(self, user_id: int = None, days: int = 30) -> Dict:
        """Get SL/TP hit statistics for success rate calculation"""
        try:
            conn = self.db.get_connection()
            
            # Build query
            if user_id:
                query = """
                    SELECT 
                        outcome,
                        closed_reason,
                        safety_score,
                        timeframe,
                        COUNT(*) as count
                    FROM trades 
                    WHERE user_id = ?
                    AND entry_time >= date('now', '-{} days')
                    AND status = 'closed'
                    AND outcome IS NOT NULL
                    GROUP BY outcome, closed_reason, safety_score, timeframe
                """.format(days)
                params = [user_id]
            else:
                query = """
                    SELECT 
                        outcome,
                        closed_reason,
                        safety_score,
                        timeframe,
                        COUNT(*) as count
                    FROM trades 
                    WHERE entry_time >= date('now', '-{} days')
                    AND status = 'closed'
                    AND outcome IS NOT NULL
                    GROUP BY outcome, closed_reason, safety_score, timeframe
                """.format(days)
                params = []
            
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()
            
            if df.empty:
                return {
                    'total_closed_trades': 0,
                    'sl_hits': 0,
                    'tp_hits': 0,
                    'success_rate': 0,
                    'by_safety_score': {},
                    'by_timeframe': {}
                }
            
            # Calculate overall statistics
            total_trades = df['count'].sum()
            sl_hits = df[df['closed_reason'] == 'sl']['count'].sum()
            tp_hits = df[df['closed_reason'].isin(['tp1', 'tp2', 'tp3'])]['count'].sum()
            
            success_rate = (tp_hits / total_trades * 100) if total_trades > 0 else 0
            
            # Success rate by safety score
            safety_stats = {}
            for score in range(1, 11):
                score_trades = df[df['safety_score'] == score]['count'].sum()
                score_tp = df[(df['safety_score'] == score) & 
                              (df['outcome'] == 'win')]['count'].sum()
                
                if score_trades > 0:
                    safety_stats[score] = {
                        'trades': score_trades,
                        'success_rate': (score_tp / score_trades * 100)
                    }
            
            # Success rate by timeframe
            timeframe_stats = {}
            for tf in df['timeframe'].unique():
                if pd.isna(tf):
                    continue
                tf_trades = df[df['timeframe'] == tf]['count'].sum()
                tf_tp = df[(df['timeframe'] == tf) & (df['outcome'] == 'win')]['count'].sum()
                
                timeframe_stats[tf] = {
                    'trades': tf_trades,
                    'success_rate': (tf_tp / tf_trades * 100) if tf_trades > 0 else 0
                }
            
            return {
                'total_closed_trades': total_trades,
                'sl_hits': sl_hits,
                'tp_hits': tp_hits,
                'success_rate': success_rate,
                'by_safety_score': safety_stats,
                'by_timeframe': timeframe_stats
            }
            
        except Exception as e:
            st.error(f"Failed to get SL/TP statistics: {str(e)}")
            return {}


# Initialize global components
@st.cache_resource
def init_analytics_system():
    """Initialize the analytics system"""
    db = TradingAnalyticsDB()
    auth = UserAuth(db)
    trade_tracker = TradeTracker(db)
    dashboard = AnalyticsDashboard(db, trade_tracker)
    
    return db, auth, trade_tracker, dashboard

# Get components
db, auth, trade_tracker, dashboard = init_analytics_system()
