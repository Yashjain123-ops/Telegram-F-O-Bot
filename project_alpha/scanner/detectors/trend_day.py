"""Trend-day quality detector."""

from __future__ import annotations

import pandas as pd

import config
from .base import DetectorResult, Evidence
from .volume import calculate_volume_ratio


def detect_trend_day(df: pd.DataFrame, sector_df: pd.DataFrame) -> DetectorResult:
    if len(df) < config.MIN_CANDLES_REQUIRED:
        return DetectorResult(
            qualified=False,
            reason="Insufficient candles",
            data={"vol_ratio": 0.0},
        )

    today_range = df["high"].max() - df["low"].min()
    atr = df["atr"].iloc[-1] if "atr" in df.columns else 0
    ltp = df["close"].iloc[-1]
    atr_price_ratio = (atr / ltp) if ltp > 0 else 0

    if atr_price_ratio < config.MIN_ATR_PRICE_RATIO:
        return DetectorResult(
            qualified=False,
            reason="Stock too illiquid/flat",
            data={"vol_ratio": 0.0},
        )

    range_expansion = (today_range / atr) if atr > 0 else 0
    volume_metrics = calculate_volume_ratio(df)
    vol_ratio = volume_metrics["vol_ratio"]
    institutional_vol = vol_ratio >= config.INSTITUTIONAL_VOL_SPIKE

    sector_momentum = False
    sector_vol_ratio = 0.0
    if len(sector_df) >= 5:
        sector_metrics = calculate_volume_ratio(sector_df)
        sector_vol_ratio = sector_metrics["vol_ratio"]
        sector_momentum = sector_vol_ratio >= config.SECTOR_VOL_SPIKE

    qualified = range_expansion >= 1.2 and institutional_vol and sector_momentum
    data = {
        "qualified": qualified,
        "vol_ratio": round(vol_ratio, 2),
        "range_expansion": round(range_expansion, 2),
        "sector_tailwind": sector_momentum,
        "sector_vol_ratio": round(sector_vol_ratio, 2),
        "atr": round(atr, 4),
        "ltp": round(ltp, 2),
    }
    return DetectorResult(
        qualified=qualified,
        reason="" if qualified else "No trend day quality",
        confidence_add=0.25 if qualified else 0.0,
        evidence=[
            Evidence("volume", "Volume Ratio", round(vol_ratio, 2)),
            Evidence("range", "Range Expansion", round(range_expansion, 2)),
            Evidence("sector", "Sector Tailwind", sector_momentum, 0.25 if sector_momentum else 0.0),
        ],
        data=data,
    )

