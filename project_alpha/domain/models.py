"""Typed contracts for the Project Alpha event pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Direction(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class SignalStage(int, Enum):
    SUSPECTED = 1
    CONFIRMED = 2
    PRIME_CANDIDATE = 3


@dataclass(slots=True)
class Tick:
    symbol: str
    ltp: float
    timestamp: datetime
    volume_delta: int = 1
    source: str = "GROWW"


@dataclass(slots=True)
class Candle:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    def to_legacy_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


@dataclass(slots=True)
class MarketContextSnapshot:
    fii_net_crore: float = 0.0
    dii_net_crore: float = 0.0
    fii_sentiment: str = "NEUTRAL"
    nifty_pcr: float = 1.0
    pcr_sentiment: str = "NEUTRAL"
    nifty_max_pain: float = 0.0
    nifty_regime: str = "NEUTRAL"
    earnings_today: frozenset[str] = frozenset()
    recent_headlines: tuple[str, ...] = ()
    updated_at: datetime | None = None
    source_status: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class SignalCandidate:
    symbol: str
    sector: str
    direction: Direction
    stage: SignalStage
    ltp: float
    confidence: float
    reasons: list[str] = field(default_factory=list)
    features: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass(slots=True)
class Signal:
    symbol: str
    sector: str
    direction: Direction
    stage: SignalStage
    entry: float
    stop_loss: float
    target: float
    rr_ratio: float
    confidence: float
    reasons: list[str] = field(default_factory=list)
    features: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass(slots=True)
class AlertRequest:
    signal: Signal
    message: str
    chart_bytes: bytes | None = None

