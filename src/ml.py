"""
Machine Learning Pipeline for Trading Insight.
Provides feature processing, model training, and prediction capabilities.
"""

import pickle
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Any

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    mean_squared_error, mean_absolute_error, r2_score
)
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.pipeline import Pipeline

from .utils import get_logger, ensure_dir
from .features import FeatureEngineer
from .indicators import TechnicalIndicators

logger = get_logger(__name__)

# Suppress sklearn warnings
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")


@dataclass
class MLConfig:
    """Configuration for machine learning pipeline."""
    
    # Model selection
    model_type: str = "random_forest"  # random_forest, logistic, ridge
    task_type: str = "classification"  # classification, regression
    
    # Feature processing
    scaler_type: str = "standard"  # standard, robust, none
    feature_selection: bool = True
    max_features: Optional[int] = 50
    
    # Model parameters
    model_params: Dict[str, Any] = field(default_factory=dict)
    
    # Training
    test_size: float = 0.2
    cv_folds: int = 5
    random_state: int = 42
    
    # Prediction
    prediction_horizon: int = 24  # hours ahead
    confidence_threshold: float = 0.6
    
    # Model persistence
    model_dir: str = "models"
    auto_save: bool = True
    
    def __post_init__(self):
        """Set default model parameters."""
        if not self.model_params:
            if self.model_type == "random_forest":
                self.model_params = {
                    "n_estimators": 100,
                    "max_depth": 10,
                    "min_samples_split": 20,
                    "min_samples_leaf": 10,
                    "random_state": self.random_state,
                    "n_jobs": -1
                }
            elif self.model_type == "logistic":
                self.model_params = {
                    "random_state": self.random_state,
                    "max_iter": 1000,
                    "class_weight": "balanced"
                }
            elif self.model_type == "ridge":
                self.model_params = {
                    "alpha": 1.0,
                    "random_state": self.random_state
                }


@dataclass 
class MLResults:
    """Results from machine learning pipeline."""
    
    model_name: str
    task_type: str
    train_score: float
    test_score: float
    cv_scores: List[float]
    cv_mean: float
    cv_std: float
    feature_importance: Optional[Dict[str, float]] = None
    predictions: Optional[pd.Series] = None
    model_path: Optional[str] = None
    training_time: float = 0.0
    n_features: int = 0
    
    @property
    def summary(self) -> Dict[str, Any]:
        """Get summary of results."""
        return {
            "model_name": self.model_name,
            "task_type": self.task_type,
            "train_score": self.train_score,
            "test_score": self.test_score,
            "cv_mean": self.cv_mean,
            "cv_std": self.cv_std,
            "n_features": self.n_features,
            "training_time": self.training_time
        }


class FeatureProcessor(BaseEstimator, TransformerMixin):
    """Custom feature processor for financial data."""
    
    def __init__(self, 
                 scaler_type: str = "standard",
                 feature_selection: bool = True, 
                 max_features: Optional[int] = 50,
                 correlation_threshold: float = 0.95):
        self.scaler_type = scaler_type
        self.feature_selection = feature_selection
        self.max_features = max_features
        self.correlation_threshold = correlation_threshold
        
        # Components
        self.scaler = None
        self.selected_features = None
        self.feature_stats = {}
        
    def fit(self, X: pd.DataFrame, y: Optional[pd.Series] = None):
        """Fit the processor."""
        logger.info(f"Fitting feature processor on {X.shape[0]} samples, {X.shape[1]} features")
        
        # Initialize scaler
        if self.scaler_type == "standard":
            self.scaler = StandardScaler()
        elif self.scaler_type == "robust":
            self.scaler = RobustScaler()
        else:
            self.scaler = None
            
        # Remove constant features
        X_processed = self._remove_constant_features(X)
        
        # Remove highly correlated features
        if self.feature_selection:
            X_processed = self._remove_correlated_features(X_processed)
            
        # Feature selection by importance (if target is provided)
        if self.feature_selection and y is not None and self.max_features:
            X_processed = self._select_important_features(X_processed, y)
            
        # Fit scaler on processed features
        if self.scaler is not None:
            self.scaler.fit(X_processed)
            
        # Store selected features
        self.selected_features = X_processed.columns.tolist()
        
        # Store feature statistics
        self._compute_feature_stats(X_processed)
        
        logger.info(f"Feature processor fitted with {len(self.selected_features)} features")
        return self
        
    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """Transform features."""
        # Select features
        X_processed = X[self.selected_features].copy()
        
        # Handle missing values
        X_processed = self._handle_missing_values(X_processed)
        
        # Scale features
        if self.scaler is not None:
            X_scaled = self.scaler.transform(X_processed)
            X_processed = pd.DataFrame(
                X_scaled, 
                index=X_processed.index,
                columns=X_processed.columns
            )
            
        return X_processed
        
    def _remove_constant_features(self, X: pd.DataFrame) -> pd.DataFrame:
        """Remove features with constant values."""
        constant_features = []
        for col in X.columns:
            if X[col].nunique() <= 1:
                constant_features.append(col)
                
        if constant_features:
            logger.info(f"Removing {len(constant_features)} constant features")
            X = X.drop(columns=constant_features)
            
        return X
        
    def _remove_correlated_features(self, X: pd.DataFrame) -> pd.DataFrame:
        """Remove highly correlated features."""
        corr_matrix = X.corr().abs()
        upper = corr_matrix.where(
            np.triu(np.ones_like(corr_matrix, dtype=bool), k=1)
        )
        
        to_drop = [column for column in upper.columns if any(upper[column] > self.correlation_threshold)]
        
        if to_drop:
            logger.info(f"Removing {len(to_drop)} highly correlated features")
            X = X.drop(columns=to_drop)
            
        return X
        
    def _select_important_features(self, X: pd.DataFrame, y: pd.Series) -> pd.DataFrame:
        """Select most important features using random forest."""
        if len(X.columns) <= self.max_features:
            return X
            
        # Use random forest for feature importance
        if y.dtype == 'object' or y.nunique() < 10:
            model = RandomForestClassifier(n_estimators=50, random_state=42, n_jobs=-1)
        else:
            model = RandomForestRegressor(n_estimators=50, random_state=42, n_jobs=-1)
            
        # Handle missing values for feature selection
        X_clean = self._handle_missing_values(X)
        y_clean = y.loc[X_clean.index]
        
        model.fit(X_clean, y_clean)
        
        # Get feature importance
        importance_df = pd.DataFrame({
            'feature': X.columns,
            'importance': model.feature_importances_
        }).sort_values('importance', ascending=False)
        
        # Select top features
        selected = importance_df.head(self.max_features)['feature'].tolist()
        
        logger.info(f"Selected {len(selected)} most important features")
        return X[selected]
        
    def _handle_missing_values(self, X: pd.DataFrame) -> pd.DataFrame:
        """Handle missing values."""
        # Forward fill then backward fill
        X_filled = X.fillna(method='ffill').fillna(method='bfill')
        
        # If still missing, fill with median
        if X_filled.isnull().any().any():
            X_filled = X_filled.fillna(X_filled.median())
            
        # If still missing, fill with 0
        X_filled = X_filled.fillna(0)
        
        return X_filled
        
    def _compute_feature_stats(self, X: pd.DataFrame):
        """Compute feature statistics."""
        self.feature_stats = {
            'n_features': len(X.columns),
            'mean': X.mean().to_dict(),
            'std': X.std().to_dict(),
            'missing_pct': (X.isnull().mean() * 100).to_dict()
        }


class MLPipeline:
    """Machine Learning Pipeline for trading signals."""
    
    def __init__(self, config: MLConfig):
        self.config = config
        self.processor = None
        self.model = None
        self.pipeline = None
        self.is_fitted = False
        
        # Initialize components
        self._initialize_components()
        
    def _initialize_components(self):
        """Initialize ML components."""
        # Feature processor
        self.processor = FeatureProcessor(
            scaler_type=self.config.scaler_type,
            feature_selection=self.config.feature_selection,
            max_features=self.config.max_features
        )
        
        # Model
        if self.config.model_type == "random_forest":
            if self.config.task_type == "classification":
                self.model = RandomForestClassifier(**self.config.model_params)
            else:
                self.model = RandomForestRegressor(**self.config.model_params)
        elif self.config.model_type == "logistic":
            self.model = LogisticRegression(**self.config.model_params)
        elif self.config.model_type == "ridge":
            self.model = Ridge(**self.config.model_params)
        else:
            raise ValueError(f"Unsupported model type: {self.config.model_type}")
            
        # Create pipeline
        self.pipeline = Pipeline([
            ('processor', self.processor),
            ('model', self.model)
        ])
        
    def prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare features for training."""
        logger.info("Preparing features for ML pipeline")
        
        # Initialize feature engineer
        feature_config = {
            'price_features': True,
            'volume_features': True, 
            'volatility_features': True,
            'trend_features': True,
            'momentum_features': True,
            'mean_reversion_features': True,
            'pattern_features': True,
            'microstructure_features': True,
            'regime_features': True,
            'cross_asset_features': False,
            'calendar_features': True
        }
        
        feature_engineer = FeatureEngineer(feature_config)
        
        # Create features
        df_features = feature_engineer.create_features(df)
        
        # Remove rows with insufficient data for indicators
        min_periods = 50  # Minimum periods for indicators
        df_features = df_features.iloc[min_periods:].copy()
        
        logger.info(f"Created {df_features.shape[1]} features for {df_features.shape[0]} samples")
        return df_features
        
    def prepare_targets(self, df: pd.DataFrame, df_features: pd.DataFrame) -> pd.Series:
        """Prepare target variable."""
        logger.info(f"Preparing targets for {self.config.task_type}")
        
        if self.config.task_type == "classification":
            # Classification: predict future price direction
            horizon = self.config.prediction_horizon
            returns = df['close'].pct_change(horizon).shift(-horizon)
            
            # Create binary labels
            targets = (returns > 0).astype(int)
            targets = targets.loc[df_features.index]
            
        else:
            # Regression: predict future returns
            horizon = self.config.prediction_horizon
            returns = df['close'].pct_change(horizon).shift(-horizon)
            targets = returns.loc[df_features.index]
            
        # Remove NaN values
        valid_mask = ~targets.isnull()
        targets = targets[valid_mask]
        
        logger.info(f"Prepared {len(targets)} target samples")
        return targets
        
    def train(self, df: pd.DataFrame) -> MLResults:
        """Train the ML model."""
        logger.info("Starting ML model training")
        start_time = pd.Timestamp.now()
        
        # Prepare features and targets
        df_features = self.prepare_features(df)
        targets = self.prepare_targets(df, df_features)
        
        # Align features and targets
        common_index = df_features.index.intersection(targets.index)
        X = df_features.loc[common_index]
        y = targets.loc[common_index]
        
        # Remove any remaining NaN values
        valid_mask = ~(X.isnull().any(axis=1) | y.isnull())
        X = X[valid_mask]
        y = y[valid_mask]
        
        logger.info(f"Training on {len(X)} samples with {X.shape[1]} features")
        
        # Time series split for validation
        tscv = TimeSeriesSplit(n_splits=self.config.cv_folds)
        
        # Cross-validation
        if self.config.task_type == "classification":
            cv_scores = cross_val_score(self.pipeline, X, y, cv=tscv, scoring='accuracy')
        else:
            cv_scores = cross_val_score(self.pipeline, X, y, cv=tscv, scoring='neg_mean_squared_error')
            cv_scores = -cv_scores  # Convert to positive MSE
            
        # Train-test split (time-based)
        split_idx = int(len(X) * (1 - self.config.test_size))
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
        
        # Fit the model
        self.pipeline.fit(X_train, y_train)
        self.is_fitted = True
        
        # Evaluate
        train_pred = self.pipeline.predict(X_train)
        test_pred = self.pipeline.predict(X_test)
        
        if self.config.task_type == "classification":
            train_score = accuracy_score(y_train, train_pred)
            test_score = accuracy_score(y_test, test_pred)
        else:
            train_score = r2_score(y_train, train_pred)
            test_score = r2_score(y_test, test_pred)
            
        # Get feature importance
        feature_importance = None
        if hasattr(self.pipeline.named_steps['model'], 'feature_importances_'):
            selected_features = self.pipeline.named_steps['processor'].selected_features
            importance_values = self.pipeline.named_steps['model'].feature_importances_
            feature_importance = dict(zip(selected_features, importance_values))
            
        # Save model if configured
        model_path = None
        if self.config.auto_save:
            model_path = self._save_model()
            
        # Create results
        training_time = (pd.Timestamp.now() - start_time).total_seconds()
        
        results = MLResults(
            model_name=f"{self.config.model_type}_{self.config.task_type}",
            task_type=self.config.task_type,
            train_score=train_score,
            test_score=test_score,
            cv_scores=cv_scores.tolist(),
            cv_mean=cv_scores.mean(),
            cv_std=cv_scores.std(),
            feature_importance=feature_importance,
            predictions=pd.Series(test_pred, index=X_test.index),
            model_path=model_path,
            training_time=training_time,
            n_features=len(self.pipeline.named_steps['processor'].selected_features)
        )
        
        logger.info(f"Training completed in {training_time:.2f}s")
        logger.info(f"Train score: {train_score:.4f}, Test score: {test_score:.4f}")
        logger.info(f"CV score: {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")
        
        return results
        
    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """Make predictions on new data."""
        if not self.is_fitted:
            raise ValueError("Model must be trained before making predictions")
            
        # Prepare features
        df_features = self.prepare_features(df)
        
        # Make predictions
        predictions = self.pipeline.predict(df_features)
        
        # Get prediction probabilities for classification
        if self.config.task_type == "classification" and hasattr(self.pipeline, 'predict_proba'):
            probabilities = self.pipeline.predict_proba(df_features)
            max_proba = probabilities.max(axis=1)
            
            # Apply confidence threshold
            confident_mask = max_proba >= self.config.confidence_threshold
            predictions[~confident_mask] = 0  # Neutral signal for low confidence
            
            results_df = pd.DataFrame({
                'prediction': predictions,
                'confidence': max_proba,
                'signal': np.where(
                    confident_mask,
                    np.where(predictions == 1, 1, -1),
                    0
                )
            }, index=df_features.index)
            
        else:
            results_df = pd.DataFrame({
                'prediction': predictions,
                'signal': np.sign(predictions)
            }, index=df_features.index)
            
        return results_df
        
    def _save_model(self) -> str:
        """Save the trained model."""
        model_dir = Path(self.config.model_dir)
        ensure_dir(model_dir)
        
        # Create filename with timestamp
        timestamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.config.model_type}_{self.config.task_type}_{timestamp}.pkl"
        filepath = model_dir / filename
        
        # Save model and config
        model_data = {
            'pipeline': self.pipeline,
            'config': self.config,
            'fitted': self.is_fitted,
            'timestamp': timestamp
        }
        
        with open(filepath, 'wb') as f:
            pickle.dump(model_data, f)
            
        logger.info(f"Model saved to {filepath}")
        return str(filepath)
        
    def load_model(self, model_path: str):
        """Load a trained model."""
        with open(model_path, 'rb') as f:
            model_data = pickle.load(f)
            
        self.pipeline = model_data['pipeline']
        self.config = model_data['config']
        self.is_fitted = model_data['fitted']
        
        # Update components from loaded pipeline
        self.processor = self.pipeline.named_steps['processor']
        self.model = self.pipeline.named_steps['model']
        
        logger.info(f"Model loaded from {model_path}")
        
    def get_feature_importance(self, top_n: int = 20) -> pd.DataFrame:
        """Get feature importance from trained model."""
        if not self.is_fitted:
            raise ValueError("Model must be trained first")
            
        if not hasattr(self.pipeline.named_steps['model'], 'feature_importances_'):
            raise ValueError("Model does not support feature importance")
            
        selected_features = self.pipeline.named_steps['processor'].selected_features
        importance_values = self.pipeline.named_steps['model'].feature_importances_
        
        importance_df = pd.DataFrame({
            'feature': selected_features,
            'importance': importance_values
        }).sort_values('importance', ascending=False)
        
        return importance_df.head(top_n)


def create_ml_pipeline(config: Dict[str, Any]) -> MLPipeline:
    """Factory function to create ML pipeline from config."""
    ml_config = MLConfig(**config)
    return MLPipeline(ml_config)