"""Talk to the local Qwen server. Two dialects, one interface.

Settings: ``backend/config/qwen.json`` (copy ``qwen.example.json``)::

    {"api": "ollama",                    # "ollama" or "openai" (LM Studio, llama.cpp server, vLLM)
     "url": "http://127.0.0.1:11434",
     "model": "qwen2.5:14b-instruct",
     "temperature": 0, "seed": 42,       # deterministic as far as the server allows
     "num_ctx": 4096,                    # context window (6 KB prompt ~ 1,700 tokens)
     "timeout_s": 60, "keep_alive": "30m"}

``ask(prompt)`` sends the strategy prompt (system + user) and returns a Reply
with the raw text, latency and model identity (name + digest, so every
decision records exactly which weights answered — V3 Part E1). Parsing and
validating the answer is qwen/contract.py's job, not this file's.

Standard library only (urllib): nothing to install.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field, replace
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parents[1] / "config" / "qwen.json"


@dataclass(frozen=True)
class QwenSettings:
    api: str = "ollama"
    url: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5:14b-instruct"
    temperature: float = 0.0
    seed: int = 42
    num_ctx: int = 4096
    timeout_s: float = 60.0
    keep_alive: str = "30m"


def load_settings(path: Path | None = None) -> QwenSettings:
    s = QwenSettings()
    path = path or CONFIG_FILE
    if path.exists():
        raw = {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if not k.startswith("_")}
        unknown = set(raw) - set(QwenSettings.__dataclass_fields__)
        if unknown:
            raise ValueError(f"{path}: unknown Qwen setting(s) {sorted(unknown)}")
        s = replace(s, **raw)
    if s.api not in ("ollama", "openai"):
        raise ValueError("qwen api must be 'ollama' or 'openai'")
    return s


@dataclass(frozen=True)
class Reply:
    text: str
    latency_ms: int
    model: str
    model_digest: str | None
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    raw: dict = field(default_factory=dict, repr=False)


class QwenError(RuntimeError):
    pass


class QwenClient:
    def __init__(self, settings: QwenSettings | None = None, transport=None) -> None:
        self.s = settings or load_settings()
        self._post = transport or _http_post          # tests inject a fake transport
        self._digest: str | None = None

    # ------------------------------------------------------------------ public
    def ask(self, system: str, user: str) -> Reply:
        t0 = time.monotonic()
        if self.s.api == "ollama":
            body = {"model": self.s.model, "stream": False, "format": "json", "keep_alive": self.s.keep_alive,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "options": {"temperature": self.s.temperature, "seed": self.s.seed, "num_ctx": self.s.num_ctx}}
            out = self._post(f"{self.s.url}/api/chat", body, self.s.timeout_s)
            text = (out.get("message") or {}).get("content", "")
            reply = Reply(text, int((time.monotonic() - t0) * 1000), out.get("model", self.s.model),
                          self.digest(), out.get("prompt_eval_count"), out.get("eval_count"), out)
        else:
            body = {"model": self.s.model, "temperature": self.s.temperature, "seed": self.s.seed,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
            out = self._post(f"{self.s.url}/v1/chat/completions", body, self.s.timeout_s)
            choice = (out.get("choices") or [{}])[0]
            usage = out.get("usage") or {}
            reply = Reply((choice.get("message") or {}).get("content", ""), int((time.monotonic() - t0) * 1000),
                          out.get("model", self.s.model), out.get("system_fingerprint"),
                          usage.get("prompt_tokens"), usage.get("completion_tokens"), out)
        if not reply.text:
            raise QwenError(f"empty answer from {self.s.api} at {self.s.url}")
        return reply

    def digest(self) -> str | None:
        """Ollama model digest (identity of the exact weights), cached per process."""
        if self.s.api != "ollama":
            return None
        if self._digest is None:
            try:
                tags = _http_get(f"{self.s.url}/api/tags", 10)
                for m in tags.get("models", []):
                    if m.get("name") == self.s.model or m.get("model") == self.s.model:
                        self._digest = m.get("digest")
            except QwenError:
                return None
        return self._digest

    def ping(self) -> dict:
        """Is the server up and the model there? Used by ``python -m qwen ping``."""
        if self.s.api == "ollama":
            tags = _http_get(f"{self.s.url}/api/tags", 10)
            names = [m.get("name") for m in tags.get("models", [])]
        else:
            names = [m.get("id") for m in _http_get(f"{self.s.url}/v1/models", 10).get("data", [])]
        return {"url": self.s.url, "api": self.s.api, "model": self.s.model,
                "model_available": self.s.model in names, "models": names, "digest": self.digest()}


def _http_post(url: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise QwenError(f"{url}: {exc}") from exc


def _http_get(url: str, timeout: float) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise QwenError(f"{url}: {exc}") from exc
