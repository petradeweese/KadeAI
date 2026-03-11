"""Entrypoint for the Kade Phase 1 local application."""

from __future__ import annotations

from pathlib import Path

import yaml

from kade.logging_utils import LogCategory, get_logger, log_event, setup_logging

CONFIG_DIR = Path(__file__).parent / "config"
LOGGER = get_logger(__name__)


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def bootstrap_config() -> dict[str, dict]:
    config_names = [
        "tickers.yaml",
        "trading_rules.yaml",
        "radar_rules.yaml",
        "personality.yaml",
        "voice.yaml",
        "execution.yaml",
        "news.yaml",
    ]
    loaded_configs: dict[str, dict] = {}
    for name in config_names:
        loaded_configs[name] = load_yaml(CONFIG_DIR / name)
        log_event(LOGGER, LogCategory.CONFIG_LOAD, "Config loaded", file=name)
    return loaded_configs


def main() -> None:
    setup_logging()
    log_event(LOGGER, LogCategory.APP_START, "Kade startup initiated")

    configs = bootstrap_config()
    watchlist = configs["tickers.yaml"].get("watchlist", [])

    log_event(
        LOGGER,
        LogCategory.APP_START,
        "Kade Phase 1 initialized",
        config_count=len(configs),
        watchlist_count=len(watchlist),
    )
    print("Kade Phase 1 initialized")
    print(f"Loaded {len(configs)} config files")
    print(f"Watchlist: {', '.join(watchlist)}")


if __name__ == "__main__":
    main()
