"""Backtesting Orchestrator."""

from __future__ import annotations

import asyncio
from typing import Dict, Any
import pandas as pd
import logging

from project_alpha.backtesting.replay import HistoricalReplayEngine
from project_alpha.backtesting.stats import (
    MonteCarloSimulator, 
    RollingWalkForwardEvaluator,
    DetectorAttributionAnalyzer,
    ScoreBucketAnalyzer,
    RegimeAnalyzer
)

log = logging.getLogger("BacktestOrchestrator")

class BacktestFramework:
    def __init__(self, strategy_instance, historical_data: Dict[str, pd.DataFrame]):
        """
        Orchestrates Phase 4 Backtesting.
        strategy_instance: An instance of MomentumScanner (from stratergy.py)
        historical_data: The entire historical tick/candle database to replay.
        """
        self.strategy = strategy_instance
        # Bind the replay engine to the strategy's exact live entry point (on_candle)
        self.replay = HistoricalReplayEngine(historical_data, self.strategy.on_candle)
        
    async def run_full_validation(self, start_date=None, end_date=None) -> dict[str, Any]:
        """
        Executes a complete historical replay followed by statistical verification.
        """
        log.info("Wiping memory state for clean backtest...")
        self.strategy.signal_store.clear()
        self.strategy.validation_engine.closed_signals.clear()
        
        # 1. Historical Replay Engine execution
        await self.replay.run_replay(start_date, end_date)
        
        signals = self.strategy.validation_engine.closed_signals
        if not signals:
            log.warning("Backtest completed but 0 signals were generated.")
            return {"error": "0 signals generated"}
            
        log.info(f"Backtest Replay completed. Generated {len(signals)} completed trades.")
        log.info("Running Statistical Verification Engine...")
        
        # 2. Hardened Edge Verification (Monte Carlo)
        mc = MonteCarloSimulator(signals)
        mc_results = mc.run_hardened()
        
        # 3. Rolling Walk Forward Testing
        wf = RollingWalkForwardEvaluator(signals)
        wf_results = wf.evaluate(train_days=60, test_days=15)
        
        # 4. Phase 4 Hardening Extensions
        detector_attribution = DetectorAttributionAnalyzer(signals).analyze()
        score_buckets = ScoreBucketAnalyzer(signals).analyze()
        regime_analysis = RegimeAnalyzer(signals).analyze()
        
        # 5. Phase 3 Base Reporting
        base_report = self.strategy.validation_engine.generate_report()
        
        # Aggregate the Complete Institutional Research Report
        report = {
            "Total Signals Processed": len(signals),
            "Base Metrics": base_report,
            "Edge Verification (Hardened)": mc_results,
            "Overfitting Analysis (Rolling Walk Forward)": wf_results,
            "Detector Attribution": detector_attribution,
            "Score Bucket Calibration": score_buckets,
            "Market Regime Analysis": regime_analysis
        }
        
        log.info("Phase 4 Hardened Backtest Framework execution complete.")
        return report
