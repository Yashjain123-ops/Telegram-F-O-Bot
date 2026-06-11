"""Cooldown tracking for alert deduplication."""

from __future__ import annotations

from datetime import datetime, timezone


class CooldownTracker:
    """Stores latest signal stage per symbol and applies cooldown rules."""

    def __init__(self, cooldown_seconds: int):
        self.cooldown_seconds = cooldown_seconds
        self.records: dict[str, dict] = {}

    def is_on_cooldown(self, symbol: str, stage: int, now: datetime | None = None) -> bool:
        record = self.records.get(symbol)
        if not record:
            return False
        if record["stage"] < stage:
            return False
        current = now or datetime.now(timezone.utc)
        elapsed = (current - record["ts"]).total_seconds()
        return elapsed < self.cooldown_seconds

    def record(self, symbol: str, stage: int, now: datetime | None = None) -> None:
        self.records[symbol] = {
            "stage": stage,
            "ts": now or datetime.now(timezone.utc),
        }

    def clear(self) -> None:
        self.records.clear()

