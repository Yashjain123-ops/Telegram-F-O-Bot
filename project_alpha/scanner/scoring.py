"""Scoring Engine for Phase 2."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, List

from project_alpha.scanner.detectors.base import Evidence, DetectorResult, DetectorInput
from project_alpha.domain.models import Direction

@dataclass(slots=True)
class ScoreBreakdown:
    total: float
    evidence: list[Evidence] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    category: str = "NOISE"
    direction: Direction = Direction.NEUTRAL

class EvidenceScorer(Protocol):
    def score(self, evidence: list[Evidence]) -> ScoreBreakdown:
        ...

class InstitutionalScoringEngine:
    def _determine_dominant_direction(self, results: List[DetectorResult]) -> Direction:
        bullish_score = 0.0
        bearish_score = 0.0
        
        for res in results:
            if not res.qualified: continue
            score = res.confidence_add
            if res.data.get("direction") == "BULLISH":
                bullish_score += score
            elif res.data.get("direction") == "BEARISH":
                bearish_score += score
                
        if bullish_score == 0 and bearish_score == 0:
            return Direction.NEUTRAL
        return Direction.BULLISH if bullish_score > bearish_score else Direction.BEARISH

    def calculate_global_score(self, results: List[DetectorResult], input_data: DetectorInput) -> ScoreBreakdown:
        dominant_direction = self._determine_dominant_direction(results)
        
        base_score = 0.0
        for res in results:
            if res.qualified and res.data.get("direction") == dominant_direction.value:
                base_score += res.confidence_add
                
        penalties = 0.0
        bonuses = 0.0
        
        if input_data.candles is not None and not input_data.candles.empty:
            last_candle = input_data.candles.iloc[-1]
            close = last_candle["close"]
            vwap = last_candle.get("vwap", close)
            
            if dominant_direction == Direction.BULLISH and close < vwap:
                penalties += 20.0
            elif dominant_direction == Direction.BEARISH and close > vwap:
                penalties += 20.0

        sector_triggered = any(r.qualified and "SECTOR" in [e.kind for e in r.evidence] for r in results)
        if not sector_triggered:
            penalties += 10.0

        aligned_engines = sum(1 for r in results if r.qualified and r.data.get("direction") == dominant_direction.value)
        if aligned_engines == 4:
            bonuses += 15.0

        final_score = base_score - penalties + bonuses
        final_score = max(0.0, min(100.0, final_score))

        category = "NOISE"
        if final_score >= 85: category = "EXTREME_ANOMALY"
        elif final_score >= 70: category = "HIGH_CONVICTION"
        elif final_score >= 40: category = "LOW_CONVICTION"

        all_evidence = []
        reasons = []
        for r in results:
            if r.qualified:
                all_evidence.extend(r.evidence)
                reasons.extend([e.label for e in r.evidence])

        if bonuses > 0:
            reasons.append(f"Institutional Consensus Bonus (+{bonuses})")
        if penalties > 0:
            reasons.append(f"Structural Penalty (-{penalties})")

        return ScoreBreakdown(
            total=final_score,
            evidence=all_evidence,
            reasons=reasons,
            category=category,
            direction=dominant_direction
        )
