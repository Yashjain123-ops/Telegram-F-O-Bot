"""Volume Anomaly Detector"""

import pandas as pd
from project_alpha.scanner.detectors.base import DetectorInput, DetectorResult, Evidence
from project_alpha.domain.models import Direction

def detect_volume_anomaly(input_data: DetectorInput, rvol_threshold: float = 2.5) -> DetectorResult:
    df = input_data.candles
    if df is None or len(df) < 20:
        return DetectorResult(qualified=False, reason="Insufficient candles")

    try:
        current_time = df.index[-1].time()
        same_time_candles = df.between_time(current_time, current_time)
        current_date = df.index[-1].date()
        historical_same_time = same_time_candles[same_time_candles.index.date < current_date]
        
        if len(historical_same_time) >= 5:
            baseline_vol = historical_same_time['volume'].tail(20).mean()
        else:
            baseline_vol = df["volume"].tail(20).mean()
    except Exception:
        baseline_vol = df["volume"].tail(20).mean()

    current_candle = df.iloc[-1]
    current_vol = current_candle.get("volume", 0)
    
    if pd.isna(current_vol) or current_vol == 0 or baseline_vol == 0:
        return DetectorResult(qualified=False, reason="No volume data")

    rvol = current_vol / baseline_vol
    if rvol < rvol_threshold:
        return DetectorResult(qualified=False, reason="Low RVOL")

    prev_vol = df.iloc[-2].get("volume", 0)
    vol_accel = current_vol / prev_vol if prev_vol > 0 else 1.0

    vwap = current_candle.get("vwap", current_candle["close"])
    close = current_candle["close"]
    open_px = current_candle["open"]
    high = current_candle["high"]
    low = current_candle["low"]
    
    direction = Direction.BULLISH if close > vwap else Direction.BEARISH

    body = abs(close - open_px)
    upper_wick = high - max(open_px, close)
    lower_wick = min(open_px, close) - low
    total_range = high - low
    
    if total_range == 0:
        return DetectorResult(qualified=False, reason="Zero range candle")

    is_bull_trap = (upper_wick > (body * 1.5)) and (close < vwap)
    is_bear_trap = (lower_wick > (body * 1.5)) and (close > vwap)
    
    if is_bull_trap and direction == Direction.BEARISH:
        state = "BULL_TRAP_DISTRIBUTION"
    elif is_bear_trap and direction == Direction.BULLISH:
        state = "BEAR_TRAP_ACCUMULATION"
    elif close > open_px:
        state = "ACCUMULATION"
    else:
        state = "DISTRIBUTION"

    if is_bull_trap and direction == Direction.BULLISH:
        return DetectorResult(qualified=False, reason="Bull Trap against trend")
    if is_bear_trap and direction == Direction.BEARISH:
        return DetectorResult(qualified=False, reason="Bear Trap against trend")

    confidence = min((rvol / 5.0) * 35.0, 35.0)
    if vol_accel > 1.5:
        confidence = min(confidence + 5.0, 35.0)

    evidence = Evidence(
        kind="VOLUME",
        label=state,
        value=rvol,
        confidence=confidence,
        metadata={"rvol": rvol, "direction": direction.value, "vol_accel": vol_accel}
    )

    return DetectorResult(
        qualified=True,
        confidence_add=confidence,
        evidence=[evidence],
        data={"rvol": rvol, "direction": direction.value, "state": state, "vol_accel": vol_accel}
    )
