"""Volume evidence helpers."""

from __future__ import annotations

import pandas as pd

import config
from .base import DetectorResult, Evidence


def calculate_volume_ratio(
    df: pd.DataFrame,
    lookback_period: int = config.AVG_VOLUME_LOOKBACK,
) -> dict:
    lookback = min(lookback_period, len(df) - 1)
    avg_vol = df["volume"].iloc[-lookback - 1:-1].mean() if lookback > 0 else 1
    cur_vol = df["volume"].iloc[-1]
    ratio = (cur_vol / avg_vol) if avg_vol > 0 else 0
    return {
        "lookback": lookback,
        "avg_volume": avg_vol,
        "current_volume": cur_vol,
        "vol_ratio": ratio,
    }


def detect_institutional_volume(df: pd.DataFrame) -> DetectorResult:
    metrics = calculate_volume_ratio(df)
    vol_ratio = metrics["vol_ratio"]
    qualified = vol_ratio >= config.INSTITUTIONAL_VOL_SPIKE
    return DetectorResult(
        qualified=qualified,
        reason="" if qualified else "Volume below institutional threshold",
        confidence_add=0.25 if vol_ratio >= config.SNIPER_VOL_SPIKE else (0.20 if qualified else 0.0),
        evidence=[
            Evidence(
                kind="volume",
                label="Institutional Volume",
                value=round(vol_ratio, 2),
                confidence=0.25 if vol_ratio >= config.SNIPER_VOL_SPIKE else (0.20 if qualified else 0.0),
                metadata=metrics,
            )
        ],
        data={
            **metrics,
            "vol_ratio": round(vol_ratio, 2),
            "institutional_vol": qualified,
        },
    )

