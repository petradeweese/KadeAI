# Kade

Kade is a local, config-driven AI trading copilot built as a **Python modular monolith**. It runs as one process with clear module boundaries for market sensing, setup detection, reasoning, options planning, execution simulation, runtime interaction, and persistence.

## Current architecture

Core modules in `kade/`:

- `market/` — market state loop, indicator engine, context intelligence, Alpaca boundary + mock client.
- `radar/` — setup scoring and queue/event generation over market state snapshots.
- `options/` — options intent-to-contract selection pipeline with deterministic mock chain support.
- `execution/` — paper execution workflow, guardrails, and lifecycle state transitions.
- `brain/` — reasoning output generation, conversation memory, style profile, and session plan tracking.
- `voice/` — wake/transcript orchestration, command routing, and spoken response formatting.
- `runtime/` — text/voice interaction orchestration, replay/debug payloads, persistence wiring, and dashboard bootstrap helpers.
- `storage/` — file-backed JSON stores for session, radar history, plans, memory, and execution history.

Supporting boundaries:

- `integrations/` — pluggable providers for wakeword, STT, and TTS (mock and runtime-oriented adapters).
- `dashboard/` — local dashboard app surface for runtime state.
- `config/` — YAML configuration for watchlist, rules, personality, voice/runtime modes, persistence, and execution constraints.

## Runtime mode today

Kade runs in **MacBook text-first mode by default**:

- text commands are the primary interaction path;
- voice stack is fully wired (wakeword/STT/TTS/orchestrator) but disabled by default via runtime flags;
- provider readiness is still tracked and surfaced in runtime/dashboard payloads even when voice is disabled.

## Persistence and session behavior

Kade persists local JSON state under configured storage paths:

- session/day payload (including done-for-day state and rollover markers),
- radar event history,
- execution history,
- reasoning memory,
- plan tracker state.

Session rollover resets day-scoped counters/flags when the calendar day changes while preserving longer-lived artifacts (for example advisor history and persisted memory/plan stores).

## Testing status

The repository includes phase-oriented pytest coverage across:

- market indicators/state/context,
- radar scoring,
- options + execution paper flow,
- brain reasoning/memory/plans,
- persistence round-trips and rollover,
- voice orchestration,
- runtime readiness and interaction behavior.

Run checks with:

```bash
pytest -q
```

## Real vs mocked right now

Real-ish runtime pieces:

- end-to-end local orchestration across market → radar → brain/options/execution → runtime/dashboard payloads,
- deterministic persistence and replay tooling,
- provider interfaces for voice stack and market boundaries.

Mocked/simulated pieces:

- market transport uses local mock Alpaca client in default runtime path,
- options chain data uses mock chain generation,
- execution is paper workflow only (no live broker routing),
- voice providers are typically configured to mock/degraded local modes by default.

## Phase 10 (not yet started)

Phase 10 is expected to focus on **runtime hardening and integration maturity** (not yet implemented in this cleanup), such as:

- deeper production-readiness around provider/integration boundaries,
- stronger end-to-end runtime validation and observability,
- incremental reduction of mocked edges where safe.

This repository remains in pre-Phase-10 state; this pass is maintenance/consistency only.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
python -m kade.main
```
