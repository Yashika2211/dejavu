"""A scripted Groq: queue HTTP responses for the OpenAI SDK's httpx2 transport."""

import json
from collections.abc import Callable
from typing import Any

import httpx2
import pytest

from dejavu.config import Settings
from dejavu.llm.client import CallRecord, LLMClient
from dejavu.llm.ratelimit import Limits, RateLimiters


def completion(
    content: str | None = None,
    tool_calls: list[tuple[str, dict]] | None = None,
    *,
    model: str = "openai/gpt-oss-120b",
    tokens: tuple[int, int] = (100, 20),
) -> dict[str, Any]:
    """An OpenAI-style chat completion body."""
    calls = [
        {"id": f"call_{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
        for i, (name, args) in enumerate(tool_calls or [])
    ]
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls" if calls else "stop",
                "message": {"role": "assistant", "content": content, "tool_calls": calls or None},
            }
        ],
        "usage": {"prompt_tokens": tokens[0], "completion_tokens": tokens[1], "total_tokens": sum(tokens)},
    }


def groq_error(status: int, code: str, message: str = "error", **extra: Any) -> httpx2.Response:
    return httpx2.Response(
        status, json={"error": {"message": message, "type": "invalid_request_error", "code": code, **extra}}
    )


class ScriptedGroq:
    """Responds to each request with the next queued response; records requests."""

    def __init__(self) -> None:
        self.queue: list[httpx2.Response | Callable[[httpx2.Request], httpx2.Response]] = []
        self.requests: list[dict[str, Any]] = []

    def add(self, *responses: httpx2.Response | dict[str, Any]) -> "ScriptedGroq":
        for r in responses:
            self.queue.append(httpx2.Response(200, json=r) if isinstance(r, dict) else r)
        return self

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(json.loads(request.content) if request.content else {})
        if not self.queue:
            raise AssertionError("no scripted response left")
        nxt = self.queue.pop(0)
        return nxt(request) if callable(nxt) else nxt


class NoWait:
    """Fake time: sleeping returns immediately but moves the clock forward."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture
def groq() -> ScriptedGroq:
    return ScriptedGroq()


@pytest.fixture
def records() -> list[CallRecord]:
    return []


@pytest.fixture
def make_client(groq: ScriptedGroq, records: list[CallRecord]):
    def build(**kwargs: Any) -> tuple[LLMClient, NoWait]:
        waits = NoWait()
        settings = Settings(
            _env_file=None, groq_api_key="test-key", groq_base_url="https://groq.test/openai/v1"
        )
        http = httpx2.AsyncClient(transport=httpx2.MockTransport(groq.handler))
        limiters = RateLimiters(Limits(1000, 10_000_000, 100_000), clock=waits.clock, sleep=waits.sleep)
        client = LLMClient(
            settings, http_client=http, limiters=limiters, sleep=waits.sleep, on_call=records.append, **kwargs
        )
        return client, waits

    return build
