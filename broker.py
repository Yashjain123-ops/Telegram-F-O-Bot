# type: ignore
# pylint: disable=all
"""
broker.py — Institutional Candle Aggregator + WebSocket Manager

ARCHITECTURE CHANGE (retail → institutional):
  OLD: Every tick was submitted as a flat OHLC candle (open=high=low=close=ltp,
       vol=100). This made ATR ≈ 0, VWAP meaningless, and volume checks useless.

  NEW: Ticks are aggregated into real 1-minute OHLC candles. Each tick updates
       the "forming candle" for that symbol. When the clock crosses into the next
       minute, the completed candle is committed to strategy memory. Volume is
       accumulated from the exchange's cumulative volume field across the session
       and converted to per-candle volume via delta computation.
"""

import asyncio
import logging
from datetime import datetime
from growwapi import GrowwAPI, GrowwFeed
import config

log = logging.getLogger("GrowwBroker")


class BrokerStream:
    def __init__(self, strategy):
        self.strategy     = strategy
        self.connected    = False
        self.groww_client = None
        self.groww_feed   = None
        self.loop = asyncio.get_running_loop()

        # forming_candles: per-symbol dict holding the candle currently being
        # built from live ticks. Committed to strategy on minute boundary.
        self.forming_candles: dict = {}

        # prev_cum_vol: tracks the last known cumulative session volume per
        # symbol so we can compute *delta* volume for each candle.
        self.prev_cum_vol: dict = {}

    # ── CONNECTION MANAGEMENT ─────────────────────────────────────────────────

    async def start(self):
        log.info("Authenticating with Groww API...")
        try:
            self.groww_client = GrowwAPI(config.BROKER_API_KEY)
            self.groww_feed   = GrowwFeed(self.groww_client)
            self.connected    = True
            log.info("Authentication successful. Connecting to live market feed...")

            # Subscribe to all F&O stocks
            instrument_list = [
                {"exchange": "NSE", "segment": "CASH", "exchange_token": symbol}
                for symbol in config.UNIVERSE
            ]
            self.groww_feed.subscribe_ltp(
                instrument_list,
                on_data_received=self._on_tick_received
            )
            log.info(f"Subscribed to live tick data for {len(config.UNIVERSE)} F&O stocks.")

            # Subscribe to Nifty 50 index separately
            # This feeds scanner.live_data["NIFTY_50"] for market regime detection
            try:
                nifty_list = [{"exchange": "NSE", "segment": "INDICES", "exchange_token": "NIFTY 50"}]
                self.groww_feed.subscribe_ltp(
                    nifty_list,
                    on_data_received=self._on_nifty_tick_received
                )
                log.info("Subscribed to NIFTY 50 index feed.")
            except Exception as e:
                log.warning(f"Nifty 50 subscription failed (will use yfinance fallback): {e}")

        except Exception as e:
            log.error(f"Failed to connect to Groww: {e}")
            self.connected = False

    async def stop(self):
        if self.connected and self.groww_feed:
            log.info("Unsubscribing from Groww feed...")
            instrument_list = [
                {"exchange": "NSE", "segment": "CASH", "exchange_token": symbol}
                for symbol in config.UNIVERSE
            ]
            try:
                self.groww_feed.unsubscribe_ltp(instrument_list)
            except Exception as e:
                log.debug(f"Disconnect cleanup: {e}")
            self.connected = False
            log.info("Disconnected from Groww WebSocket.")

    # ── CORE TICK HANDLER ─────────────────────────────────────────────────────

    def _on_tick_received(self, meta):
        try:
            ltp_data = self.groww_feed.get_ltp()
            if not ltp_data or "ltp" not in ltp_data:
                return

            cash_market = ltp_data["ltp"].get("NSE", {}).get("CASH", {})
            now_ist     = datetime.now(config.TIMEZONE)

            for symbol, data in cash_market.items():
                if symbol not in config.UNIVERSE:
                    continue

                ltp = data.get("ltp")
                if not ltp or ltp <= 0:
                    continue

                # Real Volume — delta from cumulative session volume
                cum_vol  = data.get("volume") or data.get("qty") or data.get("tradedQty") or 0
                prev_vol = self.prev_cum_vol.get(symbol, cum_vol)

                candle_vol_delta = max(0, int(cum_vol) - int(prev_vol))
                self.prev_cum_vol[symbol] = cum_vol

                if candle_vol_delta == 0 and cum_vol == 0:
                    candle_vol_delta = 1

                # Candle Aggregation
                completed = self._aggregate_tick(symbol, ltp, candle_vol_delta, now_ist)

                if completed:
                    asyncio.run_coroutine_threadsafe(
                        self.strategy.on_candle(symbol, completed),
                        self.loop
                    )

        except Exception as e:
            log.debug(f"Tick processing error: {e}")

    def _on_nifty_tick_received(self, meta):
        """
        Separate callback for Nifty 50 index ticks.
        Aggregates Nifty into 1-minute candles under the "NIFTY_50" key.
        """
        try:
            ltp_data = self.groww_feed.get_ltp()
            if not ltp_data or "ltp" not in ltp_data:
                return

            # Nifty may be under INDICES segment
            indices_market = (
                ltp_data["ltp"].get("NSE", {}).get("INDICES", {}) or
                ltp_data["ltp"].get("NSE", {}).get("CASH", {})
            )
            nifty_data = indices_market.get("NIFTY 50", {}) or indices_market.get("NIFTY50", {})
            ltp = nifty_data.get("ltp")
            if not ltp or ltp <= 0:
                return

            now_ist = datetime.now(config.TIMEZONE)
            completed = self._aggregate_tick("NIFTY_50", ltp, 1, now_ist)
            if completed:
                asyncio.run_coroutine_threadsafe(
                    self.strategy.on_candle("NIFTY_50", completed),
                    self.loop
                )
        except Exception as e:
            log.debug(f"Nifty tick error: {e}")

    # ── CANDLE AGGREGATION ENGINE ─────────────────────────────────────────────

    def _aggregate_tick(self, symbol: str, ltp: float, vol_delta: int,
                        now: datetime) -> dict | None:
        current_minute   = now.replace(second=0, microsecond=0)
        completed_candle = None

        if symbol not in self.forming_candles:
            self.forming_candles[symbol] = self._new_candle(ltp, vol_delta, current_minute)

        else:
            c = self.forming_candles[symbol]

            if current_minute > c["timestamp"]:
                # Minute boundary crossed → commit the old candle
                completed_candle = dict(c)
                log.debug(
                    f"[CANDLE] {symbol} | O:{c['open']} H:{c['high']} "
                    f"L:{c['low']} C:{c['close']} V:{c['volume']} | "
                    f"{c['timestamp'].strftime('%H:%M')}"
                )
                self.forming_candles[symbol] = self._new_candle(ltp, vol_delta, current_minute)

            else:
                # Same minute → update OHLC and accumulate volume
                c["high"]   = max(c["high"],  ltp)
                c["low"]    = min(c["low"],   ltp)
                c["close"]  = ltp
                c["volume"] += vol_delta

        return completed_candle

    @staticmethod
    def _new_candle(ltp: float, vol: int, minute_ts: datetime) -> dict:
        return {
            "open":      ltp,
            "high":      ltp,
            "low":       ltp,
            "close":     ltp,
            "volume":    vol,
            "timestamp": minute_ts,
        }