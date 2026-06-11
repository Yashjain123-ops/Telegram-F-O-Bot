"""Position Sizing and Exposure Management Engine."""

from __future__ import annotations
import logging
from typing import Dict, Any
from project_alpha.paper_trading.models import PaperTrade

log = logging.getLogger("RiskSizing")

class LotSizeRegistry:
    """Mock registry mapping symbols to Indian F&O Lot Sizes."""
    LOT_SIZES = {
        "NIFTY": 25,
        "BANKNIFTY": 15,
        "FINNIFTY": 40,
        "MIDCPNIFTY": 75,
        "HDFCBANK": 400,
        "ICICIBANK": 700,
        "RELIANCE": 250,
        "INFY": 400,
        "TCS": 175,
        "DEFAULT": 500  # Fallback for unknown stock options
    }
    
    @classmethod
    def get_lot_size(cls, symbol: str) -> int:
        for key in cls.LOT_SIZES:
            if key in symbol:
                return cls.LOT_SIZES[key]
        return cls.LOT_SIZES["DEFAULT"]

class RiskManagementEngine:
    def __init__(self, max_open_positions: int = 5, max_daily_loss_pct: float = 0.05, max_drawdown_pct: float = 0.15, max_sector_exposure_pct: float = 0.40):
        self.max_open_positions = max_open_positions
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.max_sector_exposure_pct = max_sector_exposure_pct
        
        self.trading_halted = False
        
    def evaluate_halt(self, current_capital: float, peak_capital: float, daily_pnl: float, start_of_day_capital: float) -> bool:
        if current_capital <= 0:
            self.trading_halted = True
            log.warning("FATAL: Capital wiped out. Trading Halted.")
            return True
            
        drawdown = (peak_capital - current_capital) / peak_capital
        if drawdown >= self.max_drawdown_pct:
            self.trading_halted = True
            log.warning(f"RISK LIMIT BREACH: Max Drawdown ({drawdown*100:.1f}%) exceeded. Trading Halted.")
            return True
            
        if start_of_day_capital > 0:
            daily_loss = daily_pnl / start_of_day_capital
            if daily_loss <= -self.max_daily_loss_pct:
                log.warning(f"DAILY RISK LIMIT: Daily loss ({daily_loss*100:.1f}%) exceeded limit. Halting for day.")
                return True # Soft halt
                
        return self.trading_halted

    def can_open_position(self, active_trades: list[PaperTrade], symbol: str, sector: str, current_capital: float) -> bool:
        if len(active_trades) >= self.max_open_positions:
            return False
            
        # Max Single Position Exposure (1 per ticker at a time)
        sector_capital_used = 0.0
        for t in active_trades:
            if t.symbol == symbol:
                return False
            if t.sector == sector:
                sector_capital_used += t.capital_allocated
                
        # Sector Exposure Limit
        if current_capital > 0:
            if (sector_capital_used / current_capital) >= self.max_sector_exposure_pct:
                log.warning(f"Sector Exposure Limit ({self.max_sector_exposure_pct*100}%) breached for {sector}. Rejecting {symbol}.")
                return False
                
        return True


class PositionSizingEngine:
    def __init__(self, risk_per_trade_pct: float = 0.01, max_allocation_pct: float = 0.20):
        """
        risk_per_trade_pct: Fixed fractional risk model (e.g. risk 1% of account equity per trade).
        max_allocation_pct: Hard limit on capital allocated to a single trade.
        """
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_allocation_pct = max_allocation_pct
        
    def calculate_size(self, current_capital: float, entry_price: float, sl_price: float, symbol: str) -> dict[str, Any]:
        """Calculates quantity strictly bounded by exact F&O lot sizes."""
        if entry_price <= 0 or sl_price <= 0 or current_capital <= 0:
            return {"quantity": 0, "lots": 0, "capital_allocated": 0, "risk_amount": 0}
            
        # Absolute distance to stop loss
        sl_distance = abs(entry_price - sl_price)
        if sl_distance == 0:
            return {"quantity": 0, "capital_allocated": 0, "risk_amount": 0}
            
        # Cash risk allowed
        risk_amount = current_capital * self.risk_per_trade_pct
        
        # Determine quantity based on SL distance
        raw_quantity = int(risk_amount / sl_distance)
        
        # Enforce Lot Size Rounding
        lot_size = LotSizeRegistry.get_lot_size(symbol)
        num_lots = int(raw_quantity / lot_size)
        
        if num_lots == 0:
            return {"quantity": 0, "lots": 0, "capital_allocated": 0, "risk_amount": 0}
            
        final_quantity = num_lots * lot_size
        
        # Calculate capital needed
        required_capital = final_quantity * entry_price
        max_allowed_capital = current_capital * self.max_allocation_pct
        
        # Throttle quantity if capital allocation exceeds limits
        if required_capital > max_allowed_capital:
            max_lots = int((max_allowed_capital / entry_price) / lot_size)
            if max_lots == 0:
                return {"quantity": 0, "lots": 0, "capital_allocated": 0, "risk_amount": 0}
            final_quantity = max_lots * lot_size
            required_capital = final_quantity * entry_price
            
        risk_amount = final_quantity * sl_distance
            
        return {
            "quantity": final_quantity,
            "lots": int(final_quantity / lot_size),
            "capital_allocated": required_capital,
            "risk_amount": risk_amount
        }
