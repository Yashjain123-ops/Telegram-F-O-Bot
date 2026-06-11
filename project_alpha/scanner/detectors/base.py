"""Detector contracts for Project Alpha scanner modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass(slots=True)
class DetectorInput:
    symbol: str
    candles: pd.DataFrame
    market_context: Any = None
    scanner_state: Any = None
    sector_candles: pd.DataFrame | None = None
    direction: str | None = None


@dataclass(slots=True)
class Evidence:
    kind: str
    label: str
    value: Any = None
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DetectorResult:
    qualified: bool
    reason: str = ""
    confidence_add: float = 0.0
    evidence: list[Evidence] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def to_legacy_dict(self) -> dict[str, Any]:
        payload = dict(self.data)
        payload.setdefault("qualified", self.qualified)
        if self.reason:
            payload.setdefault("reason", self.reason)
        payload.setdefault("confidence_add", self.confidence_add)
        return payload

