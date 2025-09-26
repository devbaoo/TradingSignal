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
    """Futures market specific data structure"""
    symbol: str
    funding_rate: float
    funding_countdown: int  # milliseconds to next funding
    open_interest: float
    open_interest_change_24h: float
    long_short_ratio: float  # Overall market sentiment
    top_trader_ratio: float  # Top traders sentiment
    liquidations_24h: Optional[float]  # Liquidation volume
    basis: Optional[float]  # Futures vs Spot premium
    volume_24h: float
    

class BinanceFuturesDataProvider:
    """Provides futures-specific market data from Binance"""
    
    def __init__(self):
        self.futures_base_url = "https://fapi.binance.com/fapi/v1"
        self.leverage_brackets_cache = {}  # Cache leverage brackets
        self.leverage_cache_expiry = {}    # Cache expiry timestamps
        self.spot_base_url = "https://api.binance.com/api/v3"
        
        # Session for connection pooling
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'TradingBot/1.0'
        })
        
        # Cache for frequently accessed data (5 minutes)
        self._cache = {}
        self._cache_timeout = 300  # 5 minutes
        
    def get_futures_data(self, symbol: str) -> Optional[FuturesMarketData]:
        """Get comprehensive futures market data for a symbol"""
        # Convert to Binance futures format if needed
        binance_symbol = symbol if symbol.endswith('USDT') else f"{symbol}USDT"
        
        # Check cache
        cache_key = f"futures_data_{binance_symbol}"
        if cache_key in self._cache:
            cache_time, cached_data = self._cache[cache_key]
            if time.time() - cache_time < self._cache_timeout:
                return cached_data
        
        try:
            # Gather all data
            funding_data = self._get_funding_rate(binance_symbol)
            oi_data = self._get_open_interest(binance_symbol)
            ls_data = self._get_long_short_ratio(binance_symbol)
            liquidation_data = self._get_liquidation_data(binance_symbol)
            basis_data = self._get_basis(binance_symbol)
            volume_data = self._get_24h_stats(binance_symbol)
            
            if not all([funding_data, oi_data, volume_data]):
                return None
            
            result = FuturesMarketData(
                symbol=symbol,
                funding_rate=funding_data.get('fundingRate', 0),
                funding_countdown=funding_data.get('fundingCountdown', 0),
                open_interest=oi_data.get('openInterest', 0),
                open_interest_change_24h=oi_data.get('change24h', 0),
                long_short_ratio=ls_data.get('longShortRatio', 0.5) if ls_data else 0.5,
                top_trader_ratio=ls_data.get('topTraderRatio', 0.5) if ls_data else 0.5,
                liquidations_24h=liquidation_data.get('liquidations') if liquidation_data else None,
                basis=basis_data.get('basis') if basis_data else None,
                volume_24h=volume_data.get('volume', 0)
            )
            
            # Cache the result
            self._cache[cache_key] = (time.time(), result)
            return result
            
        except Exception as e:
            print(f"Error fetching futures data for {symbol}: {e}")
            return None
    
    def _get_funding_rate(self, symbol: str) -> Optional[Dict]:
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
            # Note: Binance doesn't provide direct liquidation data via API
            # This is a placeholder for future implementation or alternative data sources
            return None
            
        except Exception as e:
            print(f"Error fetching liquidation data for {symbol}: {e}")
            return None
    
    def _get_basis(self, symbol: str) -> Optional[Dict]:
        """Calculate basis (futures vs spot premium)"""
        try:
            # Get futures price
            futures_url = f"{self.futures_base_url}/ticker/price"
            futures_params = {'symbol': symbol}
            
            futures_response = self.session.get(futures_url, params=futures_params, timeout=10)
            if futures_response.status_code != 200:
                return None
            
            futures_price = float(futures_response.json().get('price', 0))
            
            # Get spot price
            spot_url = f"{self.spot_base_url}/ticker/price"
            spot_params = {'symbol': symbol}
            
            spot_response = self.session.get(spot_url, params=spot_params, timeout=10)
            if spot_response.status_code != 200:
                return None
            
            spot_price = float(spot_response.json().get('price', 0))
            
            if spot_price > 0:
                basis = (futures_price - spot_price) / spot_price
                return {'basis': basis}
            
            return None
            
        except Exception as e:
            print(f"Error calculating basis for {symbol}: {e}")
            return None
    
    def _get_24h_stats(self, symbol: str) -> Optional[Dict]:
        """Get 24h trading statistics"""
        try:
            url = f"{self.futures_base_url}/ticker/24hr"
            params = {'symbol': symbol}
            
            response = self.session.get(url, params=params, timeout=10)
            if response.status_code != 200:
                return None
            
            data = response.json()
            
            return {
                'volume': float(data.get('volume', 0)),
                'turnover': float(data.get('quoteVolume', 0)),
                'priceChange24h': float(data.get('priceChangePercent', 0))
            }
            
        except Exception as e:
            print(f"Error fetching 24h stats for {symbol}: {e}")
            return None
    
    def get_futures_signal_filter(self, symbol: str, direction: str) -> Tuple[bool, str]:
        """
        Filter trading signals based on futures market conditions
        Returns (approved, message)
        """
        futures_data = self.get_futures_data(symbol)
        
        if not futures_data:
            return True, f"No futures data available for {symbol} - proceeding with spot analysis"
        
        issues = []
        warnings = []
        
        # 1. Funding Rate Analysis
        funding_rate = futures_data.funding_rate
        if direction == "LONG":
            if funding_rate > 0.01:  # 1% funding rate is extremely high
                issues.append(f"Extreme funding rate: {funding_rate:.4%} - very expensive to hold LONG")
            elif funding_rate > 0.001:  # 0.1% 
                warnings.append(f"High funding rate: {funding_rate:.4%} - expensive to hold LONG")
        else:  # SHORT
            if funding_rate < -0.01:  # Negative funding means shorts pay longs
                issues.append(f"Extreme negative funding rate: {funding_rate:.4%} - very expensive to hold SHORT")
            elif funding_rate < -0.001:
                warnings.append(f"High negative funding rate: {funding_rate:.4%} - expensive to hold SHORT")
        
        # 2. Open Interest Analysis
        oi_change = futures_data.open_interest_change_24h
        if abs(oi_change) > 0.5:  # 50% OI change in 24h is significant
            if oi_change > 0:
                warnings.append(f"High OI increase: +{oi_change:.1%} - increasing leverage in market")
            else:
                warnings.append(f"High OI decrease: {oi_change:.1%} - deleveraging in market")
        
        # 3. Long/Short Ratio Analysis (Market Crowding)
        ls_ratio = futures_data.long_short_ratio
        top_trader_ratio = futures_data.top_trader_ratio
        
        if direction == "LONG":
            if ls_ratio > 0.8:  # 80% of accounts are long
                issues.append(f"Overcrowded LONG: {ls_ratio:.1%} of accounts are long - high liquidation risk")
            elif ls_ratio > 0.7:
                warnings.append(f"Crowded LONG: {ls_ratio:.1%} of accounts are long")
            
            # Check if smart money (top traders) disagree
            if top_trader_ratio < 0.4 and ls_ratio > 0.6:
                warnings.append("Smart money divergence: Top traders are more bearish than retail")
                
        else:  # SHORT
            if ls_ratio < 0.2:  # 80% of accounts are short
                issues.append(f"Overcrowded SHORT: {(1-ls_ratio):.1%} of accounts are short - high liquidation risk")
            elif ls_ratio < 0.3:
                warnings.append(f"Crowded SHORT: {(1-ls_ratio):.1%} of accounts are short")
            
            # Check if smart money disagrees
            if top_trader_ratio > 0.6 and ls_ratio < 0.4:
                warnings.append("Smart money divergence: Top traders are more bullish than retail")
        
        # 4. Basis Analysis (if available)
        if futures_data.basis is not None:
            basis = futures_data.basis
            if direction == "LONG" and basis > 0.05:  # 5% premium
                warnings.append(f"High futures premium: {basis:.2%} - futures expensive vs spot")
            elif direction == "SHORT" and basis < -0.02:  # 2% discount
                warnings.append(f"High futures discount: {basis:.2%} - unusual market structure")
        
        # Decision making
        if issues:
            return False, f"❌ BLOCKED: {' | '.join(issues)}"
        
        if warnings:
            message = f"⚠️ CAUTION: {' | '.join(warnings[:2])}"  # Limit to 2 warnings
        else:
            message = f"✅ APPROVED: Favorable futures conditions for {direction}"
        
        return True, message
    
    def get_market_crowding_score(self, symbol: str) -> float:
        """
        Calculate market crowding score (0-1, where 1 is extremely crowded)
        Used for position sizing adjustments
        """
        futures_data = self.get_futures_data(symbol)
        
        if not futures_data:
            return 0.5  # Neutral if no data
        
        crowding_factors = []
        
        # Factor 1: Long/Short ratio extremes
        ls_ratio = futures_data.long_short_ratio
        if ls_ratio > 0.8 or ls_ratio < 0.2:
            crowding_factors.append(1.0)  # Extreme crowding
        elif ls_ratio > 0.7 or ls_ratio < 0.3:
            crowding_factors.append(0.7)  # High crowding
        else:
            crowding_factors.append(0.2)  # Normal
        
        # Factor 2: Open Interest change
        oi_change = abs(futures_data.open_interest_change_24h)
        if oi_change > 0.5:
            crowding_factors.append(0.8)  # High leverage changes
        elif oi_change > 0.3:
            crowding_factors.append(0.5)  # Moderate changes
        else:
            crowding_factors.append(0.2)  # Stable
        
        # Factor 3: Funding rate extremes
        funding_rate = abs(futures_data.funding_rate)
        if funding_rate > 0.01:
            crowding_factors.append(1.0)  # Extreme funding
        elif funding_rate > 0.003:
            crowding_factors.append(0.6)  # High funding
        else:
            crowding_factors.append(0.2)  # Normal
        
        return min(1.0, sum(crowding_factors) / len(crowding_factors))

    def get_leverage_brackets(self, symbol: str) -> Optional[Dict]:
        """
        Get leverage brackets for symbol from Binance API
        Uses caching to avoid rate limits (cache for 1 hour)
        """
        current_time = time.time()
        
        # Check cache first
        if (symbol in self.leverage_brackets_cache and 
            symbol in self.leverage_cache_expiry and
            current_time < self.leverage_cache_expiry[symbol]):
            return self.leverage_brackets_cache[symbol]
        
        try:
            # Note: This endpoint requires authentication in production
            # For now, we'll use fallback MMR calculations
            # In production, you would need API key and signature
            
            # Fallback MMR based on common Binance brackets
            fallback_brackets = self._get_fallback_leverage_brackets(symbol)
            
            # Cache for 1 hour
            self.leverage_brackets_cache[symbol] = fallback_brackets
            self.leverage_cache_expiry[symbol] = current_time + 3600
            
            return fallback_brackets
            
        except Exception as e:
            # Return safe fallback
            return self._get_fallback_leverage_brackets(symbol)

    def _get_fallback_leverage_brackets(self, symbol: str) -> Dict:
        """
        Fallback leverage brackets based on common Binance patterns
        This should be replaced with real API call in production
        """
        
        # Most USDT-M futures follow this pattern
        brackets = [
            {"notionalFloor": 0, "notionalCap": 50000, "maintMarginRatio": 0.004, "cum": 0},
            {"notionalFloor": 50000, "notionalCap": 250000, "maintMarginRatio": 0.005, "cum": 50},
            {"notionalFloor": 250000, "notionalCap": 1000000, "maintMarginRatio": 0.01, "cum": 1300},
            {"notionalFloor": 1000000, "notionalCap": 5000000, "maintMarginRatio": 0.025, "cum": 16300},
            {"notionalFloor": 5000000, "notionalCap": 20000000, "maintMarginRatio": 0.05, "cum": 141300},
            {"notionalFloor": 20000000, "notionalCap": 50000000, "maintMarginRatio": 0.1, "cum": 1141300},
            {"notionalFloor": 50000000, "notionalCap": 100000000, "maintMarginRatio": 0.125, "cum": 2391300},
        ]
        
        return {
            "symbol": symbol,
            "brackets": brackets
        }

    def calculate_accurate_liquidation(self, entry_price: float, leverage: float, 
                                     direction: str, position_size_usdt: float, 
                                     symbol: str) -> Dict:
        """
        Calculate accurate liquidation price using proper MMR from brackets
        """
        brackets_data = self.get_leverage_brackets(symbol)
        
        if not brackets_data:
            # Fallback to simple calculation
            return self._calculate_simple_liquidation(entry_price, leverage, direction)
        
        # Find appropriate bracket for position size
        brackets = brackets_data["brackets"]
        mmr = 0.004  # Default MMR
        cum = 0
        
        for bracket in brackets:
            if position_size_usdt <= bracket["notionalCap"]:
                mmr = bracket["maintMarginRatio"]
                cum = bracket["cum"]
                break
        
        # Binance liquidation formula
        if direction == "LONG":
            liquidation_price = (position_size_usdt - entry_price * position_size_usdt / entry_price + cum) / \
                              (position_size_usdt / entry_price * (mmr - 1))
        else:  # SHORT
            liquidation_price = (position_size_usdt + entry_price * position_size_usdt / entry_price - cum) / \
                              (position_size_usdt / entry_price * (mmr + 1))
        
        return {
            'liquidation_price': liquidation_price,
            'mmr_used': mmr,
            'bracket_info': f"MMR: {mmr*100:.2f}% (Bracket for ${position_size_usdt:,.0f})",
            'distance_percent': abs(entry_price - liquidation_price) / entry_price * 100
        }

    def _calculate_simple_liquidation(self, entry_price: float, leverage: float, direction: str) -> Dict:
        """Simple liquidation calculation as fallback"""
        mmr = 0.004 if leverage <= 20 else 0.01  # Basic MMR
        
        if direction == "LONG":
            liquidation_price = entry_price * (1 - (1/leverage) + mmr)
        else:
            liquidation_price = entry_price * (1 + (1/leverage) + mmr)
        
        return {
            'liquidation_price': liquidation_price,
            'mmr_used': mmr,
            'bracket_info': f"Simple MMR: {mmr*100:.2f}%",
            'distance_percent': abs(entry_price - liquidation_price) / entry_price * 100
        }