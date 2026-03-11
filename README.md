# Kade (Phase 1)

Kade is a local AI trading assistant focused on being a conversational trading co-pilot. This repository currently implements **Phase 1** foundations:

1. Project skeleton and modular package layout
2. Config-driven defaults for trading behavior and system personality
3. Alpaca market data client wrapper scaffolding
4. Indicator engine for core intraday signals
5. Canonical ticker state placeholder model for future mental model logic
6. Lightweight shared logging utilities
7. Basic unit tests for indicator calculations

## Architecture docs
- See `ARCHITECTURE.md` for module boundaries, data flow, and phase progression.

## Architecture

Kade uses a **modular monolith** architecture in Python:

- `kade/main.py`: bootstrap/config entrypoint (not a full runtime loop yet)
- `kade/logging_utils.py`: reusable logging setup with event categories
- `kade/market/`: market data client wrappers, indicator logic, and state models
- `kade/dashboard/`: local dashboard placeholder
- `kade/brain/`, `kade/radar/`, `kade/options/`, `kade/execution/`, `kade/news/`: placeholder packages for future phases
- `kade/integrations/`: pluggable stubs for STT/TTS/wakeword integrations
- `kade/config/`: all tunable YAML files

## What's implemented now

### Config files
The following YAML files are included in `kade/config/`:

- `tickers.yaml`
- `trading_rules.yaml`
- `radar_rules.yaml`
- `personality.yaml`
- `voice.yaml`
- `execution.yaml`
- `news.yaml`

### Market engine
- `AlpacaClient` wrapper interface with clear methods for:
  - latest quote
  - latest trade
  - historical bars
- `MockAlpacaClient` for local development and tests
- Structured market state dataclasses in `kade/market/structure.py`, including a Phase 1 `TickerState` placeholder
- **Note:** Alpaca transport/API integration is scaffolded only in Phase 1 (`NotImplementedError` for live calls)

### Indicator engine
Implemented in `kade/market/indicators.py`:

- VWAP
- RSI
- MACD
- Volume acceleration
- Regression trend slope
- Higher highs / lower highs detection
- Consolidation / breakout detection

### Logging
`kade/logging_utils.py` provides:
- reusable logger initialization
- expandable log categories
- structured, readable event logs

`kade/main.py` now emits startup and config-loading events.

### Tests
Basic unit tests for indicator calculations live in `kade/tests/test_indicators.py`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

## Config-driven design
All tunable thresholds are stored in YAML under `kade/config/`. Indicator and structure logic accepts externally supplied thresholds and avoids hard-coded trading limits in signal logic.

## Local run

```bash
python -m kade.main
```

The current app bootstraps configuration and reports basic status. It does not yet run a persistent market monitoring loop.

## Phase 2 (recommended)

1. Real-time market loop and watchlist state updates
2. Opportunity radar state machine and dedup logic
3. Trade idea evaluation pipeline (advisor mode)
4. Options chain filtering/scoring scaffolding
5. Dashboard live ticker cards + debug panel wiring
