"""Runtime persistence coordination for Phase 7 state."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from kade.brain import ConversationMemory, SessionPlanTracker
from kade.logging_utils import LogCategory, log_event
from kade.storage import BacktestStore, ExecutionStore, HistoryStore, MemoryStore, PlanStore, RadarStore, SessionStore, rollover_session


@dataclass
class RuntimePersistence:
    """Coordinates storage setup, persistence safety wrappers, and retained histories."""

    logger: object
    memory_store: MemoryStore
    plan_store: PlanStore
    radar_store: RadarStore
    execution_store: ExecutionStore
    session_store: SessionStore
    backtest_store: BacktestStore
    history_store: HistoryStore
    history_cfg: dict[str, object]
    session_cfg: dict[str, object]

    @classmethod
    def from_config(cls, storage_config: dict[str, object], logger: object) -> "RuntimePersistence":
        storage_root = Path(str(storage_config.get("root_dir", ".kade_storage")))
        history_cfg = dict(storage_config.get("history", {}))
        session_cfg = dict(storage_config.get("session", {}))
        return cls(
            logger=logger,
            memory_store=MemoryStore(storage_root),
            plan_store=PlanStore(storage_root),
            radar_store=RadarStore(storage_root),
            execution_store=ExecutionStore(storage_root),
            session_store=SessionStore(storage_root),
            backtest_store=BacktestStore(storage_root),
            history_store=HistoryStore(storage_root),
            history_cfg=history_cfg,
            session_cfg=session_cfg,
        )

    @staticmethod
    def bounded(items: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
        return items[-limit:] if limit > 0 else []

    def safe_load(self, label: str, loader: Callable[[], object], fallback: object) -> object:
        try:
            payload = loader()
            log_event(self.logger, LogCategory.STORAGE_EVENT, "Persistence loaded", scope=label)
            return payload
        except Exception as exc:  # deterministic fallback with visible log
            log_event(self.logger, LogCategory.STORAGE_EVENT, "Persistence load failed", scope=label, error=str(exc))
            return fallback

    def safe_save(self, label: str, saver: Callable[[], None]) -> None:
        try:
            saver()
            log_event(self.logger, LogCategory.STORAGE_EVENT, "Persistence saved", scope=label)
        except Exception as exc:
            log_event(self.logger, LogCategory.STORAGE_EVENT, "Persistence save failed", scope=label, error=str(exc))

    def restore_startup_state(
        self,
        memory: ConversationMemory,
        plan_tracker: SessionPlanTracker,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
        restored_memory = self.safe_load("memory", self.memory_store.load_memory, {"intents": [], "responses": [], "notes": []})
        memory.restore(restored_memory)

        restored_plans = self.safe_load("plans", self.plan_store.load_plans, {"plans": [], "events": []})
        plan_tracker.restore(restored_plans)

        radar_history: list[dict[str, object]] = self.safe_load("radar", self.radar_store.load_events, [])
        execution_history: list[dict[str, object]] = self.safe_load("execution", self.execution_store.load_events, [])
        session_fallback = self.session_store.load_session()
        session_state: dict[str, object] = self.safe_load("session", self.session_store.load_session, session_fallback)
        advisor_history: list[dict[str, object]] = list(session_state.get("advisor_history", []))
        return radar_history, advisor_history, execution_history, session_state

    def apply_rollover(self, session_state: dict[str, object]) -> dict[str, object]:
        before_day_key = session_state.get("day_key")
        rolled_state = rollover_session(session_state)
        if before_day_key != rolled_state.get("day_key"):
            log_event(self.logger, LogCategory.SESSION_EVENT, "Session rollover", day_key=rolled_state.get("day_key"))
            self.safe_save("session", lambda: self.session_store.save_session(rolled_state))
        return rolled_state

    def persist_memory(self, memory: ConversationMemory) -> None:
        self.safe_save("memory", lambda: self.memory_store.save_memory(memory.snapshot(limit=500)))

    def persist_plans(self, plan_tracker: SessionPlanTracker) -> None:
        self.safe_save("plans", lambda: self.plan_store.save_plans(plan_tracker.persistence_payload()))

    def persist_radar_history(self, radar_history: list[dict[str, object]]) -> list[dict[str, object]]:
        bounded_history = self.bounded(radar_history, int(self.history_cfg.get("radar_limit", 150)))
        self.safe_save("radar", lambda: self.radar_store.save_events(bounded_history))
        return bounded_history

    def persist_execution_history(self, execution_history: list[dict[str, object]]) -> list[dict[str, object]]:
        bounded_history = self.bounded(execution_history, int(self.history_cfg.get("execution_limit", 200)))
        self.safe_save("execution", lambda: self.execution_store.save_events(bounded_history))
        return bounded_history

    def persist_advisor_history(
        self, advisor_history: list[dict[str, object]], session_state: dict[str, object]
    ) -> list[dict[str, object]]:
        bounded_history = self.bounded(advisor_history, int(self.history_cfg.get("advisor_limit", 120)))
        session_state["advisor_history"] = bounded_history
        return bounded_history

    def retain_recent_voice_events(self, session_state: dict[str, object]) -> None:
        session_state["recent_voice_events"] = self.bounded(
            list(session_state.get("recent_voice_events", [])),
            int(self.session_cfg.get("recent_voice_events_limit", 25)),
        )

    def retain_recent_commands(self, session_state: dict[str, object]) -> None:
        session_state["recent_command_history"] = self.bounded(
            list(session_state.get("recent_command_history", [])),
            int(self.session_cfg.get("recent_command_history_limit", 40)),
        )


    def retain_provider_health_history(self, session_state: dict[str, object]) -> None:
        session_state["provider_health_history"] = self.bounded(
            list(session_state.get("provider_health_history", [])),
            int(self.session_cfg.get("provider_health_history_limit", 20)),
        )

    def persist_session(self, session_state: dict[str, object]) -> None:
        self.safe_save("session", lambda: self.session_store.save_session(session_state))


    def load_backtest_summaries(self) -> list[dict[str, object]]:
        return self.safe_load("backtesting", self.backtest_store.load_summaries, [])

    def persist_backtest_summaries(self, summaries: list[dict[str, object]]) -> list[dict[str, object]]:
        bounded = self.bounded(summaries, int(self.history_cfg.get("backtest_limit", 40)))
        self.safe_save("backtesting", lambda: self.backtest_store.save_summaries(bounded))
        return bounded


    def load_history_runtime(self) -> dict[str, object]:
        return self.safe_load("history_runtime", self.history_store.load_runtime, {"last_download": {}, "cache_status": {}, "recent_downloads": []})

    def persist_history_runtime(self, payload: dict[str, object]) -> dict[str, object]:
        history_limit = int(self.history_cfg.get("history_metadata_limit", 30))
        recents = list(payload.get("recent_downloads", []))
        payload["recent_downloads"] = recents[-history_limit:] if history_limit > 0 else []
        self.safe_save("history_runtime", lambda: self.history_store.save_runtime(payload))
        return payload

    def metadata_snapshot(self) -> dict[str, object]:
        return {
            "memory": self.memory_store.metadata_snapshot(),
            "plans": self.plan_store.metadata_snapshot(),
            "radar": self.radar_store.metadata_snapshot(),
            "execution": self.execution_store.metadata_snapshot(),
            "session": self.session_store.metadata_snapshot(),
            "backtesting": self.backtest_store.metadata_snapshot(),
            "history_runtime": self.history_store.metadata_snapshot(),
        }
