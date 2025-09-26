#!/usr/bin/env python3
"""
Real-Time Data Fetcher
Fetch real market data từ Binance API (free, không cần key)
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import time
import os

class RealTimeDataFetcher:
    def __init__(self):
        self.base_url = "https://api.binance.com/api/v3"
        self.symbols_map = {
            "BTC/USDT": "BTCUSDT",
            "ETH/USDT": "ETHUSDT", 
            "BNB/USDT": "BNBUSDT",
            "ADA/USDT": "ADAUSDT",
            "XRP/USDT": "XRPUSDT",
            "SOL/USDT": "SOLUSDT",
            "DOT/USDT": "DOTUSDT",
            "DOGE/USDT": "DOGEUSDT",
            "AVAX/USDT": "AVAXUSDT",
            "MATIC/USDT": "MATICUSDT",
            "LINK/USDT": "LINKUSDT",
            "UNI/USDT": "UNIUSDT",
            "LTC/USDT": "LTCUSDT",
            "BCH/USDT": "BCHUSDT",
            "ATOM/USDT": "ATOMUSDT",
            "FTM/USDT": "FTMUSDT",
            "ALGO/USDT": "ALGOUSDT",
            "VET/USDT": "VETUSDT",
            "ICP/USDT": "ICPUSDT",
            "NEAR/USDT": "NEARUSDT"
        }
        
        # Timeframe mapping
        self.timeframe_map = {
            "1h": "1h",
            "4h": "4h", 
            "1d": "1d"
        }
        
    def get_current_prices(self):
        """Get real-time prices từ Binance API"""
        try:
            url = f"{self.base_url}/ticker/price"
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
            print(f"❌ Error fetching current prices: {e}")
            return self._get_fallback_prices()
    
    def _get_fallback_prices(self):
        """Fallback prices nếu API không available"""
        print("📡 Using fallback prices...")
        return {
            "BTC/USDT": 67500.0,
            "ETH/USDT": 2600.0,
            "BNB/USDT": 580.0,
            "ADA/USDT": 0.45,
            "XRP/USDT": 0.58,
            "SOL/USDT": 145.0,
            "DOT/USDT": 5.8,
            "DOGE/USDT": 0.15,
            "AVAX/USDT": 28.5,
            "MATIC/USDT": 0.48,
            "LINK/USDT": 14.2,
            "UNI/USDT": 8.5,
            "LTC/USDT": 85.0,
            "BCH/USDT": 380.0,
            "ATOM/USDT": 6.2,
            "FTM/USDT": 0.32,
            "ALGO/USDT": 0.18,
            "VET/USDT": 0.028,
            "ICP/USDT": 8.5,
            "NEAR/USDT": 3.8
        }
    
    def get_klines(self, symbol, timeframe="1h", limit=500):
        """Get real OHLCV data từ Binance"""
        try:
            binance_symbol = self.symbols_map.get(symbol)
            if not binance_symbol:
                return None
                
            binance_timeframe = self.timeframe_map.get(timeframe, "1h")
            
            url = f"{self.base_url}/klines"
            params = {
                'symbol': binance_symbol,
                'interval': binance_timeframe,
                'limit': limit
            }
            
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            
            klines = response.json()
            
            # Convert to DataFrame
            df_data = []
            for kline in klines:
                df_data.append({
                    'timestamp': pd.to_datetime(kline[0], unit='ms'),
                    'open': float(kline[1]),
                    'high': float(kline[2]), 
                    'low': float(kline[3]),
                    'close': float(kline[4]),
                    'volume': float(kline[5])
                })
            
            df = pd.DataFrame(df_data)
            df.set_index('timestamp', inplace=True)
            
            return df
            
        except Exception as e:
            print(f"❌ Error fetching {symbol} data: {e}")
            return None
    
    def get_24hr_stats(self, symbol):
        """Get 24hr price change statistics"""
        try:
            binance_symbol = self.symbols_map.get(symbol)
            if not binance_symbol:
                return None
                
            url = f"{self.base_url}/ticker/24hr"
            params = {'symbol': binance_symbol}
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            return {
                'price_change': float(data['priceChange']),
                'price_change_percent': float(data['priceChangePercent']),
                'high_24h': float(data['highPrice']),
                'low_24h': float(data['lowPrice']),
                'volume': float(data['volume'])
            }
            
        except Exception as e:
            print(f"❌ Error fetching 24hr stats for {symbol}: {e}")
            return None
    
    def test_connection(self):
        """Test Binance API connection"""
        try:
            url = f"{self.base_url}/ping"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            print("✅ Binance API connection successful!")
            return True
        except Exception as e:
            print(f"❌ Binance API connection failed: {e}")
            return False
    
    def cache_real_data(self, symbols, timeframe="1h"):
        """Cache real data cho multiple symbols"""
        os.makedirs("data/cache", exist_ok=True)
        
        success_count = 0
        total_symbols = len(symbols)
        
        print(f"📡 Fetching real data for {total_symbols} symbols...")
        
        for symbol in symbols:
            try:
                print(f"⏳ Fetching {symbol}...")
                
                df = self.get_klines(symbol, timeframe)
                if df is not None and len(df) > 0:
                    # Save to cache
                    symbol_file = symbol.replace('/', '_')
                    cache_file = f"data/cache/{symbol_file}_{timeframe}_real_{datetime.now().strftime('%Y%m%d')}.csv"
                    df.to_csv(cache_file)
                    
                    success_count += 1
                    print(f"✅ {symbol}: {len(df)} candles saved")
                else:
                    print(f"❌ {symbol}: No data received")
                    
                # Delay để tránh rate limit
                time.sleep(0.1)
                
            except Exception as e:
                print(f"❌ {symbol}: {e}")
                
        print(f"\n🎉 Cached real data for {success_count}/{total_symbols} symbols")
        return success_count

if __name__ == "__main__":
    fetcher = RealTimeDataFetcher()
    
    # Test connection
    if fetcher.test_connection():
        print("\n🚀 Starting real data fetch...")
        
        # Get current prices
        print("\n📊 Current Prices:")
        prices = fetcher.get_current_prices()
        for symbol, price in list(prices.items())[:5]:
            print(f"  {symbol}: ${price:,.2f}")
        print(f"  ... and {len(prices)-5} more")
        
        # Cache data for all symbols
        symbols = list(fetcher.symbols_map.keys())
        fetcher.cache_real_data(symbols[:5], "1h")  # Test với 5 symbols đầu
        
    else:
        print("❌ Cannot connect to Binance API. Using fallback data.")