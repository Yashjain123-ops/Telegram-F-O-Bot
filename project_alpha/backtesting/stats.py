"""Statistical Edge Verification Engine for Phase 4 Hardening."""

from __future__ import annotations
import numpy as np
import pandas as pd
from typing import List, Dict, Any
from collections import defaultdict
from datetime import timedelta
from project_alpha.tracking.signal_store import SignalRecord

class RollingWalkForwardEvaluator:
    def __init__(self, signals: List[SignalRecord]):
        self.signals = sorted(signals, key=lambda s: s.created_at)

    def evaluate(self, train_days: int = 60, test_days: int = 15) -> dict[str, Any]:
        """
        True Rolling Walk-Forward Analysis.
        Slides a training window and testing window through the entire dataset.
        """
        if not self.signals:
            return {"error": "No signals provided"}
            
        start_date = self.signals[0].created_at
        end_date = self.signals[-1].created_at
        
        current_train_start = start_date
        results = []
        
        while True:
            train_end = current_train_start + timedelta(days=train_days)
            test_end = train_end + timedelta(days=test_days)
            
            if train_end >= end_date:
                break
                
            in_sample = [s for s in self.signals if current_train_start <= s.created_at < train_end]
            out_sample = [s for s in self.signals if train_end <= s.created_at < test_end]
            
            if not in_sample or not out_sample:
                current_train_start += timedelta(days=test_days)
                continue
                
            is_wr, is_pf = self._calc_metrics(in_sample)
            os_wr, os_pf = self._calc_metrics(out_sample)
            
            results.append({
                "window_start": current_train_start.isoformat(),
                "is_wr": is_wr,
                "os_wr": os_wr,
                "is_pf": is_pf,
                "os_pf": os_pf,
                "degradation_wr": is_wr - os_wr,
                "degradation_pf": is_pf - os_pf if os_pf != float('inf') else 0.0
            })
            
            current_train_start += timedelta(days=test_days)
            
        if not results:
            return {"error": "Insufficient timespan for rolling WF"}
            
        avg_degradation_wr = np.mean([r["degradation_wr"] for r in results])
        avg_degradation_pf = np.mean([r["degradation_pf"] for r in results])
        
        return {
            "windows_tested": len(results),
            "avg_degradation_wr": avg_degradation_wr,
            "avg_degradation_pf": avg_degradation_pf,
            "system_stable": avg_degradation_wr < 0.15 and avg_degradation_pf < 0.5,
            "windows": results
        }

    def _calc_metrics(self, sample: List[SignalRecord]) -> tuple[float, float]:
        wins = sum(1 for s in sample if s.status == "WIN")
        losses = sum(1 for s in sample if s.status == "LOSS")
        wr = wins / len(sample) if sample else 0.0
        
        prof = sum(s.mfe for s in sample if s.status == "WIN")
        loss = sum(abs(s.mae) for s in sample if s.status == "LOSS")
        pf = prof / loss if loss > 0 else float('inf')
        return wr, pf


class DetectorAttributionAnalyzer:
    def __init__(self, signals: List[SignalRecord]):
        self.signals = signals

    def analyze(self) -> dict[str, Any]:
        """
        Calculates contribution, win rate, expectancy, and false positive rates
        for each isolated detector logic path.
        """
        stats = defaultdict(lambda: {"wins": 0, "losses": 0, "profit": 0.0, "loss": 0.0})
        
        for s in self.signals:
            for reason in s.detector_reasons:
                if s.status == "WIN":
                    stats[reason]["wins"] += 1
                    stats[reason]["profit"] += s.mfe
                elif s.status == "LOSS":
                    stats[reason]["losses"] += 1
                    stats[reason]["loss"] += abs(s.mae)
                    
        attribution = {}
        for r, d in stats.items():
            total = d["wins"] + d["losses"]
            wr = d["wins"] / total if total > 0 else 0.0
            pf = d["profit"] / d["loss"] if d["loss"] > 0 else float('inf')
            avg_win = d["profit"] / d["wins"] if d["wins"] > 0 else 0.0
            avg_loss = d["loss"] / d["losses"] if d["losses"] > 0 else 0.0
            expectancy = (wr * avg_win) - ((1 - wr) * avg_loss)
            
            attribution[r] = {
                "total_signals_involved": total,
                "win_rate": wr,
                "profit_factor": pf,
                "expectancy": expectancy,
                "false_positive_rate": 1.0 - wr
            }
            
        return dict(sorted(attribution.items(), key=lambda x: x[1]["expectancy"], reverse=True))


class ScoreBucketAnalyzer:
    def __init__(self, signals: List[SignalRecord]):
        self.signals = signals

    def analyze(self) -> dict[str, Any]:
        buckets = {"50-59": [], "60-69": [], "70-79": [], "80-89": [], "90-100": []}
        for s in self.signals:
            score = s.institutional_score
            if 50 <= score < 60: buckets["50-59"].append(s)
            elif 60 <= score < 70: buckets["60-69"].append(s)
            elif 70 <= score < 80: buckets["70-79"].append(s)
            elif 80 <= score < 90: buckets["80-89"].append(s)
            elif score >= 90: buckets["90-100"].append(s)
            
        results = {}
        for b, records in buckets.items():
            if not records: continue
            wins = sum(1 for s in records if s.status == "WIN")
            losses = sum(1 for s in records if s.status == "LOSS")
            wr = wins / len(records)
            prof = sum(s.mfe for s in records if s.status == "WIN")
            loss = sum(abs(s.mae) for s in records if s.status == "LOSS")
            pf = prof / loss if loss > 0 else float('inf')
            
            avg_win = prof / wins if wins > 0 else 0.0
            avg_loss = loss / losses if losses > 0 else 0.0
            exp = (wr * avg_win) - ((1 - wr) * avg_loss)
            
            results[b] = {
                "signal_count": len(records),
                "win_rate": wr,
                "profit_factor": pf,
                "expectancy": exp
            }
        return results


class RegimeAnalyzer:
    def __init__(self, signals: List[SignalRecord]):
        self.signals = signals

    def analyze(self) -> dict[str, Any]:
        """Evaluates how the system performs in different Nifty regimes."""
        regimes = defaultdict(list)
        for s in self.signals:
            regimes[s.market_regime].append(s)
            
        results = {}
        for r, records in regimes.items():
            wins = sum(1 for s in records if s.status == "WIN")
            losses = sum(1 for s in records if s.status == "LOSS")
            wr = wins / len(records) if records else 0.0
            prof = sum(s.mfe for s in records if s.status == "WIN")
            loss = sum(abs(s.mae) for s in records if s.status == "LOSS")
            pf = prof / loss if loss > 0 else float('inf')
            
            avg_win = prof / wins if wins > 0 else 0.0
            avg_loss = loss / losses if losses > 0 else 0.0
            exp = (wr * avg_win) - ((1 - wr) * avg_loss)
            
            results[r] = {
                "signal_count": len(records),
                "win_rate": wr,
                "profit_factor": pf,
                "expectancy": exp
            }
        return results


class MonteCarloSimulator:
    def __init__(self, signals: List[SignalRecord], iterations: int = 1000):
        self.signals = signals
        self.iterations = iterations
        
    def _run_permutation(self, records: List[SignalRecord]) -> dict:
        if not records:
            return {"p_value": 1.0, "edge_verified": False}
        actual_profit = sum(s.mfe for s in records if s.status == "WIN") - sum(abs(s.mae) for s in records if s.status == "LOSS")
        outcomes = [s.mfe if s.status == "WIN" else -abs(s.mae) for s in records]
        
        results = []
        for _ in range(self.iterations):
            simulated = np.random.choice(outcomes, size=len(outcomes), replace=True)
            results.append(np.sum(simulated))
            
        better_sims = sum(1 for r in results if r >= actual_profit)
        p_value = better_sims / self.iterations
        return {"p_value": p_value, "edge_verified": p_value < 0.05}

    def run_hardened(self) -> dict[str, Any]:
        """
        Hardened Edge Verification. 
        Tests global edge, and tests whether edge survives across different stratifications.
        """
        global_mc = self._run_permutation(self.signals)
        
        # Cross-regime robustness
        regimes = set(s.market_regime for s in self.signals)
        regime_edges = {}
        for r in regimes:
            sub = [s for s in self.signals if s.market_regime == r]
            regime_edges[r] = self._run_permutation(sub)["edge_verified"]
            
        # Cross-score robustness (>70 vs <70)
        high_score = [s for s in self.signals if s.institutional_score >= 70]
        low_score = [s for s in self.signals if s.institutional_score < 70]
        high_edge = self._run_permutation(high_score)["edge_verified"]
        
        # System is robust if global edge exists AND it survives high conviction setups
        robust = global_mc["edge_verified"] and high_edge
        
        return {
            "global_p_value": global_mc["p_value"],
            "global_edge_verified": global_mc["edge_verified"],
            "high_score_edge_verified": high_edge,
            "regime_robustness": regime_edges,
            "system_robust": robust
        }
