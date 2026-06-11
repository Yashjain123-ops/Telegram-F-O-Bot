"""Paper Trading Simulator Engine."""

from __future__ import annotations
import logging
import pandas as pd
from typing import Any
from datetime import datetime, timezone

from project_alpha.paper_trading.models import PaperTrade
from project_alpha.paper_trading.portfolio import VirtualPortfolio, PerformanceAnalytics
from project_alpha.paper_trading.risk_sizing import RiskManagementEngine, PositionSizingEngine, LotSizeRegistry
from project_alpha.tracking.signal_store import SignalRecord

log = logging.getLogger("PaperTradingSimulator")

class CostSimulationEngine:
    @staticmethod
    def calculate_costs(trade: PaperTrade) -> float:
        """
        Calculates exact Indian F&O regulatory and brokerage costs.
        Includes STT, Exchange, SEBI, GST, Stamp Duty, and Brokerage.
        """
        turnover = (trade.entry_price + trade.exit_price) * trade.quantity
        
        # 1. Brokerage (assuming ₹20 flat per leg)
        brokerage = 40.0 
        
        # 2. STT (0.0125% on sell side for futures, simplified here)
        stt = (trade.exit_price * trade.quantity) * 0.000125
        
        # 3. Exchange Transaction Charges (approx 0.002%)
        exchange_charges = turnover * 0.00002
        
        # 4. GST (18% on Brokerage + Exchange Charges)
        gst = (brokerage + exchange_charges) * 0.18
        
        # 5. SEBI Charges (₹10 per crore)
        sebi = (turnover / 10000000) * 10
        
        # 6. Stamp Duty (0.002% on buy side only)
        stamp_duty = (trade.entry_price * trade.quantity) * 0.00002
        
        return brokerage + stt + exchange_charges + gst + sebi + stamp_duty

class PaperTradingEngine:
    def __init__(self, starting_capital: float = 1_000_000.0):
        self.portfolio = VirtualPortfolio(starting_capital)
        self.risk_engine = RiskManagementEngine(max_open_positions=5, max_daily_loss_pct=0.05, max_drawdown_pct=0.15)
        self.sizing_engine = PositionSizingEngine(risk_per_trade_pct=0.02, max_allocation_pct=0.25)
        
    def process_signal(self, record: SignalRecord) -> bool:
        """
        Takes a new PRIME_CANDIDATE signal from Phase 2/3 and opens a simulated position
        if it passes Risk & Sizing logic.
        """
        # 1. Halt Check
        today = record.created_at.date()
        daily_pnl = self.portfolio.daily_pnl.get(today, 0.0)
        halted = self.risk_engine.evaluate_halt(
            current_capital=self.portfolio.current_capital,
            peak_capital=self.portfolio.peak_capital,
            daily_pnl=daily_pnl,
            start_of_day_capital=self.portfolio.start_of_day_capital
        )
        if halted:
            return False

        # 2. Exposure Check
        if not self.risk_engine.can_open_position(
            active_trades=list(self.portfolio.open_positions.values()), 
            symbol=record.symbol,
            sector=record.sector,
            current_capital=self.portfolio.current_capital
        ):
            return False
            
        # 3. Position Sizing
        available_cap = self.portfolio.get_available_capital()
        size_data = self.sizing_engine.calculate_size(
            current_capital=available_cap,
            entry_price=record.entry_price,
            sl_price=record.sl_price,
            symbol=record.symbol
        )
        
        qty = size_data["quantity"]
        if qty == 0:
            return False
            
        # 4. Open Paper Trade
        trade = PaperTrade(
            trade_id=record.signal_id,
            symbol=record.symbol,
            sector=record.sector,
            direction=record.direction,
            entry_time=record.created_at,
            entry_price=record.entry_price,
            quantity=qty,
            lots=size_data["lots"],
            sl_price=record.sl_price,
            target_price=record.target_price,
            capital_allocated=size_data["capital_allocated"],
            risk_amount=size_data["risk_amount"],
            highest_price=record.entry_price,
            lowest_price=record.entry_price
        )
        
        self.portfolio.open_trade(trade)
        log.info(f"PAPER TRADE OPEN: {record.direction} {record.symbol} | Qty: {qty} | Risk: {size_data['risk_amount']:.2f}")
        return True

    def update_market_data(self, symbol: str, current_candle: pd.Series):
        """Simulates tick updates for PnL excursion tracking without a broker."""
        high = current_candle["high"]
        low = current_candle["low"]
        close = current_candle["close"]
        ts = current_candle.name # assuming timestamp is the index
        if not isinstance(ts, datetime):
            # Fallback if the index is not a true datetime object
            ts = datetime.now(timezone.utc)
            
        for trade_id, trade in list(self.portfolio.open_positions.items()):
            if trade.symbol != symbol:
                continue
                
            trade.highest_price = max(trade.highest_price, high)
            trade.lowest_price = min(trade.lowest_price, low)
            
            # Simulate Hit Detection (Pessimistic Collision)
            if trade.direction == "BULLISH":
                target_hit = high >= trade.target_price
                sl_hit = low <= trade.sl_price
                
                if target_hit and sl_hit:
                    self._execute_close(trade, "CLOSED_LOSS", trade.sl_price, ts)
                elif target_hit:
                    self._execute_close(trade, "CLOSED_WIN", trade.target_price, ts)
                elif sl_hit:
                    self._execute_close(trade, "CLOSED_LOSS", trade.sl_price, ts)
                    
            elif trade.direction == "BEARISH":
                target_hit = low <= trade.target_price
                sl_hit = high >= trade.sl_price
                
                if target_hit and sl_hit: self._execute_close(trade, "CLOSED_LOSS", trade.sl_price, ts)
                elif target_hit: self._execute_close(trade, "CLOSED_WIN", trade.target_price, ts)
                elif sl_hit: self._execute_close(trade, "CLOSED_LOSS", trade.sl_price, ts)
                
            # Signal Expiry Synchronization
            if trade.status == "OPEN":
                # Fallback expiry to 120 minutes if signal didn't explicitly pass it
                delta = ts - trade.entry_time
                if delta.total_seconds() / 60.0 > 120.0:
                    self._execute_close(trade, "EXPIRED", close, ts)

    def _execute_close(self, trade: PaperTrade, status: str, fill_price: float, exit_time: datetime):
        trade.status = status
        trade.exit_price = fill_price
        trade.exit_time = exit_time
        
        if trade.direction == "BULLISH": trade.gross_pnl = (fill_price - trade.entry_price) * trade.quantity
        else: trade.gross_pnl = (trade.entry_price - fill_price) * trade.quantity
            
        trade.transaction_costs = CostSimulationEngine.calculate_costs(trade)
        trade.net_pnl = trade.gross_pnl - trade.transaction_costs
        trade.roi_pct = trade.net_pnl / trade.capital_allocated
        
        log.info(f"PAPER TRADE CLOSED: {trade.symbol} | Status: {status} | Net PnL: {trade.net_pnl:.2f} | Costs: {trade.transaction_costs:.2f}")
        self.portfolio.close_trade(trade)

    def generate_report(self) -> dict[str, Any]:
        analytics = PerformanceAnalytics(self.portfolio)
        return analytics.calculate()
