"""Tick-to-candle aggregation."""

from __future__ import annotations

from datetime import datetime

from project_alpha.domain import Candle


class CandleAggregator:
    """Builds 1-minute OHLCV candles from live ticks."""

    def __init__(self):
        self.forming_candles: dict[str, dict] = {}

    def aggregate_tick(
        self,
        symbol: str,
        ltp: float,
        volume_delta: int,
        now: datetime,
    ) -> Candle | None:
        current_minute = now.replace(second=0, microsecond=0)
        completed = None

        if symbol not in self.forming_candles:
            self.forming_candles[symbol] = self.new_candle(ltp, volume_delta, current_minute)
            return None

        candle = self.forming_candles[symbol]
        if current_minute > candle["timestamp"]:
            completed = Candle(symbol=symbol, **candle)
            self.forming_candles[symbol] = self.new_candle(ltp, volume_delta, current_minute)
            return completed

        candle["high"] = max(candle["high"], ltp)
        candle["low"] = min(candle["low"], ltp)
        candle["close"] = ltp
        candle["volume"] += max(0, int(volume_delta))
        return completed

    @staticmethod
    def new_candle(ltp: float, volume: int, minute_ts: datetime) -> dict:
        return {
            "timestamp": minute_ts,
            "open": ltp,
            "high": ltp,
            "low": ltp,
            "close": ltp,
            "volume": max(0, int(volume)),
        }

