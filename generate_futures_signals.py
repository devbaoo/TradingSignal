#!/usr/bin/env python3
"""
Real Futures Trading Signal Generator
Tạo signal giao dịch futures thực tế với đầy đủ thông số
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
from pathlib import Path

# Technical Analysis
import ta
import talib

def load_market_data(symbol="BTC/USDT", timeframe="1h"):
    """Load real market data từ cache"""
    symbol_file = symbol.replace('/', '_')
    cache_file = f"data/cache/{symbol_file}_{timeframe}_binance_20230927_20250926.csv"
    
    if os.path.exists(cache_file):
        print(f"📊 Loading {symbol} data...")
        df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
        print(f"   ✅ {len(df)} candles loaded")
        print(f"   📅 Range: {df.index[0].strftime('%Y-%m-%d')} to {df.index[-1].strftime('%Y-%m-%d')}")
        return df
    else:
        print(f"❌ No data found for {symbol}")
        return None

def calculate_advanced_indicators(df):
    """Tính toán đầy đủ các chỉ báo kỹ thuật"""
    
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
    df['bb_squeeze'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle'] < 0.1
    
    # ATR for volatility
    df['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range()
    df['atr_percent'] = (df['atr'] / df['close']) * 100
    
    # Stochastic
    stoch = ta.momentum.StochasticOscillator(df['high'], df['low'], df['close'])
    df['stoch_k'] = stoch.stoch()
    df['stoch_d'] = stoch.stoch_signal()
    
    # Volume analysis (if available)
    if 'volume' in df.columns:
        df['volume_sma'] = df['volume'].rolling(20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_sma']
        df['on_balance_volume'] = ta.volume.OnBalanceVolumeIndicator(df['close'], df['volume']).on_balance_volume()
    
    # Support and Resistance levels
    df['resistance'] = df['high'].rolling(20, center=True).max()
    df['support'] = df['low'].rolling(20, center=True).min()
    
    # Trend strength
    df['trend_strength'] = (df['close'] - df['ema_200']) / df['ema_200'] * 100
    
    return df

def analyze_market_structure(df):
    """Phân tích cấu trúc thị trường chi tiết"""
    current = df.iloc[-1]
    prev = df.iloc[-2]
    
    analysis = {
        'current_price': current['close'],
        'trend': 'NEUTRAL',
        'trend_strength': 0,
        'momentum': 'NEUTRAL', 
        'volatility': 'NORMAL',
        'market_phase': 'CONSOLIDATION',
        'signals': [],
        'strength_score': 5.0,
        'risk_level': 'MEDIUM'
    }
    
    # === TREND ANALYSIS ===
    if current['close'] > current['ema_200'] and current['ema_12'] > current['ema_26']:
        if current['close'] > current['sma_50'] > current['sma_20']:
            analysis['trend'] = 'STRONG_BULLISH'
            analysis['trend_strength'] = 3
            analysis['market_phase'] = 'UPTREND'
        else:
            analysis['trend'] = 'BULLISH'
            analysis['trend_strength'] = 2
    elif current['close'] < current['ema_200'] and current['ema_12'] < current['ema_26']:
        if current['close'] < current['sma_50'] < current['sma_20']:
            analysis['trend'] = 'STRONG_BEARISH'
            analysis['trend_strength'] = -3
            analysis['market_phase'] = 'DOWNTREND'
        else:
            analysis['trend'] = 'BEARISH'
            analysis['trend_strength'] = -2
    
    # === MOMENTUM ANALYSIS ===
    # MACD signals
    if current['macd'] > current['macd_signal'] and prev['macd'] <= prev['macd_signal']:
        analysis['signals'].append('MACD_BULLISH_CROSSOVER')
        analysis['strength_score'] += 1.5
    elif current['macd'] < current['macd_signal'] and prev['macd'] >= prev['macd_signal']:
        analysis['signals'].append('MACD_BEARISH_CROSSOVER')
        analysis['strength_score'] -= 1.5
    
    # RSI analysis
    if current['rsi'] > 70:
        analysis['momentum'] = 'OVERBOUGHT'
        analysis['signals'].append('RSI_OVERBOUGHT')
        analysis['strength_score'] -= 1
    elif current['rsi'] < 30:
        analysis['momentum'] = 'OVERSOLD'  
        analysis['signals'].append('RSI_OVERSOLD')
        analysis['strength_score'] += 1.5
    elif 40 <= current['rsi'] <= 60:
        analysis['momentum'] = 'NEUTRAL'
    
    # Stochastic confirmation
    if current['stoch_k'] < 20 and current['stoch_d'] < 20:
        analysis['signals'].append('STOCH_OVERSOLD')
        analysis['strength_score'] += 0.5
    elif current['stoch_k'] > 80 and current['stoch_d'] > 80:
        analysis['signals'].append('STOCH_OVERBOUGHT')
        analysis['strength_score'] -= 0.5
    
    # === VOLATILITY ANALYSIS ===
    avg_atr = df['atr_percent'].rolling(50).mean().iloc[-1]
    if current['atr_percent'] > avg_atr * 1.5:
        analysis['volatility'] = 'HIGH'
        analysis['risk_level'] = 'HIGH'
    elif current['atr_percent'] < avg_atr * 0.7:
        analysis['volatility'] = 'LOW'
        analysis['risk_level'] = 'LOW'
    
    # === SUPPORT/RESISTANCE ===
    if abs(current['close'] - current['support']) / current['close'] < 0.02:
        analysis['signals'].append('NEAR_SUPPORT')
        analysis['strength_score'] += 0.5
    if abs(current['close'] - current['resistance']) / current['close'] < 0.02:
        analysis['signals'].append('NEAR_RESISTANCE')
        analysis['strength_score'] -= 0.5
    
    # Final strength normalization
    analysis['strength_score'] = max(0, min(10, analysis['strength_score']))
    
    return analysis

def generate_trading_signal(symbol="BTC/USDT", timeframe="1h", balance=10000):
    """Tạo signal futures trading hoàn chỉnh"""
    
    print(f"\n🚨 GENERATING REAL FUTURES TRADING SIGNAL")
    print(f"{'='*60}")
    print(f"📈 Symbol: {symbol}")
    print(f"⏰ Timeframe: {timeframe}")  
    print(f"💰 Account Balance: ${balance:,.2f}")
    print(f"🕐 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Load and analyze data
    df = load_market_data(symbol, timeframe)
    if df is None:
        return None
    
    df = calculate_advanced_indicators(df)
    market = analyze_market_structure(df)
    current_data = df.iloc[-1]
    
    print(f"\n📊 ADVANCED MARKET ANALYSIS")
    print(f"{'─'*60}")
    print(f"💵 Current Price: ${market['current_price']:,.2f}")
    print(f"📈 Trend: {market['trend']} (Strength: {market['trend_strength']}/3)")
    print(f"⚡ Momentum: {market['momentum']}")
    print(f"🌊 Volatility: {market['volatility']}")
    print(f"📊 RSI: {current_data['rsi']:.1f}")
    print(f"📈 MACD: {current_data['macd']:.2f}")
    print(f"🎯 Signals: {', '.join(market['signals']) if market['signals'] else 'None'}")
    print(f"💪 Market Strength: {market['strength_score']:.1f}/10")
    
    # === SIGNAL DECISION LOGIC ===
    signal_direction = None
    confidence = "LOW"
    safety_score = 5
    
    # LONG Signal Conditions
    if (market['trend_strength'] >= 2 and
        market['strength_score'] >= 6.5 and
        current_data['rsi'] < 65 and
        current_data['close'] > current_data['bb_lower'] and
        'MACD_BULLISH_CROSSOVER' in market['signals']):
        
        signal_direction = "LONG"
        safety_score = min(9, int(market['strength_score']))
        confidence = "HIGH" if market['strength_score'] >= 8 else "MEDIUM"
        
    # SHORT Signal Conditions  
    elif (market['trend_strength'] <= -2 and
          market['strength_score'] <= 3.5 and
          current_data['rsi'] > 35 and
          current_data['close'] < current_data['bb_upper'] and
          'MACD_BEARISH_CROSSOVER' in market['signals']):
        
        signal_direction = "SHORT"
        safety_score = min(9, int(10 - market['strength_score']))
        confidence = "HIGH" if market['strength_score'] <= 2 else "MEDIUM"
    
    # Alternative entry conditions (less strict)
    elif market['momentum'] == 'OVERSOLD' and market['trend_strength'] >= 0:
        signal_direction = "LONG"
        safety_score = 6
        confidence = "MEDIUM"
    elif market['momentum'] == 'OVERBOUGHT' and market['trend_strength'] <= 0:
        signal_direction = "SHORT" 
        safety_score = 6
        confidence = "MEDIUM"
    
    if not signal_direction:
        print(f"\n❌ NO CLEAR TRADING SIGNAL")
        print(f"Market conditions not optimal for entry")
        print(f"Recommendation: Wait for better setup")
        print(f"Check again in 2-4 hours...")
        return None
    
    # === CALCULATE ENTRY, SL, TP ===
    entry_price = market['current_price']
    atr = current_data['atr']
    
    # Dynamic ATR multipliers based on volatility
    if market['volatility'] == 'HIGH':
        sl_multiplier = 2.5
        tp1_multiplier = 3.0
    elif market['volatility'] == 'LOW':
        sl_multiplier = 1.5
        tp1_multiplier = 2.0
    else:
        sl_multiplier = 2.0
        tp1_multiplier = 2.5
    
    if signal_direction == "LONG":
        stop_loss = entry_price - (atr * sl_multiplier)
        take_profit_1 = entry_price + (atr * tp1_multiplier)
        take_profit_2 = entry_price + (atr * tp1_multiplier * 1.8)
        take_profit_3 = entry_price + (atr * tp1_multiplier * 2.5)
    else:  # SHORT
        stop_loss = entry_price + (atr * sl_multiplier)
        take_profit_1 = entry_price - (atr * tp1_multiplier)
        take_profit_2 = entry_price - (atr * tp1_multiplier * 1.8)
        take_profit_3 = entry_price - (atr * tp1_multiplier * 2.5)
    
    # === POSITION SIZING & RISK MANAGEMENT ===
    base_risk = 0.02  # 2% base risk
    
    # Adjust risk based on safety score
    if safety_score >= 8:
        risk_percent = 0.025  # 2.5% for very safe trades
        max_leverage = 5
    elif safety_score >= 6:
        risk_percent = 0.02   # 2% for safe trades
        max_leverage = 3
    else:
        risk_percent = 0.015  # 1.5% for risky trades
        max_leverage = 2
    
    risk_amount = balance * risk_percent
    price_risk = abs(entry_price - stop_loss)
    position_size_usdt = risk_amount / (price_risk / entry_price)
    position_size_percent = (position_size_usdt / balance) * 100
    
    # Leverage calculation
    risk_reward = abs(take_profit_1 - entry_price) / abs(entry_price - stop_loss)
    
    if confidence == "HIGH" and safety_score >= 7:
        leverage = min(max_leverage, 3)
    elif confidence == "MEDIUM" and safety_score >= 6:
        leverage = min(max_leverage, 2)
    else:
        leverage = 1
    
    # Risk level assessment
    if safety_score >= 8:
        risk_level = "CONSERVATIVE"
    elif safety_score >= 6:
        risk_level = "MODERATE"
    else:
        risk_level = "AGGRESSIVE"
    
    # === CREATE SIGNAL OBJECT ===
    signal = {
        'timestamp': datetime.now().isoformat(),
        'symbol': symbol,
        'timeframe': timeframe,
        'direction': signal_direction,
        'strategy': 'AdvancedTechnicalAnalysis',
        
        # Market Analysis
        'market_trend': market['trend'],
        'trend_strength': market['trend_strength'],
        'momentum_state': market['momentum'],
        'volatility_level': market['volatility'],
        'market_strength': round(market['strength_score'], 1),
        'detected_signals': market['signals'],
        
        # Technical Indicators
        'current_rsi': round(current_data['rsi'], 1),
        'current_macd': round(current_data['macd'], 2),
        'macd_signal': round(current_data['macd_signal'], 2),
        'bb_position': round((current_data['close'] - current_data['bb_lower']) / (current_data['bb_upper'] - current_data['bb_lower']) * 100, 1),
        
        # Entry Parameters
        'entry_price': round(entry_price, 2),
        'entry_range': [round(entry_price * 0.9995, 2), round(entry_price * 1.0005, 2)],
        
        # Risk Management
        'stop_loss': round(stop_loss, 2),
        'take_profit': [
            round(take_profit_1, 2),
            round(take_profit_2, 2), 
            round(take_profit_3, 2)
        ],
        
        # Position & Leverage
        'position_size_usdt': round(position_size_usdt, 2),
        'position_size_percent': round(position_size_percent, 1),
        'recommended_leverage': leverage,
        'max_leverage': max_leverage,
        'risk_per_trade': round(risk_percent * 100, 1),
        
        # Safety & Confidence
        'safety_score': safety_score,
        'confidence_level': confidence,
        'risk_level': risk_level,
        'risk_reward_ratio': round(risk_reward, 2),
        
        # Technical Data
        'atr': round(atr, 2),
        'atr_percent': round(current_data['atr_percent'], 2),
        'volatility_rank': market['volatility']
    }
    
    # === DISPLAY SIGNAL ===
    print(f"\n🎯 REAL FUTURES TRADING SIGNAL")
    print(f"{'='*60}")
    print(f"🚨 DIRECTION: {signal['direction']}")
    print(f"💰 Entry Price: ${signal['entry_price']:,.2f}")
    print(f"🛑 Stop Loss: ${signal['stop_loss']:,.2f}")
    print(f"🎯 Take Profit 1: ${signal['take_profit'][0]:,.2f} (30%)")
    print(f"🎯 Take Profit 2: ${signal['take_profit'][1]:,.2f} (40%)")
    print(f"🎯 Take Profit 3: ${signal['take_profit'][2]:,.2f} (30%)")
    
    print(f"\n📊 POSITION & LEVERAGE")
    print(f"{'─'*40}")
    print(f"📈 Recommended Leverage: {signal['recommended_leverage']}x (Max: {signal['max_leverage']}x)")
    print(f"💵 Position Size: ${signal['position_size_usdt']:,.2f}")
    print(f"📊 Position %: {signal['position_size_percent']:.1f}% of account")
    print(f"⚖️ Risk per Trade: {signal['risk_per_trade']:.1f}%")
    print(f"📈 Risk/Reward: 1:{signal['risk_reward_ratio']:.1f}")
    
    print(f"\n🛡️ SAFETY ASSESSMENT")
    print(f"{'─'*40}")
    print(f"🔒 Safety Score: {signal['safety_score']}/10")
    print(f"💪 Confidence: {signal['confidence_level']}")
    print(f"⚠️ Risk Level: {signal['risk_level']}")
    print(f"💎 Market Strength: {signal['market_strength']}/10")
    
    print(f"\n📋 FUTURES EXCHANGE PARAMETERS")
    print(f"{'='*60}")
    print(f"Symbol: {symbol}")
    print(f"Side: {signal['direction']} ({'BUY' if signal['direction'] == 'LONG' else 'SELL'})")
    print(f"Order Type: MARKET (or LIMIT at ${signal['entry_price']:,.2f})")
    print(f"Leverage: {signal['recommended_leverage']}x")
    print(f"Position Size: {signal['position_size_percent']:.1f}% of balance")
    print(f"Stop Loss: ${signal['stop_loss']:,.2f}")
    print(f"Take Profit: ${signal['take_profit'][0]:,.2f}")
    
    print(f"\n💡 EXECUTION PLAN")
    print(f"{'─'*40}")
    print(f"1. Set leverage to {signal['recommended_leverage']}x")
    print(f"2. Place {signal['direction']} order at ${signal['entry_price']:,.2f}")
    print(f"3. Set stop loss at ${signal['stop_loss']:,.2f}")
    print(f"4. Set TP1 at ${signal['take_profit'][0]:,.2f} (close 30%)")
    print(f"5. Set TP2 at ${signal['take_profit'][1]:,.2f} (close 40%)")
    print(f"6. Set TP3 at ${signal['take_profit'][2]:,.2f} (close 30%)")
    print(f"7. Monitor closely for first 2-4 hours")
    
    # Calculate potential P&L
    pnl_tp1 = ((signal['take_profit'][0] - signal['entry_price']) / signal['entry_price'] * 100) if signal['direction'] == 'LONG' else ((signal['entry_price'] - signal['take_profit'][0]) / signal['entry_price'] * 100)
    pnl_sl = ((signal['entry_price'] - signal['stop_loss']) / signal['entry_price'] * 100) if signal['direction'] == 'LONG' else ((signal['stop_loss'] - signal['entry_price']) / signal['entry_price'] * 100)
    
    print(f"\n💰 PROFIT/LOSS PROJECTIONS")
    print(f"{'─'*40}")
    print(f"📈 Potential Profit (TP1): +{pnl_tp1:.1f}%")
    print(f"📉 Potential Loss (SL): -{pnl_sl:.1f}%")
    print(f"💵 Max Risk: ${balance * risk_percent:,.2f}")
    print(f"💵 Potential Reward: ${balance * risk_percent * risk_reward:,.2f}")
    
    return signal

if __name__ == "__main__":
    print("🚀 REAL FUTURES TRADING SIGNAL GENERATOR")
    print("="*60)
    
    # Symbols to analyze
    symbols = ["BTC/USDT", "ETH/USDT"]
    generated_signals = []
    
    for symbol in symbols:
        print(f"\n{'#'*60}")
        print(f"🔍 ANALYZING {symbol}")
        print(f"{'#'*60}")
        
        signal = generate_trading_signal(symbol, "1h", 10000)
        
        if signal:
            generated_signals.append(signal)
            
            # Save signal to file
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"trading_signals/futures_signal_{symbol.replace('/', '_')}_{timestamp}.json"
            
            os.makedirs('trading_signals', exist_ok=True)
            with open(filename, 'w') as f:
                json.dump(signal, f, indent=2)
            
            print(f"\n💾 Signal saved: {filename}")
        
        print(f"\n{'─'*60}")
    
    # Summary
    if generated_signals:
        print(f"\n🎉 SIGNAL GENERATION COMPLETE!")
        print(f"{'='*60}")
        print(f"✅ Generated {len(generated_signals)} real trading signals:")
        
        for i, signal in enumerate(generated_signals, 1):
            print(f"{i}. {signal['symbol']} {signal['direction']} - Safety: {signal['safety_score']}/10 - Confidence: {signal['confidence_level']}")
            
        print(f"\n🎯 READY FOR FUTURES TRADING!")
        print(f"📋 Copy the parameters to your futures exchange")
        print(f"⚠️ Remember: Never risk more than you can afford to lose")
        
    else:
        print(f"\n⏳ NO SIGNALS GENERATED")
        print(f"Current market conditions not optimal")
        print(f"🔄 Try again in 2-4 hours or use different timeframes")
        print(f"💡 Consider 4h or 1d timeframes for better signals")