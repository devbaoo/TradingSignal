"""
Advanced Futures Contract Filter with Hard Thresholds
Filters futures contracts based on liquidity, funding, and market structure metrics.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class FuturesFilterThresholds:
    """Hard thresholds for futures contract filtering."""
    max_spread_bps: float = 5.0  # Maximum bid-ask spread in basis points
    min_depth_usdt: float = 50000.0  # Minimum depth at 0.1% from mid in USDT
    max_funding_rate_abs: float = 0.001  # Maximum absolute funding rate (0.10%)
    min_oi_change_24h_pct: float = 25.0  # Minimum 24h OI change % for activity
    crowded_ls_ratio_upper: float = 1.3  # Above this = crowded long
    crowded_ls_ratio_lower: float = 0.7  # Below this = crowded short
    min_volume_24h_usdt: float = 1000000.0  # Minimum 24h volume in USDT
    max_price_impact_bps: float = 10.0  # Maximum price impact for standard size

@dataclass
class FuturesMetrics:
    """Metrics for a futures contract."""
    symbol: str
    spread_bps: float
    depth_0_1_pct_usdt: float
    funding_rate: float
    oi_change_24h_pct: float
    long_short_ratio: float
    volume_24h_usdt: float
    price_impact_bps: float
    is_active: bool = True

class FuturesFilter:
    """Advanced futures contract filter with hard thresholds."""
    
    def __init__(self, thresholds: Optional[FuturesFilterThresholds] = None):
        self.thresholds = thresholds or FuturesFilterThresholds()
        self.logger = logging.getLogger(__name__)
    
    def calculate_spread_bps(self, bid: float, ask: float, mid_price: float) -> float:
        """Calculate bid-ask spread in basis points."""
        if mid_price <= 0:
            return float('inf')
        spread = ask - bid
        return (spread / mid_price) * 10000  # Convert to basis points
    
    def calculate_depth_at_distance(self, orderbook: Dict, mid_price: float, 
                                  distance_pct: float = 0.001) -> Tuple[float, float]:
        """Calculate order book depth at specified distance from mid."""
        if not orderbook or 'bids' not in orderbook or 'asks' not in orderbook:
            return 0.0, 0.0
        
        target_bid_price = mid_price * (1 - distance_pct)
        target_ask_price = mid_price * (1 + distance_pct)
        
        # Calculate bid depth
        bid_depth = 0.0
        for price, qty in orderbook['bids']:
            if float(price) >= target_bid_price:
                bid_depth += float(price) * float(qty)
        
        # Calculate ask depth
        ask_depth = 0.0
        for price, qty in orderbook['asks']:
            if float(price) <= target_ask_price:
                ask_depth += float(price) * float(qty)
        
        return bid_depth, ask_depth
    
    def estimate_price_impact(self, orderbook: Dict, trade_size_usdt: float,
                            side: str = 'buy') -> float:
        """Estimate price impact for a trade size in basis points."""
        if not orderbook or trade_size_usdt <= 0:
            return float('inf')
        
        try:
            orders = orderbook['asks'] if side == 'buy' else orderbook['bids']
            if not orders:
                return float('inf')
            
            total_cost = 0.0
            total_qty = 0.0
            remaining_value = trade_size_usdt
            
            for price_str, qty_str in orders:
                price = float(price_str)
                qty = float(qty_str)
                order_value = price * qty
                
                if remaining_value >= order_value:
                    total_cost += order_value
                    total_qty += qty
                    remaining_value -= order_value
                else:
                    # Partial fill
                    partial_qty = remaining_value / price
                    total_cost += remaining_value
                    total_qty += partial_qty
                    remaining_value = 0
                    break
            
            if total_qty == 0 or total_cost == 0:
                return float('inf')
            
            avg_fill_price = total_cost / total_qty
            best_price = float(orders[0][0])
            
            impact_bps = abs(avg_fill_price - best_price) / best_price * 10000
            return impact_bps
            
        except Exception as e:
            self.logger.error(f"Error calculating price impact: {e}")
            return float('inf')
    
    def check_crowded_positioning(self, long_short_ratio: float, 
                                oi_change_24h_pct: float) -> bool:
        """Check if positioning appears crowded on one side."""
        # High OI change + extreme LS ratio = crowded
        if oi_change_24h_pct > self.thresholds.min_oi_change_24h_pct:
            if (long_short_ratio > self.thresholds.crowded_ls_ratio_upper or 
                long_short_ratio < self.thresholds.crowded_ls_ratio_lower):
                return True
        return False
    
    def extract_futures_metrics(self, symbol: str, market_data: Dict) -> Optional[FuturesMetrics]:
        """Extract all relevant metrics for futures filtering."""
        try:
            # Extract basic price data
            ticker = market_data.get('ticker', {})
            orderbook = market_data.get('orderbook', {})
            funding_data = market_data.get('funding', {})
            oi_data = market_data.get('open_interest', {})
            
            if not ticker:
                return None
            
            # Calculate mid price
            bid = float(ticker.get('bidPrice', 0))
            ask = float(ticker.get('askPrice', 0))
            mid_price = (bid + ask) / 2 if bid > 0 and ask > 0 else float(ticker.get('price', 0))
            
            if mid_price <= 0:
                return None
            
            # Calculate spread
            spread_bps = self.calculate_spread_bps(bid, ask, mid_price)
            
            # Calculate depth at 0.1%
            bid_depth, ask_depth = self.calculate_depth_at_distance(orderbook, mid_price, 0.001)
            total_depth = bid_depth + ask_depth
            
            # Get funding rate
            funding_rate = abs(float(funding_data.get('fundingRate', 0)))
            
            # Get OI change
            oi_change_24h_pct = float(oi_data.get('changePercent24h', 0))
            
            # Get long/short ratio (default to 1.0 if not available)
            long_short_ratio = float(market_data.get('longShortRatio', 1.0))
            
            # Get 24h volume
            volume_24h = float(ticker.get('quoteVolume', 0))
            
            # Calculate price impact for standard trade size (10k USDT)
            price_impact_bps = min(
                self.estimate_price_impact(orderbook, 10000, 'buy'),
                self.estimate_price_impact(orderbook, 10000, 'sell')
            )
            
            return FuturesMetrics(
                symbol=symbol,
                spread_bps=spread_bps,
                depth_0_1_pct_usdt=total_depth,
                funding_rate=funding_rate,
                oi_change_24h_pct=abs(oi_change_24h_pct),
                long_short_ratio=long_short_ratio,
                volume_24h_usdt=volume_24h,
                price_impact_bps=price_impact_bps
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting metrics for {symbol}: {e}")
            return None
    
    def apply_hard_filters(self, metrics: FuturesMetrics) -> Tuple[bool, List[str]]:
        """Apply hard threshold filters to futures metrics."""
        passed = True
        reasons = []
        
        # Check spread
        if metrics.spread_bps > self.thresholds.max_spread_bps:
            passed = False
            reasons.append(f"Spread too wide: {metrics.spread_bps:.1f}bps > {self.thresholds.max_spread_bps}bps")
        
        # Check depth
        if metrics.depth_0_1_pct_usdt < self.thresholds.min_depth_usdt:
            passed = False
            reasons.append(f"Insufficient depth: ${metrics.depth_0_1_pct_usdt:,.0f} < ${self.thresholds.min_depth_usdt:,.0f}")
        
        # Check funding rate
        if metrics.funding_rate > self.thresholds.max_funding_rate_abs:
            passed = False
            reasons.append(f"High funding rate: {metrics.funding_rate:.3f}% > {self.thresholds.max_funding_rate_abs:.3f}%")
        
        # Check volume
        if metrics.volume_24h_usdt < self.thresholds.min_volume_24h_usdt:
            passed = False
            reasons.append(f"Low volume: ${metrics.volume_24h_usdt:,.0f} < ${self.thresholds.min_volume_24h_usdt:,.0f}")
        
        # Check price impact
        if metrics.price_impact_bps > self.thresholds.max_price_impact_bps:
            passed = False
            reasons.append(f"High price impact: {metrics.price_impact_bps:.1f}bps > {self.thresholds.max_price_impact_bps}bps")
        
        # Check crowded positioning
        if self.check_crowded_positioning(metrics.long_short_ratio, metrics.oi_change_24h_pct):
            passed = False
            side = "long" if metrics.long_short_ratio > 1.1 else "short"
            reasons.append(f"Crowded {side} positioning: LS={metrics.long_short_ratio:.2f}, OI_Δ={metrics.oi_change_24h_pct:.1f}%")
        
        return passed, reasons
    
    def filter_futures_symbols(self, market_data_dict: Dict[str, Dict]) -> Tuple[List[str], Dict[str, List[str]]]:
        """Filter futures symbols based on hard thresholds."""
        passed_symbols = []
        rejection_reasons = {}
        
        for symbol, market_data in market_data_dict.items():
            metrics = self.extract_futures_metrics(symbol, market_data)
            
            if metrics is None:
                rejection_reasons[symbol] = ["Failed to extract metrics"]
                continue
            
            passed, reasons = self.apply_hard_filters(metrics)
            
            if passed:
                passed_symbols.append(symbol)
                self.logger.info(f"✅ {symbol}: Passed all filters")
            else:
                rejection_reasons[symbol] = reasons
                self.logger.info(f"❌ {symbol}: {'; '.join(reasons)}")
        
        return passed_symbols, rejection_reasons
    
    def get_filter_summary(self, total_symbols: int, passed_symbols: int, 
                          rejection_reasons: Dict[str, List[str]]) -> str:
        """Generate a summary of the filtering results."""
        summary = f"Futures Filter Summary:\n"
        summary += f"Total symbols: {total_symbols}\n"
        summary += f"Passed filters: {passed_symbols}\n"
        summary += f"Rejection rate: {(total_symbols - passed_symbols) / total_symbols * 100:.1f}%\n\n"
        
        # Count rejection reasons
        reason_counts = {}
        for reasons in rejection_reasons.values():
            for reason in reasons:
                category = reason.split(':')[0]
                reason_counts[category] = reason_counts.get(category, 0) + 1
        
        summary += "Top rejection reasons:\n"
        for reason, count in sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
            summary += f"- {reason}: {count} symbols\n"
        
        return summary