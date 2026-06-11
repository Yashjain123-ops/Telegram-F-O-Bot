"""Market-session schedule helpers."""

from __future__ import annotations

from datetime import datetime, time
from enum import Enum


class SessionPhase(str, Enum):
    CLOSED = "CLOSED"
    WARMUP = "WARMUP"
    ACTIVE = "ACTIVE"


def get_session_phase(
    now: datetime,
    warmup_start: time,
    scanner_start: time,
    market_close: time,
) -> SessionPhase:
    if now.weekday() >= 5:
        return SessionPhase.CLOSED
    current = now.time()
    if warmup_start <= current < scanner_start:
        return SessionPhase.WARMUP
    if scanner_start <= current <= market_close:
        return SessionPhase.ACTIVE
    return SessionPhase.CLOSED


def is_market_session(
    now: datetime,
    warmup_start: time,
    market_close: time,
) -> bool:
    if now.weekday() >= 5:
        return False
    return warmup_start <= now.time() <= market_close


def is_scanner_active(
    now: datetime,
    scanner_start: time,
    market_close: time,
) -> bool:
    if now.weekday() >= 5:
        return False
    return scanner_start <= now.time() <= market_close

