"""Entrypoint for the Kade Phase 2B local application."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from kade.dashboard.app import create_app_status
from kade.logging_utils import LogCategory, get_logger, log_event, setup_logging
from kade.market.alpaca_client import MockAlpacaClient
from kade.market.market_loop import MarketStateLoop

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
        "market_state.yaml",
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
    tickers_config = configs["tickers.yaml"]
    market_state_config = configs["market_state.yaml"]

    market_loop = MarketStateLoop(
        market_client=MockAlpacaClient(),
        watchlist=tickers_config.get("watchlist", []),
        timeframes=tickers_config.get("timeframes", {}),
        bars_limit=market_state_config["market_loop"]["bars_limit"],
        mental_model_config=market_state_config["mental_model"],
        radar_config=configs["radar_rules.yaml"]["radar"],
    )

    run_loop = os.getenv("KADE_RUN_MARKET_LOOP", "0") == "1"
    if run_loop:
        poll_seconds = market_state_config["market_loop"]["poll_seconds"]
        log_event(LOGGER, LogCategory.APP_START, "Starting continuous market loop", poll_seconds=poll_seconds)
        market_loop.run_forever(poll_seconds=poll_seconds)
    else:
        states, debug_values = market_loop.update_once()
        dashboard_state = create_app_status(
            states,
            debug_values,
            market_loop.latest_breadth,
            market_loop.latest_radar,
        )
        print("Kade Phase 3 initialized")
        print(f"Ticker cards: {dashboard_state['card_count']}")
        print(f"Radar queue: {len(dashboard_state['radar']['queue'])}")


if __name__ == "__main__":
    main()
