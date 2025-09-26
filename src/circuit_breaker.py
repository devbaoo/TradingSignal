from datetime import datetime, timedelta
from typing import Dict, List, Any
import json

class CircuitBreakerManager:
    """
    Institutional-grade circuit breakers để protect against excessive losses
    
    DAILY LIMITS:
    - Max Daily Loss: -3R hoặc -3% account balance
    - Max Consecutive Losses: 3 trades liên tục
    - Max Daily Trades: 10 trades to prevent overtrading
    
    WEEKLY LIMITS:
    - Max Weekly Loss: -7% account balance
    - Max Weekly Trades: 35 trades
    
    AUTO-SCAN SUSPENSION:
    - Trigger: Khi daily/weekly limits reached
    - Duration: Remaining của period (day/week)
    - Override: Manual admin override only
    
    RISK ESCALATION:
    - Warning at 50% of limits
    - Soft stop at 75% of limits (require confirmation)
    - Hard stop at 100% of limits (no override except admin)
    """
    
    def __init__(self):
        self.daily_loss_limit_percent = 0.03    # -3% daily
        self.weekly_loss_limit_percent = 0.07   # -7% weekly  
        self.max_consecutive_losses = 3
        self.max_daily_trades = 10
        self.max_weekly_trades = 35
        
        # State tracking
        self.daily_pnl = 0.0
        self.weekly_pnl = 0.0
        self.consecutive_losses = 0
        self.daily_trade_count = 0
        self.weekly_trade_count = 0
        self.last_reset_date = None
        self.last_reset_week = None
        
        # Circuit breaker status
        self.daily_suspended = False
        self.weekly_suspended = False
        self.auto_scan_disabled = False
        self.last_trade_was_loss = False
        
    def check_circuit_breakers(self, account_balance: float) -> Dict[str, Any]:
        """
        Check all circuit breaker conditions
        
        RETURNS:
        - allowed: bool - Whether new trades are allowed
        - warnings: list - Active warnings
        - suspensions: list - Active suspensions
        - risk_level: str - NORMAL/WARNING/DANGER/SUSPENDED
        """
        
        self._check_and_reset_periods()
        
        warnings = []
        suspensions = []
        
        # DAILY LOSS CHECK
        daily_loss_limit = account_balance * self.daily_loss_limit_percent
        if self.daily_pnl <= -daily_loss_limit:
            self.daily_suspended = True
            suspensions.append(f"Daily loss limit exceeded: ${self.daily_pnl:.2f} <= -${daily_loss_limit:.2f}")
        elif self.daily_pnl <= -daily_loss_limit * 0.75:
            warnings.append(f"Daily loss warning: ${self.daily_pnl:.2f} (75% of limit)")
        elif self.daily_pnl <= -daily_loss_limit * 0.5:
            warnings.append(f"Daily loss caution: ${self.daily_pnl:.2f} (50% of limit)")
            
        # WEEKLY LOSS CHECK  
        weekly_loss_limit = account_balance * self.weekly_loss_limit_percent
        if self.weekly_pnl <= -weekly_loss_limit:
            self.weekly_suspended = True
            suspensions.append(f"Weekly loss limit exceeded: ${self.weekly_pnl:.2f} <= -${weekly_loss_limit:.2f}")
        elif self.weekly_pnl <= -weekly_loss_limit * 0.75:
            warnings.append(f"Weekly loss warning: ${self.weekly_pnl:.2f} (75% of limit)")
            
        # CONSECUTIVE LOSSES CHECK
        if self.consecutive_losses >= self.max_consecutive_losses:
            suspensions.append(f"Max consecutive losses: {self.consecutive_losses}/{self.max_consecutive_losses}")
            
        # TRADE COUNT CHECKS
        if self.daily_trade_count >= self.max_daily_trades:
            suspensions.append(f"Daily trade limit: {self.daily_trade_count}/{self.max_daily_trades}")
        elif self.daily_trade_count >= self.max_daily_trades * 0.8:
            warnings.append(f"Daily trades warning: {self.daily_trade_count}/{self.max_daily_trades}")
            
        if self.weekly_trade_count >= self.max_weekly_trades:
            suspensions.append(f"Weekly trade limit: {self.weekly_trade_count}/{self.max_weekly_trades}")
            
        # DETERMINE STATUS
        if suspensions:
            self.auto_scan_disabled = True
            risk_level = "SUSPENDED"
            allowed = False
        elif warnings:
            risk_level = "WARNING" if len(warnings) <= 2 else "DANGER"
            allowed = True  # Allow but with warnings
        else:
            risk_level = "NORMAL"
            allowed = True
            
        return {
            'allowed': allowed,
            'warnings': warnings,
            'suspensions': suspensions,
            'risk_level': risk_level,
            'auto_scan_enabled': not self.auto_scan_disabled,
            'daily_pnl': self.daily_pnl,
            'weekly_pnl': self.weekly_pnl,
            'consecutive_losses': self.consecutive_losses,
            'daily_trades': f"{self.daily_trade_count}/{self.max_daily_trades}",
            'weekly_trades': f"{self.weekly_trade_count}/{self.max_weekly_trades}"
        }
        
    def update_trade_result(self, pnl_amount: float, is_win: bool):
        """
        Update circuit breaker state after trade completion
        
        PARAMETERS:
        - pnl_amount: Trade P&L in USDT (positive = profit, negative = loss)
        - is_win: bool - Whether trade was profitable
        """
        
        # Update P&L
        self.daily_pnl += pnl_amount
        self.weekly_pnl += pnl_amount
        
        # Update trade counts
        self.daily_trade_count += 1
        self.weekly_trade_count += 1
        
        # Update consecutive losses
        if is_win:
            self.consecutive_losses = 0  # Reset on win
            self.last_trade_was_loss = False
        else:
            self.consecutive_losses += 1
            self.last_trade_was_loss = True
            
    def _check_and_reset_periods(self):
        """Check if we need to reset daily or weekly counters"""
        today = datetime.now().date()
        current_week = today.isocalendar()[1]
        
        # Reset daily counters if new day
        if self.last_reset_date != today:
            self.reset_daily_counters()
            self.last_reset_date = today
            
        # Reset weekly counters if new week
        if self.last_reset_week != current_week:
            self.reset_weekly_counters()
            self.last_reset_week = current_week
            
    def reset_daily_counters(self):
        """Reset daily counters at start of new day"""
        self.daily_pnl = 0.0
        self.daily_trade_count = 0
        self.daily_suspended = False
        # Don't reset consecutive_losses - carries over days
        
    def reset_weekly_counters(self):
        """Reset weekly counters at start of new week"""
        self.weekly_pnl = 0.0
        self.weekly_trade_count = 0
        self.weekly_suspended = False
        
    def admin_override_enable(self):
        """Admin override to re-enable auto-scan (use carefully)"""
        self.auto_scan_disabled = False
        self.daily_suspended = False
        self.weekly_suspended = False
        self.consecutive_losses = 0  # Reset consecutive losses on override
        
    def get_status_summary(self) -> Dict[str, Any]:
        """Get current status summary for display"""
        return {
            'daily_pnl': self.daily_pnl,
            'weekly_pnl': self.weekly_pnl,
            'consecutive_losses': self.consecutive_losses,
            'daily_trades': self.daily_trade_count,
            'weekly_trades': self.weekly_trade_count,
            'daily_suspended': self.daily_suspended,
            'weekly_suspended': self.weekly_suspended,
            'auto_scan_disabled': self.auto_scan_disabled
        }