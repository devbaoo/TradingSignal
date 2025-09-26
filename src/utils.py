"""
Utility functions and helpers for the trading system.
Includes logging setup, random seed management, and common utilities.
"""

import logging
import os
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import structlog
import yaml


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    include_timestamp: bool = True
) -> None:
    """
    Setup structured logging for the application.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional log file path
        include_timestamp: Whether to include timestamp in logs
    """
    # Clear any existing handlers
    logging.getLogger().handlers.clear()
    
    # Configure structlog
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    
    if include_timestamp:
        processors.append(structlog.processors.TimeStamper(fmt="iso"))
    
    processors.extend([
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ])
    
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Setup standard logging
    handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        if include_timestamp else '%(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(formatter)
    handlers.append(console_handler)
    
    # File handler if specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(getattr(logging, level.upper()))
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        handlers=handlers,
        force=True
    )
    
    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("ccxt").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        Configured logger instance
    """
    return structlog.get_logger(name)


def set_random_seed(seed: int = 42) -> None:
    """
    Set random seeds for reproducibility.
    
    Args:
        seed: Random seed value
    """
    random.seed(seed)
    np.random.seed(seed)
    
    # Set seeds for other libraries if available
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed(seed)
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass
    
    try:
        import tensorflow as tf
        tf.random.set_seed(seed)
    except ImportError:
        pass


def load_config(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from YAML file.
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        Configuration dictionary
    """
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # Environment variable substitution
    config = _substitute_env_vars(config)
    
    return config


def save_config(config: Dict[str, Any], config_path: str) -> None:
    """
    Save configuration to YAML file.
    
    Args:
        config: Configuration dictionary
        config_path: Path to save configuration
    """
    config_file = Path(config_path)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(config_file, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, indent=2)


def _substitute_env_vars(obj: Any) -> Any:
    """
    Recursively substitute environment variables in configuration.
    
    Args:
        obj: Configuration object (dict, list, or string)
        
    Returns:
        Object with environment variables substituted
    """
    if isinstance(obj, dict):
        return {key: _substitute_env_vars(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [_substitute_env_vars(item) for item in obj]
    elif isinstance(obj, str):
        # Replace ${VAR_NAME} or $VAR_NAME with environment variable
        if obj.startswith('${') and obj.endswith('}'):
            var_name = obj[2:-1]
            return os.environ.get(var_name, obj)
        elif obj.startswith('$'):
            var_name = obj[1:]
            return os.environ.get(var_name, obj)
    
    return obj


def create_run_directory(base_dir: str = "runs") -> Path:
    """
    Create a unique directory for a run based on timestamp.
    
    Args:
        base_dir: Base directory for runs
        
    Returns:
        Path to the created run directory
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(base_dir) / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """
    Safely divide two numbers, returning default if denominator is zero.
    
    Args:
        numerator: Numerator value
        denominator: Denominator value
        default: Default value to return if denominator is zero
        
    Returns:
        Division result or default value
    """
    if denominator == 0 or np.isnan(denominator) or np.isinf(denominator):
        return default
    return numerator / denominator


def format_percentage(value: float, decimals: int = 2) -> str:
    """
    Format a decimal value as percentage string.
    
    Args:
        value: Decimal value (e.g., 0.1 for 10%)
        decimals: Number of decimal places
        
    Returns:
        Formatted percentage string
    """
    return f"{value * 100:.{decimals}f}%"


def format_currency(value: float, currency: str = "USD", decimals: int = 2) -> str:
    """
    Format a value as currency string.
    
    Args:
        value: Numeric value
        currency: Currency code
        decimals: Number of decimal places
        
    Returns:
        Formatted currency string
    """
    if currency.upper() == "USD":
        symbol = "$"
    elif currency.upper() == "EUR":
        symbol = "€"
    elif currency.upper() == "GBP":
        symbol = "£"
    else:
        symbol = f" {currency}"
    
    if abs(value) >= 1e6:
        return f"{symbol}{value/1e6:.{decimals}f}M"
    elif abs(value) >= 1e3:
        return f"{symbol}{value/1e3:.{decimals}f}K"
    else:
        return f"{symbol}{value:.{decimals}f}"


def calculate_drawdown(equity_curve: np.ndarray) -> np.ndarray:
    """
    Calculate drawdown from equity curve.
    
    Args:
        equity_curve: Array of equity values
        
    Returns:
        Array of drawdown values (negative percentages)
    """
    peak = np.maximum.accumulate(equity_curve)
    drawdown = (equity_curve - peak) / peak
    return drawdown


def calculate_returns(prices: np.ndarray, method: str = "simple") -> np.ndarray:
    """
    Calculate returns from price series.
    
    Args:
        prices: Array of prices
        method: Return calculation method ("simple" or "log")
        
    Returns:
        Array of returns
    """
    if len(prices) < 2:
        return np.array([])
    
    if method == "log":
        returns = np.log(prices[1:] / prices[:-1])
    else:  # simple
        returns = (prices[1:] - prices[:-1]) / prices[:-1]
    
    return returns


def rolling_window(data: np.ndarray, window: int) -> np.ndarray:
    """
    Create a rolling window view of the data.
    
    Args:
        data: Input array
        window: Window size
        
    Returns:
        2D array where each row is a window
    """
    if len(data) < window:
        return np.array([])
    
    shape = data.shape[:-1] + (data.shape[-1] - window + 1, window)
    strides = data.strides + (data.strides[-1],)
    return np.lib.stride_tricks.as_strided(data, shape=shape, strides=strides)


def validate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and set default values for configuration.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Validated configuration with defaults
    """
    # Set default values
    defaults = {
        "data_dir": "data",
        "random_seed": 42,
        "logging": {
            "level": "INFO",
            "file": None
        },
        "exchanges": {},
        "data_quality": {
            "remove_outliers": True,
            "outlier_detection": "iqr",
            "outlier_threshold": 3.0,
            "fill_gaps": True,
            "gap_fill_method": "forward",
            "max_gap_size_minutes": 60
        },
        "backtest": {
            "initial_capital": 10000,
            "fee_rate": 0.001,
            "slippage_model": "fixed",
            "slippage_bps": 2
        },
        "risk": {
            "max_positions": 3,
            "risk_per_trade": 0.02,
            "max_drawdown": 0.20,
            "position_sizing": "fixed_fractional"
        }
    }
    
    # Merge with defaults
    validated_config = _deep_merge(defaults, config)
    
    return validated_config


def _deep_merge(dict1: Dict, dict2: Dict) -> Dict:
    """
    Deep merge two dictionaries, with dict2 values taking precedence.
    
    Args:
        dict1: Base dictionary
        dict2: Override dictionary
        
    Returns:
        Merged dictionary
    """
    result = dict1.copy()
    
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    
    return result


class Timer:
    """Context manager for timing code execution."""
    
    def __init__(self, name: str = "Operation", logger: Optional[logging.Logger] = None):
        self.name = name
        self.logger = logger or get_logger(__name__)
        self.start_time = None
        self.end_time = None
    
    def __enter__(self):
        self.start_time = datetime.now()
        self.logger.info(f"Starting {self.name}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = datetime.now()
        duration = self.end_time - self.start_time
        self.logger.info(f"Completed {self.name} in {duration.total_seconds():.2f} seconds")
    
    @property
    def elapsed(self) -> float:
        """Get elapsed time in seconds."""
        if self.start_time is None:
            return 0.0
        
        end_time = self.end_time or datetime.now()
        return (end_time - self.start_time).total_seconds()


def ensure_directory(path: str) -> Path:
    """
    Ensure directory exists, create if necessary.
    
    Args:
        path: Directory path
        
    Returns:
        Path object
    """
    dir_path = Path(path)
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def get_memory_usage() -> Dict[str, float]:
    """
    Get current memory usage information.
    
    Returns:
        Dictionary with memory usage stats
    """
    try:
        import psutil
        process = psutil.Process()
        memory_info = process.memory_info()
        return {
            "rss_mb": memory_info.rss / 1024 / 1024,  # Resident Set Size
            "vms_mb": memory_info.vms / 1024 / 1024,  # Virtual Memory Size
            "percent": process.memory_percent()
        }
    except ImportError:
        return {"rss_mb": 0, "vms_mb": 0, "percent": 0}


def chunk_list(lst: list, chunk_size: int):
    """
    Yield successive chunks from list.
    
    Args:
        lst: Input list
        chunk_size: Size of each chunk
        
    Yields:
        Chunks of the list
    """
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]