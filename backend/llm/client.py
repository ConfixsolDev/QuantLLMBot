"""Talk to the local LLM server. Default: Bonsai 2 27B on the PrismML llama-server.

The trading model is ``prism-ml/Ternary-Bonsai-2-27B-gguf`` (Qwen3.8-27B in
ternary weights, 6-7 GB). Its PQ2_0 / PTQ1_0 files load ONLY in the PrismML
fork of llama.cpp (Ollama, LM Studio and stock llama.cpp cannot run them), so
the default dialect is that fork's ``llama-server`` (OpenAI-compatible API on
port 8080). Start it with ``Start-LLM.bat`` at the repository root.

Settings: ``backend/config/llm.json`` (copy ``llm.example.json``)::

    {"api": "llama_server",              # llama_server | openai | ollama
     "url": "http://127.0.0.1:8080",
     "model": "Ternary-Bonsai-2-27B",     # name for the journal; llama-server serves one model
     "reasoning_effort": "none",          # none | medium | xhigh   (NOT low/high, see below)
     "max_tokens": 512,                   # answer only; raise to 16384 if reasoning is on
     "temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0.0,
     "presence_penalty": 1.5, "seed": 42,
     "json_schema": true,                 # grammar-constrain the answer to the contract
     "timeout_s": 120}

Why these defaults (model card + KNOWN_ISSUES of the model, 2026-09-23):

* Bonsai 2 is a THINKING model and reasons at "xhigh" by default — thousands
  of tokens before the answer. A trade decision has a few M1 bars to live, so
  reasoning is OFF ("none"; the server must stay at ``--reasoning auto``,
  ``--reasoning on`` would override it). "medium" is the measured middle
  ground if answers prove better with thinking; "low" is not supported and
  "high" returns HTTP 500.
* Non-thinking sampling from the model card: temperature 0.7, top_p 0.8,
  top_k 20, min_p 0, presence_penalty 1.5. A fixed seed makes one server build
  on one machine repeatable.
* The chat template requires exactly ONE system message, first — the prompt
  always has one system + one user message.
* ``json_schema``: llama-server turns the answer contract into a grammar, so
  the model cannot produce anything but {"decision": <a candidate id of THIS
  prompt or "wait">, "confidence": 0-100, "cites": [...], "why": "..."}.
  llm/contract.py checks still run (citations, confidence) — the grammar only
  removes broken JSON.

``ask(system, user, schema)`` returns a Reply (answer text, any reasoning
text, latency, token counts, model identity = file name + size reported by
the server's /props). Standard library only.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field, replace
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parents[1] / "config" / "llm.json"
EFFORTS = ("none", "medium", "xhigh")


@dataclass(frozen=True)
class LLMSettings:
    api: str = "llama_server"
    url: str = "http://127.0.0.1:8080"
    model: str = "Ternary-Bonsai-2-27B"
    reasoning_effort: str = "none"
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.8
    top_k: int = 20
    min_p: float = 0.0
    presence_penalty: float = 1.5
    seed: int = 42
    json_schema: bool = True
    timeout_s: float = 120.0
    keep_alive: str = "30m"           # ollama only


def load_settings(path: Path | None = None) -> LLMSettings:
    s = LLMSettings()
    path = path or CONFIG_FILE
    if path.exists():
        raw = {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if not k.startswith("_")}
        unknown = set(raw) - set(LLMSettings.__dataclass_fields__)
        if unknown:
            raise ValueError(f"{path}: unknown LLM setting(s) {sorted(unknown)}")
        s = replace(s, **raw)
    if s.api not in ("llama_server", "openai", "ollama"):
        raise ValueError("llm api must be llama_server, openai or ollama")
    if s.reasoning_effort not in EFFORTS:
        raise ValueError(f"reasoning_effort must be one of {EFFORTS} (Bonsai 2: 'low' is not supported, "
                         "'high' returns HTTP 500)")
    if s.reasoning_effort != "none" and s.max_tokens < 4096:
        raise ValueError("with reasoning on, max_tokens must be >= 4096 (16384 recommended): the reasoning "
                         "counts against the limit and a small cap returns an empty answer")
    return s


@dataclass(frozen=True)
class Reply:
    text: str                           # the answer (JSON expected)
    latency_ms: int
    model: str
    model_digest: str | None            # identity of the exact weights
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    reasoning: str = ""                 # thinking text, when reasoning is on
    raw: dict = field(default_factory=dict, repr=False)


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, settings: LLMSettings | None = None, transport=None, getter=None) -> None:
        self.s = settings or load_settings()
        self._post = transport or _http_post            # tests inject fakes
        self._get = getter or _http_get
        self._identity: str | None = None

    # ------------------------------------------------------------------ ask
    def ask(self, system: str, user: str, schema: dict | None = None) -> Reply:
        s = self.s
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        t0 = time.monotonic()
        if s.api == "ollama":
            body = {"model": s.model, "stream": False, "format": schema if (schema and s.json_schema) else "json",
                    "keep_alive": s.keep_alive, "messages": msgs,
                    "options": {"temperature": s.temperature, "top_p": s.top_p, "top_k": s.top_k,
                                "min_p": s.min_p, "presence_penalty": s.presence_penalty, "seed": s.seed,
                                "num_predict": s.max_tokens}}
            out = self._post(f"{s.url}/api/chat", body, s.timeout_s)
            msg = out.get("message") or {}
            text, reasoning = msg.get("content", ""), msg.get("thinking", "")
            ptok, otok = out.get("prompt_eval_count"), out.get("eval_count")
        else:
            body = {"model": s.model, "messages": msgs, "temperature": s.temperature, "top_p": s.top_p,
                    "seed": s.seed, "max_tokens": s.max_tokens, "presence_penalty": s.presence_penalty,
                    "stream": False}
            if s.api == "llama_server":
                body.update(top_k=s.top_k, min_p=s.min_p, reasoning_effort=s.reasoning_effort)
                if s.reasoning_effort == "none":
                    # The Bonsai chat template switches thinking off through enable_thinking
                    # (it raises on an unknown effort); "none" alone also works on this
                    # server, both are sent so either path closes the <think> block.
                    body["chat_template_kwargs"] = {"enable_thinking": False}
            if schema and s.json_schema:
                body["response_format"] = {"type": "json_schema",
                                           "json_schema": {"name": "decision", "strict": True, "schema": schema}}
            else:
                body["response_format"] = {"type": "json_object"}
            out = self._post(f"{s.url}/v1/chat/completions", body, s.timeout_s)
            choice = (out.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            text, reasoning = msg.get("content") or "", msg.get("reasoning_content") or ""
            usage = out.get("usage") or {}
            ptok, otok = usage.get("prompt_tokens"), usage.get("completion_tokens")
            if choice.get("finish_reason") == "length" and not text.strip():
                raise LLMError(f"the model used all {s.max_tokens} tokens without answering "
                               "(reasoning on? raise max_tokens or use reasoning_effort 'none'/'medium')")
        latency = int((time.monotonic() - t0) * 1000)
        if not text.strip():
            raise LLMError(f"empty answer from {s.api} at {s.url}")
        return Reply(text, latency, out.get("model", s.model), self.identity(), ptok, otok, reasoning, out)

    # ------------------------------------------------------------------ identity
    def identity(self) -> str | None:
        """Which exact weights answer: llama-server /props model file (+ size), Ollama digest."""
        if self._identity is not None:
            return self._identity
        try:
            if self.s.api == "ollama":
                for m in self._get(f"{self.s.url}/api/tags", 10).get("models", []):
                    if self.s.model in (m.get("name"), m.get("model")):
                        self._identity = m.get("digest")
            elif self.s.api == "llama_server":
                props = self._get(f"{self.s.url}/props", 10)
                path = props.get("model_path") or ""
                self._identity = Path(path.replace("\\", "/")).name or None
                if self._identity and props.get("build_info"):
                    self._identity += f" @ {props['build_info']}"
        except LLMError:
            return None
        return self._identity

    def ping(self) -> dict:
        """Server up? Which model? Used by ``python -m llm ping``."""
        s = self.s
        info: dict = {"api": s.api, "url": s.url, "model": s.model, "reasoning_effort": s.reasoning_effort}
        if s.api == "ollama":
            names = [m.get("name") for m in self._get(f"{s.url}/api/tags", 10).get("models", [])]
            info.update(models=names, model_available=s.model in names)
        else:
            if s.api == "llama_server":
                health = self._get(f"{s.url}/health", 10)
                info["health"] = health.get("status", health)
            models = [m.get("id") for m in self._get(f"{s.url}/v1/models", 10).get("data", [])]
            info.update(models=models, model_available=bool(models))
        info["identity"] = self.identity()
        return info


def _http_post(url: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise LLMError(f"{url}: HTTP {exc.code} {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise LLMError(f"{url}: {exc}") from exc


def _http_get(url: str, timeout: float) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise LLMError(f"{url}: {exc}") from exc
