"""Shared fixtures. Tests marked `live` are skipped unless real API keys are configured."""

import pytest

from dejavu.config import Settings, get_settings


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
