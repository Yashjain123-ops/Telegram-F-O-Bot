# Project Alpha Phase 1 Engineering Audit and Refactoring Blueprint

Date: 2026-06-07

## Mission Alignment

Project Alpha is an Indian F&O Telegram scanner whose core advantage is early detection of abnormal institutional activity before the majority of the price move becomes obvious. Phase 1 must protect the existing working behavior while restructuring the codebase so future engines can be added cleanly.

This document is a blueprint only. It does not implement new signals, OI analysis, futures basis analysis, ranking, AI, or backtesting.

## Current Repository Map

### `bot.py`

Current role: top-level orchestration.

Responsibilities:

- Loads process-wide services at import time: `TelegramNotifier`, `MarketDataFetcher`, `MomentumScanner`.
- Builds `FLAT_SECTOR_MAP` from `config.SECTOR_GROUPS`.
- Defines market schedule helpers: `is_market_open`, `is_orb_period`, `is_pre_market`.
- Runs morning market intelligence fetch.
- Runs intraday options/news refresh.
- Runs health monitor.
- Starts and stops `BrokerStream`.
- Sends market open/offline Telegram messages.
- Clears scanner state after market close.

Issues:

- Mixes application lifecycle, schedule policy, dependency wiring, session reset, Telegram text, and market state.
- Creates global runtime objects at import time, making testing and reuse harder.
- `stratergy.py` imports `FLAT_SECTOR_MAP` from `bot.py`, creating a circular dependency risk.
- Current market-open guard is `9:15-15:30`, while project mission says warm-up is `9:15-9:20` and scanner starts at `9:20`.
- `ORB_END` exists, but strategy evaluation is not explicitly blocked by `is_orb_period`.

### `broker.py`

Current role: Groww live feed client plus candle aggregation.

Responsibilities:

- Authenticates with Groww.
- Subscribes to F&O cash symbols from `config.UNIVERSE`.
- Subscribes to NIFTY 50 index.
- Receives tick snapshots from Groww.
- Converts cumulative volume into per-candle volume deltas.
- Aggregates ticks into 1-minute OHLCV candles.
- Emits completed candles to `strategy.on_candle`.

Reusable components:

- `_aggregate_tick` and `_new_candle` are the core candle aggregation logic.
- `prev_cum_vol` delta calculation is useful for live volume anomaly detection.
- Event-driven candle callback model is the right shape for early detection.

Issues:

- Groww connection management and candle aggregation live in the same class.
- Uses `# type: ignore` and disables pylint for the entire file.
- Error handling is broad and often only debug-logged.
- `self.loop = asyncio.get_running_loop()` in `__init__` assumes construction always happens inside a running loop.
- Sector keys are initialized in the scanner, but the broker does not subscribe to or synthesize sector candles. Since the current strategy requires sector momentum, this may suppress all Phase 1 alerts.
- NIFTY volume is hardcoded to `1`, which is acceptable for VWAP direction approximation but not for volume-aware index/sector analysis.

### `stratergy.py`

Current role: scanner state, indicator calculations, setup detection, signal dedupe, alert formatting, and legacy sync API.

Responsibilities:

- Maintains live candle memory per symbol.
- Maintains NIFTY 50 and sector DataFrames.
- Calculates ATR and VWAP.
- Detects fakeout candles.
- Computes NIFTY regime.
- Runs the full evaluation pipeline on every candle close.
- Applies current layers: opening breakout/breakdown, ATR/range, volume spike, sector tailwind, NIFTY regime, FII alignment, PCR confirmation, earnings skip, VWAP pullback, R:R gate.
- Deduplicates signals via cooldown.
- Formats Telegram alert copy.
- Calls chart generation and Telegram photo sending.
- Exposes `evaluate_autonomous_trade` as a legacy sync API.

Reusable components:

- ATR calculation.
- VWAP calculation.
- Candle fakeout check.
- NIFTY regime calculation.
- Current two-stage alert concept: watch first, trigger second.
- Cooldown/dedupe concept.
- R:R calculation.
- Existing alert copy can be preserved as a compatibility formatter.

Issues:

- File is misspelled as `stratergy.py`; imports depend on the typo.
- Too many responsibilities in one class.
- Scanner mutates and reads raw pandas DataFrames directly, making state contracts loose.
- Alert generation is coupled to scanner logic and Telegram delivery.
- Strategy imports `FLAT_SECTOR_MAP` from `bot.py`; scanner should not import the app entrypoint.
- Opening range uses only first 3 candles, while `MIN_CANDLES_REQUIRED` is 15 and `ORB_END` is 9:30. This is inconsistent with both code comments and the mission schedule.
- Sector DataFrames are never populated by current broker flow, but sector tailwind is mandatory for qualification.
- Several broad exception handlers can hide data contract issues.
- No structured signal object; alerts are formatted directly from temporary dictionaries.
- `last_signal` only stores stage and timestamp, not signal identity, reasons, initial price, follow-up state, or outcome.
- The architecture is not ready for OI, basis, scoring, tracking, or backtesting without adding more coupling.

### `data_fetcher.py`

Current role: external market context fetcher.

Responsibilities:

- Defines `NSEClient` with browser-like headers and retry behavior.
- Defines mutable `MarketContext`.
- Fetches FII/DII data.
- Fetches NIFTY options chain data for PCR/max pain.
- Fetches corporate actions/earnings calendar.
- Fetches news headlines from RSS.
- Provides morning and intraday refresh methods.

Reusable components:

- `NSEClient` retrying fail-safe HTTP client.
- `MarketContext` neutral defaults.
- Morning/intraday refresh split.
- Max pain calculation.

Issues:

- Uses synchronous `requests` inside async flows via `asyncio.to_thread`; workable but not cleanly abstracted.
- External data parsing and context mutation are mixed.
- Market context is a mutable shared object rather than an immutable snapshot.
- Options chain fallback to `/api/allIndices` is structurally suspicious because the parser expects option records with strikes and CE/PE fields.
- `date` and `pytz` imports appear unused.
- No source freshness timestamp per context field except FII date.
- No confidence penalty or stale-data flag when external context fails.

### `notifier.py`

Current role: queued Telegram delivery.

Responsibilities:

- Queues text and photo messages.
- Sends Telegram `sendMessage` and `sendPhoto` requests.
- Applies Markdown parse mode.
- Rate-limits by sleeping 0.5 seconds after each send.

Reusable components:

- Async queue worker.
- Separation between enqueue and send.
- Text/photo support.

Issues:

- No response status checking from Telegram.
- No retry/backoff per failed message.
- No alert transport abstraction.
- Worker cancellation after `queue.join()` is okay, but there is no flush timeout.
- Markdown escaping risk exists in alert text.

### `chart_generator.py`

Current role: Telegram chart image generation.

Responsibilities:

- Converts candle DataFrame into mplfinance format.
- Plots 1-minute candlesticks, VWAP, entry, SL, target, and volume.
- Returns PNG bytes.

Reusable components:

- In-memory chart rendering.
- Clear chart contract: symbol, DataFrame, levels, direction.

Issues:

- Generates synthetic timestamps starting at 09:15 instead of using real candle timestamps.
- Imports `numpy` but does not appear to use it.
- Chart rendering is coupled to current alert shape, not a generic artifact service.
- Fails closed with `None`, which is okay, but failure reason is not propagated to alert telemetry.

### `config.py`

Current role: all credentials, universe, schedule, thresholds, scanner parameters, and sector groups.

Responsibilities:

- Loads `.env`.
- Defines Telegram and Groww credentials.
- Defines F&O universe.
- Defines market schedule and refresh intervals.
- Defines signal thresholds.
- Defines sector groups.

Reusable components:

- Existing universe.
- Existing sector grouping.
- Existing threshold values should be preserved during migration.

Issues:

- Credentials, universe, schedule, and strategy thresholds are all in one file.
- No dataclass or validated settings object.
- Project mission says scanner starts at 9:20, current `MARKET_OPEN` is 9:15.
- `MORNING_FETCH_TIME` is a string but current bot hardcodes 9:00 in logic.
- Dependencies are imported at config import time via dotenv loading.

### `requirements.txt` and `Procfile`

Current role: deployment support.

Findings:

- `Procfile` runs `worker: python bot.py`.
- `requirements.txt` does not list several directly imported packages: `growwapi`, `mplfinance`, `feedparser`, and `python-dotenv`. `matplotlib` is also required by chart generation unless installed transitively.
- Requirements include unused or currently unreferenced packages such as Flask, APScheduler, scikit-learn, scipy, yfinance, ta, python-telegram-bot, and others. Some may be intended for future use, but Phase 1 should classify them before pruning.

## Current Runtime Flow

1. `bot.py` imports config and constructs notifier, data fetcher, and scanner.
2. `main_loop` starts Telegram notifier.
3. Before market open, `_morning_fetch_task` fetches FII/DII, earnings, PCR, and news.
4. At market open, `BrokerStream` authenticates with Groww and subscribes to live ticks.
5. Broker receives tick snapshots and aggregates them into 1-minute candles.
6. Completed candles are sent to `MomentumScanner.on_candle`.
7. Scanner appends candle state and evaluates only F&O symbols.
8. Scanner may emit Stage 1 watch or Stage 2 trigger alerts.
9. Stage 2 trigger alerts generate a chart image and send photo plus caption to Telegram.
10. At market close, broker stops and scanner session memory is cleared.

## Reusable Assets to Preserve

- Groww live feed integration.
- Existing Telegram delivery.
- Existing 1-minute candle aggregation.
- Existing universe and sector mapping.
- Existing external context fetches.
- Current ATR/VWAP calculations.
- Current two-stage alert philosophy.
- Current chart generation output.
- Current cooldown behavior.
- Current market-open/offline notifications.
- Current neutral-fallback behavior when external intelligence fails.

## Technical Debt Summary

### Critical

- Sector tailwind is mandatory in scanner qualification, but sector candles are not currently populated.
- Schedule semantics conflict with mission: project says warm-up 9:15-9:20 and scanner start 9:20; code uses market open 9:15, ORB end 9:30, and a 15-candle readiness gate.
- `stratergy.py` imports from `bot.py`, creating an application-layer dependency inside the scanner.
- Missing imported packages in `requirements.txt` can break deployment.

### High

- Scanner class mixes state storage, indicator calculation, signal detection, scoring, alert formatting, chart generation, and notification.
- Broker mixes Groww transport and candle aggregation.
- Shared mutable `MarketContext` has no freshness or source status metadata.
- No structured domain models for tick, candle, signal, alert, or tracked setup.
- Broad exception handling can hide production failures.

### Medium

- Alert Markdown is not safely escaped.
- Chart timestamps are synthetic.
- Config is unvalidated and monolithic.
- No tests for candle aggregation, scanner gates, cooldown, alert formatting, or data parsing.
- File naming typo (`stratergy.py`) reduces maintainability.

### Low

- Unused imports.
- Requirements likely contain unused packages.
- Comments and alert strings should be reviewed for encoding consistency before refactor.

## Proposed Modular Architecture

The future architecture should treat the scanner as an event-driven pipeline:

`Tick -> Candle -> Feature Snapshot -> Signal Candidate -> Scored Signal -> Alert -> Tracked Signal`

This shape supports early institutional detection because it keeps raw events, derived features, scoring, alerting, and tracking separate. Future OI, futures basis, and ranking modules can add evidence to the same candidate without rewriting the transport or alert layer.

## Proposed Folder Structure

```text
project_alpha/
  __init__.py
  app/
    __init__.py
    main.py
    runtime.py
    scheduler.py
    session.py
  config/
    __init__.py
    settings.py
    universe.py
    sectors.py
    thresholds.py
  domain/
    __init__.py
    models.py
    enums.py
    events.py
  ingestion/
    __init__.py
    groww_stream.py
    nse_client.py
    market_context_fetcher.py
    news_fetcher.py
  candles/
    __init__.py
    aggregator.py
    store.py
  indicators/
    __init__.py
    atr.py
    vwap.py
    volume.py
  scanner/
    __init__.py
    engine.py
    context.py
    filters.py
    detectors/
      __init__.py
      opening_range.py
      volume_anomaly.py
      vwap_pullback.py
    scoring.py
  alerting/
    __init__.py
    notifier.py
    telegram.py
    formatter.py
    chart_service.py
  tracking/
    __init__.py
    signal_store.py
    cooldown.py
    lifecycle.py
  backtesting/
    __init__.py
    replay.py
    fixtures.py
  tests/
    unit/
    integration/
```

Compatibility wrappers can remain at the repository root during migration:

- `bot.py` imports and runs `project_alpha.app.main`.
- `broker.py` can temporarily re-export `BrokerStream`.
- `stratergy.py` can temporarily re-export `MomentumScanner`.
- `notifier.py`, `data_fetcher.py`, and `chart_generator.py` can temporarily re-export moved classes/functions.

## Target Responsibility Separation

### Data Ingestion

Package: `project_alpha.ingestion`

Owns:

- Groww authentication and subscription.
- NSE HTTP client.
- External context fetches.
- News fetches.

Does not own:

- Candle aggregation rules.
- Scanner rules.
- Alert formatting.

Target contracts:

- Emits `TickEvent`.
- Emits `MarketContextSnapshot`.
- Reports source status and freshness.

### Candle Aggregation

Package: `project_alpha.candles`

Owns:

- Tick-to-candle aggregation.
- Per-symbol cumulative-volume delta handling.
- Candle memory and retrieval.
- Optional derived sector candle synthesis if no sector index feed exists.

Does not own:

- Groww connection details.
- Signal evaluation.

Target contracts:

- Accepts `TickEvent`.
- Emits `CandleClosedEvent`.
- Stores `Candle` objects with timestamp.

### Scanner Engine

Package: `project_alpha.scanner`

Owns:

- Invoking detectors on candle close.
- Combining live candle state and market context.
- Producing structured signal candidates.
- Calling scoring.

Does not own:

- Telegram.
- Chart rendering.
- Broker transport.

Target contracts:

- Accepts `CandleClosedEvent`.
- Reads `ScannerContext`.
- Emits `SignalCandidate` or `Signal`.

### Alerting

Package: `project_alpha.alerting`

Owns:

- Telegram transport.
- Alert formatting.
- Chart rendering.
- Delivery retry/backoff.

Does not own:

- Signal detection.
- Signal cooldown decisions.

Target contracts:

- Accepts `AlertRequest`.
- Emits delivery result/telemetry.

### Tracking

Package: `project_alpha.tracking`

Owns:

- Cooldowns.
- Signal lifecycle.
- Watch-to-trigger transitions.
- Signal outcome metadata.
- Later backtest/live reconciliation.

Does not own:

- Scoring math.
- Alert transport.

Target contracts:

- Accepts `Signal`.
- Returns whether alert should be emitted.
- Stores signal state.

### Configuration

Package: `project_alpha.config`

Owns:

- Credentials.
- Market schedule.
- Universe.
- Sectors.
- Thresholds.
- Feature flags.

Target contracts:

- Validated settings object.
- No ad hoc global reads inside domain logic.

## Future Expansion Readiness

### Volume Anomaly Detection

Add under `scanner/detectors/volume_anomaly.py` and `indicators/volume.py`.

Needs from Phase 1:

- Reliable per-minute volume delta.
- Historical/intraday baseline abstraction.
- Signal candidate can carry evidence such as volume ratio, percentile, and acceleration.

### OI Build-up Detection

Add under future `derivatives/oi.py` or `scanner/detectors/oi_buildup.py`.

Needs from Phase 1:

- Domain models that can accept derivative snapshots separately from cash candles.
- Candidate evidence bag that supports long buildup, short buildup, short covering, and long unwinding.
- Source freshness metadata.

### Futures Basis Analysis

Add under future `derivatives/basis.py`.

Needs from Phase 1:

- Symbol mapping between cash, futures, and expiry contracts.
- Market context snapshot that can include basis, premium/discount, and change rate.
- Scoring should accept basis evidence without changing alert transport.

### Signal Scoring

Add/expand `scanner/scoring.py`.

Needs from Phase 1:

- Structured `Evidence` objects.
- Score components separated from detector booleans.
- Configurable weights.
- Explanation strings generated from evidence, not hand-built in scanner.

### Signal Tracking

Add/expand `tracking/lifecycle.py`.

Needs from Phase 1:

- Signal IDs.
- Initial alert price, stage, timestamp, direction, target, stop, and reasons.
- State transitions: candidate, watch, trigger, invalidated, target_hit, stopped, expired.

### Backtesting

Add under `backtesting/`.

Needs from Phase 1:

- Scanner engine callable with historical candle events.
- No dependency on Telegram or Groww inside detection logic.
- Deterministic settings and injectable clock.
- Structured outputs instead of direct message sends.

## Refactoring Plan

### Phase 1A: Stabilize Contracts Without Behavior Change

1. Add domain models: `Tick`, `Candle`, `MarketContextSnapshot`, `SignalCandidate`, `Signal`, `AlertRequest`.
2. Create config settings modules while keeping root `config.py` as a compatibility shim.
3. Move sector-map construction out of `bot.py`.
4. Move cooldown state to tracking module.
5. Add minimal unit tests for candle aggregation and ATR/VWAP parity.

Expected behavior change: none.

### Phase 1B: Extract Candle Aggregation

1. Move `_aggregate_tick` and `_new_candle` into `candles/aggregator.py`.
2. Keep `BrokerStream` responsible only for Groww subscription and tick extraction.
3. Preserve `strategy.on_candle` callback initially.
4. Add tests for minute boundary, OHLC updates, cumulative volume deltas, and zero-volume fallback.

Expected behavior change: none.

### Phase 1C: Extract Scanner Internals

1. Move ATR/VWAP into `indicators`.
2. Move opening range, fakeout, trend-day quality, VWAP pullback, and R:R logic into scanner submodules.
3. Keep `MomentumScanner` as a facade for compatibility.
4. Replace temporary dictionaries with structured candidate/signal objects.
5. Remove `from bot import FLAT_SECTOR_MAP`.

Expected behavior change: none, except improved observability.

### Phase 1D: Extract Alerting

1. Move Telegram class to `alerting/telegram.py`.
2. Move formatters to `alerting/formatter.py`.
3. Move chart generator to `alerting/chart_service.py`.
4. Scanner emits `AlertRequest`; alerting handles Telegram delivery.
5. Add Telegram response status logging and retry policy.

Expected behavior change: none for user-facing alerts.

### Phase 1E: Fix Schedule Semantics

1. Represent schedule explicitly:
   - warm-up starts: 9:15
   - scanner evaluation starts: 9:20
   - scanner ends: 15:30
2. Decide whether opening range should be 5 minutes, 15 minutes, or configurable by detector.
3. Gate scanner evaluation using the explicit scanner-start time, not just candle count.
4. Keep market data ingestion active during warm-up.

Expected behavior change: aligns runtime with mission.

### Phase 1F: Resolve Sector Context

Choose one:

- Subscribe to live sector/index instruments and aggregate true sector candles.
- Synthesize sector breadth/momentum from member-stock candles.
- Temporarily make sector tailwind an optional scoring boost instead of a mandatory gate until sector data is reliable.

Recommendation: synthesize member-based sector momentum first because it uses already available stock candles and directly measures F&O participation breadth. Later, add true sector index feeds as a separate context layer.

Expected behavior change: current mandatory sector gate becomes operational instead of silently blocking alerts.

## Migration Plan

### Step 1: Create Package Skeleton

- Add `project_alpha/` package with empty modules.
- Keep root files as operational entrypoints.
- No runtime behavior change.

### Step 2: Add Tests Around Existing Behavior

Minimum tests before moving code:

- Candle starts on first tick.
- Candle updates high/low/close during same minute.
- Candle commits on minute boundary.
- Volume delta calculation handles cumulative volume.
- ATR and VWAP output matches current scanner for sample candles.
- Cooldown suppresses repeated same-stage alerts.
- Missing market context remains neutral.

### Step 3: Move Pure Logic First

- Move config constants into structured modules.
- Move indicator functions.
- Move chart generation.
- Move alert formatting.

Use wrappers to keep existing imports working.

### Step 4: Move Stateful Runtime Pieces

- Move candle aggregator.
- Move broker stream.
- Move market context fetcher.
- Move scanner engine facade.

### Step 5: Replace Root Entrypoint

- Update `bot.py` to call `project_alpha.app.main`.
- Keep `Procfile` unchanged until deployment verification passes.

### Step 6: Verify Live Compatibility

Dry-run checks:

- Import all root modules.
- Start notifier with fake credentials disabled or mocked.
- Run candle aggregation unit tests.
- Run scanner against fixture candles.
- Generate chart from fixture candles.
- Confirm Telegram payload format without sending.

Live-market checks:

- 9:15 warm-up: Groww connected and candles forming.
- 9:20 scanner active.
- 15:30 broker stopped and session state cleared.
- Morning/intraday context refresh logs source status.

## Risk Assessment

### Runtime Risk

Risk: refactor breaks live Groww callback behavior.

Mitigation: keep `BrokerStream` facade and only extract aggregation after tests exist.

### Signal Regression Risk

Risk: detector extraction changes signal firing conditions.

Mitigation: create fixture candles and compare old vs new outputs before changing runtime.

### Alert Regression Risk

Risk: Telegram Markdown/photo delivery changes.

Mitigation: preserve formatter output snapshots and add Telegram transport tests with mocked HTTP.

### Schedule Risk

Risk: aligning scanner start to 9:20 changes alert timing.

Mitigation: separate ingestion start from scanner start; collect 9:15-9:20 warm-up candles, then evaluate from 9:20.

### Sector Risk

Risk: current sector tailwind requirement blocks alerts if sector data remains empty.

Mitigation: make sector context an explicit module with a tested data source. Until it is reliable, treat sector tailwind as a score component rather than a hidden hard dependency.

### Dependency Risk

Risk: deployment fails because imported packages are missing from `requirements.txt`.

Mitigation: reconcile requirements before code migration and classify runtime vs development/future dependencies.

### Data Quality Risk

Risk: NSE/Telegram/Groww APIs fail or return changed shapes.

Mitigation: parse into typed snapshots with source status, freshness timestamps, and neutral fallback.

## Recommended Phase 1 Definition of Done

- Existing `bot.py` still starts the scanner.
- Existing Telegram alerts still work.
- Existing Groww candle ingestion still works.
- Codebase has separated modules for ingestion, candles, scanner, alerting, tracking, and config.
- No new OI, futures basis, ranking, AI, or backtesting logic is implemented.
- Sector context problem is resolved or explicitly disabled as a mandatory gate.
- Schedule matches mission: warm-up 9:15-9:20, scanner active 9:20-15:30.
- Unit tests cover candle aggregation, indicators, cooldown, and scanner facade behavior.
- Requirements are reconciled with actual imports.

## Engineering Lead Recommendation

Do not add any new institutional signals until the sector-context and schedule mismatches are fixed. The current code has strong raw ingredients, especially event-driven candle evaluation, volume-delta aggregation, Telegram delivery, and market context enrichment. The main engineering move is to turn those ingredients into explicit contracts so each future institutional evidence source can plug into the same pipeline without making the scanner class larger or more fragile.
