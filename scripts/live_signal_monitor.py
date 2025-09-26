#!/usr/bin/env python3
"""
Live Trading Signal Monitor
Continuously monitors markets and generates actionable futures trading signals.
"""

import sys
import time
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# Add src to path
sys.path.append('src')

from signals import TradingSignalGenerator, TradingSignal
from utils import get_logger, ensure_directory

logger = get_logger(__name__)


class LiveSignalMonitor:
    """Live monitoring system for trading signals."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.signal_generator = TradingSignalGenerator(config)
        self.is_running = False
        self.last_signals = {}
        self.signal_history = []
        
        # Results directory
        self.results_dir = Path("trading_signals")
        ensure_directory(self.results_dir)
        
    def start_monitoring(self, 
                        symbols: List[str],
                        timeframes: List[str] = ["1h"],
                        strategies: List[str] = ["StrategyMomo"],
                        scan_interval: int = 300,  # 5 minutes
                        min_safety_score: int = 6,
                        max_signals_per_hour: int = 3):
        """Start live signal monitoring."""
        
        print(f"""
🚀 STARTING LIVE TRADING SIGNAL MONITOR
{'='*50}
📊 Symbols: {', '.join(symbols)}
⏰ Timeframes: {', '.join(timeframes)}
🎯 Strategies: {', '.join(strategies)}
🔍 Scan Interval: {scan_interval}s
🛡️ Min Safety Score: {min_safety_score}/10
⚡ Max Signals/Hour: {max_signals_per_hour}
{'='*50}
""")
        
        self.is_running = True
        signals_this_hour = 0
        hour_start = datetime.now().replace(minute=0, second=0, microsecond=0)
        
        try:
            while self.is_running:
                current_time = datetime.now()
                
                # Reset hourly signal counter
                if current_time >= hour_start + timedelta(hours=1):
                    signals_this_hour = 0
                    hour_start = current_time.replace(minute=0, second=0, microsecond=0)
                
                print(f"\n⏰ MARKET SCAN - {current_time.strftime('%H:%M:%S')}")
                print("-" * 40)
                
                new_signals = []
                
                # Scan all combinations
                for symbol in symbols:
                    for timeframe in timeframes:
                        for strategy in strategies:
                            
                            if signals_this_hour >= max_signals_per_hour:
                                print(f"🛑 Max signals per hour reached ({max_signals_per_hour})")
                                break
                            
                            print(f"🔍 Scanning {symbol} {timeframe} {strategy}...")
                            
                            try:
                                signal = self.signal_generator.generate_signal(
                                    symbol=symbol,
                                    timeframe=timeframe,
                                    strategy_name=strategy
                                )
                                
                                if signal and signal.safety_score >= min_safety_score:
                                    # Check if this is a new signal (avoid duplicates)
                                    signal_key = f"{symbol}_{timeframe}_{strategy}"
                                    
                                    if self._is_new_signal(signal, signal_key):
                                        new_signals.append(signal)
                                        self.last_signals[signal_key] = current_time
                                        signals_this_hour += 1
                                        
                                        print(f"🎯 NEW SIGNAL FOUND!")
                                        print(f"   {symbol} {signal.direction} - Safety: {signal.safety_score}/10")
                                    else:
                                        print(f"   ⏭️  Signal too recent, skipping")
                                else:
                                    if signal:
                                        print(f"   ❌ Safety score too low: {signal.safety_score}/{min_safety_score}")
                                    else:
                                        print(f"   💤 No signal conditions met")
                                        
                            except Exception as e:
                                print(f"   ❌ Error scanning {symbol}: {e}")
                                logger.error(f"Error scanning {symbol}: {e}")
                
                # Process new signals
                if new_signals:
                    self._process_new_signals(new_signals)
                else:
                    print("💤 No new signals this scan")
                
                # Wait for next scan
                print(f"\n⏳ Next scan in {scan_interval}s...")
                time.sleep(scan_interval)
                
        except KeyboardInterrupt:
            print("\n🛑 Monitoring stopped by user")
        except Exception as e:
            print(f"\n❌ Error in monitoring: {e}")
            logger.error(f"Monitoring error: {e}")
        finally:
            self.is_running = False
            self._save_session_summary()
        
        print("\n✅ Live signal monitoring ended")
    
    def _is_new_signal(self, signal: TradingSignal, signal_key: str) -> bool:
        """Check if this is a new signal (not generated recently)."""
        
        if signal_key not in self.last_signals:
            return True
        
        last_signal_time = self.last_signals[signal_key]
        time_since_last = datetime.now() - last_signal_time
        
        # Only generate new signal if >30 minutes since last
        return time_since_last.total_seconds() > 1800
    
    def _process_new_signals(self, signals: List[TradingSignal]):
        """Process and display new trading signals."""
        
        print(f"\n🚨 TRADING SIGNALS ALERT! ({len(signals)} new signals)")
        print("=" * 80)
        
        for i, signal in enumerate(signals, 1):
            # Display formatted signal
            print(f"\nSIGNAL #{i}:")
            print(signal.trading_command)
            
            # Save signal to history
            self.signal_history.append({
                'timestamp': signal.timestamp.isoformat(),
                'signal': self._signal_to_dict(signal)
            })
            
            # Save individual signal file
            signal_filename = f"signal_{signal.symbol.replace('/', '_')}_{signal.timestamp.strftime('%Y%m%d_%H%M%S')}.json"
            signal_path = self.results_dir / signal_filename
            
            with open(signal_path, 'w') as f:
                json.dump(self._signal_to_dict(signal), f, indent=2, default=str)
            
            print(f"💾 Signal saved to: {signal_path}")
        
        # Send notifications (placeholder for actual implementation)
        self._send_notifications(signals)
    
    def _signal_to_dict(self, signal: TradingSignal) -> Dict:
        """Convert signal to dictionary for JSON serialization."""
        
        return {
            'symbol': signal.symbol,
            'direction': signal.direction,
            'timestamp': signal.timestamp.isoformat(),
            'strategy': signal.strategy_name,
            'timeframe': signal.timeframe,
            'entry_price': signal.entry_price,
            'entry_range': signal.entry_price_range,
            'stop_loss': signal.stop_loss,
            'take_profit': signal.take_profit,
            'risk_per_trade': signal.risk_per_trade,
            'recommended_leverage': signal.recommended_leverage,
            'position_size_usdt': signal.position_size_usdt,
            'position_size_percent': signal.position_size_percent,
            'safety_score': signal.safety_score,
            'confidence_level': signal.confidence_level,
            'risk_level': signal.risk_level,
            'trend_strength': signal.trend_strength,
            'volatility_percentile': signal.volatility_percentile,
            'volume_profile': signal.volume_profile,
            'rsi': signal.rsi,
            'ema_trend': signal.ema_trend,
            'macd_signal': signal.macd_signal,
            'support_resistance': signal.support_resistance,
            'market_conditions': signal.market_conditions,
            'execution_notes': signal.execution_notes,
            'validity_period': signal.validity_period,
            'risk_reward_ratio': signal.risk_reward_ratio,
            'trading_command': signal.trading_command
        }
    
    def _send_notifications(self, signals: List[TradingSignal]):
        """Send notifications for new signals."""
        
        # Placeholder for notification implementation
        # Could integrate with:
        # - Telegram Bot API
        # - Discord Webhooks
        # - Email alerts
        # - Slack notifications
        # - Push notifications
        
        print(f"\n📢 NOTIFICATIONS:")
        print(f"   📱 {len(signals)} signals would be sent to notification channels")
        print(f"   💌 Email alerts would be sent")
        print(f"   📲 Push notifications would be delivered")
        
        # Example notification format
        for signal in signals:
            notification_text = f"""
🚨 TRADING SIGNAL ALERT!

{signal.symbol} {signal.direction}
Entry: ${signal.entry_price:,.4f}
Stop Loss: ${signal.stop_loss:,.4f}
Take Profit: ${signal.take_profit[0]:,.4f}
Safety Score: {signal.safety_score}/10
Position Size: ${signal.position_size_usdt:,.0f}
Leverage: {signal.recommended_leverage}x
"""
            print(f"📲 Notification: {notification_text.strip()}")
    
    def _save_session_summary(self):
        """Save session summary."""
        
        if not self.signal_history:
            print("📝 No signals generated in this session")
            return
        
        summary = {
            'session_start': datetime.now().isoformat(),
            'total_signals': len(self.signal_history),
            'signals': self.signal_history,
            'symbols_monitored': list(self.config.get('symbols', [])),
            'config': self.config
        }
        
        summary_file = self.results_dir / f"session_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        print(f"\n📋 SESSION SUMMARY:")
        print(f"   📊 Total Signals Generated: {len(self.signal_history)}")
        print(f"   💾 Session saved to: {summary_file}")
    
    def stop_monitoring(self):
        """Stop the monitoring process."""
        self.is_running = False
        print("🛑 Signal monitoring stop requested")


def main():
    """Main function for live signal monitoring."""
    
    # Configuration
    config = {
        'account_balance': 10000,  # Your account balance in USDT
        'data': {
            'source': 'binance_spot',
            'cache_enabled': True
        },
        'backtest': {
            'initial_capital': 10000,
            'fee_rate': 0.001,
            'slippage_bps': 2.0
        },
        'strategy_params': {
            'StrategyMomo': {
                'ema_short': 12,
                'ema_long': 26,
                'rsi_period': 14,
                'rsi_overbought': 70,
                'rsi_oversold': 30,
                'risk_per_trade': 0.02,
                'stop_loss_pct': 0.03,
                'take_profit_pct': 0.06
            },
            'StrategyMeanRev': {
                'bb_period': 20,
                'bb_std': 2.0,
                'rsi_period': 14,
                'rsi_overbought': 70,
                'rsi_oversold': 30,
                'risk_per_trade': 0.02,
                'stop_loss_pct': 0.025,
                'take_profit_pct': 0.05
            }
        }
    }
    
    # Create monitor
    monitor = LiveSignalMonitor(config)
    
    try:
        # Start monitoring
        monitor.start_monitoring(
            symbols=['BTC/USDT', 'ETH/USDT'],  # Add more symbols as needed
            timeframes=['1h'],                  # Add '4h', '1d' for different timeframes
            strategies=['StrategyMomo'],        # Add 'StrategyMeanRev' for more strategies
            scan_interval=300,                  # 5 minutes between scans
            min_safety_score=7,                 # Only show high-quality signals
            max_signals_per_hour=2              # Limit signal frequency
        )
        
    except KeyboardInterrupt:
        print("\n🛑 Stopping live signal monitor...")
        monitor.stop_monitoring()


if __name__ == "__main__":
    main()