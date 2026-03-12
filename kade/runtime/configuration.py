"""Config helpers for environment-backed runtime settings."""

from __future__ import annotations

import os


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _env_first(environ: dict[str, str], *names: str) -> str | None:
    for name in names:
        value = environ.get(name)
        if value is not None and str(value).strip() != "":
            return str(value)
    return None


def _apply_if_present(target: dict[str, object], key: str, value: object | None) -> None:
    if value is not None:
        target[key] = value


def apply_runtime_env_overrides(configs: dict[str, dict], environ: dict[str, str] | None = None) -> dict[str, dict]:
    env = dict(os.environ if environ is None else environ)

    execution = dict(configs.get("execution.yaml", {}))
    providers = dict(execution.get("providers", {}))
    market_backends = dict(providers.get("market_data_backends", {}))
    options_backends = dict(providers.get("options_data_backends", {}))
    market_alpaca = dict(market_backends.get("alpaca", {}))
    options_alpaca = dict(options_backends.get("alpaca", {}))

    credentials = {
        "api_key": _env_first(env, "KADE_ALPACA_API_KEY", "ALPACA_API_KEY", "APCA_API_KEY_ID"),
        "secret_key": _env_first(env, "KADE_ALPACA_SECRET_KEY", "ALPACA_SECRET_KEY", "APCA_API_SECRET_KEY"),
        "base_url": _env_first(env, "KADE_ALPACA_BASE_URL", "ALPACA_BASE_URL"),
        "data_url": _env_first(env, "KADE_ALPACA_DATA_URL", "ALPACA_DATA_URL"),
    }
    for key, value in credentials.items():
        _apply_if_present(market_alpaca, key, value)
        _apply_if_present(options_alpaca, key, value)

    _apply_if_present(market_alpaca, "enabled", _parse_bool(_env_first(env, "KADE_ALPACA_MARKET_DATA_ENABLED", "KADE_ALPACA_ENABLED")))
    _apply_if_present(options_alpaca, "enabled", _parse_bool(_env_first(env, "KADE_ALPACA_OPTIONS_ENABLED", "KADE_ALPACA_ENABLED")))
    _apply_if_present(options_alpaca, "supported", _parse_bool(_env_first(env, "KADE_ALPACA_OPTIONS_SUPPORTED")))

    market_backends["alpaca"] = market_alpaca
    options_backends["alpaca"] = options_alpaca
    providers["market_data_backends"] = market_backends
    providers["options_data_backends"] = options_backends
    execution["providers"] = providers
    configs["execution.yaml"] = execution

    market_intelligence = dict(configs.get("market_intelligence.yaml", {}))
    market_intelligence_root = dict(market_intelligence.get("market_intelligence", {}))
    intelligence_alpaca = dict(market_intelligence_root.get("alpaca", {}))
    for key, value in credentials.items():
        _apply_if_present(intelligence_alpaca, key, value)
    _apply_if_present(
        intelligence_alpaca,
        "enabled",
        _parse_bool(_env_first(env, "KADE_ALPACA_MARKET_INTELLIGENCE_ENABLED", "KADE_ALPACA_ENABLED")),
    )
    market_intelligence_root["alpaca"] = intelligence_alpaca
    market_intelligence["market_intelligence"] = market_intelligence_root
    configs["market_intelligence.yaml"] = market_intelligence

    llm_cfg = dict(configs.get("llm.yaml", {}))
    llm_root = dict(llm_cfg.get("llm", {}))
    llm_providers = dict(llm_root.get("providers", {}))
    ollama_cfg = dict(llm_providers.get("ollama", {}))
    _apply_if_present(ollama_cfg, "enabled", _parse_bool(_env_first(env, "KADE_OLLAMA_ENABLED")))
    _apply_if_present(ollama_cfg, "host", _env_first(env, "KADE_OLLAMA_HOST", "OLLAMA_HOST"))
    _apply_if_present(ollama_cfg, "model", _env_first(env, "KADE_OLLAMA_MODEL"))
    timeout_raw = _env_first(env, "KADE_OLLAMA_TIMEOUT_SECONDS")
    if timeout_raw is not None:
        try:
            ollama_cfg["timeout_seconds"] = int(timeout_raw)
        except ValueError:
            pass
    _apply_if_present(ollama_cfg, "api_key", _env_first(env, "KADE_OLLAMA_API_KEY"))
    provider_name = _env_first(env, "KADE_LLM_PROVIDER")
    if provider_name is not None:
        llm_root["provider"] = provider_name
    llm_providers["ollama"] = ollama_cfg
    llm_root["providers"] = llm_providers
    llm_cfg["llm"] = llm_root
    configs["llm.yaml"] = llm_cfg

    return configs
