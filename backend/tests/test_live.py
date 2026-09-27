"""Checks against the real Groq and Hindsight endpoints. Skipped when keys are missing."""

import pytest

from dejavu.config import get_settings
from dejavu.health import run_checks

pytestmark = pytest.mark.live


async def test_dependencies_reachable_with_configured_keys() -> None:
    results = {r.name: r for r in await run_checks(get_settings())}
    assert results["groq"].ok, results["groq"].detail
    assert results["hindsight"].ok, results["hindsight"].detail
