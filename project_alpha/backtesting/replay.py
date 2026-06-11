"""Historical Replay Engine.

Reconstructs market events chronologically to eliminate lookahead bias.
"""

from __future__ import annotations

import pandas as pd
from typing import Dict, Any, Callable, Awaitable
import asyncio
import logging

log = logging.getLogger("ReplayEngine")

class HistoricalReplayEngine:
    def __init__(self, historical_data: Dict[str, pd.DataFrame], strategy_callback: Callable[[str, Dict[str, Any]], Awaitable[None]]):
        """
        historical_data: dict mapping symbol string to a DataFrame of 1-minute candles.
        strategy_callback: stratergy.on_candle method pointer.
        """
        self.historical_data = historical_data
        self.strategy_callback = strategy_callback
        
    async def run_replay(self, start_date=None, end_date=None):
        """Simulates live market conditions by stepping through time chronologically."""
        log.info("Starting historical replay... Packing event stream.")
        
        # Combine all data into a single event stream to ensure strict chronological ordering across all symbols
        events = []
        for symbol, df in self.historical_data.items():
            if start_date: 
                df = df[df.index >= start_date]
            if end_date: 
                df = df[df.index <= end_date]
                
            for ts, row in df.iterrows():
                # Reconstruct dict format expected by the live execution engine
                candle_dict = row.to_dict()
                candle_dict["timestamp"] = ts
                
                events.append({
                    "symbol": symbol,
                    "timestamp": ts,
                    "candle": candle_dict
                })
                
        if not events:
            log.warning("No historical events found for the requested window.")
            return

        # Sort strictly by timestamp to prevent any lookahead cross-asset bias
        log.info("Sorting chronologically...")
        events.sort(key=lambda x: x["timestamp"])
        
        log.info(f"Replay initialized. Feeding {len(events)} events to the Strategy Engine.")
        
        for i, event in enumerate(events):
            await self.strategy_callback(event["symbol"], event["candle"])
            
            if i % 10000 == 0 and i > 0:
                log.info(f"Replay progress: {i}/{len(events)} candles processed.")
                
        log.info(f"Replay complete. Processed {len(events)} historical candles.")
