#!/usr/bin/env python3
"""
Analytics Demo Data Generator
Create sample trading data for testing the analytics system
Version 1.0.0 - September 27, 2025
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from trading_analytics import db, auth, trade_tracker
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random

def create_demo_user():
    """Create a demo user account"""
    print("Creating demo user account...")
    
    success, message = auth.register_user(
        username="demo_trader",
        email="demo@tradinginsight.com", 
        password="demo123456"
    )
    
    if success:
        print("✅ Demo user created successfully!")
        
        # Authenticate to get user ID
        user_info = auth.authenticate_user("demo_trader", "demo123456")
        return user_info['id']
    else:
        print(f"❌ {message}")
        
        # Try to authenticate existing user
        user_info = auth.authenticate_user("demo_trader", "demo123456")
        if user_info:
            print("✅ Using existing demo user")
            return user_info['id']
        
        return None

def generate_sample_trades(user_id, num_days=30, trades_per_day_range=(2, 8)):
    """Generate realistic sample trading data"""
    print(f"Generating sample trades for {num_days} days...")
    
    # Common futures symbols
    symbols = [
        'BTCUSDT', 'ETHUSDT', 'ADAUSDT', 'DOTUSDT', 'LINKUSDT',
        'BNBUSDT', 'XRPUSDT', 'LTCUSDT', 'BCHUSDT', 'EOSUSDT',
        'TRXUSDT', 'ETCUSDT', 'XLMUSDT', 'ATOMUSDT', 'XMRUSDT'
    ]
    
    # Price ranges for symbols (approximate)
    price_ranges = {
        'BTCUSDT': (25000, 35000),
        'ETHUSDT': (1500, 2500),
        'ADAUSDT': (0.25, 0.45),
        'DOTUSDT': (4, 8),
        'LINKUSDT': (6, 12),
        'BNBUSDT': (200, 350),
        'XRPUSDT': (0.4, 0.7),
        'LTCUSDT': (60, 100),
        'BCHUSDT': (100, 200),
        'EOSUSDT': (0.8, 1.5),
        'TRXUSDT': (0.05, 0.12),
        'ETCUSDT': (15, 30),
        'XLMUSDT': (0.08, 0.15),
        'ATOMUSDT': (7, 15),
        'XMRUSDT': (120, 180)
    }
    
    timeframes = ['1h', '4h', '1d']
    directions = ['LONG', 'SHORT']
    market_regimes = ['bull_strong', 'bull_weak', 'bear_strong', 'bear_weak', 'sideways']
    volatility_levels = ['low', 'medium', 'high']
    outcomes = ['sl_hit', 'tp1_hit', 'tp2_hit', 'tp3_hit', 'manual_close']
    
    trades_created = 0
    
    for day_offset in range(num_days):
        trade_date = datetime.now() - timedelta(days=day_offset)
        num_trades = random.randint(*trades_per_day_range)
        
        for trade_num in range(num_trades):
            # Random trade parameters
            symbol = random.choice(symbols)
            direction = random.choice(directions)
            timeframe = random.choice(timeframes)
            leverage = random.choice([1, 2, 3, 5, 10])
            safety_score = random.randint(1, 10)
            
            # Price generation
            price_range = price_ranges.get(symbol, (1, 100))
            base_price = random.uniform(*price_range)
            entry_price = round(base_price * random.uniform(0.98, 1.02), 6)
            
            # Position size based on leverage and safety
            base_size = random.uniform(50, 500)  # USDT
            position_size = base_size * (1 + (leverage - 1) * 0.1)
            
            # Stop loss and take profits
            if direction == 'LONG':
                stop_loss = entry_price * random.uniform(0.97, 0.99)
                tp1 = entry_price * random.uniform(1.01, 1.03)
                tp2 = entry_price * random.uniform(1.03, 1.06)
                tp3 = entry_price * random.uniform(1.06, 1.10)
            else:
                stop_loss = entry_price * random.uniform(1.01, 1.03)
                tp1 = entry_price * random.uniform(0.97, 0.99)
                tp2 = entry_price * random.uniform(0.94, 0.97)
                tp3 = entry_price * random.uniform(0.90, 0.94)
            
            # Risk reward ratio
            if direction == 'LONG':
                risk = entry_price - stop_loss
                reward = tp1 - entry_price
            else:
                risk = stop_loss - entry_price
                reward = entry_price - tp1
            
            rr_ratio = reward / risk if risk > 0 else 1.0
            
            # Margin and liquidation
            margin_required = position_size / leverage
            if direction == 'LONG':
                liq_price = entry_price * (1 - 0.8/leverage)  # Approximate
            else:
                liq_price = entry_price * (1 + 0.8/leverage)
            
            # Create trade data
            trade_data = {
                'symbol': symbol,
                'direction': direction,
                'entry_price': entry_price,
                'position_size_usdt': position_size,
                'leverage': leverage,
                'stop_loss': stop_loss,
                'take_profit_1': tp1,
                'take_profit_2': tp2,
                'take_profit_3': tp3,
                'risk_reward_ratio': rr_ratio,
                'safety_score': safety_score,
                'margin_required': margin_required,
                'liquidation_price': liq_price,
                'timeframe': timeframe,
                'market_regime': random.choice(market_regimes),
                'volatility_level': random.choice(volatility_levels),
                'signal_source': 'trading_insight',
                'strategy_version': '4.2.1'
            }
            
            # Add trade
            success = trade_tracker.add_trade(user_id, trade_data)
            if success:
                trades_created += 1
                
                # For closed trades, add outcome
                if random.random() < 0.7:  # 70% of trades are closed
                    # Get the trade ID (simplified - in production you'd track this better)
                    conn = db.get_connection()
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT id FROM trades 
                        WHERE user_id = ? AND symbol = ? AND entry_price = ?
                        ORDER BY entry_time DESC LIMIT 1
                    """, (user_id, symbol, entry_price))
                    
                    trade_row = cursor.fetchone()
                    if trade_row:
                        trade_id = trade_row[0]
                        
                        # Determine outcome based on safety score (higher score = better success rate)
                        success_probability = (safety_score / 10) * 0.8 + 0.1  # 10%-90% based on safety
                        
                        if random.random() < success_probability:
                            # Successful trade
                            outcome = random.choices(
                                ['tp1_hit', 'tp2_hit', 'tp3_hit'],
                                weights=[0.5, 0.3, 0.2]
                            )[0]
                            
                            if outcome == 'tp1_hit':
                                exit_price = tp1
                            elif outcome == 'tp2_hit':
                                exit_price = tp2
                            else:
                                exit_price = tp3
                        else:
                            # Failed trade
                            outcome = 'sl_hit'
                            exit_price = stop_loss
                        
                        # Random exit time (few hours to few days later)
                        exit_time = trade_date + timedelta(
                            hours=random.randint(1, 72)
                        )
                        
                        trade_tracker.update_trade_outcome(
                            trade_id, exit_price, outcome, exit_time
                        )
                    
                    conn.close()
    
    print(f"✅ Created {trades_created} sample trades!")
    return trades_created

def show_demo_stats(user_id):
    """Show statistics for the demo data"""
    print("\n📊 Demo Data Statistics:")
    
    # Get all trades
    trades_df = trade_tracker.get_user_trades(user_id, limit=1000)
    
    if not trades_df.empty:
        total_trades = len(trades_df)
        open_trades = len(trades_df[trades_df['status'] == 'open'])
        closed_trades = len(trades_df[trades_df['status'] == 'closed'])
        
        print(f"Total Trades: {total_trades}")
        print(f"Open Trades: {open_trades}")
        print(f"Closed Trades: {closed_trades}")
        
        if closed_trades > 0:
            closed_df = trades_df[trades_df['status'] == 'closed']
            total_pnl = closed_df['pnl_usdt'].sum()
            winning_trades = len(closed_df[closed_df['pnl_usdt'] > 0])
            win_rate = winning_trades / closed_trades * 100
            
            print(f"Win Rate: {win_rate:.1f}%")
            print(f"Total P&L: ${total_pnl:.2f}")
            print(f"Best Trade: ${closed_df['pnl_usdt'].max():.2f}")
            print(f"Worst Trade: ${closed_df['pnl_usdt'].min():.2f}")
            
            # Outcome distribution
            outcomes = closed_df['outcome'].value_counts()
            print(f"\nOutcome Distribution:")
            for outcome, count in outcomes.items():
                print(f"  {outcome}: {count} ({count/closed_trades*100:.1f}%)")

def main():
    """Main demo data generation"""
    print("🚀 Trading Analytics Demo Data Generator")
    print("=" * 50)
    
    # Create demo user
    user_id = create_demo_user()
    if not user_id:
        print("❌ Failed to create/find demo user")
        return
    
    # Generate sample trades
    num_days = 45  # More data for better analytics
    trades_created = generate_sample_trades(user_id, num_days)
    
    if trades_created > 0:
        # Show statistics
        show_demo_stats(user_id)
        
        print("\n✅ Demo data generation complete!")
        print("\nTo test the analytics system:")
        print("1. Run: streamlit run src/analytics_gui.py --server.port 8502")
        print("2. Login with: demo_trader / demo123456")
        print("3. Explore the analytics dashboard!")
    else:
        print("❌ No demo data was created")

if __name__ == "__main__":
    main()