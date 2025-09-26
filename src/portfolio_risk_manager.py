"""
Portfolio Risk Manager - Professional risk management for multiple positions
Handles correlation, position limits, portfolio-wide risk controls
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import time

@dataclass
class Position:
    """Individual position tracking"""
    symbol: str
    direction: str  # LONG/SHORT
    entry_price: float
    position_size_usdt: float
    leverage: float
    stop_loss: float
    take_profit_1: float
    risk_amount: float  # Actual $ at risk
    timestamp: float
    timeframe: str
    safety_score: int

@dataclass 
class PortfolioRisk:
    """Portfolio-wide risk metrics"""
    total_risk_amount: float  # Total $ at risk across all positions
    total_notional: float     # Total position sizes
    risk_percentage: float    # % of portfolio at risk
    max_correlated_risk: float # Risk from correlated positions
    position_count: int
    leverage_weighted_avg: float

class PortfolioRiskManager:
    """Professional portfolio risk management"""
    
    def __init__(self):
        # Risk limits - professional institutional levels
        self.max_portfolio_risk_pct = 0.05  # 5% total portfolio risk
        self.max_single_position_risk_pct = 0.01  # 1% per position
        self.max_correlated_position_risk_pct = 0.03  # 3% for correlated cluster
        self.max_positions = 3  # Circuit breaker
        self.max_leverage_portfolio = 50  # Max weighted average leverage (increased for crypto futures)
        
        # Correlation thresholds
        self.high_correlation_threshold = 0.7  # Same direction correlation limit
        self.crypto_correlation_clusters = {
            'MAJOR_CLUSTER': ['BTCUSDT', 'ETHUSDT', 'BNBUSDT'],  # Core crypto majors
            
            'LAYER1_CLUSTER': ['ADAUSDT', 'SOLUSDT', 'DOTUSDT', 'AVAXUSDT', 'ATOMUSDT', 
                              'NEARUSDT', 'ALGOUSDT', 'ICPUSDT', 'FTMUSDT', 'ONEUSDT',
                              'HBARUSDT', 'EGLDUSDT', 'FLOWUSDT', 'ROSEUSDT', 'KSMUSDT',
                              'KAVAUSDT', 'MINAUSDT', 'OSMOUSDT', 'ARBUSDT', 'OPUSDT', 'SUIUSDT', 'APTUSDT'],
            
            'DEFI_CLUSTER': ['UNIUSDT', 'AAVEUSDT', 'COMPUSDT', 'SUSHIUSDT', 'MKRUSDT',
                            'SNXUSDT', 'CRVUSDT', '1INCHUSDT', 'YFIUSDT', 'CAKEUSDT',
                            'GMXUSDT', 'DYDXUSDT', 'LDOUSDT', 'RPLUSDT', 'LINKUSDT'],
            
            'LEGACY_CLUSTER': ['LTCUSDT', 'BCHUSDT', 'ETCUSDT', 'XMRUSDT', 'ZECUSDT',
                              'DASHUSDT', 'XLMUSDT', 'XRPUSDT', 'TRXUSDT', 'LUNCUSDT', 'USTCUSDT'],
            
            'MEME_CLUSTER': ['DOGEUSDT', 'SHIBUSDT', 'FLOKIUSDT', 'PEPEUSDT', 
                            'BONKUSDT', 'WIFUSDT'],
            
            'GAMING_NFT_CLUSTER': ['AXSUSDT', 'SANDUSDT', 'MANAUSDT', 'ENJUSDT',
                                  'GALAUSDT', 'APEUSDT', 'IMXUSDT', 'GMTUSDT', 'CHZUSDT', 'BLURUSDT'],
            
            'AI_TECH_CLUSTER': ['FETUSDT', 'AGIXUSDT', 'OCEANUSDT', 'GRTUSDT',
                               'RENDERUSDT', 'THETAUSDT', 'RNDRUSDT', 'PYTHUSDT'],
            
            'INFRASTRUCTURE_CLUSTER': ['MATICUSDT', 'VETUSDT', 'FILUSDT', 'JTOUSDT'],
            
            'EXCHANGE_CLUSTER': ['FTTUSDT']
        }
        
        # Active positions tracking
        self.active_positions: List[Position] = []
        
    def can_open_position(self, 
                         symbol: str, 
                         direction: str,
                         position_size_usdt: float,
                         leverage: float,
                         stop_loss: float,
                         entry_price: float,
                         portfolio_balance: float,
                         safety_score: int) -> Tuple[bool, str]:
        """
        Check if new position can be opened based on portfolio risk rules
        Returns (can_open, reason)
        """
        
        # Calculate position risk
        if direction == "LONG":
            risk_distance = abs(entry_price - stop_loss) / entry_price
        else:
            risk_distance = abs(stop_loss - entry_price) / entry_price
            
        position_risk_amount = position_size_usdt * risk_distance
        
        # 1. Check position count limit
        if len(self.active_positions) >= self.max_positions:
            return False, f"Portfolio limit: Max {self.max_positions} positions (circuit breaker)"
            
        # 2. Check single position risk
        if portfolio_balance > 0:  # Safety check for division by zero
            single_position_risk_pct = position_risk_amount / portfolio_balance
            if single_position_risk_pct > self.max_single_position_risk_pct:
                return False, f"Position too risky: {single_position_risk_pct:.1%} > {self.max_single_position_risk_pct:.1%} limit"
        else:
            return False, "Invalid portfolio balance"
            
        # 3. Check portfolio-wide risk
        current_portfolio_risk = sum(pos.risk_amount for pos in self.active_positions)
        total_risk_after = current_portfolio_risk + position_risk_amount
        
        if portfolio_balance > 0:  # Safety check for division by zero
            total_risk_pct = total_risk_after / portfolio_balance
            if total_risk_pct > self.max_portfolio_risk_pct:
                return False, f"Portfolio risk too high: {total_risk_pct:.1%} > {self.max_portfolio_risk_pct:.1%} limit"
            
        # 4. Check correlation limits
        correlation_issue = self._check_correlation_limits(symbol, direction, position_risk_amount, portfolio_balance)
        if correlation_issue:
            return False, correlation_issue
            
        # 5. Check portfolio exposure limits (notional / balance ratio)
        current_notional = sum(pos.position_size_usdt for pos in self.active_positions)
        total_notional_after = current_notional + position_size_usdt
        
        # Calculate portfolio exposure ratio (not sum of leverages)
        portfolio_exposure_ratio = total_notional_after / portfolio_balance if portfolio_balance > 0 else 0
        max_exposure_ratio = 10.0  # Max 10x total exposure (institutional limit)
        
        if portfolio_exposure_ratio > max_exposure_ratio:
            return False, f"Portfolio exposure too high: {portfolio_exposure_ratio:.1f}x > {max_exposure_ratio}x limit"
            
        # 6. Safety score minimum for portfolio positions
        if len(self.active_positions) >= 2 and safety_score < 7:
            return False, f"Multi-position requires safety ≥7, got {safety_score}"
            
        return True, "✅ Portfolio risk approved"
        
    def _check_correlation_limits(self, symbol: str, direction: str, position_risk_amount: float, portfolio_balance: float) -> Optional[str]:
        """Check if position violates correlation limits"""
        
        # Find symbol's cluster
        new_symbol_cluster = None
        for cluster_name, symbols in self.crypto_correlation_clusters.items():
            if symbol in symbols:
                new_symbol_cluster = cluster_name
                break
                
        if not new_symbol_cluster:
            return None  # No correlation constraints for uncategorized symbols
            
        # Check existing positions in same cluster
        cluster_positions = [
            pos for pos in self.active_positions 
            if any(pos.symbol in symbols for cluster_name, symbols in self.crypto_correlation_clusters.items() 
                   if cluster_name == new_symbol_cluster)
        ]
        
        if not cluster_positions:
            return None  # No positions in same cluster
            
        # Check same direction positions in cluster
        same_direction_positions = [pos for pos in cluster_positions if pos.direction == direction]
        
        if same_direction_positions:
            # Calculate total correlated risk
            current_cluster_risk = sum(pos.risk_amount for pos in same_direction_positions)
            total_cluster_risk = current_cluster_risk + position_risk_amount
            cluster_risk_pct = total_cluster_risk / portfolio_balance
            
            if cluster_risk_pct > self.max_correlated_position_risk_pct:
                return f"Correlated cluster risk too high: {cluster_risk_pct:.1%} > {self.max_correlated_position_risk_pct:.1%} for {new_symbol_cluster}"
                
        return None
        
    def add_position(self, position: Position):
        """Add new position to portfolio tracking"""
        self.active_positions.append(position)
        
    def remove_position(self, symbol: str):
        """Remove position when closed"""
        self.active_positions = [pos for pos in self.active_positions if pos.symbol != symbol]
        
    def get_portfolio_metrics(self, portfolio_balance: float) -> PortfolioRisk:
        """Get current portfolio risk metrics"""
        if not self.active_positions:
            return PortfolioRisk(0, 0, 0, 0, 0, 0)
            
        total_risk = sum(pos.risk_amount for pos in self.active_positions)
        total_notional = sum(pos.position_size_usdt for pos in self.active_positions)
        risk_percentage = total_risk / portfolio_balance if portfolio_balance > 0 else 0
        
        # Calculate max correlated cluster risk
        max_cluster_risk = 0
        for cluster_name, symbols in self.crypto_correlation_clusters.items():
            cluster_positions = [
                pos for pos in self.active_positions 
                if pos.symbol in symbols
            ]
            if cluster_positions:
                cluster_risk = sum(pos.risk_amount for pos in cluster_positions)
        # Portfolio exposure ratio (institutional metric)
        total_notional = sum(pos.position_size_usdt for pos in self.active_positions)
        portfolio_exposure_ratio = total_notional / portfolio_balance if portfolio_balance > 0 else 0
        
        return PortfolioRisk(
            total_risk_amount=total_risk,
            total_notional=total_notional,
            risk_percentage=risk_percentage,
            max_correlated_risk=max_cluster_risk,
            position_count=len(self.active_positions),
            leverage_weighted_avg=portfolio_exposure_ratio  # This is the real institutional metric
        )
        
    def get_position_limits_info(self, portfolio_balance: float) -> Dict:
        """Get current limits and utilization for UI display"""
        metrics = self.get_portfolio_metrics(portfolio_balance)
        
        return {
            'max_positions': self.max_positions,
            'current_positions': metrics.position_count,
            'max_portfolio_risk': self.max_portfolio_risk_pct,
            'current_portfolio_risk': metrics.risk_percentage,
            'max_single_risk': self.max_single_position_risk_pct,
            'max_correlated_risk': self.max_correlated_position_risk_pct,
            'current_max_cluster_risk': metrics.max_correlated_risk / portfolio_balance if portfolio_balance > 0 else 0,
            'max_portfolio_leverage': self.max_leverage_portfolio,
            'current_avg_leverage': metrics.leverage_weighted_avg,
            'risk_utilization': metrics.risk_percentage / self.max_portfolio_risk_pct,
            'position_utilization': metrics.position_count / self.max_positions
        }
        
    def clear_expired_positions(self, max_age_hours: int = 24):
        """Remove positions older than max_age_hours (for demo/testing)"""
        current_time = time.time()
        self.active_positions = [
            pos for pos in self.active_positions 
            if (current_time - pos.timestamp) < (max_age_hours * 3600)
        ]