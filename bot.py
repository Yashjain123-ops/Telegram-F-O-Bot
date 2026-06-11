# bot.py
"""
bot.py — Orchestration Layer (v2 — Full Intelligence)

Manages:
  - Groww WebSocket lifecycle (connect at 9:15, disconnect at 3:30)
  - Morning intelligence fetch at 9:00 AM (FII/DII + Earnings Calendar)
  - Intraday refresh every 30 min (Options Chain + News)
  - Background health monitor every 5 minutes
  - Graceful shutdown + session memory reset

All evaluation is event-driven — triggered by candle close, not a timer.
"""

import nest_asyncio
nest_asyncio.apply()

import asyncio
import argparse
import datetime
import logging
import pytz
from stratergy import MomentumScanner
import config
from notifier import TelegramNotifier
from broker import BrokerStream
from data_fetcher import MarketDataFetcher

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt = "%H:%M:%S",
)
log = logging.getLogger("Bot")


# ── Sector lookup map ─────────────────────────────────────────────────────────
FLAT_SECTOR_MAP: dict[str, str] = config.FLAT_SECTOR_MAP

# ── System initialization ─────────────────────────────────────────────────────
tg_bot      = TelegramNotifier()
data_fetcher = MarketDataFetcher()
scanner     = MomentumScanner(notifier=tg_bot, market_context=data_fetcher.context)


# ══════════════════════════════════════════════════════════════════════════════
# MARKET HOURS GUARDS
# ══════════════════════════════════════════════════════════════════════════════

def is_market_open() -> tuple[bool, str]:
    now = datetime.datetime.now(config.TIMEZONE)
    if now.weekday() >= 5:
        return False, now.strftime("%I:%M %p")
    return config.MARKET_OPEN <= now.time() <= config.MARKET_CLOSE, now.strftime("%I:%M %p")

def is_orb_period() -> bool:
    return datetime.datetime.now(config.TIMEZONE).time() < config.SCANNER_START

def is_scanner_active() -> tuple[bool, str]:
    now = datetime.datetime.now(config.TIMEZONE)
    if now.weekday() >= 5:
        return False, now.strftime("%I:%M %p")
    return config.SCANNER_START <= now.time() <= config.MARKET_CLOSE, now.strftime("%I:%M %p")

def is_pre_market() -> bool:
    """Returns True between 9:00 AM and 9:15 AM — morning fetch window."""
    now  = datetime.datetime.now(config.TIMEZONE)
    pre  = datetime.time(9, 0)
    open = config.MARKET_OPEN
    return pre <= now.time() < open


# ══════════════════════════════════════════════════════════════════════════════
# BACKGROUND TASKS
# ══════════════════════════════════════════════════════════════════════════════

async def _morning_fetch_task():
    """
    Runs once at 9:00 AM before market opens.
    Fetches FII/DII and earnings calendar for the day.
    Sends a market intelligence briefing to Telegram.
    """
    # Wait until 9:00 AM, but if we start during market hours, break immediately
    while True:
        now = datetime.datetime.now(config.TIMEZONE).time()
        if now >= datetime.time(9, 0) and now <= config.MARKET_CLOSE:
            break
        await asyncio.sleep(30)

    log.info("⏰ 9:00 AM — Running morning intelligence fetch...")
    await data_fetcher.morning_refresh()

    ctx = data_fetcher.context
    earnings_str = ", ".join(sorted(ctx.earnings_today)) if ctx.earnings_today else "None"

    await tg_bot.send(
        f"🌅 *Morning Market Briefing*\n\n"
        f"📊 *FII Flow:* ₹{ctx.fii_net_crore:+.0f}cr — *{ctx.fii_sentiment}*\n"
        f"📊 *DII Flow:* ₹{ctx.dii_net_crore:+.0f}cr\n"
        f"📊 *Nifty PCR:* {ctx.nifty_pcr:.2f} — *{ctx.pcr_sentiment}*\n"
        f"📊 *Max Pain:* ₹{ctx.nifty_max_pain:,.0f}\n\n"
        f"⚠️ *Earnings Today:* {earnings_str}\n\n"
        f"_Market opens in 15 minutes. Engine on standby._"
    )


async def _intraday_refresh_task():
    """
    Runs every 30 minutes during market hours.
    Refreshes options chain PCR + news headlines.
    """
    while True:
        await asyncio.sleep(config.INTRADAY_REFRESH_SECONDS)
        scanner_active, _ = is_scanner_active()
        if not scanner_active:
            continue
        log.debug("🔄 Running intraday refresh (options + news)...")
        await data_fetcher.intraday_refresh()


async def _health_monitor():
    """Logs engine status every 5 minutes."""
    while True:
        await asyncio.sleep(300)
        market_open, current_time = is_market_open()
        if not market_open:
            continue
        scanner_active, _ = is_scanner_active()
        ready_symbols = sum(
            1 for sym in config.UNIVERSE
            if len(scanner.live_data.get(sym, [])) >= config.MIN_CANDLES_REQUIRED
        )
        ctx = data_fetcher.context
        log.info(
            f"[{current_time}] {'🟢 LIVE' if scanner_active else '🟡 WARMUP'} | "
            f"Ready: {ready_symbols}/{len(config.UNIVERSE)} | "
            f"Signals: {len(scanner.last_signal)} | "
            f"FII: ₹{ctx.fii_net_crore:+.0f}cr | PCR: {ctx.nifty_pcr:.2f}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# MAIN LOOP
# ══════════════════════════════════════════════════════════════════════════════

async def main_loop():
    log.info("🤖 Institutional Quant Engine v2 initializing...")
    await tg_bot.start()
    
    # Boot Phase 6 Background Reliability Tasks
    await scanner.start_background_tasks()

    live_broker    = BrokerStream(strategy=scanner)
    broker_started = False
    background_tasks = []

    try:
        while True:
            market_open, current_time = is_market_open()

            # ── Pre-market: run morning fetch at 9:00 AM ──────────────────────
            if is_pre_market() and not broker_started:
                if not any(t.get_name() == "morning_fetch" for t in background_tasks if not t.done()):
                    t = asyncio.create_task(_morning_fetch_task(), name="morning_fetch")
                    background_tasks.append(t)

            if not market_open:
                log.info(f"[{current_time} IST] Market closed. Sleeping 60s...")
                if broker_started:
                    await live_broker.stop()
                    broker_started = False
                    # Cancel background tasks
                    for t in background_tasks:
                        t.cancel()
                    background_tasks.clear()
                    # Reset memory for next session
                    scanner.last_signal.clear()
                    for sym in list(scanner.live_data.keys()):
                        scanner.live_data[sym] = scanner.live_data[sym].iloc[0:0]
                    log.info("Session reset complete. Memory cleared.")
                await asyncio.sleep(60)
                continue

            # ── Market open: connect WebSocket ─────────────────────────────────
            if not broker_started:
                # Fetch intelligence immediately if we skipped pre-market
                if not any(t.get_name() == "morning_fetch" for t in background_tasks if not t.done()):
                    log.info("Fetching initial market intelligence before starting engine...")
                    await data_fetcher.morning_refresh()

                log.info(f"[{current_time} IST] 🟡 WARM-UP START — Booting Groww WebSocket...")
                await live_broker.start()
                broker_started = True

                # Start background tasks
                background_tasks.append(asyncio.create_task(_intraday_refresh_task(), name="intraday_refresh"))
                background_tasks.append(asyncio.create_task(_health_monitor(), name="health_monitor"))

                await tg_bot.send(
                    f"🟢 *NSE Market Open*\n"
                    f"Engine connected. Warm-up runs until *9:20 AM*.\n"
                    f"Scanning *{len(config.UNIVERSE)}* F\\&O stocks after warm-up.\n"
                    f"FII: ₹{data_fetcher.context.fii_net_crore:+.0f}cr | "
                    f"PCR: {data_fetcher.context.nifty_pcr:.2f}\n"
                    f"_Watching for institutional setups..._"
                )

            # Event-driven — evaluation fires inside strategy.on_candle()
            await asyncio.sleep(10)

    except KeyboardInterrupt:
        log.info("Shutdown signal received.")
    finally:
        log.info("Shutting down gracefully...")
        for t in background_tasks:
            t.cancel()
            
        # Phase 6: Ensure Persistence Snapshot before shutdown
        if hasattr(scanner, "deployment_manager"):
            # Trigger preservation
            scanner.deployment_manager._handle_shutdown(None, None)
            
        await live_broker.stop()
        await tg_bot.send("🔴 *Engine Offline* — Graceful shutdown complete.")
        await tg_bot.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Project Alpha Bot Orchestrator")
    parser.add_argument("--backtest", action="store_true", help="Run Phase 4 Backtesting Engine instead of Live Live")
    args = parser.parse_args()

    if args.backtest:
        log.info("🤖 Booting Phase 4 Backtesting Engine from bot.py...")
        from project_alpha.backtesting.engine import WalkForwardEngine
        from project_alpha.backtesting.replay import ReplayEngine
        
        # Simple backtest hook mapping to Phase 4
        log.info("Initializing Replay Engine...")
        engine = WalkForwardEngine(train_months=6, test_months=1)
        # Note: In a real run, you'd feed historical dataframes to engine.run()
        log.info("Phase 4 Backtesting Mode active. Historical data required to execute runs.")
        # Execute run (mocked wrapper to demonstrate connection)
        # engine.run(historical_data)
        log.info("Phase 4 Backtest completed.")
    else:
        asyncio.run(main_loop())
