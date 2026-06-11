"""Opening range breakout/breakdown detector."""

from __future__ import annotations

import pandas as pd

from .base import DetectorResult, Evidence


def detect_opening_range(df: pd.DataFrame) -> DetectorResult:
    current = df.iloc[-1]
    ltp = current["close"]
    vwap = current["vwap"]
    opening_high = df["high"].iloc[:3].max()
    opening_low = df["low"].iloc[:3].min()

    bullish = ltp > opening_high and ltp > vwap
    bearish = ltp < opening_low and ltp < vwap
    direction = "BULLISH" if bullish else ("BEARISH" if bearish else None)

    return DetectorResult(
        qualified=direction is not None,
        reason="" if direction else "No opening range break",
        confidence_add=0.30 if direction else 0.0,
        evidence=[
            Evidence(
                kind="opening_range",
                label="ORB Breakout" if bullish else ("ORB Breakdown" if bearish else "No ORB Break"),
                value=direction,
                confidence=0.30 if direction else 0.0,
                metadata={
                    "opening_high": opening_high,
                    "opening_low": opening_low,
                    "ltp": ltp,
                    "vwap": vwap,
                },
            )
        ],
        data={
            "direction": direction,
            "bullish": bullish,
            "bearish": bearish,
            "opening_high": opening_high,
            "opening_low": opening_low,
            "ltp": ltp,
            "vwap": vwap,
        },
    )

