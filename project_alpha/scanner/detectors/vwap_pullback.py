"""VWAP pullback detector."""

from __future__ import annotations

import pandas as pd

import config
from .base import DetectorResult, Evidence


def detect_vwap_pullback(df: pd.DataFrame, direction: str) -> DetectorResult:
    if len(df) < 8:
        return DetectorResult(
            qualified=False,
            reason="Insufficient pullback candles",
            data={"setup_confirmed": False},
        )

    ltp = df["close"].iloc[-1]
    vwap = df["vwap"].iloc[-1]
    atr = df["atr"].iloc[-1]

    if vwap <= 0 or atr <= 0:
        return DetectorResult(
            qualified=False,
            reason="Invalid VWAP/ATR",
            data={"setup_confirmed": False},
        )

    vwap_proximity_pct = abs(ltp - vwap) / vwap
    near_vwap = vwap_proximity_pct <= config.VWAP_PROXIMITY_BAND
    breakout_vol = df["volume"].iloc[-8:-3].mean()
    pullback_vol = df["volume"].iloc[-3:].mean()
    volume_dried = (pullback_vol < breakout_vol * config.PULLBACK_VOL_RATIO) if breakout_vol > 0 else False
    last = df.iloc[-1]
    candle_range = last["high"] - last["low"]
    close_location = (last["close"] - last["low"]) / candle_range if candle_range > 0 else 0.5

    if direction == "BULLISH":
        rejection_confirmed = close_location >= config.REJECTION_CLOSE_LOC
        setup_confirmed = near_vwap and volume_dried and rejection_confirmed and ltp > vwap
        entry_zone = round(vwap * 1.001, 2)
        invalidation = round(vwap * 0.997, 2)
    else:
        rejection_confirmed = close_location <= (1 - config.REJECTION_CLOSE_LOC)
        setup_confirmed = near_vwap and volume_dried and rejection_confirmed and ltp < vwap
        entry_zone = round(vwap * 0.999, 2)
        invalidation = round(vwap * 1.003, 2)

    data = {
        "setup_confirmed": setup_confirmed,
        "vwap": round(vwap, 2),
        "vwap_proximity_pct": round(vwap_proximity_pct * 100, 3),
        "volume_dried_up": volume_dried,
        "rejection_candle": rejection_confirmed,
        "entry_zone": entry_zone,
        "invalidation": invalidation,
        "confidence_add": 0.20 if setup_confirmed else 0.0,
    }
    return DetectorResult(
        qualified=setup_confirmed,
        reason="" if setup_confirmed else "VWAP pullback not confirmed",
        confidence_add=data["confidence_add"],
        evidence=[
            Evidence("vwap", "VWAP Proximity", data["vwap_proximity_pct"]),
            Evidence("volume", "Pullback Volume Dry-up", volume_dried),
            Evidence("price_action", "Rejection Candle", rejection_confirmed),
        ],
        data=data,
    )

