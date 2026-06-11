"""Fakeout candle detector."""

from __future__ import annotations

import pandas as pd

import config
from .base import DetectorResult, Evidence


def is_fakeout_candle(
    candle: pd.Series,
    direction: str,
    max_wick_percent: float = config.MAX_WICK_PERCENT,
) -> bool:
    total_range = candle["high"] - candle["low"]
    if total_range <= 0:
        return True
    if direction == "BULLISH":
        upper_wick = candle["high"] - max(candle["open"], candle["close"])
        return (upper_wick / total_range) > max_wick_percent
    if direction == "BEARISH":
        lower_wick = min(candle["open"], candle["close"]) - candle["low"]
        return (lower_wick / total_range) > max_wick_percent
    return False


def detect_fakeout(candle: pd.Series, direction: str) -> DetectorResult:
    fakeout = is_fakeout_candle(candle, direction)
    return DetectorResult(
        qualified=not fakeout,
        reason="Fakeout candle detected" if fakeout else "",
        evidence=[
            Evidence(
                kind="price_action",
                label="Fakeout Filter",
                value=fakeout,
                confidence=0.0,
            )
        ],
        data={"fakeout": fakeout},
    )

