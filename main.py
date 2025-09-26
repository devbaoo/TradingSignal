"""
Main entry point for Trading Insight.
Command-line interface and programmatic access.
"""

import sys
from pathlib import Path

# Add src to Python path for development
sys.path.insert(0, str(Path(__file__).parent))

from src.cli import main

if __name__ == "__main__":
    main()