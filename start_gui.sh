#!/bin/bash

# Trading Insight Pro - Quick Start Script
# Tự động activate virtual environment và chạy GUI

echo "🚀 Starting Trading Insight Pro GUI..."
echo "=================================="

# Check if in correct directory
if [ ! -f "trading_gui.py" ]; then
    echo "❌ Error: trading_gui.py not found!"
    echo "Please run this script from the TradingInsight directory"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "❌ Error: Virtual environment not found!"
    echo "Please run: python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source .venv/bin/activate

# Check if streamlit is installed
if ! command -v streamlit &> /dev/null; then
    echo "❌ Error: Streamlit not installed!"
    echo "Installing Streamlit..."
    pip install streamlit plotly
fi

# Start the GUI
echo "🎯 Launching Trading GUI..."
echo "📱 Access the app at: http://localhost:8501"
echo "🔄 Press Ctrl+C to stop the server"
echo "=================================="

# Skip streamlit email prompt and run
echo "" | streamlit run trading_gui.py --server.port 8501 --browser.serverAddress localhost

echo "👋 Thanks for using Trading Insight Pro!"