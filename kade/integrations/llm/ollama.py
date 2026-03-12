"""Local Ollama provider for optional narrative generation."""

from __future__ import annotations

import json
from urllib.error import URLError
from urllib.request import Request, urlopen

from kade.integrations.health import ProviderHealth
from kade.integrations.llm.base import LLMGeneration, LLMProvider


class OllamaLLMProvider(LLMProvider):
    provider_name = "ollama"

    def __init__(self, config: dict[str, object] | None = None) -> None:
        cfg = config or {}
        self.enabled = bool(cfg.get("enabled", False))
        self.host = str(cfg.get("host", "http://localhost:11434")).rstrip("/")
        self.model = str(cfg.get("model", "llama3.1"))
        self.timeout_seconds = int(cfg.get("timeout_seconds", 30))
        self.api_key = str(cfg.get("api_key", "")).strip()

    def _request_json(self, path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(f"{self.host}{path}", data=data, headers=headers, method="POST" if payload is not None else "GET")
        with urlopen(request, timeout=self.timeout_seconds) as response:  # nosec - operator-provided local host
            raw = response.read().decode("utf-8")
        return json.loads(raw or "{}")

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMGeneration:
        if not self.enabled:
            return LLMGeneration(
                provider_name=self.provider_name,
                model=self.model,
                success=False,
                content="",
                finish_reason="disabled",
                error="ollama_disabled",
            )
        try:
            payload = {"model": self.model, "prompt": prompt, "stream": False, "options": {}}
            if system_prompt:
                payload["system"] = system_prompt
            if temperature is not None:
                payload["options"]["temperature"] = temperature
            if max_tokens is not None:
                payload["options"]["num_predict"] = max_tokens
            response = self._request_json("/api/generate", payload=payload)
            return LLMGeneration(
                provider_name=self.provider_name,
                model=self.model,
                success=bool(response.get("response")),
                content=str(response.get("response", "")).strip(),
                finish_reason=str(response.get("done_reason", "stop")),
                raw_response={
                    "done": response.get("done"),
                    "eval_count": response.get("eval_count"),
                    "prompt_eval_count": response.get("prompt_eval_count"),
                },
            )
        except Exception as exc:
            return LLMGeneration(
                provider_name=self.provider_name,
                model=self.model,
                success=False,
                content="",
                finish_reason="error",
                error=str(exc),
            )

    def health_snapshot(self, active: bool) -> ProviderHealth:
        if not self.enabled:
            return ProviderHealth(
                provider_type="llm",
                provider_name=self.provider_name,
                state="disabled",
                active=active,
                metadata={"enabled": False, "host": self.host, "model": self.model, "timeout_seconds": self.timeout_seconds},
            )
        try:
            payload = self._request_json("/api/tags")
            models = [item.get("name") for item in list(payload.get("models", [])) if isinstance(item, dict)]
            state = "ready" if self.model in models or not models else "degraded"
            return ProviderHealth(
                provider_type="llm",
                provider_name=self.provider_name,
                state=state,
                active=active,
                metadata={
                    "enabled": True,
                    "host": self.host,
                    "model": self.model,
                    "timeout_seconds": self.timeout_seconds,
                    "available_models": models[:10],
                    "api_key_present": bool(self.api_key),
                },
            )
        except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
            return ProviderHealth(
                provider_type="llm",
                provider_name=self.provider_name,
                state="degraded",
                active=active,
                metadata={
                    "enabled": True,
                    "host": self.host,
                    "model": self.model,
                    "timeout_seconds": self.timeout_seconds,
                    "api_key_present": bool(self.api_key),
                    "error": str(exc),
                },
            )
