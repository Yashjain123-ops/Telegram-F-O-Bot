"""Virtual Portfolio and Performance Analytics Engine."""

from __future__ import annotations
import numpy as np
from typing import List, Dict, Any
from collections import defaultdict
from datetime import datetime, date

from project_alpha.paper_trading.models import PaperTrade

class VirtualPortfolio:
    def __init__(self, starting_capital: float = 1_000_000.0):
        self.starting_capital = starting_capital
        self.current_capital = starting_capital
        self.used_capital = 0.0
        self.peak_capital = starting_capital
        
        self.open_positions: dict[str, PaperTrade] = {}
        self.closed_positions: List[PaperTrade] = []
        
        # PnL Tracking
        self.daily_pnl = defaultdict(float)
        self.weekly_pnl = defaultdict(float)
        self.monthly_pnl = defaultdict(float)
        self.equity_curve = []
        
        self.start_of_day_capital = starting_capital
        self.current_date: date | None = None

    def get_available_capital(self) -> float:
        return self.current_capital - self.used_capital

    def _update_date(self, new_datetime: datetime):
        new_date = new_datetime.date()
        if self.current_date is None or new_date > self.current_date:
            self.current_date = new_date
            self.start_of_day_capital = self.current_capital

    def open_trade(self, trade: PaperTrade):
        self._update_date(trade.entry_time)
        self.open_positions[trade.trade_id] = trade
        self.used_capital += trade.capital_allocated

    def close_trade(self, trade: PaperTrade):
        if trade.trade_id in self.open_positions:
            self._update_date(trade.exit_time)
            
            self.used_capital -= trade.capital_allocated
            self.current_capital += trade.net_pnl
            self.peak_capital = max(self.peak_capital, self.current_capital)
            
            # PnL Trackers
            iso_week = trade.exit_time.isocalendar()[1]
            iso_month = trade.exit_time.month
            
            self.daily_pnl[self.current_date] += trade.net_pnl
            self.weekly_pnl[f"{trade.exit_time.year}-W{iso_week:02d}"] += trade.net_pnl
            self.monthly_pnl[f"{trade.exit_time.year}-M{iso_month:02d}"] += trade.net_pnl
            
            self.equity_curve.append({
                "timestamp": trade.exit_time.isoformat(),
                "capital": self.current_capital,
                "trade_pnl": trade.net_pnl,
                "status": trade.status
            })
            
            del self.open_positions[trade.trade_id]
            self.closed_positions.append(trade)

class PerformanceAnalytics:
    def __init__(self, portfolio: VirtualPortfolio):
        self.p = portfolio
        
    def calculate(self) -> dict[str, Any]:
        trades = self.p.closed_positions
        if not trades: return {"error": "No closed trades"}
            
        wins = [t for t in trades if t.net_pnl > 0]
        losses = [t for t in trades if t.net_pnl <= 0]
        
        win_rate = len(wins) / len(trades)
        
        total_profit = sum(t.net_pnl for t in wins)
        total_loss = sum(abs(t.net_pnl) for t in losses)
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
        
        avg_win = total_profit / len(wins) if wins else 0.0
        avg_loss = total_loss / len(losses) if losses else 0.0
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        
        roc = (self.p.current_capital - self.p.starting_capital) / self.p.starting_capital
        
        drawdown = (self.p.peak_capital - self.p.current_capital) / self.p.peak_capital
        
        # Max Drawdown calculation from equity curve
        peak = self.p.starting_capital
        max_dd = 0.0
        for eq in self.p.equity_curve:
            if eq["capital"] > peak: peak = eq["capital"]
            dd = (peak - eq["capital"]) / peak
            if dd > max_dd: max_dd = dd
            
        # Sharpe Approximation (assuming daily returns)
        daily_returns = []
        last_cap = self.p.starting_capital
        for eq in self.p.equity_curve:
            ret = (eq["capital"] - last_cap) / last_cap
            daily_returns.append(ret)
            last_cap = eq["capital"]
            
        sharpe = 0.0
        if daily_returns:
            mean = np.mean(daily_returns)
            std = np.std(daily_returns)
            if std > 0:
                sharpe = (mean / std) * np.sqrt(252)
                
        return {
            "total_trades": len(trades),
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "expectancy_currency": expectancy,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "roc_pct": roc,
            "current_drawdown_pct": drawdown,
            "max_drawdown_pct": max_dd,
            "sharpe_ratio_approx": sharpe,
            "final_capital": self.p.current_capital
        }
