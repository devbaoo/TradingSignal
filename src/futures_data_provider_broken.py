"""
Futures Data Provider - Binance Futures specific data
Includes funding rates, open interest, long/short ratios, liquidation data
Filters signals based on futures market conditions
"""

import time
import requests
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

@dataclass
class FuturesMarketData:
        """Get current funding rate data"""
        try:
            url = f"{self.futures_base_url}/premiumIndex"
            params = {'symbol': symbol}
            
            response = self.session.get(url, params=params, timeout=10)
            
            # Handle 400 errors gracefully (symbol not available for futures)
            if response.status_code == 400:
                return None
                
            response.raise_for_status()
            
            data = response.json()
            
            return {
                'fundingRate': float(data.get('lastFundingRate', 0)),
                'fundingCountdown': int(data.get('nextFundingTime', 0)) - int(time.time() * 1000)
            }
            
        except Exception as e:
            # Only print error for unexpected issues, not for unavailable symbols
            if "400 Client Error" not in str(e):
                print(f"Error fetching funding rate for {symbol}: {e}")
            return Nonet ratios, liquidations
"""

import requests
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import json
import time
from dataclasses import dataclass


@dataclass 
class FuturesMarketData:
    """Futures market specific data structure"""
    symbol: str
    funding_rate: float
    funding_countdown: int  # milliseconds to next funding
    open_interest: float
    open_interest_change_24h: float
    long_short_ratio: float
    top_trader_long_short_ratio: float
    liquidation_data: Dict
    basis: float  # Futures - Spot price difference
    volume_24h: float
    price_change_24h: float
    
    
class BinanceFuturesDataProvider:
    """Provides futures-specific market data from Binance"""
    
    def __init__(self):
        self.futures_base_url = "https://fapi.binance.com/fapi/v1"
        self.spot_base_url = "https://api.binance.com/api/v3"
        self.session = requests.Session()
        
        # Thresholds for crowded positions
        self.crowded_long_threshold = {
            'funding_rate': 0.01,  # 1% funding rate
            'oi_change': 0.20,     # 20% OI increase
            'long_ratio': 0.70     # 70% long positions
        }
        
        self.crowded_short_threshold = {
            'funding_rate': -0.01, # -1% funding rate  
            'oi_change': 0.20,     # 20% OI increase
            'short_ratio': 0.70    # 70% short positions
        }
    
    def get_futures_market_data(self, symbol: str) -> Optional[FuturesMarketData]:
        """Get comprehensive futures market data for a symbol"""
        try:
            # Convert symbol format (BTC/USDT -> BTCUSDT)
            binance_symbol = symbol.replace('/', '')
            
            # Get all required data
            funding_data = self._get_funding_rate(binance_symbol)
            oi_data = self._get_open_interest(binance_symbol)
            ls_ratio = self._get_long_short_ratio(binance_symbol)
            liquidation_data = self._get_liquidation_data(binance_symbol)
            basis_data = self._get_basis(binance_symbol)
            volume_data = self._get_24h_stats(binance_symbol)
            
            if not all([funding_data, oi_data, volume_data]):
                return None
            
            return FuturesMarketData(
                symbol=symbol,
                funding_rate=funding_data.get('fundingRate', 0),
                funding_countdown=funding_data.get('fundingCountdown', 0),
                open_interest=oi_data.get('openInterest', 0),
                open_interest_change_24h=oi_data.get('change24h', 0),
                long_short_ratio=ls_ratio.get('longShortRatio', 0.5),
                top_trader_long_short_ratio=ls_ratio.get('topTraderRatio', 0.5),
                liquidation_data=liquidation_data or {},
                basis=basis_data.get('basis', 0),
                volume_24h=volume_data.get('volume', 0),
                price_change_24h=volume_data.get('priceChangePercent', 0)
            )
            
        except Exception as e:
            print(f"Error fetching futures data for {symbol}: {e}")
            return None
    
    def _get_funding_rate(self, symbol: str) -> Optional[Dict]:
        """Get current funding rate and countdown"""
        try:
            url = f"{self.futures_base_url}/premiumIndex"
            params = {'symbol': symbol}
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            return {
                'fundingRate': float(data.get('lastFundingRate', 0)),
                'fundingCountdown': int(data.get('nextFundingTime', 0)) - int(time.time() * 1000)
            }
            
        except Exception as e:
            print(f"Error fetching funding rate for {symbol}: {e}")
            return None
    
    def _get_open_interest(self, symbol: str) -> Optional[Dict]:
        """Get open interest data"""
        try:
            # Current OI
            url = f"{self.futures_base_url}/openInterest"
            params = {'symbol': symbol}
            
            response = self.session.get(url, params=params, timeout=10)
            
            # Handle 400 errors gracefully (symbol not available for futures)
            if response.status_code == 400:
                return None
                
            response.raise_for_status()
            
            current_oi = float(response.json().get('openInterest', 0))
            
            # Historical OI for change calculation (last 24h)
            hist_url = f"{self.futures_base_url}/openInterestHist"
            hist_params = {
                'symbol': symbol,
                'period': '1d',
                'limit': 2
            }
            
            hist_response = self.session.get(hist_url, params=hist_params, timeout=10)
            if hist_response.status_code == 200:
                hist_data = hist_response.json()
                if len(hist_data) >= 2:
                    prev_oi = float(hist_data[-2].get('sumOpenInterest', current_oi))
                    oi_change = (current_oi - prev_oi) / prev_oi if prev_oi > 0 else 0
                else:
                    oi_change = 0
            else:
                oi_change = 0
            
            return {
                'openInterest': current_oi,
                'change24h': oi_change
            }
            
        except Exception as e:
            # Only print error for unexpected issues, not for unavailable symbols
            if "400 Client Error" not in str(e):
                print(f"Error fetching open interest for {symbol}: {e}")
            return None
    
    def _get_long_short_ratio(self, symbol: str) -> Optional[Dict]:
        """Get long/short position ratios"""
        try:
            # Global long/short ratio
            url = f"{self.futures_base_url}/globalLongShortAccountRatio"
            params = {
                'symbol': symbol,
                'period': '1d',
                'limit': 1
            }
            
            response = self.session.get(url, params=params, timeout=10)
            
            # Handle 400 errors gracefully (symbol not available for futures)
            if response.status_code == 400:
                return {'longShortRatio': 0.5, 'topTraderRatio': 0.5}
                
            if response.status_code == 200:
                data = response.json()
                if data:
                    long_ratio = float(data[0].get('longShortRatio', 0.5))
                    long_pct = long_ratio / (1 + long_ratio)
                else:
                    long_pct = 0.5
            else:
                long_pct = 0.5
            
            # Top trader long/short ratio
            top_url = f"{self.futures_base_url}/topLongShortAccountRatio"
            top_params = {
                'symbol': symbol,
                'period': '1d', 
                'limit': 1
            }
            
            top_response = self.session.get(top_url, params=top_params, timeout=10)
            if top_response.status_code == 200:
                top_data = top_response.json()
                if top_data:
                    top_long_ratio = float(top_data[0].get('longShortRatio', 0.5))
                    top_long_pct = top_long_ratio / (1 + top_long_ratio)
                else:
                    top_long_pct = 0.5
            else:
                top_long_pct = 0.5
            
            return {
                'longShortRatio': long_pct,
                'topTraderRatio': top_long_pct
            }
            
        except Exception as e:
            # Only print error for unexpected issues, not for unavailable symbols
            if "400 Client Error" not in str(e):
                print(f"Error fetching long/short ratio for {symbol}: {e}")
            return {'longShortRatio': 0.5, 'topTraderRatio': 0.5}
    
    def _get_liquidation_data(self, symbol: str) -> Optional[Dict]:
        """Get liquidation data (if available)"""
        try:
            # This is a placeholder as Binance doesn't provide public liquidation API
            # In production, you'd use third-party services like Coinalyze, Bybt, etc.
            return {
                'long_liquidations_24h': 0,
                'short_liquidations_24h': 0,
                'total_liquidations_24h': 0,
                'liquidation_heatmap': []
            }
            
        except Exception as e:
            print(f"Error fetching liquidation data for {symbol}: {e}")
            return {}
    
    def _get_basis(self, symbol: str) -> Optional[Dict]:
        """Calculate futures-spot basis"""
        try:
            # Get futures price
            futures_url = f"{self.futures_base_url}/ticker/price"
            futures_params = {'symbol': symbol}
            
            futures_response = self.session.get(futures_url, params=futures_params, timeout=10)
            futures_response.raise_for_status()
            futures_price = float(futures_response.json().get('price', 0))
            
            # Get spot price
            spot_url = f"{self.spot_base_url}/ticker/price"
            spot_params = {'symbol': symbol}
            
            spot_response = self.session.get(spot_url, params=spot_params, timeout=10)
            spot_response.raise_for_status()
            spot_price = float(spot_response.json().get('price', 0))
            
            # Calculate basis
            if spot_price > 0:
                basis = (futures_price - spot_price) / spot_price
            else:
                basis = 0
            
            return {
                'basis': basis,
                'futures_price': futures_price,
                'spot_price': spot_price
            }
            
        except Exception as e:
            print(f"Error calculating basis for {symbol}: {e}")
            return {'basis': 0}
    
    def _get_24h_stats(self, symbol: str) -> Optional[Dict]:
        """Get 24h volume and price change stats"""
        try:
            url = f"{self.futures_base_url}/ticker/24hr"
            params = {'symbol': symbol}
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            return {
                'volume': float(data.get('volume', 0)),
                'priceChangePercent': float(data.get('priceChangePercent', 0))
            }
            
        except Exception as e:
            print(f"Error fetching 24h stats for {symbol}: {e}")
            return None
    
    def analyze_crowded_positions(self, market_data: FuturesMarketData) -> Dict[str, bool]:
        """Analyze if positions are crowded (dangerous to enter)"""
        
        analysis = {
            'crowded_long': False,
            'crowded_short': False,
            'avoid_long': False,
            'avoid_short': False,
            'reasoning': []
        }
        
        # Check for crowded long positions
        if (market_data.funding_rate > self.crowded_long_threshold['funding_rate'] and
            market_data.open_interest_change_24h > self.crowded_long_threshold['oi_change'] and
            market_data.long_short_ratio > self.crowded_long_threshold['long_ratio']):
            
            analysis['crowded_long'] = True
            analysis['avoid_long'] = True
            analysis['reasoning'].append(
                f"Crowded LONG: Funding={market_data.funding_rate:.4f}, "
                f"OI Change={market_data.open_interest_change_24h:.2%}, "
                f"Long Ratio={market_data.long_short_ratio:.2%}"
            )
        
        # Check for crowded short positions
        if (market_data.funding_rate < self.crowded_short_threshold['funding_rate'] and
            market_data.open_interest_change_24h > self.crowded_short_threshold['oi_change'] and
            (1 - market_data.long_short_ratio) > self.crowded_short_threshold['short_ratio']):
            
            analysis['crowded_short'] = True
            analysis['avoid_short'] = True
            analysis['reasoning'].append(
                f"Crowded SHORT: Funding={market_data.funding_rate:.4f}, "
                f"OI Change={market_data.open_interest_change_24h:.2%}, "
                f"Short Ratio={1-market_data.long_short_ratio:.2%}"
            )
        
        return analysis
    
    def get_futures_signal_filter(self, symbol: str, direction: str) -> Tuple[bool, str]:
        """Filter trading signals based on futures market data"""
        
        market_data = self.get_futures_market_data(symbol)
        if not market_data:
            return True, "No futures data available - proceed with caution"
        
        crowded_analysis = self.analyze_crowded_positions(market_data)
        
        # Check if we should avoid this direction
        if direction == "LONG" and crowded_analysis['avoid_long']:
            return False, f"AVOID LONG: {'; '.join(crowded_analysis['reasoning'])}"
        
        if direction == "SHORT" and crowded_analysis['avoid_short']:
            return False, f"AVOID SHORT: {'; '.join(crowded_analysis['reasoning'])}"
        
        # Additional filters
        warnings = []
        
        # High funding rate warnings
        if abs(market_data.funding_rate) > 0.005:  # 0.5% funding
            warnings.append(f"High funding rate: {market_data.funding_rate:.4f}")
        
        # High open interest growth
        if market_data.open_interest_change_24h > 0.3:  # 30% OI growth
            warnings.append(f"High OI growth: {market_data.open_interest_change_24h:.2%}")
        
        # Basis warnings
        if abs(market_data.basis) > 0.02:  # 2% basis
            warnings.append(f"High basis: {market_data.basis:.2%}")
        
        message = "Signal approved"
        if warnings:
            message += f" - Monitor: {'; '.join(warnings)}"
        
        return True, message


def create_futures_data_provider() -> BinanceFuturesDataProvider:
    """Factory function to create futures data provider"""
    return BinanceFuturesDataProvider()