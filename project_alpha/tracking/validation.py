"""Phase 3 Validation Engine."""

from __future__ import annotations

import pandas as pd
from typing import List, Dict, Any
from collections import defaultdict
import logging

from datetime import datetime, timezone

from project_alpha.tracking.signal_store import SignalRecord

log = logging.getLogger("Validation")

class PerformanceMetrics:
    def __init__(self):
        self.total_signals = 0
        self.wins = 0
        self.losses = 0
        self.total_profit_pct = 0.0
        self.total_loss_pct = 0.0
        
        # Detector Attribution
        self.detector_wins = defaultdict(int)
        self.detector_losses = defaultdict(int)
        
        # Score Bucket Analysis
        self.score_buckets_wins = {"80-100": 0, "60-79": 0, "40-59": 0, "0-39": 0}
        self.score_buckets_losses = {"80-100": 0, "60-79": 0, "40-59": 0, "0-39": 0}

    def _get_bucket(self, score: float) -> str:
        if score >= 80: return "80-100"
        if score >= 60: return "60-79"
        if score >= 40: return "40-59"
        return "0-39"

    def record_outcome(self, record: SignalRecord):
        self.total_signals += 1
        bucket = self._get_bucket(record.institutional_score)
        
        if record.status == "WIN":
            self.wins += 1
            self.total_profit_pct += record.mfe
            self.score_buckets_wins[bucket] += 1
            for reason in record.detector_reasons:
                self.detector_wins[reason] += 1
        elif record.status == "LOSS":
            self.losses += 1
            self.total_loss_pct += abs(record.mae)
            self.score_buckets_losses[bucket] += 1
            for reason in record.detector_reasons:
                self.detector_losses[reason] += 1

    def get_expectancy(self) -> float:
        if self.total_signals == 0: return 0.0
        win_rate = self.wins / self.total_signals
        loss_rate = self.losses / self.total_signals
        avg_win = self.total_profit_pct / self.wins if self.wins > 0 else 0.0
        avg_loss = self.total_loss_pct / self.losses if self.losses > 0 else 0.0
        return (win_rate * avg_win) - (loss_rate * avg_loss)

    def get_profit_factor(self) -> float:
        if self.total_loss_pct == 0.0: return float('inf') if self.total_profit_pct > 0 else 0.0
        return self.total_profit_pct / self.total_loss_pct


class ValidationEngine:
    def __init__(self):
        self.closed_signals: List[SignalRecord] = []
        self.metrics = PerformanceMetrics()
        
    def update_signal(self, record: SignalRecord, current_candle: pd.Series) -> None:
        """Called on every new candle to update MFE, MAE and status."""
        if record.status != "ACTIVE" or record.entry_price == 0:
            return
            
        high = current_candle["high"]
        low = current_candle["low"]
        close = current_candle["close"]
        
        entry = record.entry_price
            
        if record.direction == "BULLISH":
            mfe = (high - entry) / entry * 100.0
            mae = (low - entry) / entry * 100.0
        else:
            mfe = (entry - low) / entry * 100.0
            mae = (entry - high) / entry * 100.0
            
        record.mfe = max(record.mfe, mfe)
        record.mae = min(record.mae, mae)
        
        # Win/Loss Classification and Intra-Candle Collision Handling
        target_hit = record.target_pct > 0 and mfe >= record.target_pct
        sl_hit = record.sl_pct > 0 and mae <= -record.sl_pct

        if target_hit and sl_hit:
            # PESSIMISTIC COLLISION: If both target and SL are breached in the same 1-min candle,
            # we assume SL was hit first to prevent false confidence in backtesting validation.
            record.status = "LOSS"
            record.exit_price = record.sl_price
            self._close_signal(record)
        elif target_hit:
            record.status = "WIN"
            record.exit_price = record.target_price
            self._close_signal(record)
        elif sl_hit:
            record.status = "LOSS"
            record.exit_price = record.sl_price
            self._close_signal(record)
        else:
            # Time-based Signal Expiry logic
            if getattr(record, 'expiry_minutes', 0) > 0:
                delta = datetime.now(timezone.utc) - record.created_at
                if delta.total_seconds() / 60.0 > record.expiry_minutes:
                    record.status = "EXPIRED"
                    record.exit_price = close
                    self._close_signal(record)

    def _close_signal(self, record: SignalRecord):
        self.closed_signals.append(record)
        self.metrics.record_outcome(record)
        log.info(f"Signal {record.signal_id} Closed as {record.status}. MFE: {record.mfe:.2f}%, MAE: {record.mae:.2f}%")

    def evaluate_kill_switch(self) -> bool:
        """
        Hybrid Kill Switch: 
        Evaluates a rolling 10-signal window. If Win Rate < 30% AND Profit Factor < 0.5, 
        it triggers a protective shutdown to prevent drawdown.
        """
        recent = self.closed_signals[-10:]
        if len(recent) < 10:
            return False
            
        wins = sum(1 for s in recent if s.status == "WIN")
        losses = sum(1 for s in recent if s.status == "LOSS")
        total_finished = wins + losses
        
        if total_finished == 0:
            return False
            
        win_rate = wins / total_finished
        
        total_profit = sum(s.mfe for s in recent if s.status == "WIN")
        total_loss = sum(abs(s.mae) for s in recent if s.status == "LOSS")
        
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
        
        if win_rate < 0.30 and profit_factor < 0.5:
            return True
        return False
        
    def generate_report(self) -> dict[str, Any]:
        return {
            "total_signals": self.metrics.total_signals,
            "win_rate": (self.metrics.wins / self.metrics.total_signals * 100) if self.metrics.total_signals > 0 else 0.0,
            "profit_factor": self.metrics.get_profit_factor(),
            "expectancy_pct": self.metrics.get_expectancy(),
            "kill_switch_active": self.evaluate_kill_switch(),
            "detector_attribution": {
                "wins": dict(self.metrics.detector_wins),
                "losses": dict(self.metrics.detector_losses)
            },
            "score_buckets": {
                "wins": self.metrics.score_buckets_wins,
                "losses": self.metrics.score_buckets_losses
            }
        }
