"""OI Buildup Detector"""

import pandas as pd
from project_alpha.scanner.detectors.base import DetectorInput, DetectorResult, Evidence
from project_alpha.domain.models import Direction

def detect_oi_buildup(input_data: DetectorInput, oi_threshold_pct: float = 3.0) -> DetectorResult:
    df = input_data.candles
    if len(df) < 5:
        return DetectorResult(qualified=False, reason="Insufficient candles")

    current_candle = df.iloc[-1]
    
    if "oi" not in df.columns:
        return DetectorResult(qualified=False, reason="No OI data")
        
    current_oi = current_candle.get("oi", 0)
    prev_oi = df["oi"].iloc[-5:-1].mean()
    
    if pd.isna(current_oi) or pd.isna(prev_oi) or prev_oi == 0:
        return DetectorResult(qualified=False, reason="No OI data")

    delta_oi_pct = ((current_oi - prev_oi) / prev_oi) * 100.0
    
    current_close = current_candle["close"]
    prev_close = df["close"].iloc[-5]
    delta_price_pct = ((current_close - prev_close) / prev_close) * 100.0

    if abs(delta_oi_pct) < oi_threshold_pct:
        return DetectorResult(qualified=False, reason="Low OI change")

    if delta_oi_pct > 0 and delta_price_pct > 0:
        direction = Direction.BULLISH
        buildup_type = "LONG_BUILDUP"
    elif delta_oi_pct < 0 and delta_price_pct > 0:
        direction = Direction.BULLISH
        buildup_type = "SHORT_COVERING"
    elif delta_oi_pct > 0 and delta_price_pct < 0:
        direction = Direction.BEARISH
        buildup_type = "SHORT_BUILDUP"
    elif delta_oi_pct < 0 and delta_price_pct < 0:
        direction = Direction.BEARISH
        buildup_type = "LONG_UNWINDING"
    else:
        return DetectorResult(qualified=False, reason="Neutral Buildup")

    confidence = min((abs(delta_oi_pct) / 8.0) * 30.0, 30.0)

    evidence = Evidence(
        kind="OI",
        label=buildup_type,
        value=delta_oi_pct,
        confidence=confidence,
        metadata={"direction": direction.value, "buildup_type": buildup_type, "delta_price_pct": delta_price_pct}
    )

    return DetectorResult(
        qualified=True,
        confidence_add=confidence,
        evidence=[evidence],
        data={"direction": direction.value, "delta_oi_pct": delta_oi_pct, "buildup_type": buildup_type}
    )
