"""
Calibrated Safety Score System with Isotonic Regression
Replaces hardcoded win rate mapping with data-driven calibration.
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import brier_score_loss, calibration_curve
import json
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

@dataclass
class SafetyScoreRecord:
    """Record of a safety score and its outcome."""
    timestamp: datetime
    symbol: str
    timeframe: str
    safety_score: float
    signal_features: Dict[str, float]  # RSI, MACD, etc.
    market_regime: str
    outcome: Optional[bool] = None  # True=win, False=loss, None=pending
    profit_loss_pct: Optional[float] = None
    exit_reason: Optional[str] = None
    hold_duration_candles: Optional[int] = None

@dataclass
class CalibrationData:
    """Calibration model data and metadata."""
    isotonic_model: IsotonicRegression
    decile_boundaries: np.ndarray
    decile_win_rates: np.ndarray
    sample_counts: np.ndarray
    last_update: datetime
    brier_score: float
    calibration_error: float
    n_samples: int

class SafetyScoreCalibrator:
    """Calibrates safety scores to actual win probabilities using isotonic regression."""
    
    def __init__(self, min_samples_per_decile: int = 20, calibration_file: str = None):
        self.min_samples_per_decile = min_samples_per_decile
        self.calibration_file = calibration_file
        self.logger = logging.getLogger(__name__)
        
        # Historical records
        self.score_records: List[SafetyScoreRecord] = []
        
        # Calibration models by regime and timeframe
        self.calibration_models: Dict[str, Dict[str, CalibrationData]] = {}
        
        # Default hardcoded mapping as fallback
        self.default_score_to_winrate = {
            0.0: 0.45, 0.1: 0.48, 0.2: 0.51, 0.3: 0.54, 0.4: 0.57,
            0.5: 0.60, 0.6: 0.63, 0.7: 0.66, 0.8: 0.69, 0.9: 0.72, 1.0: 0.75
        }
        
        # Load existing calibration data
        self.load_calibration_data()
    
    def add_record(self, record: SafetyScoreRecord) -> None:
        """Add a new safety score record."""
        self.score_records.append(record)
        
        # Trigger recalibration if we have enough new records
        if len(self.score_records) % 50 == 0:  # Recalibrate every 50 records
            self.update_calibration()
    
    def update_outcome(self, symbol: str, timestamp: datetime, 
                      outcome: bool, profit_loss_pct: float, 
                      exit_reason: str = None, hold_duration: int = None) -> bool:
        """Update the outcome for an existing record."""
        for record in self.score_records:
            if (record.symbol == symbol and 
                abs((record.timestamp - timestamp).total_seconds()) < 300):  # 5min tolerance
                record.outcome = outcome
                record.profit_loss_pct = profit_loss_pct
                record.exit_reason = exit_reason
                record.hold_duration_candles = hold_duration
                return True
        
        self.logger.warning(f"Could not find record to update: {symbol} at {timestamp}")
        return False
    
    def get_completed_records(self, min_age_hours: int = 24) -> List[SafetyScoreRecord]:
        """Get records with known outcomes that are old enough to be complete."""
        cutoff_time = datetime.now() - timedelta(hours=min_age_hours)
        
        completed = [
            record for record in self.score_records
            if (record.outcome is not None and 
                record.timestamp < cutoff_time)
        ]
        
        return completed
    
    def calculate_decile_performance(self, records: List[SafetyScoreRecord]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Calculate win rates by safety score decile."""
        if len(records) < 20:
            return np.array([]), np.array([]), np.array([])
        
        scores = np.array([r.safety_score for r in records])
        outcomes = np.array([r.outcome for r in records])
        
        # Calculate decile boundaries
        decile_boundaries = np.percentile(scores, np.linspace(0, 100, 11))
        decile_win_rates = []
        sample_counts = []
        
        for i in range(10):
            lower = decile_boundaries[i]
            upper = decile_boundaries[i + 1]
            
            # Include records in this decile
            if i == 9:  # Last decile includes upper boundary
                mask = (scores >= lower) & (scores <= upper)
            else:
                mask = (scores >= lower) & (scores < upper)
            
            decile_outcomes = outcomes[mask]
            
            if len(decile_outcomes) >= 5:  # Minimum samples per decile
                win_rate = np.mean(decile_outcomes)
                decile_win_rates.append(win_rate)
                sample_counts.append(len(decile_outcomes))
            else:
                # Insufficient data - use interpolated value
                decile_win_rates.append(0.5 + i * 0.03)  # Linear progression
                sample_counts.append(0)
        
        return (np.array(decile_boundaries[:-1]),  # Use left boundaries
                np.array(decile_win_rates), 
                np.array(sample_counts))
    
    def fit_isotonic_regression(self, records: List[SafetyScoreRecord]) -> Optional[CalibrationData]:
        """Fit isotonic regression model to calibrate scores."""
        if len(records) < self.min_samples_per_decile * 5:  # Need minimum data
            return None
        
        try:
            scores = np.array([r.safety_score for r in records])
            outcomes = np.array([r.outcome for r in records], dtype=float)
            
            # Split into train/test for evaluation
            if len(records) > 100:
                X_train, X_test, y_train, y_test = train_test_split(
                    scores, outcomes, test_size=0.2, random_state=42
                )
            else:
                X_train, y_train = scores, outcomes
                X_test, y_test = scores, outcomes
            
            # Fit isotonic regression
            iso_reg = IsotonicRegression(out_of_bounds='clip')
            iso_reg.fit(X_train, y_train)
            
            # Calculate performance metrics
            y_pred = iso_reg.predict(X_test)
            brier_score = brier_score_loss(y_test, y_pred)
            
            # Calculate calibration error
            try:
                fraction_pos, mean_pred = calibration_curve(y_test, y_pred, n_bins=5)
                calibration_error = np.mean(np.abs(fraction_pos - mean_pred))
            except:
                calibration_error = 0.1  # Default if calculation fails
            
            # Calculate decile statistics for interpretability
            decile_boundaries, decile_win_rates, sample_counts = self.calculate_decile_performance(records)
            
            calibration_data = CalibrationData(
                isotonic_model=iso_reg,
                decile_boundaries=decile_boundaries,
                decile_win_rates=decile_win_rates,
                sample_counts=sample_counts,
                last_update=datetime.now(),
                brier_score=brier_score,
                calibration_error=calibration_error,
                n_samples=len(records)
            )
            
            self.logger.info(f"Fitted calibration model: {len(records)} samples, "
                           f"Brier={brier_score:.3f}, CalibError={calibration_error:.3f}")
            
            return calibration_data
            
        except Exception as e:
            self.logger.error(f"Error fitting isotonic regression: {e}")
            return None
    
    def update_calibration(self) -> None:
        """Update calibration models for all regime/timeframe combinations."""
        completed_records = self.get_completed_records()
        
        if len(completed_records) < 50:
            self.logger.info(f"Too few completed records ({len(completed_records)}) for calibration")
            return
        
        # Group by regime and timeframe
        groups = {}
        for record in completed_records:
            key = f"{record.market_regime}_{record.timeframe}"
            if key not in groups:
                groups[key] = []
            groups[key].append(record)
        
        # Update calibration for each group
        updated_count = 0
        for group_key, group_records in groups.items():
            if len(group_records) >= self.min_samples_per_decile * 3:
                regime, timeframe = group_key.split('_', 1)
                
                calibration_data = self.fit_isotonic_regression(group_records)
                if calibration_data:
                    if regime not in self.calibration_models:
                        self.calibration_models[regime] = {}
                    self.calibration_models[regime][timeframe] = calibration_data
                    updated_count += 1
        
        if updated_count > 0:
            self.logger.info(f"Updated {updated_count} calibration models")
            self.save_calibration_data()
    
    def get_calibrated_win_rate(self, safety_score: float, 
                               market_regime: str = 'NEUTRAL',
                               timeframe: str = '5m') -> float:
        """Get calibrated win rate for a safety score."""
        
        # Try to use calibrated model
        if (market_regime in self.calibration_models and 
            timeframe in self.calibration_models[market_regime]):
            
            calibration_data = self.calibration_models[market_regime][timeframe]
            try:
                calibrated_rate = calibration_data.isotonic_model.predict([safety_score])[0]
                # Ensure reasonable bounds
                calibrated_rate = max(0.3, min(0.85, calibrated_rate))
                return calibrated_rate
            except Exception as e:
                self.logger.warning(f"Error using calibrated model: {e}")
        
        # Fallback to regime-specific default
        regime_adjustment = self._get_regime_adjustment(market_regime)
        base_rate = self._interpolate_default_rate(safety_score)
        
        adjusted_rate = base_rate * regime_adjustment
        return max(0.3, min(0.85, adjusted_rate))
    
    def _get_regime_adjustment(self, regime: str) -> float:
        """Get win rate adjustment factor for market regime."""
        adjustments = {
            'BULL': 1.1,        # Bull markets have higher win rates
            'BEAR': 0.9,        # Bear markets have lower win rates  
            'NEUTRAL': 1.0,     # No adjustment
            'VOLATILE': 0.95,   # Volatile markets slightly lower
            'TRENDING': 1.05    # Trending markets slightly higher
        }
        return adjustments.get(regime, 1.0)
    
    def _interpolate_default_rate(self, safety_score: float) -> float:
        """Interpolate win rate from default mapping."""
        score_keys = sorted(self.default_score_to_winrate.keys())
        
        if safety_score <= score_keys[0]:
            return self.default_score_to_winrate[score_keys[0]]
        if safety_score >= score_keys[-1]:
            return self.default_score_to_winrate[score_keys[-1]]
        
        # Linear interpolation
        for i in range(len(score_keys) - 1):
            if score_keys[i] <= safety_score <= score_keys[i + 1]:
                lower_score, upper_score = score_keys[i], score_keys[i + 1]
                lower_rate = self.default_score_to_winrate[lower_score]
                upper_rate = self.default_score_to_winrate[upper_score]
                
                ratio = (safety_score - lower_score) / (upper_score - lower_score)
                return lower_rate + ratio * (upper_rate - lower_rate)
        
        return 0.6  # Default fallback
    
    def get_calibration_quality(self, market_regime: str = 'NEUTRAL', 
                               timeframe: str = '5m') -> Dict[str, Any]:
        """Get calibration model quality metrics."""
        if (market_regime not in self.calibration_models or 
            timeframe not in self.calibration_models[market_regime]):
            return {
                'status': 'no_model',
                'using_defaults': True
            }
        
        calibration_data = self.calibration_models[market_regime][timeframe]
        
        return {
            'status': 'calibrated',
            'using_defaults': False,
            'n_samples': calibration_data.n_samples,
            'brier_score': calibration_data.brier_score,
            'calibration_error': calibration_data.calibration_error,
            'last_update': calibration_data.last_update.isoformat(),
            'decile_win_rates': calibration_data.decile_win_rates.tolist(),
            'sample_counts': calibration_data.sample_counts.tolist()
        }
    
    def save_calibration_data(self) -> None:
        """Save calibration data to file."""
        if not self.calibration_file:
            return
        
        try:
            # Prepare data for JSON serialization
            save_data = {
                'models': {},
                'records_count': len(self.score_records),
                'last_save': datetime.now().isoformat()
            }
            
            for regime, timeframes in self.calibration_models.items():
                save_data['models'][regime] = {}
                for timeframe, calibration_data in timeframes.items():
                    save_data['models'][regime][timeframe] = {
                        'decile_boundaries': calibration_data.decile_boundaries.tolist(),
                        'decile_win_rates': calibration_data.decile_win_rates.tolist(),
                        'sample_counts': calibration_data.sample_counts.tolist(),
                        'last_update': calibration_data.last_update.isoformat(),
                        'brier_score': calibration_data.brier_score,
                        'calibration_error': calibration_data.calibration_error,
                        'n_samples': calibration_data.n_samples
                    }
            
            with open(self.calibration_file, 'w') as f:
                json.dump(save_data, f, indent=2)
            
            self.logger.info(f"Saved calibration data to {self.calibration_file}")
            
        except Exception as e:
            self.logger.error(f"Error saving calibration data: {e}")
    
    def load_calibration_data(self) -> None:
        """Load calibration data from file."""
        if not self.calibration_file or not os.path.exists(self.calibration_file):
            return
        
        try:
            with open(self.calibration_file, 'r') as f:
                save_data = json.load(f)
            
            # Reconstruct calibration models (without isotonic regression objects)
            # We'll rebuild those on next update
            for regime, timeframes in save_data.get('models', {}).items():
                self.calibration_models[regime] = {}
                for timeframe, data in timeframes.items():
                    # Create placeholder calibration data
                    calibration_data = CalibrationData(
                        isotonic_model=IsotonicRegression(),  # Placeholder
                        decile_boundaries=np.array(data['decile_boundaries']),
                        decile_win_rates=np.array(data['decile_win_rates']),
                        sample_counts=np.array(data['sample_counts']),
                        last_update=datetime.fromisoformat(data['last_update']),
                        brier_score=data['brier_score'],
                        calibration_error=data['calibration_error'],
                        n_samples=data['n_samples']
                    )
                    
                    self.calibration_models[regime][timeframe] = calibration_data
            
            self.logger.info(f"Loaded calibration data from {self.calibration_file}")
            
        except Exception as e:
            self.logger.error(f"Error loading calibration data: {e}")
    
    def get_summary(self) -> str:
        """Get summary of calibration system status."""
        total_records = len(self.score_records)
        completed_records = len(self.get_completed_records())
        
        model_count = sum(len(timeframes) for timeframes in self.calibration_models.values())
        
        summary = f"Safety Score Calibration Summary:\n"
        summary += f"Total records: {total_records}\n"
        summary += f"Completed records: {completed_records}\n"
        summary += f"Calibration models: {model_count}\n\n"
        
        if model_count > 0:
            summary += "Model Quality:\n"
            for regime, timeframes in self.calibration_models.items():
                for timeframe, calibration_data in timeframes.items():
                    summary += f"  {regime}/{timeframe}: {calibration_data.n_samples} samples, "
                    summary += f"Brier={calibration_data.brier_score:.3f}, "
                    summary += f"CalibError={calibration_data.calibration_error:.3f}\n"
        else:
            summary += "Using default hardcoded mappings (no calibration data yet)\n"
        
        return summary

# Global calibrator instance
_global_calibrator: Optional[SafetyScoreCalibrator] = None

def get_safety_score_calibrator(calibration_file: str = None) -> SafetyScoreCalibrator:
    """Get global safety score calibrator."""
    global _global_calibrator
    if _global_calibrator is None:
        default_file = calibration_file or "safety_score_calibration.json"
        _global_calibrator = SafetyScoreCalibrator(calibration_file=default_file)
    return _global_calibrator