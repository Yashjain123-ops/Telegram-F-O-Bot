# Project Alpha Phase 1 Audit and Implementation Report

Date: 2026-06-08

## Executive Summary

Project Alpha now has a safer Phase 1 foundation while preserving the existing Groww, Telegram, candle, scanner, market-context, and chart functionality. The implementation did not add OI, futures basis, ranking, AI, or backtesting engines.

The main fixes were:

- Mission schedule is explicit: warm-up starts at 9:15 AM and scanner evaluation starts at 9:20 AM.
- The scanner no longer depends on `bot.py` for sector mapping.
- Sector context is synthesized from same-minute member-stock candles so sector tailwind can actually operate.
- Candle aggregation has been extracted into `project_alpha.candles`.
- Domain models and tracking foundations now exist for the future event pipeline.
- Telegram delivery checks API responses and retries.
- Market context records source status/freshness.
- Deployment requirements now include directly imported runtime packages.

## Audit Findings

### CRITICAL

1. Sector-tailwind pipeline was effectively broken.

Root cause: `MomentumScanner` initialized sector DataFrames and required sector momentum for Phase 1 qualification, but `BrokerStream` only subscribed to F&O stocks and NIFTY 50. No live sector candles were populated.

Fix made: `MomentumScanner._update_sector_context` now synthesizes sector candles from same-minute member-stock candles with a minimum breadth guard.

2. Schedule did not match the mission.

Root cause: `MARKET_OPEN` was 9:15 and `MIN_CANDLES_REQUIRED` was 15, meaning the bot connected at 9:15 but evaluation effectively started around 9:30, not 9:20.

Fix made: Added `WARMUP_START = 9:15`, `SCANNER_START = 9:20`, kept `MARKET_OPEN` as a compatibility alias, changed `MIN_CANDLES_REQUIRED` to 5, and gated scanner evaluation with `_is_scanner_active`.

3. Scanner depended on the app entrypoint.

Root cause: `stratergy.py` imported `FLAT_SECTOR_MAP` from `bot.py`, creating circular dependency risk and making scanner logic depend on runtime orchestration.

Fix made: Sector lookup now lives in `config.py` via `FLAT_SECTOR_MAP` and `get_sector_for_symbol`.

4. Deployment requirements were incomplete.

Root cause: directly imported packages were missing from `requirements.txt`.

Fix made: Added `feedparser`, `growwapi`, `matplotlib`, `mplfinance`, and `python-dotenv`.

### HIGH

1. Broker mixed Groww transport and candle aggregation.

Root cause: `_aggregate_tick` and connection/subscription logic were in the same class.

Fix made: Added `project_alpha.candles.CandleAggregator`; `BrokerStream` now delegates aggregation while preserving its public API.

2. Broker captured event loop in `__init__`.

Root cause: `asyncio.get_running_loop()` was called during construction, which fails if constructed outside an active loop.

Fix made: `BrokerStream` now captures the loop inside `start()`.

3. Session reset could leave stale broker state.

Root cause: broker forming candles and cumulative volumes were not cleared on stop.

Fix made: `BrokerStream.stop()` clears forming candles and cumulative volume state.

4. Telegram failures were invisible.

Root cause: notifier ignored Telegram HTTP status and API `ok` response.

Fix made: notifier now checks HTTP status, validates Telegram response JSON, and retries three times.

5. Market context failures were too quiet.

Root cause: fallback values were neutral, but source status/freshness was not tracked.

Fix made: `MarketContext` now records `updated_at` and `source_status`; fetchers mark OK/fallback/failed states.

### MEDIUM

1. Scanner responsibilities remain broad.

Root cause: `MomentumScanner` still owns state, indicators, filters, scoring, alert formatting, chart triggering, and delivery decisions.

Status: partially fixed through domain/tracking foundations and sector/cooldown extraction, but full detector extraction remains.

2. Chart timestamps were synthetic.

Root cause: chart generation ignored live candle timestamps.

Fix made: `chart_generator.py` now uses real `timestamp` values when available.

3. No typed event contracts existed.

Root cause: pipeline data used unstructured dictionaries and pandas rows.

Fix made: added typed domain models for `Tick`, `Candle`, `MarketContextSnapshot`, `SignalCandidate`, `Signal`, and `AlertRequest`.

4. Cooldown tracking was embedded in scanner.

Root cause: `last_signal` was a raw dict in `MomentumScanner`.

Fix made: added `CooldownTracker` and wired scanner cooldown methods through it while preserving `scanner.last_signal`.

### LOW

1. Root module names and comments still carry legacy issues.

Root cause: `stratergy.py` is misspelled and several files contain old encoded comments/strings.

Status: preserved for compatibility. Future migration should rename via wrapper.

2. Requirements still include likely unused packages.

Root cause: prior requirements list appears broader than the current code needs.

Status: not pruned to avoid accidentally breaking deployment.

## What Was Preserved

- Root entrypoint: `bot.py`.
- Deployment command: `worker: python bot.py`.
- `BrokerStream` public class and methods.
- `MomentumScanner` public class and `on_candle` entrypoint.
- Current ATR/VWAP/range/volume/VWAP-pullback/R:R signal logic.
- Current Telegram text/photo alert behavior.
- Current market-context neutral fallback behavior.
- Current chart-generation fallback to text-only alert if chart creation fails.

## File-by-File Modifications

### `config.py`

- Added explicit schedule constants: `WARMUP_START`, `SCANNER_START`.
- Kept `MARKET_OPEN` as compatibility alias for warm-up/live-data start.
- Set `ORB_END` to `SCANNER_START`.
- Changed `MIN_CANDLES_REQUIRED` from 15 to 5.
- Added `FLAT_SECTOR_MAP`.
- Added `get_sector_for_symbol`.

### `bot.py`

- Uses `config.FLAT_SECTOR_MAP`.
- Added `is_scanner_active`.
- `is_orb_period` now reflects pre-9:20 warm-up.
- Intraday refresh waits for scanner-active time.
- Health monitor reports WARMUP vs LIVE.
- Market-open message now says warm-up runs until 9:20 AM.

### `broker.py`

- Rewritten in clean ASCII while preserving `BrokerStream`.
- Delegates candle aggregation to `project_alpha.candles.CandleAggregator`.
- Captures event loop in `start()` instead of `__init__`.
- Centralizes completed-candle submission.
- Clears broker candle/volume state on stop.

### `stratergy.py`

- Added timestamped candle columns.
- Added schedule gate before evaluating F&O candles.
- Added sector context synthesis from same-minute member-stock candles.
- Removed import from `bot.py`.
- Uses `config.get_sector_for_symbol`.
- Uses `CooldownTracker` while preserving `last_signal`.
- Added `SignalStore` foundation.

### `data_fetcher.py`

- `MarketContext` now tracks `updated_at` and `source_status`.
- FII/DII, options chain, earnings, and news fetches now mark OK/fallback/failed source status.
- Summary now includes source status.

### `notifier.py`

- Rewritten in clean ASCII while preserving `TelegramNotifier`.
- Adds Telegram HTTP/API response validation.
- Adds three-attempt retry with simple backoff.
- Awaits worker cancellation cleanly on stop.

### `chart_generator.py`

- Uses real candle timestamps when present.
- Keeps synthetic timestamp fallback for legacy/offline data.
- Removed unused `numpy` import.

### `requirements.txt`

- Added missing runtime imports: `feedparser`, `growwapi`, `matplotlib`, `mplfinance`, `python-dotenv`.

## New Folder Structure

```text
project_alpha/
  __init__.py
  candles/
    __init__.py
    aggregator.py
  config/
    __init__.py
    schedule.py
    sectors.py
  domain/
    __init__.py
    models.py
  scanner/
    __init__.py
  tracking/
    __init__.py
    cooldown.py
    signal_store.py
```

## Migration Notes

- Root modules remain the operational compatibility layer.
- New modules are foundations; the scanner has not yet been fully decomposed into detector/scoring/alerting subpackages.
- `stratergy.py` should eventually become a wrapper around `project_alpha.scanner.engine`.
- `notifier.py`, `broker.py`, and `chart_generator.py` can later become wrappers around `project_alpha.alerting`, `project_alpha.ingestion`, and `project_alpha.alerting.chart_service`.
- Sector context is currently member-synthesized, not true sector-index feed data.

## Verification

- In-memory syntax compilation passed for all Python files.
- `python -m compileall .` could not be used because Windows denied writing `.pyc` files into existing `__pycache__` directories. This was a bytecode-write permission issue, not a syntax failure.

## Risks Remaining

- Groww/NSE/Telegram live behavior still needs market-hours verification.
- Sector synthesis assumes enough same-minute member candles arrive; thin or delayed symbols can reduce sector availability.
- `MomentumScanner` still has too many responsibilities.
- Alert Markdown escaping is still not fully sanitized.
- No automated unit tests exist yet.
- Requirements may still include unused packages and one unpinned package (`growwapi`).
- Options-chain fallback parsing should be validated against current NSE response shapes.

## Technical Debt Remaining

- Rename `stratergy.py` safely through a compatibility wrapper.
- Extract indicator functions from `MomentumScanner`.
- Extract detector modules for opening range, trend-day quality, fakeout, VWAP pullback, and R:R.
- Create formal alert formatter and chart service modules.
- Add tests before additional signal engines are introduced.
- Add persistent tracking if live signal outcomes need to survive restarts.
- Add structured logging/telemetry around data-source freshness and alert delivery.

## PHASE 2 READINESS REPORT

Readiness score: 58%

### Volume Anomaly Engine

Already ready:

- Live per-minute volume delta exists.
- Candle aggregation is extracted.
- Sector synthesis creates a first version of participation context.

Partially ready:

- Current volume ratio logic exists inside scanner.
- Baseline uses recent intraday average only.

Missing:

- Dedicated volume anomaly detector.
- Opening auction/session-aware baselines.
- Percentile/z-score/relative-volume history.
- Volume acceleration and absorption features.

Must be built first:

- `scanner/detectors/volume_anomaly.py`.
- Unit tests for volume baselines and false-positive suppression.

Future bottlenecks:

- Groww volume field quality and callback timing.
- Lack of historical intraday volume profiles.

Architectural risks:

- If volume scoring remains inside `MomentumScanner`, future OI/basis evidence will make the class unstable again.

### OI Build-up Engine

Already ready:

- Domain model foundations can carry future evidence.
- Market-context source status pattern exists.

Partially ready:

- NSE client can fetch external data, but no derivative contract mapping exists.

Missing:

- OI data source.
- Cash-to-futures/options symbol mapping.
- Expiry selection.
- OI build-up classification.
- Freshness and error handling per derivative source.

Must be built first:

- Derivatives instrument registry.
- OI snapshot model.
- OI fetch client and parser.

Future bottlenecks:

- NSE rate limits and response-shape changes.
- Mapping F&O symbols to correct near-month contracts.

Architectural risks:

- OI evidence should feed the scoring layer, not directly send alerts.

### Futures Basis Engine

Already ready:

- Schedule and candle foundations are separate enough to accept new evidence.

Partially ready:

- No futures price ingestion yet.

Missing:

- Futures LTP ingestion or fetcher.
- Basis calculation model.
- Expiry-aware contract selection.
- Basis trend/velocity features.

Must be built first:

- Futures instrument registry.
- Futures quote source.
- Basis snapshot model.

Future bottlenecks:

- Reliable low-latency futures quotes.
- Handling expiry roll and illiquid contracts.

Architectural risks:

- Basis should be treated as contextual evidence, not as a separate alert path.

### Scoring and Ranking Engine

Already ready:

- Domain models include `SignalCandidate` and `Signal`.
- Existing confidence concept exists.

Partially ready:

- Current confidence is hardcoded inside scanner logic.

Missing:

- Scoring module.
- Evidence objects.
- Weight configuration.
- Ranking queue across symbols.
- Explanation generator.

Must be built first:

- `scanner/scoring.py`.
- Evidence schema.
- Candidate aggregation layer.

Future bottlenecks:

- Scoring without backtest/forward-test feedback can overfit intuition.

Architectural risks:

- Ranking must not delay early alerts too long; institutional detection is time-sensitive.

### Overall Phase 2 Gate

Before Phase 2 begins:

- Add unit tests around candle aggregation, scanner schedule, sector synthesis, cooldowns, and current signal logic.
- Extract current detector logic out of `MomentumScanner`.
- Add a formal scoring interface.
- Add source freshness into alert context.
- Validate requirements in a clean environment.
- Run one live market-session smoke test from 9:15 to 9:25.
