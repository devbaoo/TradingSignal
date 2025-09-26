"""
Trading Insight - A robust trading strategy development and testing framework.

This package provides tools for:
- Data loading and quality control
- Technical indicator calculation
- Strategy development (rule-based and ML)
- Backtesting and optimization
- Risk management
- Live/paper trading

Author: Trading Insight Team
License: MIT
"""

__version__ = "0.1.0"
__author__ = "Trading Insight Team"

# Import key classes and functions for easy access
from .utils import get_logger, setup_logging, set_random_seed, load_config
from .data import DataLoader, load_data

__all__ = [
    "get_logger",
    "setup_logging", 
    "set_random_seed",
    "load_config",
    "DataLoader",
    "load_data",
]