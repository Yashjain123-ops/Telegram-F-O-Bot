# strategy.py
"""
strategy.py — Institutional VWAP Sniper Engine (v2 — Full Intelligence)

ARCHITECTURE: Three-phase evaluation + 5 intelligence layers

  PHASE 1 — Trend Day Quality Scanner
    Gate: 3x+ institutional volume + range expansion > 1.2x ATR + sector tailwind

  PHASE 2 — VWAP Pullback Sniper Detector
    Gate: Price within 0.2% of VWAP + volume dried up + bullish rejection candle

  PHASE 3 — Institutional Risk-to-Reward Gate
    Gate: R:R ≥ 1:3 minimum (1:4 on 5x volume days)

INTELLIGENCE LAYERS (new in v2):
  ① Nifty 50 Regime    — Block long trades if Nifty is below VWAP
  ② FII Flow           — Confidence boost when FII aligns with trade direction
  ③ Earnings Skip      — Skip any stock with corporate action today
  ④ PCR Filter         — Options market sentiment confirms direction
  ⑤ Chart on Telegram  — Stage 2 alert sends a live candlestick chart image

HUMAN-AI SYMBIOSIS:
  Stage 1 ⚠️ WARZONE  — Bot tells you WHERE to look
  Stage 2 🎯 TRIGGER  — Bot confirms the setup + sends chart image
  You open the real chart, read the tape, pull the trigger
"""

import pandas as pd
import numpy as np
import logging
from datetime import datetime, timezone
import config
from chart_generator import generate_signal_chart

log = logging.getLogger("Strategy")


class MomentumScanner:

    def __init__(self, notifier=None, market_context=None):
        self.notifier       = notifier
        self.market_context = market_context   # MarketContext from data_fetcher.py

        # ── Live memory bank ─────────────────────────────────────────────────
        self.live_data: dict[str, pd.DataFrame] = {
            symbol: pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
            for symbol in config.UNIVERSE
        }
        self.live_data["NIFTY_50"] = pd.DataFrame(
            columns=["open", "high", "low", "close", "volume"]
        )
        for sector in config.SECTOR_GROUPS:
            self.live_data[sector] = pd.DataFrame(
                columns=["open", "high", "low", "close", "volume"]
            )

        # ── Signal deduplication ─────────────────────────────────────────────
        self.last_signal: dict[str, dict] = {}

    # ══════════════════════════════════════════════════════════════════════════
    # DATA INGESTION
    # ══════════════════════════════════════════════════════════════════════════

    async def on_candle(self, symbol: str, candle_data: dict):
        """
        Called by broker.py on every committed 1-minute candle.
        Appends to memory and triggers immediate evaluation.
        """
        try:
            new_row = pd.DataFrame([{
                "open":   candle_data["open"],
                "high":   candle_data["high"],
                "low":    candle_data["low"],
                "close":  candle_data["close"],
                "volume": candle_data.get("volume", 1),
            }])
            self.live_data[symbol] = pd.concat(
                [self.live_data[symbol], new_row], ignore_index=True
            ).tail(50)

            # Only evaluate F&O stocks, not sector indices or NIFTY_50
            if symbol in config.UNIVERSE:
                await self._evaluate_symbol(symbol)

        except KeyError:
            pass
        except Exception as e:
            log.debug(f"on_candle error [{symbol}]: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # INDICATOR CALCULATIONS
    # ══════════════════════════════════════════════════════════════════════════

    def _calculate_atr(self, df: pd.DataFrame) -> pd.DataFrame:
        high_low   = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift(1))
        low_close  = np.abs(df["low"]  - df["close"].shift(1))
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df = df.copy()
        df["atr"]  = true_range.ewm(span=config.ATR_PERIOD, adjust=False).mean()
        return df

    def _calculate_vwap(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        typical_price     = (df["high"] + df["low"] + df["close"]) / 3
        cumulative_tp_vol = (typical_price * df["volume"]).cumsum()
        cumulative_vol    = df["volume"].cumsum().replace(0, np.nan)
        df["vwap"]        = cumulative_tp_vol / cumulative_vol
        return df

    def _is_fakeout_candle(self, candle: pd.Series, direction: str) -> bool:
        total_range = candle["high"] - candle["low"]
        if total_range <= 0:
            return True
        if direction == "BULLISH":
            upper_wick = candle["high"] - max(candle["open"], candle["close"])
            return (upper_wick / total_range) > config.MAX_WICK_PERCENT
        elif direction == "BEARISH":
            lower_wick = min(candle["open"], candle["close"]) - candle["low"]
            return (lower_wick / total_range) > config.MAX_WICK_PERCENT
        return False

    # ══════════════════════════════════════════════════════════════════════════
    # ① NIFTY 50 REGIME FILTER  (new)
    # ══════════════════════════════════════════════════════════════════════════

    def _get_nifty_regime(self) -> str:
        """
        Determines the current market regime based on Nifty 50 vs its VWAP.
        BULLISH = Nifty above VWAP → only allow long setups
        BEARISH = Nifty below VWAP → only allow short setups
        NEUTRAL = insufficient data → allow both
        """
        nifty_df = self.live_data.get("NIFTY_50", pd.DataFrame())
        if len(nifty_df) < 5:
            return "NEUTRAL"
        try:
            nifty_df = self._calculate_vwap(nifty_df)
            ltp  = nifty_df["close"].iloc[-1]
            vwap = nifty_df["vwap"].iloc[-1]
            if ltp > vwap * 1.001:
                return "BULLISH"
            elif ltp < vwap * 0.999:
                return "BEARISH"
            return "NEUTRAL"
        except Exception:
            return "NEUTRAL"

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 1 — TREND DAY QUALITY SCANNER
    # ══════════════════════════════════════════════════════════════════════════

    def _is_trend_day_candidate(self, df: pd.DataFrame, sector_df: pd.DataFrame) -> dict:
        if len(df) < config.MIN_CANDLES_REQUIRED:
            return {"qualified": False, "reason": "Insufficient candles", "vol_ratio": 0.0}

        today_range     = df["high"].max() - df["low"].min()
        atr             = df["atr"].iloc[-1] if "atr" in df.columns else 0
        ltp             = df["close"].iloc[-1]
        atr_price_ratio = (atr / ltp) if ltp > 0 else 0

        if atr_price_ratio < config.MIN_ATR_PRICE_RATIO:
            return {"qualified": False, "reason": "Stock too illiquid/flat", "vol_ratio": 0.0}

        range_expansion = (today_range / atr) if atr > 0 else 0
        lookback        = min(config.AVG_VOLUME_LOOKBACK, len(df) - 1)
        avg_vol         = df["volume"].iloc[-lookback - 1:-1].mean() if lookback > 0 else 1
        cur_vol         = df["volume"].iloc[-1]
        vol_ratio       = (cur_vol / avg_vol) if avg_vol > 0 else 0
        institutional_vol = vol_ratio >= config.INSTITUTIONAL_VOL_SPIKE

        sector_momentum  = False
        sector_vol_ratio = 0.0
        if len(sector_df) >= 5:
            s_lookback       = min(config.AVG_VOLUME_LOOKBACK, len(sector_df) - 1)
            s_avg_vol        = sector_df["volume"].iloc[-s_lookback - 1:-1].mean()
            s_cur_vol        = sector_df["volume"].iloc[-1]
            sector_vol_ratio = (s_cur_vol / s_avg_vol) if s_avg_vol > 0 else 0
            sector_momentum  = sector_vol_ratio >= config.SECTOR_VOL_SPIKE

        qualified = range_expansion >= 1.2 and institutional_vol and sector_momentum

        return {
            "qualified":        qualified,
            "vol_ratio":        round(vol_ratio, 2),
            "range_expansion":  round(range_expansion, 2),
            "sector_tailwind":  sector_momentum,
            "sector_vol_ratio": round(sector_vol_ratio, 2),
            "atr":              round(atr, 4),
            "ltp":              round(ltp, 2),
        }

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 2 — VWAP PULLBACK SNIPER DETECTOR
    # ══════════════════════════════════════════════════════════════════════════

    def _detect_vwap_pullback(self, df: pd.DataFrame, direction: str) -> dict:
        if len(df) < 8:
            return {"setup_confirmed": False, "confidence_add": 0.0}

        ltp  = df["close"].iloc[-1]
        vwap = df["vwap"].iloc[-1]
        atr  = df["atr"].iloc[-1]

        if vwap <= 0 or atr <= 0:
            return {"setup_confirmed": False, "confidence_add": 0.0}

        vwap_proximity_pct = abs(ltp - vwap) / vwap
        near_vwap          = vwap_proximity_pct <= config.VWAP_PROXIMITY_BAND
        breakout_vol       = df["volume"].iloc[-8:-3].mean()
        pullback_vol       = df["volume"].iloc[-3:].mean()
        volume_dried       = (pullback_vol < breakout_vol * config.PULLBACK_VOL_RATIO) if breakout_vol > 0 else False
        last               = df.iloc[-1]
        candle_range       = last["high"] - last["low"]
        close_location     = (last["close"] - last["low"]) / candle_range if candle_range > 0 else 0.5

        if direction == "BULLISH":
            rejection_confirmed = close_location >= config.REJECTION_CLOSE_LOC
            setup_confirmed     = near_vwap and volume_dried and rejection_confirmed and ltp > vwap
            entry_zone          = round(vwap * 1.001, 2)
            invalidation        = round(vwap * 0.997, 2)
        else:
            rejection_confirmed = close_location <= (1 - config.REJECTION_CLOSE_LOC)
            setup_confirmed     = near_vwap and volume_dried and rejection_confirmed and ltp < vwap
            entry_zone          = round(vwap * 0.999, 2)
            invalidation        = round(vwap * 1.003, 2)

        return {
            "setup_confirmed":    setup_confirmed,
            "vwap":               round(vwap, 2),
            "vwap_proximity_pct": round(vwap_proximity_pct * 100, 3),
            "volume_dried_up":    volume_dried,
            "rejection_candle":   rejection_confirmed,
            "entry_zone":         entry_zone,
            "invalidation":       invalidation,
            "confidence_add":     0.20 if setup_confirmed else 0.0,
        }

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 3 — INSTITUTIONAL R:R GATE
    # ══════════════════════════════════════════════════════════════════════════

    def _calculate_institutional_rr(self, entry: float, sl: float, vol_ratio: float) -> dict:
        risk = abs(entry - sl)
        if risk <= 0:
            return {"viable": False, "rr_ratio": 0.0, "target": entry, "risk": 0.0, "tier": 0}

        # THREE-TIER TARGET SYSTEM based on institutional volume strength
        #
        #  TIER 3 — Campaign day (8x+ vol) → 1:8 target
        #           Rare. Budget day, RBI policy, big earnings.
        #           Stock typically moves 6%–10% intraday.
        #
        #  TIER 2 — Strong institutional day (5x–7.9x vol) → 1:6 target
        #           TCS June 2 type day. 4%–6% move.
        #
        #  TIER 1 — Normal institutional day (3x–4.9x vol) → 1:4 target
        #           Solid trend day. 2%–4% move.

        if vol_ratio >= config.CAMPAIGN_VOL_SPIKE:
            rr_mult = config.CAMPAIGN_DAY_RR_MULT    # 1:8
            tier    = 3
            tier_label = "🔥 CAMPAIGN DAY"
        elif vol_ratio >= config.SNIPER_VOL_SPIKE:
            rr_mult = config.TREND_DAY_RR_MULT       # 1:6
            tier    = 2
            tier_label = "⚡ STRONG DAY"
        else:
            rr_mult = config.STANDARD_RR_MULT        # 1:4
            tier    = 1
            tier_label = "📈 TREND DAY"

        target    = entry + (risk * rr_mult) if entry > sl else entry - (risk * rr_mult)
        actual_rr = abs(target - entry) / risk

        return {
            "viable":      actual_rr >= config.MIN_RR_RATIO,
            "rr_ratio":    round(actual_rr, 2),
            "target":      round(target, 2),
            "risk":        round(risk, 2),
            "tier":        tier,
            "tier_label":  tier_label,
        }

    # ══════════════════════════════════════════════════════════════════════════
    # SIGNAL DEDUPLICATION
    # ══════════════════════════════════════════════════════════════════════════

    def _is_on_cooldown(self, symbol: str, stage: int) -> bool:
        last = self.last_signal.get(symbol)
        if not last:
            return False
        elapsed = (datetime.now(timezone.utc) - last["ts"]).total_seconds()
        if last["stage"] < stage:
            return False
        return elapsed < config.SIGNAL_COOLDOWN_SECONDS

    def _record_signal(self, symbol: str, stage: int):
        self.last_signal[symbol] = {"stage": stage, "ts": datetime.now(timezone.utc)}

    # ══════════════════════════════════════════════════════════════════════════
    # MAIN EVALUATION GATEWAY
    # ══════════════════════════════════════════════════════════════════════════

    async def _evaluate_symbol(self, symbol: str):
        """
        Full evaluation pipeline with all 5 intelligence layers.
        Triggered on every candle close via on_candle().
        """
        try:
            from bot import FLAT_SECTOR_MAP
            assigned_sector = FLAT_SECTOR_MAP.get(symbol, "NIFTY_50")
        except ImportError:
            assigned_sector = "NIFTY_50"

        stock_df  = self.live_data.get(symbol, pd.DataFrame())
        sector_df = self.live_data.get(assigned_sector, pd.DataFrame())

        if len(stock_df) < config.MIN_CANDLES_REQUIRED:
            return

        df = self._calculate_atr(stock_df.copy())
        df = self._calculate_vwap(df)

        current_candle = df.iloc[-1]
        ltp            = current_candle["close"]
        vwap           = current_candle["vwap"]
        opening_high   = df["high"].iloc[:3].max()
        opening_low    = df["low"].iloc[:3].min()

        bullish   = ltp > opening_high and ltp > vwap
        bearish   = ltp < opening_low  and ltp < vwap
        if not bullish and not bearish:
            return

        direction = "BULLISH" if bullish else "BEARISH"

        if self._is_fakeout_candle(current_candle, direction):
            return

        # ══ INTELLIGENCE LAYER ①: NIFTY 50 REGIME ════════════════════════════
        nifty_regime = self._get_nifty_regime()
        # Block long trades in bearish regime, short trades in bullish regime
        if nifty_regime == "BEARISH" and direction == "BULLISH":
            return   # Market falling — don't chase longs
        if nifty_regime == "BULLISH" and direction == "BEARISH":
            return   # Market rising — don't chase shorts
        # Update context for alert display
        if self.market_context:
            self.market_context.nifty_regime = nifty_regime

        # ══ INTELLIGENCE LAYER ③: EARNINGS SKIP ══════════════════════════════
        if self.market_context and self.market_context.is_earnings_day(symbol):
            log.debug(f"[{symbol}] Skipping — earnings/corporate action today")
            return   # Too unpredictable — sit out

        # ══ PHASE 1: TREND DAY QUALITY ════════════════════════════════════════
        phase1 = self._is_trend_day_candidate(df, sector_df)
        if not phase1["qualified"]:
            return

        vol_ratio  = phase1["vol_ratio"]
        confidence = 0.0
        reasons    = []

        confidence += 0.30
        reasons.append(f"ORB {'Breakout' if bullish else 'Breakdown'}")

        if vol_ratio >= config.SNIPER_VOL_SPIKE:
            confidence += 0.25
            reasons.append(f"Institutional Campaign ({vol_ratio}x vol 🏛️)")
        elif vol_ratio >= config.INSTITUTIONAL_VOL_SPIKE:
            confidence += 0.20
            reasons.append(f"Institutional Accumulation ({vol_ratio}x vol)")

        if phase1["sector_tailwind"]:
            confidence += 0.25
            reasons.append(f"Sector Tailwind ({phase1['sector_vol_ratio']}x sector vol)")

        # ══ INTELLIGENCE LAYER ②: FII FLOW ═══════════════════════════════════
        if self.market_context:
            fii_sentiment = self.market_context.fii_sentiment
            if (direction == "BULLISH" and fii_sentiment == "BULLISH") or \
               (direction == "BEARISH" and fii_sentiment == "BEARISH"):
                confidence += config.FII_CONFIDENCE_BOOST
                reasons.append(f"FII Aligned ₹{self.market_context.fii_net_crore:+.0f}cr ✅")
            elif (direction == "BULLISH" and fii_sentiment == "BEARISH") or \
                 (direction == "BEARISH" and fii_sentiment == "BULLISH"):
                confidence -= config.FII_CONFIDENCE_BOOST
                reasons.append(f"FII Contra ₹{self.market_context.fii_net_crore:+.0f}cr ⚠️")

        # ══ INTELLIGENCE LAYER ④: PCR FILTER ═════════════════════════════════
        if self.market_context:
            pcr_sentiment = self.market_context.pcr_sentiment
            if (direction == "BULLISH" and pcr_sentiment == "BULLISH") or \
               (direction == "BEARISH" and pcr_sentiment == "BEARISH"):
                confidence += config.PCR_CONFIDENCE_BOOST
                reasons.append(f"PCR Confirms ({self.market_context.nifty_pcr:.2f}) ✅")

        # ── Stage 1 WATCH alert ───────────────────────────────────────────────
        if confidence >= config.CONFIDENCE_WATCH_THRESHOLD and not self._is_on_cooldown(symbol, 1):
            atr = phase1["atr"]
            sl  = (ltp - atr * config.ATR_MULTIPLIER_SL) if bullish else (ltp + atr * config.ATR_MULTIPLIER_SL)
            rr  = self._calculate_institutional_rr(ltp, sl, vol_ratio)
            self._record_signal(symbol, 1)
            if self.notifier:
                await self.notifier.send(
                    self._format_watch_alert(symbol, assigned_sector, ltp, vwap, phase1, rr, reasons, direction, nifty_regime)
                )
            return

        # ══ PHASE 2: VWAP PULLBACK ════════════════════════════════════════════
        phase2 = self._detect_vwap_pullback(df, direction)
        if phase2["setup_confirmed"]:
            confidence += phase2["confidence_add"]
            reasons.append("VWAP Pullback + Rejection ✅")

        # ── Stage 2 TRIGGER alert ─────────────────────────────────────────────
        if confidence >= config.CONFIDENCE_TRIGGER_THRESHOLD and phase2["setup_confirmed"]:
            if self._is_on_cooldown(symbol, 2):
                return

            entry = phase2["entry_zone"]
            sl    = phase2["invalidation"]
            rr    = self._calculate_institutional_rr(entry, sl, vol_ratio)

            if not rr["viable"]:
                return

            self._record_signal(symbol, 2)

            if self.notifier:
                # ══ INTELLIGENCE LAYER ⑤: CHART IMAGE ════════════════════════
                # Get news context for this symbol
                news = []
                if self.market_context:
                    news = self.market_context.get_news_for(symbol)

                # Format text alert
                alert_text = self._format_trigger_alert(
                    symbol, assigned_sector, entry, sl, rr,
                    phase1, phase2, reasons, direction, nifty_regime, news
                )

                # Generate chart image
                chart_bytes = generate_signal_chart(
                    symbol    = symbol,
                    df        = df,
                    entry     = entry,
                    sl        = sl,
                    target    = rr["target"],
                    direction = direction,
                    vwap_col  = "vwap",
                )

                if chart_bytes:
                    # Send chart photo with alert as caption
                    await self.notifier.send_photo(caption=alert_text, image_bytes=chart_bytes)
                else:
                    # Fallback to text-only if chart generation failed
                    await self.notifier.send(alert_text)

    # ══════════════════════════════════════════════════════════════════════════
    # ALERT FORMATTERS
    # ══════════════════════════════════════════════════════════════════════════

    def _format_watch_alert(self, symbol, sector, ltp, vwap, phase1, rr, reasons, direction, nifty_regime) -> str:
        emoji = "📈" if direction == "BULLISH" else "📉"
        arrow = "▲" if direction == "BULLISH" else "▼"
        ctx   = self.market_context
        return (
            f"⚠️ *WARZONE FOUND — WATCH* {emoji}\n\n"
            f"*{symbol}* | {sector}\n"
            f"{'─' * 30}\n"
            f"Direction: *{direction}* {arrow}\n"
            f"LTP: ₹{ltp} | VWAP: ₹{round(vwap, 2)}\n"
            f"Vol Ratio: *{phase1['vol_ratio']}x* 🏛️\n"
            f"Range Expansion: *{phase1['range_expansion']}x ATR*\n"
            f"Sector Tailwind: {'✅' if phase1['sector_tailwind'] else '❌'}\n\n"
            f"📊 *Market Intelligence:*\n"
            f"  Nifty Regime : *{nifty_regime}*\n"
            f"  FII Flow     : ₹{ctx.fii_net_crore:+.0f}cr ({ctx.fii_sentiment})\n"
            f"  PCR          : {ctx.nifty_pcr:.2f} ({ctx.pcr_sentiment})\n\n"
            f"Projected R:R: *1:{rr['rr_ratio']}*\n\n"
            f"📋 *Catalysts:*\n" +
            "\n".join(f"  • {r}" for r in reasons) +
            f"\n\n🔍 *Open chart. Wait for VWAP pullback.*\n"
            f"_Bot found the warzone. You are the sniper._"
        ) if ctx else (
            f"⚠️ *WARZONE FOUND — WATCH* {emoji}\n\n"
            f"*{symbol}* | {sector} | *{direction}* {arrow}\n"
            f"LTP: ₹{ltp} | Vol: *{phase1['vol_ratio']}x* | R:R: *1:{rr['rr_ratio']}*\n"
            f"{'─' * 30}\n" +
            "\n".join(f"  • {r}" for r in reasons) +
            f"\n\n🔍 *Wait for VWAP pullback.*"
        )

    def _format_trigger_alert(self, symbol, sector, entry, sl, rr, phase1, phase2, reasons, direction, nifty_regime, news) -> str:
        arrow      = "▲" if direction == "BULLISH" else "▼"
        risk_pct   = round((abs(entry - sl) / entry) * 100, 2)
        ctx        = self.market_context
        news_str   = news[0][:60] + "..." if news else "No major headlines"
        tier_label = rr.get("tier_label", "📈 TREND DAY")

        base = (
            f"🎯 *SNIPER TRIGGER — ENTRY ZONE* {arrow}\n\n"
            f"*{symbol}* | {sector}\n"
            f"{'─' * 30}\n"
            f"Direction : *{direction}*\n"
            f"Day Type  : *{tier_label}*\n"
            f"Vol Ratio : *{phase1['vol_ratio']}x* 🏛️\n\n"
            f"💰 *TRADE PARAMETERS:*\n"
            f"  Entry Zone : ₹{entry}\n"
            f"  Stop-Loss  : ₹{sl}  ({risk_pct}% risk)\n"
            f"  Target     : ₹{rr['target']}\n"
            f"  R:R Ratio  : *1:{rr['rr_ratio']}* ✅\n\n"
        )
        if ctx:
            base += (
                f"🏛️ *Market Intelligence:*\n"
                f"  Nifty Regime   : *{nifty_regime}* ✅\n"
                f"  FII Flow       : ₹{ctx.fii_net_crore:+.0f}cr ({ctx.fii_sentiment})\n"
                f"  Market PCR     : {ctx.nifty_pcr:.2f} ({ctx.pcr_sentiment})\n"
                f"  Earnings Today : {'⚠️ YES' if ctx.is_earnings_day(symbol) else 'None ✅'}\n"
                f"  News           : {news_str}\n\n"
            )
        base += (
            f"🔬 *Setup Quality:*\n"
            f"  VWAP Proximity : {phase2['vwap_proximity_pct']}%\n"
            f"  Volume Dry-up  : {'✅' if phase2['volume_dried_up'] else '❌'}\n"
            f"  Rejection Wick : {'✅' if phase2['rejection_candle'] else '❌'}\n\n"
            f"📋 *Confirmed Factors:*\n" +
            "\n".join(f"  • {r}" for r in reasons) +
            f"\n\n⚡ *HUMAN CONFIRMATION REQUIRED*\n"
            f"_Open chart. Confirm tape. Pull the trigger._"
        )
        return base

    # ══════════════════════════════════════════════════════════════════════════
    # LEGACY SYNC API
    # ══════════════════════════════════════════════════════════════════════════

    def evaluate_autonomous_trade(self, df, nifty_df, sector_df, opening_high, opening_low, symbol, live_news_headline="Neutral") -> dict:
        if len(df) < config.MIN_CANDLES_REQUIRED:
            return {"action": "HOLD", "reason": "Insufficient data"}
        df     = self._calculate_atr(df)
        df     = self._calculate_vwap(df)
        candle = df.iloc[-1]
        ltp    = candle["close"]
        vwap   = candle["vwap"]
        atr    = candle["atr"]
        bullish   = ltp > opening_high and ltp > vwap
        bearish   = ltp < opening_low  and ltp < vwap
        direction = "BULLISH" if bullish else ("BEARISH" if bearish else None)
        if not direction:
            return {"action": "HOLD", "reason": "No directional bias"}
        if self._is_fakeout_candle(candle, direction):
            return {"action": "HOLD", "reason": "Fakeout candle detected"}
        phase1 = self._is_trend_day_candidate(df, sector_df)
        if not phase1["qualified"]:
            return {"action": "HOLD", "reason": f"No trend day quality"}
        phase2 = self._detect_vwap_pullback(df, direction)
        entry  = phase2["entry_zone"] if phase2["setup_confirmed"] else ltp
        sl     = phase2["invalidation"] if phase2["setup_confirmed"] else (
            ltp - atr * config.ATR_MULTIPLIER_SL if bullish else ltp + atr * config.ATR_MULTIPLIER_SL
        )
        rr = self._calculate_institutional_rr(entry, sl, phase1["vol_ratio"])
        if not rr["viable"]:
            return {"action": "HOLD", "reason": f"R:R below minimum"}
        return {
            "action": "BUY" if bullish else "SHORT",
            "entry": entry, "sl": sl, "tp": rr["target"],
            "rr": rr["rr_ratio"], "vol_ratio": phase1["vol_ratio"],
            "vwap_setup": phase2["setup_confirmed"],
        }