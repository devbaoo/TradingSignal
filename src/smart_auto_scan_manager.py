"""
Smart Auto-scan Results Manager
Intelligently filters results based on quality thresholds and market conditions.
"""

import logging
import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)

class MarketCondition(Enum):
    """Market condition classification."""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair" 
    POOR = "poor"
    TERRIBLE = "terrible"

@dataclass
class QualityThresholds:
    """Quality thresholds for different market conditions."""
    min_safety_score: float
    min_win_probability: float
    min_risk_reward_ratio: float
    max_correlation_exposure: float
    max_position_count: int
    market_condition: MarketCondition

@dataclass
class AutoScanResult:
    """Result from auto-scan with quality metadata."""
    signals: List[Dict[str, Any]]
    market_condition: MarketCondition
    quality_score: float
    filters_applied: List[str]
    rejected_signals: Dict[str, List[str]]  # symbol -> rejection reasons
    warnings: List[str]
    circuit_breaker_active: bool = False

class SmartAutoScanManager:
    """Manages intelligent auto-scan with adaptive quality filtering."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Quality thresholds for different market conditions
        self.quality_thresholds = {
            MarketCondition.EXCELLENT: QualityThresholds(
                min_safety_score=0.7,
                min_win_probability=0.65,
                min_risk_reward_ratio=2.0,
                max_correlation_exposure=0.6,
                max_position_count=8
            ),
            MarketCondition.GOOD: QualityThresholds(
                min_safety_score=0.6,
                min_win_probability=0.60,
                min_risk_reward_ratio=2.0,
                max_correlation_exposure=0.7,
                max_position_count=6
            ),
            MarketCondition.FAIR: QualityThresholds(
                min_safety_score=0.5,
                min_win_probability=0.55,
                min_risk_reward_ratio=2.0,
                max_correlation_exposure=0.8,
                max_position_count=4
            ),
            MarketCondition.POOR: QualityThresholds(
                min_safety_score=0.7,  # Higher bar in poor conditions
                min_win_probability=0.65,
                min_risk_reward_ratio=2.5,
                max_correlation_exposure=0.5,
                max_position_count=2
            ),
            MarketCondition.TERRIBLE: QualityThresholds(
                min_safety_score=0.8,  # Very high bar
                min_win_probability=0.70,
                min_risk_reward_ratio=3.0,
                max_correlation_exposure=0.3,
                max_position_count=1
            )
        }
        
        # Circuit breaker conditions
        self.circuit_breaker_triggers = {
            'max_consecutive_losses': 5,
            'max_daily_loss_pct': 10.0,
            'min_market_stability': 0.3,
            'max_volatility_spike': 3.0
        }
        
        # Recent performance tracking
        self.recent_performance: List[Dict] = []
        self.circuit_breaker_active = False
        self.circuit_breaker_until: Optional[datetime] = None
    
    def assess_market_condition(self, 
                              market_analysis: Dict,
                              regime_analysis: Dict,
                              volatility_metrics: Dict) -> MarketCondition:
        """Assess overall market condition for threshold setting."""
        
        score = 0
        factors = []
        
        try:
            # Regime strength factor
            regime_strength = regime_analysis.get('regime_strength', 0.5)
            if regime_strength > 0.8:
                score += 2
                factors.append("Strong regime")
            elif regime_strength > 0.6:
                score += 1
                factors.append("Moderate regime")
            elif regime_strength < 0.3:
                score -= 2
                factors.append("Weak regime")
            
            # Market trend factor
            trend_score = market_analysis.get('trend_score', 0.5)
            if trend_score > 0.7:
                score += 1
                factors.append("Strong trend")
            elif trend_score < 0.3:
                score -= 1
                factors.append("Weak trend")
            
            # Volatility factor
            volatility_percentile = volatility_metrics.get('volatility_percentile', 50)
            if volatility_percentile > 80:
                score -= 2
                factors.append("High volatility")
            elif volatility_percentile < 20:
                score += 1
                factors.append("Low volatility")
            elif volatility_percentile < 40:
                score += 0.5
                factors.append("Moderate volatility")
            
            # Market breadth factor
            breadth_score = market_analysis.get('market_breadth', 0.5)
            if breadth_score > 0.7:
                score += 1
                factors.append("Good breadth")
            elif breadth_score < 0.3:
                score -= 1
                factors.append("Poor breadth")
            
            # Risk-off sentiment factor
            risk_sentiment = market_analysis.get('risk_sentiment', 0.5)
            if risk_sentiment < 0.2:
                score -= 2
                factors.append("Risk-off sentiment")
            elif risk_sentiment > 0.8:
                score += 1
                factors.append("Risk-on sentiment")
            
            # Determine market condition
            if score >= 3:
                condition = MarketCondition.EXCELLENT
            elif score >= 1:
                condition = MarketCondition.GOOD
            elif score >= -1:
                condition = MarketCondition.FAIR
            elif score >= -3:
                condition = MarketCondition.POOR
            else:
                condition = MarketCondition.TERRIBLE
            
            self.logger.info(f"Market condition: {condition.value} (score: {score}) - {', '.join(factors)}")
            return condition
            
        except Exception as e:
            self.logger.error(f"Error assessing market condition: {e}")
            return MarketCondition.FAIR  # Default fallback
    
    def check_circuit_breaker(self, 
                            recent_performance: List[Dict],
                            current_volatility: float = 1.0) -> Tuple[bool, List[str]]:
        """Check if circuit breaker should be triggered."""
        
        triggers = []
        
        if not recent_performance:
            return False, triggers
        
        try:
            # Check consecutive losses
            consecutive_losses = 0
            for perf in reversed(recent_performance[-10:]):  # Last 10 trades
                if perf.get('outcome') == 'loss':
                    consecutive_losses += 1
                else:
                    break
            
            if consecutive_losses >= self.circuit_breaker_triggers['max_consecutive_losses']:
                triggers.append(f"{consecutive_losses} consecutive losses")
            
            # Check daily loss percentage
            today_trades = [p for p in recent_performance[-50:] if p.get('date') == datetime.now().date()]
            if today_trades:
                daily_pnl = sum(p.get('pnl_pct', 0) for p in today_trades)
                if daily_pnl < -self.circuit_breaker_triggers['max_daily_loss_pct']:
                    triggers.append(f"Daily loss: {daily_pnl:.1f}%")
            
            # Check volatility spike
            if current_volatility > self.circuit_breaker_triggers['max_volatility_spike']:
                triggers.append(f"Volatility spike: {current_volatility:.1f}x")
            
            # Check win rate deterioration
            recent_wins = [p for p in recent_performance[-20:] if p.get('outcome') == 'win']
            if len(recent_performance[-20:]) >= 10:  # Need minimum sample
                win_rate = len(recent_wins) / len(recent_performance[-20:])
                if win_rate < 0.3:  # Below 30% win rate
                    triggers.append(f"Low win rate: {win_rate:.1%}")
            
            return len(triggers) > 0, triggers
            
        except Exception as e:
            self.logger.error(f"Error checking circuit breaker: {e}")
            return False, []
    
    def filter_signals_by_quality(self,
                                 signals: List[Dict],
                                 market_condition: MarketCondition,
                                 correlation_manager=None,
                                 force_minimum: bool = False) -> Tuple[List[Dict], Dict[str, List[str]]]:
        """Filter signals based on market condition and quality thresholds."""
        
        if not signals:
            return [], {}
        
        thresholds = self.quality_thresholds[market_condition]
        passed_signals = []
        rejection_reasons = {}
        
        for signal in signals:
            symbol = signal.get('symbol', 'UNKNOWN')
            reasons = []
            
            # Safety score check
            safety_score = signal.get('safety_score', 0)
            if safety_score < thresholds.min_safety_score:
                reasons.append(f"Safety score {safety_score:.2f} < {thresholds.min_safety_score:.2f}")
            
            # Win probability check
            win_probability = signal.get('win_probability', 0)
            if win_probability < thresholds.min_win_probability:
                reasons.append(f"Win probability {win_probability:.2f} < {thresholds.min_win_probability:.2f}")
            
            # Risk/reward ratio check
            rr_ratio = signal.get('risk_reward_ratio', 0)
            if rr_ratio < thresholds.min_risk_reward_ratio:
                reasons.append(f"R/R ratio {rr_ratio:.2f} < {thresholds.min_risk_reward_ratio:.2f}")
            
            # Correlation exposure check (if manager available)
            if correlation_manager:
                try:
                    correlated_symbols = correlation_manager.get_correlated_symbols(symbol)
                    correlation_exposure = len([s for s in passed_signals 
                                              if s.get('symbol') in correlated_symbols])
                    if correlation_exposure >= 2:  # Already have 2+ correlated positions
                        reasons.append(f"Correlation limit: {correlation_exposure} correlated positions")
                except Exception as e:
                    self.logger.debug(f"Could not check correlation for {symbol}: {e}")
            
            if reasons:
                rejection_reasons[symbol] = reasons
            else:
                passed_signals.append(signal)
                
                # Stop if we hit position limit
                if len(passed_signals) >= thresholds.max_position_count:
                    break
        
        # If force_minimum is True and we have no signals, return top 1 with warning
        if not passed_signals and force_minimum and signals:
            best_signal = max(signals, key=lambda s: s.get('safety_score', 0))
            passed_signals = [best_signal]
            self.logger.warning(f"Force returning 1 signal despite quality filters: {best_signal.get('symbol')}")
        
        return passed_signals, rejection_reasons
    
    def calculate_portfolio_quality_score(self, signals: List[Dict]) -> float:
        """Calculate overall quality score for the signal portfolio."""
        
        if not signals:
            return 0.0
        
        try:
            # Weighted average of individual scores
            safety_scores = [s.get('safety_score', 0) for s in signals]
            win_probabilities = [s.get('win_probability', 0) for s in signals]
            rr_ratios = [s.get('risk_reward_ratio', 0) for s in signals]
            
            # Calculate weighted averages
            avg_safety = np.mean(safety_scores) if safety_scores else 0
            avg_win_prob = np.mean(win_probabilities) if win_probabilities else 0
            avg_rr = np.mean(rr_ratios) if rr_ratios else 0
            
            # Diversity bonus (more signals = slight quality boost)
            diversity_bonus = min(0.1, len(signals) * 0.02)
            
            # Combined score
            quality_score = (avg_safety * 0.4 + avg_win_prob * 0.4 + 
                           min(avg_rr / 3.0, 0.2) * 0.2 + diversity_bonus)
            
            return min(1.0, quality_score)
            
        except Exception as e:
            self.logger.error(f"Error calculating quality score: {e}")
            return 0.5
    
    def smart_auto_scan(self,
                       raw_signals: List[Dict],
                       market_analysis: Dict,
                       regime_analysis: Dict,
                       volatility_metrics: Dict,
                       correlation_manager=None,
                       recent_performance: List[Dict] = None,
                       allow_zero_results: bool = True) -> AutoScanResult:
        """Perform smart auto-scan with quality filtering and circuit breaker."""
        
        warnings = []
        filters_applied = []
        
        # Check circuit breaker
        circuit_breaker_active, cb_triggers = self.check_circuit_breaker(
            recent_performance or [], 
            volatility_metrics.get('current_volatility', 1.0)
        )
        
        if circuit_breaker_active:
            warnings.extend([f"Circuit breaker: {trigger}" for trigger in cb_triggers])
            return AutoScanResult(
                signals=[],
                market_condition=MarketCondition.TERRIBLE,
                quality_score=0.0,
                filters_applied=["Circuit breaker activated"],
                rejected_signals={},
                warnings=warnings,
                circuit_breaker_active=True
            )
        
        # Assess market condition
        market_condition = self.assess_market_condition(
            market_analysis, regime_analysis, volatility_metrics
        )
        
        filters_applied.append(f"Market condition: {market_condition.value}")
        
        # Apply quality filtering
        filtered_signals, rejection_reasons = self.filter_signals_by_quality(
            raw_signals,
            market_condition,
            correlation_manager,
            force_minimum=not allow_zero_results
        )
        
        # Add filtering statistics
        filters_applied.append(f"Quality filter: {len(filtered_signals)}/{len(raw_signals)} passed")
        
        # Generate warnings for poor conditions
        if market_condition == MarketCondition.POOR:
            warnings.append("Poor market conditions detected - using strict filtering")
        elif market_condition == MarketCondition.TERRIBLE:
            warnings.append("Terrible market conditions - very high quality bar")
        
        # Warning if no signals meet criteria
        if not filtered_signals and raw_signals:
            if allow_zero_results:
                warnings.append(f"No signals meet quality thresholds for {market_condition.value} market")
            else:
                warnings.append("Forced to return signals below quality threshold")
        
        # Calculate portfolio quality
        quality_score = self.calculate_portfolio_quality_score(filtered_signals)
        
        # Add quality warning if below par
        if quality_score < 0.5:
            warnings.append(f"Low portfolio quality score: {quality_score:.2f}")
        
        return AutoScanResult(
            signals=filtered_signals,
            market_condition=market_condition,
            quality_score=quality_score,
            filters_applied=filters_applied,
            rejected_signals=rejection_reasons,
            warnings=warnings,
            circuit_breaker_active=False
        )
    
    def get_auto_scan_summary(self, result: AutoScanResult) -> str:
        """Generate human-readable summary of auto-scan results."""
        
        summary = f"🎯 Smart Auto-Scan Results\n"
        summary += f"Market Condition: {result.market_condition.value.upper()}\n"
        summary += f"Quality Score: {result.quality_score:.2f}/1.00\n"
        summary += f"Signals Returned: {len(result.signals)}\n\n"
        
        if result.circuit_breaker_active:
            summary += "🚨 CIRCUIT BREAKER ACTIVE - No trading allowed\n\n"
            return summary
        
        if result.warnings:
            summary += "⚠️ Warnings:\n"
            for warning in result.warnings:
                summary += f"• {warning}\n"
            summary += "\n"
        
        if not result.signals:
            summary += "❌ No signals meet current quality thresholds\n"
            summary += f"Consider manual review or wait for better market conditions\n"
        else:
            summary += f"✅ {len(result.signals)} high-quality signals selected\n"
            
            # Show top rejection reasons
            if result.rejected_signals:
                rejection_counts = {}
                for reasons in result.rejected_signals.values():
                    for reason in reasons:
                        category = reason.split(' ')[0]  # First word
                        rejection_counts[category] = rejection_counts.get(category, 0) + 1
                
                summary += "\n📊 Top rejection reasons:\n"
                for reason, count in sorted(rejection_counts.items(), 
                                          key=lambda x: x[1], reverse=True)[:3]:
                    summary += f"• {reason}: {count} signals\n"
        
        return summary
    
    def update_performance_tracking(self, trade_result: Dict) -> None:
        """Update recent performance tracking for circuit breaker."""
        self.recent_performance.append({
            'timestamp': datetime.now(),
            'symbol': trade_result.get('symbol'),
            'outcome': 'win' if trade_result.get('pnl_pct', 0) > 0 else 'loss',
            'pnl_pct': trade_result.get('pnl_pct', 0),
            'date': datetime.now().date()
        })
        
        # Keep only last 100 trades
        if len(self.recent_performance) > 100:
            self.recent_performance = self.recent_performance[-100:]