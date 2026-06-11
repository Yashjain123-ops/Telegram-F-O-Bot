"""Paper Trading Domain Models."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime

@dataclass(slots=True)
class PaperTrade:
    trade_id: str
    symbol: str
    sector: str
    direction: str
    entry_time: datetime
    entry_price: float
    quantity: int
    lots: int
    sl_price: float
    target_price: float
    capital_allocated: float
    risk_amount: float
    
    # Excursion Tracking
    highest_price: float = 0.0
    lowest_price: float = 0.0
    
    # Resolution
    status: str = "OPEN" # OPEN, CLOSED_WIN, CLOSED_LOSS, EXPIRED
    exit_time: datetime | None = None
    exit_price: float = 0.0
    gross_pnl: float = 0.0
    transaction_costs: float = 0.0
    net_pnl: float = 0.0
    roi_pct: float = 0.0
