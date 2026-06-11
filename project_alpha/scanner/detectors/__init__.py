"""Detector modules for the Phase 1 & 2 scanner."""

from .base import DetectorInput, DetectorResult, Evidence
from .fakeout import detect_fakeout, is_fakeout_candle
from .opening_range import detect_opening_range
from .risk_reward import calculate_institutional_rr
from .trend_day import detect_trend_day
from .volume import calculate_volume_ratio, detect_institutional_volume
from .vwap_pullback import detect_vwap_pullback

from .volume_anomaly import detect_volume_anomaly
from .oi_buildup import detect_oi_buildup
from .futures_basis import detect_futures_basis
from .sector_participation import detect_sector_participation

__all__ = [
    "DetectorInput",
    "DetectorResult",
    "Evidence",
    "calculate_institutional_rr",
    "calculate_volume_ratio",
    "detect_fakeout",
    "detect_institutional_volume",
    "detect_opening_range",
    "detect_trend_day",
    "detect_vwap_pullback",
    "is_fakeout_candle",
    "detect_volume_anomaly",
    "detect_oi_buildup",
    "detect_futures_basis",
    "detect_sector_participation",
]

