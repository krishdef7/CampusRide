"""Provider-agnostic chat model with forced tool calling, response caching and usage/cost accounting."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sqlite3
import threading
import time
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, messages_from_dict, messages_to_dict

from campusride.config import Settings
from campusride.observability import LLM_CALLS, LLM_COST, LLM_LATENCY, LLM_TOKENS, get_logger, span

log = get_logger(__name__)

# USD per 1M tokens (input, output). List prices at time of writing; edit as they change.
PRICES: dict[str, tuple[float, float]] = {
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "llama-3.1-8b-instant": (0.05, 0.08),
}


def price_for(model: str) -> tuple[float, float]:
    for k in sorted(PRICES, key=len, reverse=True):
        if model.startswith(k) or k in model:
            return PRICES[k]
    return (0.0, 0.0)


@dataclass
class LLMResult:
    message: AIMessage
    input_tokens: int
    output_tokens: int
    latency_s: float
    cached: bool
    cost_usd: float
    wait_s: float = 0.0  # client-side rate limiting, failed attempts and backoff (not model latency)


def _signature_preserving_chat_openai():
    """ChatOpenAI that round-trips provider `extra_content` on tool calls.

    Gemini 3 / Gemma 4 on Google's OpenAI-compatible endpoint attach a `thought_signature` to every
    tool call and reject the next request (e.g. a self-repair turn) if it isn't sent back.
    langchain_openai drops unknown fields, so stash them on the AIMessage and re-inject them.
    """
    from langchain_openai import ChatOpenAI

    class _ChatOpenAI(ChatOpenAI):
        def _create_chat_result(self, response, generation_info=None):
            result = super()._create_chat_result(response, generation_info)
            raw = response if isinstance(response, dict) else response.model_dump()
            for gen, choice in zip(result.generations, raw.get("choices") or [], strict=False):
                extra = {tc["id"]: tc["extra_content"] for tc in (choice["message"].get("tool_calls") or [])
                         if tc.get("extra_content")}
                if extra:
                    gen.message.additional_kwargs["tool_call_extra_content"] = extra
            return result

        def _get_request_payload(self, input_, *, stop=None, **kwargs):
            payload = super()._get_request_payload(input_, stop=stop, **kwargs)
            messages = self._convert_input(input_).to_messages()
            for src, out in zip(messages, payload.get("messages", []), strict=False):
                extra = src.additional_kwargs.get("tool_call_extra_content") if isinstance(src, AIMessage) else None
                if extra:
                    out.pop("tool_call_extra_content", None)
                    for tc in out.get("tool_calls") or []:
                        if tc["id"] in extra:
                            tc["extra_content"] = extra[tc["id"]]
            return payload

    return _ChatOpenAI


def build_chat_model(settings: Settings, tools: list) -> BaseChatModel:
    """Bind tools with tool_choice='any' so every turn produces exactly one structured tool call."""
    if settings.llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        base = ChatAnthropic(model=settings.llm_model, api_key=settings.llm_api_key, temperature=0,
                             timeout=settings.llm_timeout_s, max_retries=0, max_tokens=512)
        return base.bind_tools(tools, tool_choice="any")
    if settings.llm_provider == "openai":
        ChatOpenAI = _signature_preserving_chat_openai()
        kwargs = dict(model=settings.llm_model, temperature=0, timeout=settings.llm_timeout_s, max_retries=0)
        if settings.llm_api_key:
            kwargs["api_key"] = settings.llm_api_key
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
        base = ChatOpenAI(**kwargs)
        extra = {} if settings.llm_base_url and "googleapis" in settings.llm_base_url else {"parallel_tool_calls": False}
        return base.bind_tools(tools, tool_choice="required", **extra)
    raise ValueError(f"unknown llm_provider {settings.llm_provider!r}")


class ResponseCache:
    """SQLite cache keyed on (model, messages, tools). Makes eval re-runs deterministic and free."""

    def __init__(self, path: str):
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
        self._lock = threading.Lock()

    def get(self, key: str) -> dict | None:
        with self._lock:
            row = self._db.execute("SELECT v FROM cache WHERE k = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, value: dict) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO cache VALUES (?, ?)", (key, json.dumps(value)))
            self._db.commit()


_RETRYABLE = re.compile(r"429|RESOURCE_EXHAUSTED|rate.?limit|503|UNAVAILABLE|overloaded|high demand|500|INTERNAL|timed? ?out|APIConnectionError|Connection error", re.I)


class _RateLimiter:
    """Spaces request starts at least 60/rpm seconds apart (free-tier quotas are per minute)."""

    def __init__(self, rpm: float):
        self.interval = 60.0 / rpm if rpm > 0 else 0.0
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        if not self.interval:
            return
        async with self._lock:
            now = time.monotonic()
            delay = self._next - now
            self._next = max(now, self._next) + self.interval
        if delay > 0:
            await asyncio.sleep(delay)


class LLMClient:
    def __init__(self, settings: Settings, tools: list, model: BaseChatModel | None = None):
        self.model_name = settings.llm_model
        self.model = model or build_chat_model(settings, tools)
        self.limiter = _RateLimiter(settings.llm_rpm)
        self.max_attempts = max(1, settings.llm_max_attempts)
        self.cache = ResponseCache(settings.llm_cache_path) if settings.llm_cache_path else None
        self._tools_sig = json.dumps([t.model_json_schema() for t in tools], sort_keys=True)

    def _key(self, messages: list[BaseMessage]) -> str:
        # LangGraph assigns every message a fresh random id, so ids must not be part of the key.
        msgs = [{**m, "data": {k: v for k, v in m["data"].items() if k != "id"}} for m in messages_to_dict(messages)]
        blob = json.dumps([self.model_name, msgs, self._tools_sig], sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()

    async def ainvoke(self, messages: list[BaseMessage]) -> LLMResult:
        key = self._key(messages) if self.cache else None
        if self.cache and (hit := self.cache.get(key)):
            msg = messages_from_dict([hit["message"]])[0]
            return LLMResult(msg, hit["in"], hit["out"], hit["latency"], True, hit["cost"])

        with span("llm.chat", **{"gen_ai.request.model": self.model_name, "gen_ai.operation.name": "chat"}) as s:
            msg, latency, wait = await self._call_with_retry(messages)
            usage = msg.usage_metadata or {}
            tin, tout = int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
            pin, pout = price_for(self.model_name)
            cost = (tin * pin + tout * pout) / 1e6
            s.set_attribute("gen_ai.usage.input_tokens", tin)
            s.set_attribute("gen_ai.usage.output_tokens", tout)

        LLM_CALLS.labels(self.model_name, "ok").inc()
        LLM_LATENCY.labels(self.model_name).observe(latency)
        LLM_TOKENS.labels(self.model_name, "input").inc(tin)
        LLM_TOKENS.labels(self.model_name, "output").inc(tout)
        LLM_COST.labels(self.model_name).inc(cost)
        if self.cache:
            self.cache.put(key, {"message": messages_to_dict([msg])[0], "in": tin, "out": tout, "latency": latency, "cost": cost})
        return LLMResult(msg, tin, tout, latency, False, cost, wait)

    async def _call_with_retry(self, messages: list[BaseMessage]) -> tuple[AIMessage, float, float]:
        """Returns (message, latency of the successful attempt, time lost to rate limits / retries)."""
        start = time.perf_counter()
        for attempt in range(1, self.max_attempts + 1):
            await self.limiter.wait()
            t0 = time.perf_counter()
            try:
                msg = await self.model.ainvoke(messages)
                return msg, time.perf_counter() - t0, t0 - start
            except Exception as e:
                LLM_CALLS.labels(self.model_name, "error").inc()
                if attempt == self.max_attempts or not _RETRYABLE.search(str(e)):
                    raise
                hint = re.search(r"retry in ([\d.]+)s|retryDelay['\": ]+(\d+)s", str(e))
                delay = float(next(g for g in hint.groups() if g)) if hint else min(60.0, 2.0 ** attempt)
                log.warning("llm_retry", model=self.model_name, attempt=attempt, delay_s=round(delay, 1),
                            error=f"{type(e).__name__}: {e}"[:200])
                await asyncio.sleep(delay + 0.5)
        raise AssertionError("unreachable")
