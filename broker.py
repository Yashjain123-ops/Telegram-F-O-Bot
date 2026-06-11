"""Groww live feed transport for Project Alpha.

BrokerStream owns Groww authentication/subscription and delegates tick-to-candle
work to project_alpha.candles.CandleAggregator.
"""

import asyncio
import logging
from datetime import datetime

from growwapi import GrowwAPI, GrowwFeed

import config
from project_alpha.candles import CandleAggregator

log = logging.getLogger("GrowwBroker")


class BrokerStream:
    def __init__(self, strategy):
        self.strategy = strategy
        self.groww_client = None
        self.groww_feed = None
        self.connected = False
        self.aggregator = CandleAggregator()
        self.nifty_token = None
        self.prev_cum_vol = {}
        self.token_to_symbol = {}
        
        # Diagnostics
        self.ticks_processed = 0
        self.nifty_ticks_processed = 0
        self.candles_built = 0

    async def start(self):
        log.info("Authenticating with Groww API...")
        try:
            self.loop = asyncio.get_running_loop()
            self.groww_client = GrowwAPI(config.BROKER_API_KEY)
            self.groww_feed = GrowwFeed(self.groww_client)
            self.connected = True
            log.info("Authentication successful. Connecting to live market feed...")

            self.token_to_symbol.clear()
            instrument_list = []
            for symbol in config.UNIVERSE:
                inst = self.groww_client.get_instrument_by_exchange_and_trading_symbol("NSE", symbol)
                if inst and inst.get("exchange_token"):
                    token = inst["exchange_token"]
                    self.token_to_symbol[token] = symbol
                    instrument_list.append({"exchange": "NSE", "segment": "CASH", "exchange_token": token})
                else:
                    log.warning(f"Failed to map token for {symbol}")

            if instrument_list:
                self.groww_feed.subscribe_ltp(
                    instrument_list,
                    on_data_received=self._on_tick_received,
                )
                log.info(f"Subscribed to live tick data for {len(instrument_list)} F&O stocks.")

            try:
                nifty_inst = self.groww_client.get_instrument_by_exchange_and_trading_symbol("NSE", "NIFTY")
                if nifty_inst and nifty_inst.get("exchange_token"):
                    self.nifty_token = nifty_inst["exchange_token"]
                    nifty_list = [{"exchange": "NSE", "segment": "CASH", "exchange_token": self.nifty_token}]
                    self.groww_feed.subscribe_ltp(
                        nifty_list,
                        on_data_received=self._on_nifty_tick_received,
                    )
                    log.info(f"Subscribed to NIFTY 50 index feed (token: {self.nifty_token}).")
                else:
                    log.warning("Failed to map token for NIFTY")
            except Exception as exc:
                log.warning(f"Nifty 50 subscription failed: {exc}")

        except Exception as exc:
            log.error(f"Failed to connect to Groww: {exc}")
            self.connected = False

    async def stop(self):
        if self.connected and self.groww_feed:
            log.info("Unsubscribing from Groww feed...")
            instrument_list = [
                {"exchange": "NSE", "segment": "CASH", "exchange_token": token}
                for token in self.token_to_symbol.keys()
            ]
            try:
                if instrument_list:
                    self.groww_feed.unsubscribe_ltp(instrument_list)
                if self.nifty_token:
                    self.groww_feed.unsubscribe_ltp([{"exchange": "NSE", "segment": "CASH", "exchange_token": self.nifty_token}])
            except Exception as exc:
                log.debug(f"Disconnect cleanup: {exc}")
            self.connected = False
            self.aggregator.forming_candles.clear()
            self.prev_cum_vol.clear()
            log.info("Disconnected from Groww WebSocket.")

    def _on_tick_received(self, meta):
        try:
            ltp_data = self.groww_feed.get_ltp()
            if not ltp_data or "NSE" not in ltp_data:
                return

            self.ticks_processed += 1
            if self.ticks_processed == 1:
                log.info(f"FIRST TICK DIAGNOSTIC: {list(ltp_data.get('NSE', {}).get('CASH', {}).keys())[:5]}")

            cash_market = ltp_data.get("NSE", {}).get("CASH", {})
            now_ist = datetime.now(config.TIMEZONE)

            for token, data in cash_market.items():
                symbol = self.token_to_symbol.get(token)
                if not symbol:
                    continue

                ltp = data.get("ltp")
                if not ltp or ltp <= 0:
                    continue

                cum_vol = data.get("volume") or data.get("qty") or data.get("tradedQty") or 0
                prev_vol = self.prev_cum_vol.get(symbol, cum_vol)
                candle_vol_delta = max(0, int(cum_vol) - int(prev_vol))
                self.prev_cum_vol[symbol] = cum_vol

                if candle_vol_delta == 0 and cum_vol == 0:
                    candle_vol_delta = 1

                completed = self._aggregate_tick(symbol, ltp, candle_vol_delta, now_ist)
                if completed:
                    self.candles_built += 1
                    if self.candles_built == 1:
                        log.info(f"FIRST CANDLE DIAGNOSTIC: {symbol}")
                    self._submit_completed_candle(symbol, completed)

        except Exception as exc:
            log.debug(f"Tick processing error: {exc}")

    def _on_nifty_tick_received(self, meta):
        try:
            ltp_data = self.groww_feed.get_ltp()
            if not ltp_data or "NSE" not in ltp_data:
                return
            if not self.nifty_token:
                return

            self.nifty_ticks_processed += 1
            if self.nifty_ticks_processed == 1:
                log.info("FIRST NIFTY TICK RECEIVED.")

            cash_market = ltp_data.get("NSE", {}).get("CASH", {})
            nifty_data = cash_market.get(self.nifty_token, {})
            ltp = nifty_data.get("ltp")
            if not ltp or ltp <= 0:
                return

            completed = self._aggregate_tick("NIFTY_50", ltp, 1, datetime.now(config.TIMEZONE))
            if completed:
                self.candles_built += 1
                self._submit_completed_candle("NIFTY_50", completed)

        except Exception as exc:
            log.debug(f"Nifty tick error: {exc}")

    def _aggregate_tick(self, symbol: str, ltp: float, vol_delta: int, now: datetime) -> dict | None:
        completed = self.aggregator.aggregate_tick(symbol, ltp, vol_delta, now)
        if not completed:
            return None

        candle = completed.to_legacy_dict()
        log.debug(
            f"[CANDLE] {symbol} | O:{candle['open']} H:{candle['high']} "
            f"L:{candle['low']} C:{candle['close']} V:{candle['volume']} | "
            f"{candle['timestamp'].strftime('%H:%M')}"
        )
        return candle

    @staticmethod
    def _new_candle(ltp: float, vol: int, minute_ts: datetime) -> dict:
        return CandleAggregator.new_candle(ltp, vol, minute_ts)

    def _submit_completed_candle(self, symbol: str, candle: dict):
        if not self.loop:
            log.warning(f"Dropping candle for {symbol}: event loop is not initialized")
            return
        asyncio.run_coroutine_threadsafe(
            self.strategy.on_candle(symbol, candle),
            self.loop,
        )
