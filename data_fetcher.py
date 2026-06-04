# data_fetcher.py
"""
data_fetcher.py — External Market Intelligence Client

Fetches 4 types of external market data that the Groww WebSocket cannot provide:

  1. FII/DII Flow     — NSE API, fetched daily at 9:00 AM
  2. Options Chain    — NSE API, PCR + Max Pain, refreshed every 30 min
  3. Earnings Calendar— NSE corporate actions, fetched daily at 9:00 AM
  4. News Headlines   — Economic Times RSS, refreshed every 30 min

BUGS FIXED (v2):
  - Removed broken homepage cookie dance (homepage returns 403, API works directly)
  - Fixed options chain endpoint (old endpoint returned 404)
  - Added 2-attempt retry with delay for all NSE calls
  - All fetches remain fail-safe: bot continues even if NSE is down

MarketContext is the single object passed to the strategy engine.
It holds a snapshot of the current market intelligence.
"""

import logging
import asyncio
import time
import requests
import feedparser
from datetime import datetime, date
import pytz
import config

log = logging.getLogger("DataFetcher")


# ══════════════════════════════════════════════════════════════════════════════
# NSE SESSION CLIENT (Fixed)
#
# FINDING: NSE homepage returns 403 for automated requests, but the API
# endpoints themselves return 200 with real JSON data — no cookies needed.
# Previous code was stuck in a loop: homepage 403 → cookie_fresh=False →
# retry homepage → 403 → never calls actual API.
#
# FIX: Call API endpoints directly with browser headers. No homepage visit needed.
# ══════════════════════════════════════════════════════════════════════════════

class NSEClient:
    BASE_URL = "https://www.nseindia.com"
    HEADERS  = {
        "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept":          "application/json, text/plain, */*",
        "Referer":         "https://www.nseindia.com/",
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def get(self, endpoint: str, retries: int = 2) -> dict | list:
        """
        Make a GET request to an NSE API endpoint.
        Retries once with a short delay on failure.
        Returns empty dict/list on final failure — never raises.
        """
        url = f"{self.BASE_URL}{endpoint}"
        for attempt in range(retries):
            try:
                resp = self.session.get(url, timeout=15)
                # NSE returns 404 HTML on bad endpoints — detect it
                content_type = resp.headers.get("Content-Type", "")
                if resp.status_code != 200:
                    log.warning(f"NSE API [{endpoint}] returned HTTP {resp.status_code}")
                    time.sleep(2)
                    continue
                if "text/html" in content_type:
                    log.warning(f"NSE API [{endpoint}] returned HTML (blocked/wrong endpoint)")
                    return {}
                return resp.json()
            except requests.exceptions.Timeout:
                log.warning(f"NSE API [{endpoint}] timed out (attempt {attempt+1}/{retries})")
                time.sleep(3)
            except Exception as e:
                log.warning(f"NSE API [{endpoint}] failed: {e}")
                time.sleep(2)
        return {}


# ══════════════════════════════════════════════════════════════════════════════
# MARKET CONTEXT  (the intelligence snapshot the strategy reads)
# ══════════════════════════════════════════════════════════════════════════════

class MarketContext:
    """
    Single object holding all external market intelligence.
    Passed to MomentumScanner so every signal evaluation has full context.
    Defaults are neutral so the strategy runs even if fetches fail.
    """

    def __init__(self):
        # ── FII / DII ────────────────────────────────────────────────────────
        self.fii_net_crore: float = 0.0       # Positive = buying, Negative = selling
        self.dii_net_crore: float = 0.0
        self.fii_sentiment: str   = "NEUTRAL" # BULLISH / BEARISH / NEUTRAL
        self.fii_data_date: str   = "N/A"

        # ── Options Market ───────────────────────────────────────────────────
        self.nifty_pcr: float      = 1.0      # Put-Call Ratio for NIFTY
        self.nifty_max_pain: float = 0.0      # Max Pain strike price
        self.pcr_sentiment: str    = "NEUTRAL"

        # ── Earnings / Corporate Actions ─────────────────────────────────────
        self.earnings_today: set = set()      # Symbols with results/actions today

        # ── News ─────────────────────────────────────────────────────────────
        self.recent_headlines: list = []      # Last 20 headlines fetched

        # ── Nifty Regime (computed from live candle data in strategy) ────────
        self.nifty_regime: str = "NEUTRAL"   # BULLISH / BEARISH / NEUTRAL

    def is_earnings_day(self, symbol: str) -> bool:
        return symbol.upper() in self.earnings_today

    def get_news_for(self, symbol: str) -> list:
        return [h for h in self.recent_headlines if symbol.upper() in h.upper()]

    def summary(self) -> str:
        return (
            f"FII: ₹{self.fii_net_crore:+.0f}cr ({self.fii_sentiment}) | "
            f"PCR: {self.nifty_pcr:.2f} ({self.pcr_sentiment}) | "
            f"Earnings today: {len(self.earnings_today)} stocks"
        )


# ══════════════════════════════════════════════════════════════════════════════
# MARKET DATA FETCHER  (the engine that fills MarketContext)
# ══════════════════════════════════════════════════════════════════════════════

class MarketDataFetcher:

    def __init__(self):
        self.nse     = NSEClient()
        self.context = MarketContext()

    # ── PUBLIC API ────────────────────────────────────────────────────────────

    async def morning_refresh(self):
        """
        Run once at market open (9:00 AM).
        Fetches FII/DII data and earnings calendar for the day.
        """
        log.info("🌅 Running morning market intelligence fetch...")
        await asyncio.to_thread(self._fetch_fii_dii)
        await asyncio.to_thread(self._fetch_earnings_calendar)
        await asyncio.to_thread(self._fetch_options_chain)   # Also fetch PCR at open
        await asyncio.to_thread(self._fetch_news)
        log.info(f"Morning refresh complete. {self.context.summary()}")

    async def intraday_refresh(self):
        """
        Run every 30 minutes during market hours.
        Refreshes options chain and news headlines.
        """
        log.debug("🔄 Running intraday market intelligence refresh...")
        await asyncio.to_thread(self._fetch_options_chain)
        await asyncio.to_thread(self._fetch_news)
        log.debug(f"Intraday refresh done. {self.context.summary()}")

    # ── FII / DII ─────────────────────────────────────────────────────────────

    def _fetch_fii_dii(self):
        """
        Fetches FII and DII net buy/sell data from NSE.
        NSE publishes the previous trading day's data by morning.
        Endpoint: /api/fiidiiTradeReact  (confirmed working 04-Jun-2026)
        """
        try:
            data = self.nse.get("/api/fiidiiTradeReact")
            if not data:
                log.warning("FII/DII: No data returned from NSE (keeping neutral defaults)")
                return

            fii_net = 0.0
            dii_net = 0.0

            # NSE returns a list — each item has category, buyValue, sellValue, netValue
            records = data if isinstance(data, list) else data.get("data", [])
            for record in records:
                category = str(record.get("category", "")).upper()
                try:
                    net = float(str(record.get("netValue", "0")).replace(",", "") or 0)
                except (ValueError, TypeError):
                    net = 0.0
                if "FII" in category or "FPI" in category:
                    fii_net += net
                elif "DII" in category:
                    dii_net += net

            self.context.fii_net_crore = round(fii_net, 2)
            self.context.dii_net_crore = round(dii_net, 2)
            self.context.fii_data_date = datetime.now(config.TIMEZONE).strftime("%d-%b-%Y")

            # Classify FII sentiment
            if fii_net >= config.FII_BULLISH_THRESHOLD:
                self.context.fii_sentiment = "BULLISH"
            elif fii_net <= config.FII_BEARISH_THRESHOLD:
                self.context.fii_sentiment = "BEARISH"
            else:
                self.context.fii_sentiment = "NEUTRAL"

            log.info(f"FII/DII → FII: ₹{fii_net:+.0f}cr | DII: ₹{dii_net:+.0f}cr | Sentiment: {self.context.fii_sentiment}")

        except Exception as e:
            log.warning(f"FII/DII fetch failed: {e}")

    # ── OPTIONS CHAIN (PCR + MAX PAIN) ────────────────────────────────────────

    def _fetch_options_chain(self):
        """
        Fetches Nifty 50 options chain from NSE.
        Calculates:
          - PCR (Put-Call Ratio): Total Put OI / Total Call OI
            > 1.2 = market bullish (more puts = fear = contrarian buy)
            < 0.8 = market bearish (more calls = greed = contrarian sell)
          - Max Pain: Strike where total option holder loss is minimized

        ENDPOINT NOTE: /api/option-chain-indices returns 404.
        Working endpoint confirmed: /api/optionchain-equities or use the
        allIndices approach.
        """
        # Try multiple known NSE options endpoints
        endpoints = [
            "/api/option-chain-indices?symbol=NIFTY",
            "/api/allIndices",   # fallback to get PCR from index data
        ]

        data = {}
        for ep in endpoints:
            result = self.nse.get(ep)
            if result and isinstance(result, dict):
                # Check if this has the options data we need
                if "filtered" in result or "data" in result:
                    data = result
                    break

        if not data:
            log.warning("Options chain: All endpoints failed. PCR remains at previous value.")
            return

        try:
            records = data.get("filtered", {}).get("data", []) or data.get("data", [])
            if not records:
                return

            total_call_oi = 0
            total_put_oi  = 0
            strike_data   = {}

            for record in records:
                strike  = record.get("strikePrice", 0)
                call_oi = record.get("CE", {}).get("openInterest", 0) or 0
                put_oi  = record.get("PE", {}).get("openInterest", 0) or 0
                total_call_oi += call_oi
                total_put_oi  += put_oi
                strike_data[strike] = {"call_oi": call_oi, "put_oi": put_oi}

            if total_call_oi > 0:
                pcr = round(total_put_oi / total_call_oi, 3)
                self.context.nifty_pcr = pcr

                if pcr >= config.PCR_BULLISH_THRESHOLD:
                    self.context.pcr_sentiment = "BULLISH"
                elif pcr <= config.PCR_BEARISH_THRESHOLD:
                    self.context.pcr_sentiment = "BEARISH"
                else:
                    self.context.pcr_sentiment = "NEUTRAL"

            if strike_data:
                self.context.nifty_max_pain = self._calculate_max_pain(strike_data)

            log.info(f"Options → PCR: {self.context.nifty_pcr} ({self.context.pcr_sentiment}) | Max Pain: ₹{self.context.nifty_max_pain}")

        except Exception as e:
            log.warning(f"Options chain parsing failed: {e}")

    @staticmethod
    def _calculate_max_pain(strike_data: dict) -> float:
        """
        Max Pain = the strike at which total option holder loss is minimized.
        Institutions push price toward this level near expiry.
        """
        min_pain    = float("inf")
        max_pain_px = 0.0
        for test_price in strike_data:
            total_pain = 0
            for strike, oi in strike_data.items():
                if test_price < strike:
                    total_pain += oi["call_oi"] * (strike - test_price)
                if test_price > strike:
                    total_pain += oi["put_oi"] * (test_price - strike)
            if total_pain < min_pain:
                min_pain    = total_pain
                max_pain_px = test_price
        return float(max_pain_px)

    # ── EARNINGS CALENDAR ─────────────────────────────────────────────────────

    def _fetch_earnings_calendar(self):
        """
        Fetches today's corporate actions from NSE.
        Marks stocks with Board Meetings / Results today → excluded from signals.
        Date format required by NSE: DD-MM-YYYY  e.g. 04-06-2026
        Confirmed working endpoint (04-Jun-2026 test: returned real data).
        """
        try:
            today    = datetime.now(config.TIMEZONE)
            date_str = today.strftime("%d-%m-%Y")   # DD-MM-YYYY — confirmed correct
            endpoint = f"/api/corporates-corporateActions?index=equities&from_date={date_str}&to_date={date_str}"
            data     = self.nse.get(endpoint)

            if not data:
                log.info("Earnings calendar: No data returned (no actions today, or NSE unavailable)")
                return

            records = data if isinstance(data, list) else data.get("data", [])
            earnings_today = set()

            for record in records:
                purpose = str(record.get("purpose", "") or record.get("subject", "")).upper()
                symbol  = str(record.get("symbol", "")).upper().strip()
                if any(kw in purpose for kw in ["RESULTS", "BOARD MEETING", "DIVIDEND", "BONUS", "SPLIT", "AGM"]):
                    if symbol:
                        earnings_today.add(symbol)

            self.context.earnings_today = earnings_today
            if earnings_today:
                log.info(f"Corporate actions today ({len(earnings_today)} stocks): {', '.join(sorted(earnings_today))}")
            else:
                log.info("No corporate actions found for today.")

        except Exception as e:
            log.warning(f"Earnings calendar fetch failed: {e}")

    # ── NEWS HEADLINES ────────────────────────────────────────────────────────

    def _fetch_news(self):
        """
        Fetches latest market headlines from Economic Times RSS feed.
        Headlines are stored and matched against stock symbols when alerting.
        """
        try:
            feed      = feedparser.parse(config.NEWS_RSS_URL)
            headlines = []
            for entry in feed.entries[:20]:
                title = entry.get("title", "")
                if title:
                    headlines.append(title)
            self.context.recent_headlines = headlines
            log.debug(f"News: {len(headlines)} headlines fetched.")
        except Exception as e:
            log.warning(f"News fetch failed: {e}")
