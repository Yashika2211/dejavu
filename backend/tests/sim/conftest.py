"""Shared simulator fixtures: telemetry is generated once per test session into a temp dir."""

from collections.abc import Callable
from pathlib import Path

import pytest

from dejavu.sim.scenario import Scenario
from dejavu.sim.world import IncidentWorld


@pytest.fixture(scope="session")
def telemetry_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("incidents")


@pytest.fixture
def open_world(telemetry_root: Path) -> Callable[[Scenario], IncidentWorld]:
    """Fresh world (clock at the alert, no interventions) over session-cached telemetry."""
    return lambda scenario: IncidentWorld.open(scenario, telemetry_root)
