"""Shared fixtures: settings, a scripted Groq wired into a real LLMClient, simulated worlds.

Tests marked `live` are skipped unless real API keys are configured.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2
import pytest

from dejavu.config import Settings, get_settings
from dejavu.llm.client import CallRecord, LLMClient
from dejavu.llm.ratelimit import Limits, RateLimiters
from dejavu.sim.scenario import Scenario
from dejavu.sim.world import IncidentWorld
from tests.llm.fakegroq import NoWait, ScriptedGroq


@pytest.fixture
def settings() -> Settings:
    """Settings isolated from the developer's `.env`, with dummy keys."""
    return Settings(
        _env_file=None,
        groq_api_key="test-groq-key",
        hindsight_api_key="test-hindsight-key",
        hindsight_base_url="https://hindsight.test",
        groq_base_url="https://groq.test/openai/v1",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    real = get_settings()
    if real.groq_api_key and real.hindsight_api_key:
        return
    skip = pytest.mark.skip(reason="live test: GROQ_API_KEY and HINDSIGHT_API_KEY not set")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def groq() -> ScriptedGroq:
    return ScriptedGroq()


@pytest.fixture
def records() -> list[CallRecord]:
    return []


@pytest.fixture
def make_client(groq: ScriptedGroq, records: list[CallRecord]) -> Callable[..., tuple[LLMClient, NoWait]]:
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


@pytest.fixture(scope="session")
def telemetry_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("incidents")


@pytest.fixture
def open_world(telemetry_root: Path) -> Callable[[Scenario], IncidentWorld]:
    """Fresh world (clock at the alert, no interventions) over session-cached telemetry."""
    return lambda scenario: IncidentWorld.open(scenario, telemetry_root)
