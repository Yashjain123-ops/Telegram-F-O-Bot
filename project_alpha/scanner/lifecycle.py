"""Lifecycle Engine for Phase 2."""

from __future__ import annotations

from project_alpha.domain.models import SignalStage
from project_alpha.scanner.scoring import ScoreBreakdown

class LifecycleEngine:
    def evaluate_transition(self, score_breakdown: ScoreBreakdown, current_stage: int) -> int:
        score = score_breakdown.total
        evidence_kinds = [e.kind for e in score_breakdown.evidence]

        has_vol = "VOLUME" in evidence_kinds
        has_oi = "OI" in evidence_kinds
        has_basis = "BASIS" in evidence_kinds
        has_sector = "SECTOR" in evidence_kinds
        
        # Kill Rules: Instant demotion to 0
        # If noise or counter-trend completely overtakes
        if score < 20:
            return 0
            
        # Promotion / Demotion logic
        new_stage = current_stage
        
        if score >= 85 and has_vol and has_sector:
            new_stage = SignalStage.PRIME_CANDIDATE
        elif score >= 60 and has_vol:
            new_stage = SignalStage.CONFIRMED
        elif score >= 35 and has_vol:
            new_stage = SignalStage.SUSPECTED
        else:
            new_stage = 0
            
        # Hard Demotion rule: If we were Prime Candidate but lost Sector and OI, drop down
        if current_stage == SignalStage.PRIME_CANDIDATE and new_stage < SignalStage.PRIME_CANDIDATE:
            # We enforce a penalty demotion
            return SignalStage.CONFIRMED if score >= 60 else SignalStage.SUSPECTED

        return new_stage
