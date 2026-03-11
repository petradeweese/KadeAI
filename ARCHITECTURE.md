# Kade Architecture (Phase 1)

## Overview
Kade is a **Python modular monolith**. Modules are isolated by responsibility but run inside one local process/runtime.

Design principles:
- Config-driven behavior (YAML first)
- Readable, deterministic logic
- Paper trading only (live trading disabled)
- Incremental phase delivery

## Module responsibilities
- `kade/main.py`: app bootstrap and config loading (current entrypoint)
- `kade/logging_utils.py`: shared structured logging setup and event categories
- `kade/config/`: all tunable configuration files
- `kade/market/`: market data interfaces/wrappers, indicators, market state models
- `kade/brain/`: future reasoning + memory orchestration (placeholder)
- `kade/radar/`: future opportunity detection and dedup logic (placeholder)
- `kade/options/`: future options contract selection/scoring (placeholder)
- `kade/execution/`: future order workflow (paper first, live later if enabled)
- `kade/news/`: future news/event context ingestion and interpretation
- `kade/dashboard/`: local dashboard surface (placeholder app status)
- `kade/integrations/{stt,tts,wakeword}`: voice integration interfaces (placeholder)

## Phase 1 scope
Implemented now:
- Project/package skeleton
- YAML configuration layout
- Alpaca client scaffold + mock client
- Indicator calculations (VWAP/RSI/MACD/structure/volume/slope)
- Canonical `TickerState` placeholder model
- Shared lightweight logging setup
- Basic indicator tests

Placeholder only (not implemented):
- Real-time market loop
- Opportunity radar engine
- Reasoning/mental model logic
- Options evaluation pipeline
- Execution logic beyond config scaffolding
- News intelligence pipeline
- Voice runtime behavior

## Intended data flow (target architecture)
1. **Config** (`kade/config/*.yaml`)
   - Provides thresholds, modes, watchlist, execution constraints.
2. **Market Data** (`kade/market/alpaca_client.py`)
   - Supplies bars/quotes/trades from provider.
3. **Indicators** (`kade/market/indicators.py`)
   - Computes technical/context features from market series.
4. **Ticker State / Mental Model** (`TickerState`)
   - Stores per-symbol snapshot used by higher-level logic.
5. **Radar** (`kade/radar/`)
   - Consumes ticker states; emits prioritized setup events.
6. **Reasoning** (`kade/brain/`)
   - Converts context + user intent into recommendations.
7. **Options** (`kade/options/`)
   - Maps trade intent to candidate contracts.
8. **Execution** (`kade/execution/`)
   - Handles paper order staging/confirmation workflow.
9. **Dashboard** (`kade/dashboard/`)
   - Displays state, radar queue, debug signals.
10. **Voice Integrations** (`kade/integrations/`)
   - Optional I/O surface to same core flows (later phases).

## Phase progression (high level)
- **Phase 1 (current):** skeleton, config, market scaffold, indicators, tests.
- **Phase 2:** real-time market loop, ticker state updates, radar/reasoning scaffolding, dashboard wiring.
- **Later phases:** deeper options/execution workflows, richer memory/style behavior, voice node support.
