"""
Data loading and processing module.
Handles OHLCV data from multiple sources with timezone normalization and quality control.
"""

import logging
import os
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import ccxt
import numpy as np
import pandas as pd
import pytz
from scipy import stats

from .utils import get_logger

warnings.filterwarnings("ignore", category=FutureWarning)

logger = get_logger(__name__)


class DataLoader:
    """
    Handles data loading from multiple sources with quality control.
    
    Supports:
    - CCXT exchanges (Binance, Bybit, etc.)
    - CSV files for XAUUSD and other instruments
    - Data caching and quality validation
    """
    
    def __init__(self, config: Dict):
        """
        Initialize data loader with configuration.
        
        Args:
            config: Configuration dictionary containing data settings
        """
        self.config = config
        self.data_dir = Path(config.get("data_dir", "data"))
        self.raw_dir = self.data_dir / "raw"
        self.processed_dir = self.data_dir / "processed"
        self.cache_dir = self.data_dir / "cache"
        
        # Create directories if they don't exist
        for dir_path in [self.raw_dir, self.processed_dir, self.cache_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
            
        # Initialize exchange connections
        self.exchanges = {}
        self._init_exchanges()
        
        # Data quality control settings
        self.quality_config = config.get("data_quality", {})
        self.outlier_method = self.quality_config.get("outlier_detection", "iqr")
        self.outlier_threshold = self.quality_config.get("outlier_threshold", 3.0)
        self.fill_method = self.quality_config.get("gap_fill_method", "forward")
        self.max_gap_size = self.quality_config.get("max_gap_size_minutes", 60)
        
    def _init_exchanges(self) -> None:
        """Initialize exchange connections from config."""
        exchange_configs = self.config.get("exchanges", {})
        
        for name, config in exchange_configs.items():
            try:
                if name.lower() == "binance":
                    exchange_class = ccxt.binance
                elif name.lower() == "bybit":
                    exchange_class = ccxt.bybit
                else:
                    logger.warning(f"Unsupported exchange: {name}")
                    continue
                    
                exchange = exchange_class({
                    'apiKey': config.get('api_key', ''),
                    'secret': config.get('secret', ''),
                    'sandbox': config.get('sandbox', True),
                    'enableRateLimit': True,
                    'timeout': 30000,
                })
                
                self.exchanges[name] = exchange
                logger.info(f"Initialized {name} exchange (sandbox: {config.get('sandbox', True)})")
                
            except Exception as e:
                logger.error(f"Failed to initialize {name} exchange: {e}")
    
    def load_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: Optional[Union[str, datetime]] = None,
        to: Optional[Union[str, datetime]] = None,
        exchange: str = "binance",
        force_reload: bool = False
    ) -> pd.DataFrame:
        """
        Load OHLCV data for a symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            timeframe: Timeframe string (e.g., '1h', '4h', '1d')
            since: Start date/time
            to: End date/time
            exchange: Exchange name
            force_reload: Force reload from source, ignore cache
            
        Returns:
            DataFrame with OHLCV data
        """
        # Handle special case for XAUUSD
        if symbol == "XAUUSD":
            return self._load_xauusd(timeframe, since, to, force_reload)
            
        # Check cache first
        cache_file = self._get_cache_filename(symbol, timeframe, exchange, since, to)
        if not force_reload and cache_file.exists():
            logger.info(f"Loading {symbol} data from cache: {cache_file}")
            try:
                df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
                return self._post_process_ohlcv(df)
            except Exception as e:
                logger.warning(f"Failed to load from cache: {e}")
                
        # Load from exchange
        if exchange not in self.exchanges:
            raise ValueError(f"Exchange '{exchange}' not configured")
            
        logger.info(f"Loading {symbol} data from {exchange} exchange")
        df = self._fetch_from_exchange(symbol, timeframe, since, to, exchange)
        
        # Cache the data
        df.to_csv(cache_file)
        logger.info(f"Cached data to: {cache_file}")
        
        return self._post_process_ohlcv(df)
    
    def _fetch_from_exchange(
        self,
        symbol: str,
        timeframe: str,
        since: Optional[Union[str, datetime]],
        to: Optional[Union[str, datetime]],
        exchange: str
    ) -> pd.DataFrame:
        """Fetch OHLCV data from exchange via CCXT."""
        exchange_obj = self.exchanges[exchange]
        
        # Convert dates to timestamps
        since_ts = self._parse_datetime(since) if since else None
        to_ts = self._parse_datetime(to) if to else None
        
        all_data = []
        current_since = since_ts
        
        while True:
            try:
                # Fetch batch of data
                ohlcv = exchange_obj.fetch_ohlcv(
                    symbol,
                    timeframe,
                    since=current_since,
                    limit=1000
                )
                
                if not ohlcv:
                    break
                    
                # Convert to DataFrame
                df_batch = pd.DataFrame(
                    ohlcv,
                    columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                )
                
                # Filter by end date if specified
                if to_ts:
                    df_batch = df_batch[df_batch['timestamp'] <= to_ts]
                    
                all_data.append(df_batch)
                
                # Check if we've reached the end
                if to_ts and df_batch['timestamp'].iloc[-1] >= to_ts:
                    break
                    
                # Update since for next batch
                current_since = df_batch['timestamp'].iloc[-1] + 1
                
            except ccxt.BaseError as e:
                logger.error(f"Exchange error: {e}")
                break
                
        if not all_data:
            raise ValueError(f"No data found for {symbol} on {exchange}")
            
        # Combine all batches
        df = pd.concat(all_data, ignore_index=True)
        df.drop_duplicates(subset=['timestamp'], inplace=True)
        df.sort_values('timestamp', inplace=True)
        
        # Convert timestamp to datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
        df.set_index('timestamp', inplace=True)
        
        return df
    
    def _load_xauusd(
        self,
        timeframe: str,
        since: Optional[Union[str, datetime]],
        to: Optional[Union[str, datetime]],
        force_reload: bool
    ) -> pd.DataFrame:
        """
        Load XAUUSD data from CSV or simulate data.
        For demonstration, we'll create a simple gold price simulation.
        In production, you'd connect to a real gold price data source.
        """
        cache_file = self._get_cache_filename("XAUUSD", timeframe, "simulated", since, to)
        
        if not force_reload and cache_file.exists():
            logger.info(f"Loading XAUUSD data from cache: {cache_file}")
            try:
                df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
                return self._post_process_ohlcv(df)
            except Exception as e:
                logger.warning(f"Failed to load XAUUSD from cache: {e}")
        
        # Check for CSV file in raw data
        csv_file = self.raw_dir / "XAUUSD.csv"
        if csv_file.exists():
            logger.info(f"Loading XAUUSD from CSV: {csv_file}")
            df = pd.read_csv(csv_file)
            
            # Standardize column names
            df.columns = df.columns.str.lower()
            required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            
            # Map common column variations
            column_mapping = {
                'time': 'timestamp',
                'datetime': 'timestamp',
                'date': 'timestamp',
                'vol': 'volume',
            }
            
            df.rename(columns=column_mapping, inplace=True)
            
            # Ensure all required columns exist
            for col in required_cols:
                if col not in df.columns:
                    if col == 'volume':
                        df[col] = 0  # Default volume for XAUUSD if not provided
                    else:
                        raise ValueError(f"Required column '{col}' not found in XAUUSD CSV")
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
            df.set_index('timestamp', inplace=True)
            
        else:
            # Simulate XAUUSD data for demonstration
            logger.warning("No XAUUSD CSV found, generating simulated data")
            df = self._simulate_xauusd(timeframe, since, to)
        
        # Resample to requested timeframe if needed
        df = self._resample_data(df, timeframe)
        
        # Cache the processed data
        df.to_csv(cache_file)
        
        return self._post_process_ohlcv(df)
    
    def _simulate_xauusd(
        self,
        timeframe: str,
        since: Optional[Union[str, datetime]],
        to: Optional[Union[str, datetime]]
    ) -> pd.DataFrame:
        """Generate simulated XAUUSD data for demonstration purposes."""
        start_date = self._parse_datetime(since) if since else datetime(2021, 1, 1, tzinfo=timezone.utc)
        end_date = self._parse_datetime(to) if to else datetime.now(timezone.utc)
        
        # Convert to pandas datetime
        start_date = pd.to_datetime(start_date, utc=True)
        end_date = pd.to_datetime(end_date, utc=True)
        
        # Create time index based on timeframe
        timeframe_minutes = self._timeframe_to_minutes(timeframe)
        freq = f"{timeframe_minutes}T"
        
        date_range = pd.date_range(start=start_date, end=end_date, freq=freq)
        
        # Simulate gold price around $2000 with realistic volatility
        np.random.seed(42)  # For reproducibility
        n_periods = len(date_range)
        
        # Gold price parameters
        initial_price = 2000.0
        drift = 0.0001  # Small positive drift
        volatility = 0.01  # 1% daily volatility
        
        # Generate random returns
        dt = timeframe_minutes / (24 * 60)  # Time step in days
        returns = np.random.normal(
            drift * dt,
            volatility * np.sqrt(dt),
            n_periods
        )
        
        # Create price series
        prices = [initial_price]
        for ret in returns[1:]:
            prices.append(prices[-1] * (1 + ret))
        
        prices = np.array(prices)
        
        # Create OHLC data with some intrabar movement
        noise = np.random.normal(0, 0.002, n_periods)  # Small noise for OHLC spread
        
        opens = prices
        highs = prices * (1 + np.abs(noise) + 0.001)
        lows = prices * (1 - np.abs(noise) - 0.001)
        closes = prices * (1 + noise * 0.5)
        
        # Ensure OHLC relationships are maintained
        for i in range(len(prices)):
            high_val = max(opens[i], highs[i], lows[i], closes[i])
            low_val = min(opens[i], highs[i], lows[i], closes[i])
            highs[i] = high_val
            lows[i] = low_val
        
        # Create volume (simulated)
        volumes = np.random.lognormal(8, 1, n_periods)  # Log-normal distribution
        
        df = pd.DataFrame({
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volumes
        }, index=date_range)
        
        return df
    
    def _post_process_ohlcv(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply post-processing steps to OHLCV data."""
        # Ensure index is timezone-aware UTC
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC')
        elif df.index.tz != pytz.UTC:
            df.index = df.index.tz_convert('UTC')
        
        # Sort by timestamp
        df = df.sort_index()
        
        # Remove duplicates
        df = df[~df.index.duplicated(keep='first')]
        
        # Apply data quality controls
        if self.quality_config.get("remove_outliers", True):
            df = self._remove_outliers(df)
            
        if self.quality_config.get("fill_gaps", True):
            df = self._fill_gaps(df)
            
        # Ensure positive prices
        price_cols = ['open', 'high', 'low', 'close']
        for col in price_cols:
            if col in df.columns:
                df[col] = df[col].clip(lower=0.001)  # Minimum price
        
        # Ensure volume is non-negative
        if 'volume' in df.columns:
            df['volume'] = df['volume'].clip(lower=0)
        
        return df
    
    def _remove_outliers(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove price outliers using specified method."""
        price_cols = ['open', 'high', 'low', 'close']
        
        for col in price_cols:
            if col not in df.columns:
                continue
                
            if self.outlier_method == "iqr":
                Q1 = df[col].quantile(0.25)
                Q3 = df[col].quantile(0.75)
                IQR = Q3 - Q1
                lower_bound = Q1 - self.outlier_threshold * IQR
                upper_bound = Q3 + self.outlier_threshold * IQR
                
            elif self.outlier_method == "zscore":
                mean = df[col].mean()
                std = df[col].std()
                lower_bound = mean - self.outlier_threshold * std
                upper_bound = mean + self.outlier_threshold * std
                
            else:
                continue
            
            # Mark outliers
            outliers = (df[col] < lower_bound) | (df[col] > upper_bound)
            n_outliers = outliers.sum()
            
            if n_outliers > 0:
                logger.info(f"Removing {n_outliers} outliers from {col}")
                # Replace outliers with forward fill
                df.loc[outliers, col] = np.nan
                df[col] = df[col].fillna(method='ffill')
        
        return df
    
    def _fill_gaps(self, df: pd.DataFrame) -> pd.DataFrame:
        """Fill data gaps using specified method."""
        if len(df) < 2:
            return df
            
        # Detect gaps in the index
        expected_freq = pd.infer_freq(df.index[:min(10, len(df))])
        if expected_freq is None:
            logger.warning("Could not infer data frequency, skipping gap filling")
            return df
        
        # Reindex to fill gaps
        full_index = pd.date_range(
            start=df.index[0],
            end=df.index[-1],
            freq=expected_freq,
            tz=df.index.tz
        )
        
        missing_periods = len(full_index) - len(df)
        if missing_periods > 0:
            logger.info(f"Filling {missing_periods} missing data points")
            df = df.reindex(full_index)
            
            if self.fill_method == "forward":
                df = df.fillna(method='ffill')
            elif self.fill_method == "backward":
                df = df.fillna(method='bfill')
            elif self.fill_method == "interpolate":
                df = df.interpolate(method='linear')
        
        return df
    
    def _resample_data(self, df: pd.DataFrame, target_timeframe: str) -> pd.DataFrame:
        """Resample data to target timeframe."""
        try:
            # Convert timeframe to pandas frequency
            freq_map = {
                '1m': '1T', '5m': '5T', '15m': '15T', '30m': '30T',
                '1h': '1H', '2h': '2H', '4h': '4H', '6h': '6H', '12h': '12H',
                '1d': '1D', '1w': '1W'
            }
            
            freq = freq_map.get(target_timeframe)
            if not freq:
                logger.warning(f"Unknown timeframe: {target_timeframe}, returning original data")
                return df
            
            # Resample OHLCV data
            resampled = df.resample(freq).agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
            
            return resampled
            
        except Exception as e:
            logger.warning(f"Failed to resample data: {e}, returning original")
            return df
    
    def _get_cache_filename(
        self,
        symbol: str,
        timeframe: str,
        exchange: str,
        since: Optional[Union[str, datetime]],
        to: Optional[Union[str, datetime]]
    ) -> Path:
        """Generate cache filename for the data."""
        symbol_clean = symbol.replace('/', '_')
        since_str = self._datetime_to_str(since) if since else "beginning"
        to_str = self._datetime_to_str(to) if to else "end"
        
        filename = f"{symbol_clean}_{timeframe}_{exchange}_{since_str}_{to_str}.csv"
        return self.cache_dir / filename
    
    def _parse_datetime(self, dt: Union[str, datetime]) -> int:
        """Parse datetime string or object to timestamp."""
        if isinstance(dt, str):
            dt = pd.to_datetime(dt, utc=True)
        elif isinstance(dt, datetime):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt = pd.to_datetime(dt)
        
        return int(dt.timestamp() * 1000)  # Convert to milliseconds
    
    def _datetime_to_str(self, dt: Union[str, datetime]) -> str:
        """Convert datetime to string for filename."""
        if isinstance(dt, str):
            dt = pd.to_datetime(dt, utc=True)
        elif isinstance(dt, datetime):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
                
        return dt.strftime("%Y%m%d")
    
    def _timeframe_to_minutes(self, timeframe: str) -> int:
        """Convert timeframe string to minutes."""
        timeframe_map = {
            '1m': 1, '5m': 5, '15m': 15, '30m': 30,
            '1h': 60, '2h': 120, '4h': 240, '6h': 360, '12h': 720,
            '1d': 1440, '1w': 10080
        }
        return timeframe_map.get(timeframe, 60)
    
    def get_available_symbols(self, exchange: str = "binance") -> List[str]:
        """Get list of available trading symbols from exchange."""
        if exchange not in self.exchanges:
            return []
            
        try:
            markets = self.exchanges[exchange].load_markets()
            symbols = [symbol for symbol in markets.keys() if '/USDT' in symbol or '/USD' in symbol]
            return sorted(symbols)
        except Exception as e:
            logger.error(f"Failed to get symbols from {exchange}: {e}")
            return []
    
    def validate_data(self, df: pd.DataFrame, symbol: str) -> Dict:
        """
        Validate data quality and return metrics.
        
        Returns:
            Dictionary with validation metrics
        """
        if df.empty:
            return {"valid": False, "reason": "Empty dataset"}
        
        results = {"valid": True, "metrics": {}}
        
        # Check for required columns
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            results["valid"] = False
            results["reason"] = f"Missing columns: {missing_cols}"
            return results
        
        # Calculate metrics
        metrics = results["metrics"]
        metrics["n_periods"] = len(df)
        metrics["date_range"] = {
            "start": df.index[0].isoformat(),
            "end": df.index[-1].isoformat()
        }
        
        # Check for missing data
        metrics["missing_values"] = df.isnull().sum().to_dict()
        
        # Price metrics
        price_cols = ['open', 'high', 'low', 'close']
        for col in price_cols:
            metrics[f"{col}_range"] = {
                "min": float(df[col].min()),
                "max": float(df[col].max()),
                "mean": float(df[col].mean())
            }
        
        # Volume metrics
        if 'volume' in df.columns and df['volume'].sum() > 0:
            metrics["volume_stats"] = {
                "total": float(df['volume'].sum()),
                "mean": float(df['volume'].mean()),
                "zero_volume_periods": int((df['volume'] == 0).sum())
            }
        
        # Data consistency checks
        ohlc_valid = (
            (df['high'] >= df['open']) & 
            (df['high'] >= df['close']) & 
            (df['low'] <= df['open']) & 
            (df['low'] <= df['close'])
        )
        metrics["ohlc_consistency"] = {
            "valid_periods": int(ohlc_valid.sum()),
            "invalid_periods": int((~ohlc_valid).sum()),
            "consistency_rate": float(ohlc_valid.mean())
        }
        
        if metrics["ohlc_consistency"]["consistency_rate"] < 0.95:
            results["valid"] = False
            results["reason"] = "Poor OHLC consistency"
        
        return results


def load_data(
    symbol: str,
    timeframe: str,
    config: Dict,
    since: Optional[str] = None,
    to: Optional[str] = None,
    exchange: str = "binance"
) -> pd.DataFrame:
    """
    Convenience function to load data.
    
    Args:
        symbol: Trading symbol
        timeframe: Timeframe string
        config: Configuration dictionary
        since: Start date
        to: End date  
        exchange: Exchange name
        
    Returns:
        OHLCV DataFrame
    """
    loader = DataLoader(config)
    return loader.load_ohlcv(symbol, timeframe, since, to, exchange)