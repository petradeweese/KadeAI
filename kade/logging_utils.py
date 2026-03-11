"""Shared lightweight logging utilities for Kade."""

from __future__ import annotations

import logging
from enum import Enum


class LogCategory(str, Enum):
    CONFIG_LOAD = "CONFIG_LOAD"
    APP_START = "APP_START"
    MARKET_EVENT = "MARKET_EVENT"
    RADAR_EVENT = "RADAR_EVENT"
    REASONING_EVENT = "REASONING_EVENT"
    ORDER_EVENT = "ORDER_EVENT"
    NEWS_EVENT = "NEWS_EVENT"


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_event(logger: logging.Logger, category: LogCategory, message: str, **fields: object) -> None:
    suffix = " ".join(f"{key}={value}" for key, value in fields.items())
    full_message = f"[{category}] {message}" + (f" | {suffix}" if suffix else "")
    logger.info(full_message)
