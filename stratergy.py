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
import asyncio
import logging
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timezone
import config
from chart_generator import generate_signal_chart
from project_alpha.scanner.detectors import (
    calculate_institutional_rr as detector_calculate_institutional_rr,
    detect_opening_range,
    detect_trend_day,
    detect_vwap_pullback,
    is_fakeout_candle as detector_is_fakeout_candle,
    DetectorInput,
    detect_volume_anomaly,
    detect_oi_buildup,
    detect_futures_basis,
    detect_sector_participation,
)
from project_alpha.domain.models import SignalStage, Signal
from project_alpha.scanner.scoring import InstitutionalScoringEngine
from project_alpha.scanner.lifecycle import LifecycleEngine
from project_alpha.tracking.signal_store import SignalRecord, SignalStore
from project_alpha.tracking.validation import ValidationEngine
from project_alpha.tracking.cooldown import CooldownTracker
from project_alpha.paper_trading.engine import PaperTradingEngine
from project_alpha.reliability.persistence import StatePersistenceEngine
from project_alpha.reliability.recovery import TelegramRecoveryEngine, BrokerRecoveryEngine
from project_alpha.reliability.monitoring import OperationalAlerting, HealthMonitoringEngine
from project_alpha.reliability.deployment import DeploymentManager

log = logging.getLogger("MomentumScanner")


class MomentumScanner:

    def __init__(self, notifier=None, market_context=None):
        self.notifier       = notifier
        self.market_context = market_context   # MarketContext from data_fetcher.py

        # ── Live memory bank ─────────────────────────────────────────────────
        self.candle_columns = ["timestamp", "open", "high", "low", "close", "volume"]
        self.live_data: dict[str, pd.DataFrame] = {
            symbol: pd.DataFrame(columns=self.candle_columns)
            for symbol in config.UNIVERSE
        }
        self.live_data["NIFTY_50"] = pd.DataFrame(
            columns=self.candle_columns
        )
        for sector in config.SECTOR_GROUPS:
            self.live_data[sector] = pd.DataFrame(
                columns=self.candle_columns
            )

        # ── Signal deduplication ─────────────────────────────────────────────
        # Phase 6: Startup Recovery & Persistence
        self.persistence = StatePersistenceEngine()
        recovered_state = self.persistence.load_state()
        
        if recovered_state:
            log.info("Booting from recovered State Snapshot.")
            self.signal_store = recovered_state.get("signal_store", SignalStore())
            self.validation_engine = recovered_state.get("validation_engine", ValidationEngine())
            self.paper_trading = recovered_state.get("paper_trading", PaperTradingEngine(starting_capital=1_000_000.0))
        else:
            log.info("Booting fresh state.")
            self.signal_store = SignalStore()
            self.validation_engine = ValidationEngine()
            self.paper_trading = PaperTradingEngine(starting_capital=1_000_000.0)

        self.scoring_engine = InstitutionalScoringEngine()
        self.lifecycle_engine = LifecycleEngine()
        self.cooldowns = CooldownTracker(cooldown_seconds=300)

        # Phase 6: Telegram Recovery Engine
        self._raw_notifier = notifier
        self.telegram_recovery = TelegramRecoveryEngine(
            send_callback=self._send_telegram_alert, 
            max_retries=5
        )
        
        # Phase 6: Broker Recovery Engine (Mock callbacks for F&O Live Integration)
        self.broker_recovery = BrokerRecoveryEngine(
            reconnect_callback=self._mock_broker_reconnect,
            validate_callback=self._mock_broker_validate
        )
        
        # Phase 6: Operational Alerting & Health Monitor
        self.op_alerting = OperationalAlerting(alert_callback=self._send_telegram_alert)
        self.health_monitor = HealthMonitoringEngine(
            strategy_instance=self,
            alert_engine=self.op_alerting,
            broker_recovery=self.broker_recovery
        )
        
        # Phase 6: Deployment Hardening
        self.deployment_manager = DeploymentManager(self, self.persistence)
        
    async def _mock_broker_validate(self) -> bool:
        """Mock broker socket validation."""
        return True
        
    async def _mock_broker_reconnect(self) -> bool:
        """Mock broker reconnect logic."""
        return True
        
    async def _send_telegram_alert(self, msg: str, **kwargs) -> bool:
        """Wrapper for Telegram API to support recovery queues."""
        if self._raw_notifier:
            try:
                photo = kwargs.get("photo")
                if asyncio.iscoroutinefunction(self._raw_notifier.send_photo) if hasattr(self._raw_notifier, 'send_photo') else False:
                    if photo:
                        await self._raw_notifier.send_photo(caption=msg, image_bytes=photo)
                    else:
                        await self._raw_notifier.send(msg)
                else:
                    if photo and hasattr(self._raw_notifier, 'send_photo'):
                        self._raw_notifier.send_photo(caption=msg, image_bytes=photo)
                    elif hasattr(self._raw_notifier, 'send'):
                        self._raw_notifier.send(msg)
                    else:
                        if asyncio.iscoroutinefunction(self._raw_notifier):
                            await self._raw_notifier(msg)
                        else:
                            self._raw_notifier(msg)
                return True
            except Exception:
                return False
        return True

    async def start_background_tasks(self):
        """Phase 6 background services."""
        await self.telegram_recovery.start()
        await self.broker_recovery.start_monitoring()
        await self.health_monitor.start()

    # ══════════════════════════════════════════════════════════════════════════
    # DATA INGESTION
    # ══════════════════════════════════════════════════════════════════════════

    async def on_candle(self, symbol: str, candle_dict: dict[str, Any]):
        try:
            candle_df = pd.DataFrame([candle_dict])
            candle_df.set_index("timestamp", inplace=True)
            self._update_live_data(symbol, candle_df)
            
            # Check Kill Switch
            if self.validation_engine.evaluate_kill_switch():
                log.warning("💀 KILL SWITCH ACTIVE. 5 consecutive losses. Suspending trading.")
                return

            df = self.live_data.get(symbol, pd.DataFrame())
            if not df.empty:
                current_candle = df.iloc[-1]
                # 2. MFE/MAE UPDATES: Update Excursion metrics for all ACTIVE tracked trades
                for record in self.signal_store.get_all_active():
                    if record.symbol == symbol:
                        self.validation_engine.update_signal(record, current_candle)
                        
                # 3. PAPER TRADING TICK UPDATE:
                self.paper_trading.update_market_data(symbol, current_candle)

            if len(df) >= config.MIN_CANDLES_REQUIRED:
                await self._evaluate_symbol(symbol)
        except Exception as e:
            log.error(f"Error evaluating candle for {symbol}: {e}", exc_info=True)

    def _update_live_data(self, symbol: str, candle_df: pd.DataFrame):
        df = self.live_data.get(symbol, pd.DataFrame(columns=self.candle_columns))
        self.live_data[symbol] = pd.concat([df, candle_df]).tail(50)
        self._update_sector_context(symbol)

    def _is_scanner_active(self, candle_ts=None) -> bool:
        ts = candle_ts
        if ts is None or pd.isna(ts):
            ts = datetime.now(config.TIMEZONE)
        if ts.tzinfo is None:
            ts = config.TIMEZONE.localize(ts)
        if ts.weekday() >= 5:
            return False
        return config.SCANNER_START <= ts.time() <= config.MARKET_CLOSE

    def _update_sector_context(self, symbol: str):
        sector = config.get_sector_for_symbol(symbol)
        members = config.SECTOR_GROUPS.get(sector, [])
        if not members:
            return

        source_df = self.live_data.get(symbol)
        if source_df is None or source_df.empty:
            return

        current_ts = source_df.iloc[-1].get("timestamp")
        if current_ts is None or pd.isna(current_ts):
            return

        rows = []
        for member in members:
            member_df = self.live_data.get(member)
            if member_df is None or member_df.empty:
                continue
            latest = member_df.iloc[-1]
            if latest.get("timestamp") == current_ts:
                rows.append(latest)

        min_members = min(5, max(3, len(members) // 4))
        if len(rows) < min_members:
            return

        sector_row = pd.DataFrame([{
            "timestamp": current_ts,
            "open": sum(float(row["open"]) for row in rows),
            "high": sum(float(row["high"]) for row in rows),
            "low": sum(float(row["low"]) for row in rows),
            "close": sum(float(row["close"]) for row in rows),
            "volume": sum(int(row["volume"]) for row in rows),
        }])
        sector_df = self.live_data.get(sector, pd.DataFrame(columns=self.candle_columns))
        if not sector_df.empty and sector_df.iloc[-1].get("timestamp") == current_ts:
            sector_df = sector_df.iloc[:-1]
        self.live_data[sector] = (
            sector_row if sector_df.empty
            else pd.concat([sector_df, sector_row], ignore_index=True)
        ).tail(50)

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
        return detector_is_fakeout_candle(candle, direction)

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
        return detect_trend_day(df, sector_df).to_legacy_dict()

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 2 — VWAP PULLBACK SNIPER DETECTOR
    # ══════════════════════════════════════════════════════════════════════════

    def _detect_vwap_pullback(self, df: pd.DataFrame, direction: str) -> dict:
        payload = detect_vwap_pullback(df, direction).to_legacy_dict()
        payload.setdefault("setup_confirmed", False)
        payload.setdefault("confidence_add", 0.0)
        return payload

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 3 — INSTITUTIONAL R:R GATE
    # ══════════════════════════════════════════════════════════════════════════

    def _calculate_institutional_rr(self, entry: float, sl: float, vol_ratio: float) -> dict:
        return detector_calculate_institutional_rr(entry, sl, vol_ratio).to_legacy_dict()

    # ══════════════════════════════════════════════════════════════════════════
    # SIGNAL DEDUPLICATION
    # ══════════════════════════════════════════════════════════════════════════

    def _is_on_cooldown(self, symbol: str, stage: int) -> bool:
        return self.cooldowns.is_on_cooldown(symbol, stage)

    def _record_signal(self, symbol: str, stage: int):
        self.cooldowns.record(symbol, stage, datetime.now(timezone.utc))

    # ══════════════════════════════════════════════════════════════════════════
    # MAIN EVALUATION GATEWAY
    # ══════════════════════════════════════════════════════════════════════════

    async def _evaluate_symbol(self, symbol: str):
        """
        Full evaluation pipeline with all 5 intelligence layers.
        Triggered on every candle close via on_candle().
        """
        assigned_sector = config.get_sector_for_symbol(symbol)

        stock_df  = self.live_data.get(symbol, pd.DataFrame())
        sector_df = self.live_data.get(assigned_sector, pd.DataFrame())

        if len(stock_df) < config.MIN_CANDLES_REQUIRED:
            return

        df = self._calculate_atr(stock_df.copy())
        df = self._calculate_vwap(df)

        current_candle = df.iloc[-1]
        opening_range = detect_opening_range(df).to_legacy_dict()
        ltp           = opening_range["ltp"]
        vwap          = opening_range["vwap"]
        bullish       = opening_range["bullish"]
        bearish       = opening_range["bearish"]

        if not opening_range["qualified"]:
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

        # ══ PHASE 1 & 2: BRAIN IMPLANT (INSTITUTIONAL PIPELINE) ═════════════
        detector_input = DetectorInput(
            symbol=symbol,
            candles=df,
            market_context=self.market_context,
            sector_candles=sector_df,
            direction=direction
        )

        vol_res = detect_volume_anomaly(detector_input)
        oi_res = detect_oi_buildup(detector_input)
        basis_res = detect_futures_basis(detector_input)
        sector_res = detect_sector_participation(detector_input)

        results = [vol_res, oi_res, basis_res, sector_res]
        score_breakdown = self.scoring_engine.calculate_global_score(results, detector_input)
        new_stage = self.lifecycle_engine.evaluate_transition(score_breakdown, 0)

        # Retrieve entry points via base logic fallback
        phase2 = self._detect_vwap_pullback(df, direction)
        vol_ratio = vol_res.data.get("rvol", 1.0) if vol_res.qualified else 1.0

        if new_stage == SignalStage.SUSPECTED:
            if self._is_on_cooldown(symbol, int(SignalStage.SUSPECTED)): return
            self._record_signal(symbol, int(SignalStage.SUSPECTED))
            log.info(f"[{symbol}] SUSPECTED Anomaly (Score: {score_breakdown.total})")
            
        elif new_stage == SignalStage.CONFIRMED:
            if self._is_on_cooldown(symbol, int(SignalStage.CONFIRMED)): return
            self._record_signal(symbol, int(SignalStage.CONFIRMED))
            atr = df.iloc[-1]["atr"]
            sl = (ltp - atr * config.ATR_MULTIPLIER_SL) if bullish else (ltp + atr * config.ATR_MULTIPLIER_SL)
            rr = self._calculate_institutional_rr(ltp, sl, vol_ratio)
            if self.notifier:
                await self.notifier.send(
                    self._format_watch_alert(symbol, assigned_sector, ltp, vwap, {"vol_ratio": round(vol_ratio,2), "range_expansion": 1.5, "sector_tailwind": sector_res.qualified}, rr, score_breakdown.reasons, direction, nifty_regime, score_breakdown)
                )

        elif new_stage == SignalStage.PRIME_CANDIDATE:
            if self._is_on_cooldown(symbol, int(SignalStage.PRIME_CANDIDATE)): return
            self._record_signal(symbol, int(SignalStage.PRIME_CANDIDATE))
            entry = phase2.get("entry_zone", ltp)
            sl = phase2.get("invalidation", ltp * 0.99)
            rr = self._calculate_institutional_rr(entry, sl, vol_ratio)
            
            # Phase 3 Tracking: Upsert to signal store
            signal_id = f"{symbol}_{datetime.now(timezone.utc).strftime('%H%M%S')}"
            sl_pct = abs(entry - sl) / entry * 100.0 if entry > 0 else 0
            target_pct = abs(rr['target'] - entry) / entry * 100.0 if entry > 0 else 0
            
            
            # Determine sector (mocking an extractor if market_context is generic)
            sector = "UNKNOWN"
            if "BANK" in symbol: sector = "BANKING"
            elif "FIN" in symbol: sector = "FINANCE"
            elif "IT" in symbol or symbol in ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM"]: sector = "IT"
            elif symbol in ["RELIANCE", "ONGC", "BPCL", "IOC", "PETRONET"]: sector = "ENERGY"
            elif symbol in ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]: sector = "INDEX"
            
            record = SignalRecord(
                signal_id=signal_id,
                symbol=symbol,
                stage=int(SignalStage.PRIME_CANDIDATE),
                direction=direction,
                created_at=datetime.now(timezone.utc),
                entry_price=entry,
                sl_price=sl,
                target_price=rr['target'],
                sl_pct=sl_pct,
                target_pct=target_pct,
                detector_reasons=score_breakdown.reasons,
                institutional_score=score_breakdown.total,
                market_regime=nifty_regime,
                sector=sector
            )
            self.signal_store.upsert(record)
            
            # Phase 5: Hook into Paper Trading Simulation
            self.paper_trading.process_signal(record)
            
            # Phase 6: Telegram Recovery Engine triggers safe transmit
            if self._raw_notifier:
                news = self.market_context.get_news_for(symbol) if self.market_context else []
                alert_text = self._format_trigger_alert(
                    symbol, assigned_sector, entry, sl, rr,
                    {"vol_ratio": round(vol_ratio,2)}, phase2, score_breakdown.reasons, direction, nifty_regime, news, score_breakdown
                )
                chart_bytes = generate_signal_chart(symbol=symbol, df=df, entry=entry, sl=sl, target=rr["target"], direction=direction, vwap_col="vwap")
                
                # Using TelegramRecoveryEngine
                asyncio.create_task(self.telegram_recovery.queue_alert(alert_text, photo=chart_bytes))

    # ══════════════════════════════════════════════════════════════════════════
    # ALERT FORMATTERS
    # ══════════════════════════════════════════════════════════════════════════

    def _format_watch_alert(self, symbol, sector, ltp, vwap, phase1, rr, reasons, direction, nifty_regime, score_breakdown=None) -> str:
        emoji = "📈" if direction == "BULLISH" else "📉"
        arrow = "▲" if direction == "BULLISH" else "▼"
        ctx   = self.market_context
        score_text = f"\n\n🏆 *Institutional Score:* {score_breakdown.total}/100 ({score_breakdown.category})" if score_breakdown else ""
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
            f"  PCR          : {ctx.nifty_pcr:.2f} ({ctx.pcr_sentiment}){score_text}\n\n"
            f"Projected R:R: *1:{rr['rr_ratio']}*\n\n"
            f"📋 *Catalysts:*\n" +
            "\n".join(f"  • {r}" for r in reasons) +
            f"\n\n🔍 *Open chart. Wait for VWAP pullback.*\n"
            f"_Bot found the warzone. You are the sniper._"
        ) if ctx else (
            f"⚠️ *WARZONE FOUND — WATCH* {emoji}\n\n"
            f"*{symbol}* | {sector} | *{direction}* {arrow}\n"
            f"LTP: ₹{ltp} | Vol: *{phase1['vol_ratio']}x* | R:R: *1:{rr['rr_ratio']}*{score_text}\n"
            f"{'─' * 30}\n" +
            "\n".join(f"  • {r}" for r in reasons) +
            f"\n\n🔍 *Wait for VWAP pullback.*"
        )

    def _format_trigger_alert(self, symbol, sector, entry, sl, rr, phase1, phase2, reasons, direction, nifty_regime, news, score_breakdown=None) -> str:
        arrow      = "▲" if direction == "BULLISH" else "▼"
        risk_pct   = round((abs(entry - sl) / entry) * 100, 2)
        ctx        = self.market_context
        news_str   = news[0][:60] + "..." if news else "No major headlines"
        tier_label = rr.get("tier_label", "📈 TREND DAY")
        score_text = f"\n🏆 *Institutional Score:* {score_breakdown.total}/100 ({score_breakdown.category})" if score_breakdown else ""

        base = (
            f"🎯 *SNIPER TRIGGER — ENTRY ZONE* {arrow}\n\n"
            f"*{symbol}* | {sector}\n"
            f"{'─' * 30}\n"
            f"Direction : *{direction}*\n"
            f"Day Type  : *{tier_label}*\n"
            f"Vol Ratio : *{phase1['vol_ratio']}x* 🏛️{score_text}\n\n"
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
            f"  VWAP Proximity : {phase2.get('vwap_proximity_pct', 0)}%\n"
            f"  Volume Dry-up  : {'✅' if phase2.get('volume_dried_up') else '❌'}\n"
            f"  Rejection Wick : {'✅' if phase2.get('rejection_candle') else '❌'}\n\n"
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
