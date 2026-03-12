"""Helpers for deterministic level extraction from existing textual reasoning payloads."""

from __future__ import annotations

import re

_NUMBER_PATTERN = re.compile(r"[-+]?\d*\.?\d+")


def parse_first_level(text: str | None) -> float | None:
    if not text:
        return None
    match = _NUMBER_PATTERN.search(str(text))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None
