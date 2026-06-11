"""Risk/reward filter."""

from __future__ import annotations

import config
from .base import DetectorResult, Evidence


def calculate_institutional_rr(entry: float, stop_loss: float, vol_ratio: float) -> DetectorResult:
    risk = abs(entry - stop_loss)
    if risk <= 0:
        return DetectorResult(
            qualified=False,
            reason="Invalid risk",
            data={"viable": False, "rr_ratio": 0.0, "target": entry, "risk": 0.0, "tier": 0},
        )

    if vol_ratio >= config.CAMPAIGN_VOL_SPIKE:
        rr_mult = config.CAMPAIGN_DAY_RR_MULT
        tier = 3
        tier_label = "CAMPAIGN DAY"
    elif vol_ratio >= config.SNIPER_VOL_SPIKE:
        rr_mult = config.TREND_DAY_RR_MULT
        tier = 2
        tier_label = "STRONG DAY"
    else:
        rr_mult = config.STANDARD_RR_MULT
        tier = 1
        tier_label = "TREND DAY"

    target = entry + (risk * rr_mult) if entry > stop_loss else entry - (risk * rr_mult)
    actual_rr = abs(target - entry) / risk
    viable = actual_rr >= config.MIN_RR_RATIO
    data = {
        "viable": viable,
        "rr_ratio": round(actual_rr, 2),
        "target": round(target, 2),
        "risk": round(risk, 2),
        "tier": tier,
        "tier_label": tier_label,
    }
    return DetectorResult(
        qualified=viable,
        reason="" if viable else "R:R below minimum",
        evidence=[
            Evidence("risk_reward", "Risk Reward", data["rr_ratio"], metadata=data)
        ],
        data=data,
    )
