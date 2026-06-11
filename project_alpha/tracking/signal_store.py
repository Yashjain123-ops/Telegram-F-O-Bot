"""In-memory signal tracking primitives for future lifecycle management."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class SignalRecord:
    signal_id: str
    symbol: str
    stage: int
    direction: str
    created_at: datetime
    status: str = "ACTIVE"
    metadata: dict[str, Any] = field(default_factory=dict)
    
    # Phase 3 Validation Metrics
    entry_price: float = 0.0
    sl_price: float = 0.0
    target_price: float = 0.0
    sl_pct: float = 0.0
    target_pct: float = 0.0
    
    mfe: float = 0.0  # Maximum Favorable Excursion (%)
    mae: float = 0.0  # Maximum Adverse Excursion (%)
    exit_price: float = 0.0
    detector_reasons: list[str] = field(default_factory=list)
    institutional_score: float = 0.0
    expiry_minutes: int = 120  # Intraday signal expiry
    market_regime: str = "UNKNOWN"
    sector: str = "UNKNOWN"


class SignalStore:
    """Small in-memory store; can be replaced by persistence later."""

    def __init__(self):
        self.records: dict[str, SignalRecord] = {}

    def upsert(self, record: SignalRecord) -> None:
        self.records[record.signal_id] = record

    def get(self, signal_id: str) -> SignalRecord | None:
        return self.records.get(signal_id)
        
    def get_all_active(self) -> list[SignalRecord]:
        return [r for r in self.records.values() if r.status == "ACTIVE"]

    def clear(self) -> None:
        self.records.clear()
