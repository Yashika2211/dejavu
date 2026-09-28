"""Groq chat completions through the OpenAI SDK, with our own retry policy and call accounting.

The SDK's built-in retries are off (`max_retries=0`); this client decides what to retry:
429s honour `retry-after` (and pause the model's rate limiter) unless it is beyond `max_wait_s`,
as with a daily cap, which raises `QuotaExhaustedError` instead of sleeping for hours. 5xx and
connection errors back off exponentially with jitter. Errors only the caller can fix are raised as typed exceptions:
tool_use_failed (repair or re-prompt), 413 / context length (trim), unknown model (fall back).
Every call, successful or not, is reported to `on_call` for the run trace.
"""

import asyncio
import json
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx2
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    BadRequestError,
    RateLimitError,
)

from dejavu.config import Settings
from dejavu.llm.errors import (
    ContextTooLongError,
    LLMError,
    ModelUnavailableError,
    QuotaExhaustedError,
    RetriesExhaustedError,
    ToolUseFailedError,
)
from dejavu.llm.pricing import cost_usd
from dejavu.llm.ratelimit import Limits, RateLimiters
from dejavu.tokens import count_tokens

RETRYABLE_STATUS = {500, 502, 503, 504}


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON text, validated by the caller


@dataclass(frozen=True)
class LLMResponse:
    model: str
    content: str | None
    tool_calls: list[ToolCall]
    tokens_in: int
    tokens_out: int
    latency_s: float
    retries: int
    finish_reason: str | None


@dataclass(frozen=True)
class CallRecord:
    """One HTTP call to the model, as the run trace records it."""

    model: str
    purpose: str
    tokens_in: int
    tokens_out: int
    latency_s: float
    retries: int
    cost_usd: float
    error: str | None = None


@dataclass
class _Attempt:
    retries: int = 0
    errors: list[str] = field(default_factory=list)


def _error_body(exc: APIStatusError) -> dict[str, Any]:
    body = exc.body if isinstance(exc.body, dict) else {}
    inner = body.get("error", body)
    return inner if isinstance(inner, dict) else {}


def _retry_after(response: httpx2.Response | None) -> float | None:
    if response is None:
        return None
    for header in ("retry-after", "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"):
        raw = response.headers.get(header)
        if raw:
            try:
                return float(raw.rstrip("s"))
            except ValueError:
                continue
    return None


class LLMClient:
    """Async chat-completions client for Groq's OpenAI-compatible API."""

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx2.AsyncClient | None = None,
        limiters: RateLimiters | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        on_call: Callable[[CallRecord], None] | None = None,
        max_attempts: int = 6,
        max_wait_s: float = 120.0,
        rng: random.Random | None = None,
    ) -> None:
        api_key = settings.groq_api_key.get_secret_value() if settings.groq_api_key else "missing"
        self._openai = AsyncOpenAI(
            api_key=api_key,
            base_url=settings.groq_base_url,
            max_retries=0,
            timeout=settings.llm_timeout_s,
            http_client=http_client,
        )
        self._settings = settings
        self._limiters = limiters or RateLimiters(
            Limits(settings.llm_rpm, settings.llm_tpm, settings.llm_rpd)
        )
        self._sleep = sleep
        self._on_call = on_call or (lambda _record: None)
        self._max_attempts = max_attempts
        self._max_wait_s = max_wait_s
        self._rng = rng or random.Random()
        self.calls: list[CallRecord] = []  # every call, for per-run accounting

    async def available_models(self) -> set[str]:
        """Ids of the models this key can use right now (inactive ones excluded)."""
        page = await self._openai.models.list()
        return {m.id for m in page.data if (m.model_extra or {}).get("active", True)}

    def _backoff(self, attempt: int) -> float:
        base = min(30.0, 2.0**attempt)
        return base / 2 + self._rng.uniform(0, base / 2)

    def _record(
        self,
        model: str,
        purpose: str,
        *,
        tin: int = 0,
        tout: int = 0,
        latency: float = 0.0,
        retries: int = 0,
        error: str | None = None,
    ) -> None:
        record = CallRecord(
            model,
            purpose,
            tin,
            tout,
            round(latency, 3),
            retries,
            cost_usd(model, tin, tout, self._settings),
            error,
        )
        self.calls.append(record)
        self._on_call(record)

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1200,
        response_format: dict[str, Any] | None = None,
        reasoning_effort: str | None = None,
        purpose: str = "agent",
    ) -> LLMResponse:
        """One chat completion, retried on rate limits and server errors."""
        estimate = count_tokens(json.dumps(messages)) + max_tokens
        state = _Attempt()
        limiter = self._limiters.for_model(model)
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice or "auto"
            if model.startswith("qwen/"):
                kwargs["extra_body"] = {"reasoning_format": "hidden"}
        if response_format:
            kwargs["response_format"] = response_format
        if reasoning_effort and model.startswith("openai/gpt-oss"):
            kwargs["reasoning_effort"] = reasoning_effort

        while True:
            await limiter.acquire(estimate)
            start = time.perf_counter()
            try:
                resp = await self._openai.chat.completions.create(**kwargs)
            except RateLimitError as exc:
                wait = _retry_after(exc.response) or self._backoff(state.retries)
                if wait > self._max_wait_s:
                    self._record(model, purpose, retries=state.retries, error=f"429 retry-after {wait:g}s")
                    raise QuotaExhaustedError(model, wait) from exc
                limiter.pause(wait)
                await self._retry_or_raise(model, purpose, state, f"429 retry-after {wait:g}s")
                continue
            except BadRequestError as exc:
                body = _error_body(exc)
                code = str(body.get("code", ""))
                self._record(model, purpose, retries=state.retries, error=f"400 {code}")
                if code == "tool_use_failed":
                    raise ToolUseFailedError(model, str(body.get("failed_generation", ""))) from exc
                if "context" in code or "too long" in str(body.get("message", "")).lower():
                    raise ContextTooLongError(str(body.get("message", code))) from exc
                if code in {"model_not_found", "model_decommissioned"}:
                    raise ModelUnavailableError(f"{model}: {code}") from exc
                raise LLMError(f"{model}: 400 {body.get('message', code)}") from exc
            except APIStatusError as exc:
                if exc.status_code == 413:
                    self._record(model, purpose, retries=state.retries, error="413")
                    raise ContextTooLongError(f"{model}: request too large") from exc
                if exc.status_code == 404:
                    self._record(model, purpose, retries=state.retries, error="404")
                    raise ModelUnavailableError(f"{model}: not found") from exc
                if exc.status_code in RETRYABLE_STATUS:
                    await self._retry_or_raise(model, purpose, state, f"{exc.status_code}")
                    await self._sleep(self._backoff(state.retries))
                    continue
                self._record(model, purpose, retries=state.retries, error=str(exc.status_code))
                raise LLMError(f"{model}: HTTP {exc.status_code}") from exc
            except (APIConnectionError, APITimeoutError) as exc:
                await self._retry_or_raise(model, purpose, state, type(exc).__name__)
                await self._sleep(self._backoff(state.retries))
                continue

            latency = time.perf_counter() - start
            choice = resp.choices[0]
            message = choice.message
            calls = [
                ToolCall(tc.id, tc.function.name, tc.function.arguments or "{}")
                for tc in (message.tool_calls or [])
                if getattr(tc, "function", None) is not None
            ]
            tin = resp.usage.prompt_tokens if resp.usage else 0
            tout = resp.usage.completion_tokens if resp.usage else 0
            self._record(model, purpose, tin=tin, tout=tout, latency=latency, retries=state.retries)
            return LLMResponse(
                model, message.content, calls, tin, tout, latency, state.retries, choice.finish_reason
            )

    async def _retry_or_raise(self, model: str, purpose: str, state: _Attempt, error: str) -> None:
        state.retries += 1
        state.errors.append(error)
        self._record(model, purpose, retries=state.retries, error=error)
        if state.retries >= self._max_attempts:
            raise RetriesExhaustedError(
                f"{model}: gave up after {state.retries} attempts ({', '.join(state.errors)})"
            )
