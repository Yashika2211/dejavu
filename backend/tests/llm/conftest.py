"""Fixtures wiring the scripted Groq into a real LLMClient."""

from typing import Any

import httpx2
import pytest

from dejavu.config import Settings
from dejavu.llm.client import CallRecord, LLMClient
from dejavu.llm.ratelimit import Limits, RateLimiters
from tests.llm.fakegroq import NoWait, ScriptedGroq


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
