"""Futures Basis Detector"""

import pandas as pd
from project_alpha.scanner.detectors.base import DetectorInput, DetectorResult, Evidence
from project_alpha.domain.models import Direction

def detect_futures_basis(input_data: DetectorInput, velocity_threshold: float = 0.05) -> DetectorResult:
    df = input_data.candles
    if len(df) < 5:
        return DetectorResult(qualified=False, reason="Insufficient candles")

    current_candle = df.iloc[-1]
    
    current_spot = current_candle.get("close", 0)
    current_futures = current_candle.get("futures_close", current_spot)
    
    if pd.isna(current_futures) or current_spot == 0:
        return DetectorResult(qualified=False, reason="No futures data")

    spot_series = df["close"]
    futures_series = df.get("futures_close", spot_series)
    basis_series = (futures_series - spot_series) / spot_series * 100.0

    current_basis = basis_series.iloc[-1]
    rolling_basis_mean = basis_series.iloc[-5:-1].mean()
    
    basis_velocity = current_basis - rolling_basis_mean

    if abs(basis_velocity) < velocity_threshold:
        return DetectorResult(qualified=False, reason="Stable basis")

    is_premium = current_basis > 0
    
    if basis_velocity > 0:
        direction = Direction.BULLISH
        if is_premium:
            state = "PREMIUM_EXPANSION"
        else:
            state = "DISCOUNT_CONTRACTION"
    else:
        direction = Direction.BEARISH
        if is_premium:
            state = "PREMIUM_CONTRACTION"
        else:
            state = "DISCOUNT_EXPANSION"
            
    urgency = abs(basis_velocity) > 0.15
    if urgency:
        state += "_WITH_URGENCY"
    
    confidence = min((abs(basis_velocity) / 0.15) * 15.0, 15.0)

    evidence = Evidence(
        kind="BASIS",
        label=state,
        value=basis_velocity,
        confidence=confidence,
        metadata={"direction": direction.value, "basis_velocity": basis_velocity, "current_basis": current_basis, "urgency": urgency}
    )

    return DetectorResult(
        qualified=True,
        confidence_add=confidence,
        evidence=[evidence],
        data={"direction": direction.value, "basis_velocity": basis_velocity, "state": state, "urgency": urgency}
    )
