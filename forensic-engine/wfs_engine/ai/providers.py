"""AI provider abstraction: local Ollama by default, optional OpenAI-compatible.

Evidence only leaves the machine when the user explicitly selects an external
provider, and the request payload is limited to the retrieved context that the
UI discloses.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class ProviderError(RuntimeError):
    pass


def _post_json(url: str, payload: dict[str, Any], *, headers: dict[str, str] | None = None,
               timeout: float = 120.0) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise ProviderError(f"{url} returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderError(f"cannot reach {url}: {exc}") from exc
    except ValueError as exc:
        raise ProviderError(f"invalid JSON from {url}: {exc}") from exc


def _get_json(url: str, *, headers: dict[str, str] | None = None,
              timeout: float = 20.0) -> dict[str, Any]:
    req = urllib.request.Request(url, method="GET")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"{url} returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderError(f"cannot reach {url}: {exc}") from exc


@dataclass
class ChatResult:
    text: str
    model: str
    provider: str
    usage: dict[str, Any]


class OllamaProvider:
    name = "ollama"
    external = False

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or os.environ.get("WFS_OLLAMA_URL")
                         or "http://127.0.0.1:11434").rstrip("/")

    def health(self) -> dict[str, Any]:
        try:
            data = _get_json(f"{self.base_url}/api/tags", timeout=4)
            models = [m.get("name") for m in data.get("models", [])]
            return {"ok": True, "provider": self.name, "base_url": self.base_url,
                    "models": models}
        except ProviderError as exc:
            return {"ok": False, "provider": self.name, "base_url": self.base_url,
                    "models": [], "error": str(exc),
                    "hint": "Start Ollama locally (ollama serve) and pull a model, e.g. "
                            "ollama pull llama3.1"}

    def chat(self, messages: list[dict[str, str]], model: str,
             temperature: float = 0.2, context_length: int = 8192) -> ChatResult:
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_ctx": context_length},
        }
        data = _post_json(f"{self.base_url}/api/chat", payload, timeout=300)
        message = data.get("message") or {}
        return ChatResult(text=message.get("content", ""), model=model,
                          provider=self.name, usage={
                              "eval_count": data.get("eval_count"),
                              "prompt_eval_count": data.get("prompt_eval_count")})

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        out = []
        for text in texts:
            data = _post_json(f"{self.base_url}/api/embeddings",
                              {"model": model, "prompt": text}, timeout=120)
            vector = data.get("embedding") or []
            out.append([float(v) for v in vector])
        return out


class OpenAICompatProvider:
    name = "openai-compatible"
    external = True

    def __init__(self, base_url: str, api_key: str, model: str = "gpt-4o-mini"):
        if not base_url:
            raise ProviderError("external provider base URL is not configured")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = model

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def health(self) -> dict[str, Any]:
        if not self.api_key:
            return {"ok": False, "provider": self.name, "external": True,
                    "error": "no API key in the OS credential store",
                    "hint": "Save the key in Settings → AI; it is stored by the "
                            "operating system credential vault, never in project files."}
        try:
            data = _get_json(f"{self.base_url}/models", headers=self._headers(), timeout=8)
            return {"ok": True, "provider": self.name, "external": True,
                    "models": [m.get("id") for m in data.get("data", [])]}
        except ProviderError as exc:
            return {"ok": False, "provider": self.name, "external": True, "error": str(exc)}

    def chat(self, messages: list[dict[str, str]], model: str,
             temperature: float = 0.2, context_length: int = 8192) -> ChatResult:
        payload = {"model": model or self.default_model, "messages": messages,
                   "temperature": temperature}
        data = _post_json(f"{self.base_url}/chat/completions", payload,
                          headers=self._headers(), timeout=180)
        choice = (data.get("choices") or [{}])[0]
        return ChatResult(text=(choice.get("message") or {}).get("content", ""),
                          model=payload["model"], provider=self.name,
                          usage=data.get("usage") or {})

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        data = _post_json(f"{self.base_url}/embeddings",
                          {"model": model, "input": texts},
                          headers=self._headers(), timeout=120)
        return [[float(v) for v in item.get("embedding", [])]
                for item in data.get("data", [])]


def build_provider(settings: dict[str, Any], *, api_key: str | None = None):
    kind = settings.get("ai_provider", "ollama")
    if kind == "openai-compatible":
        if not settings.get("ai_external_enabled"):
            raise ProviderError(
                "The external AI provider is disabled. Enable it in Settings → AI and "
                "confirm the data-sharing disclosure first.")
        return OpenAICompatProvider(
            settings.get("ai_external_base_url", ""),
            api_key or os.environ.get("OPENAI_API_KEY", ""),
            settings.get("ai_model", "gpt-4o-mini"))
    return OllamaProvider()


def status(settings: dict[str, Any], *, api_key: str | None = None) -> dict[str, Any]:
    provider = build_provider(settings, api_key=api_key) if settings.get("ai_enabled") else None
    if provider is None:
        return {"ok": False, "enabled": False, "provider": None,
                "hint": "AI features are switched off in Settings."}
    health = provider.health()
    health["enabled"] = bool(settings.get("ai_enabled"))
    health["configured_model"] = settings.get("ai_model")
    health["external"] = provider.external
    health["requires_disclosure"] = provider.external
    return health
