"""Shared simulator fixtures: telemetry is generated once per test session into a temp dir."""

from collections.abc import Callable
from pathlib import Path

import pytest

from dejavu.sim.clock import ist
from dejavu.sim.rng import stable_hash
from dejavu.sim.scenario import Scenario, archetype_ids, instantiate
from dejavu.sim.world import IncidentWorld

PRE = "2026-08-26T20:10"  # before both migrations
POST_M1 = "2026-09-07T12:30"  # PgBouncer in place, still Redis
POST_M2 = "2026-09-20T12:30"  # after both migrations

MIGRATION_SENSITIVE = {"db_pool_exhaustion", "missing_index_slow_query", "cache_stampede"}

CASES = [(a, PRE) for a in archetype_ids()] + [(a, POST_M2) for a in archetype_ids()]
CASES += [(a, POST_M1) for a in sorted(MIGRATION_SENSITIVE)]


def scenario_for(archetype: str, when: str, seed: int = 42) -> Scenario:
    incident_id = f"INC-{9000 + stable_hash(archetype, when, seed) % 999}"
    return instantiate(archetype, seed=seed, incident_id=incident_id, alert_at=ist(when))


@pytest.fixture(scope="session")
def telemetry_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("incidents")


@pytest.fixture
def open_world(telemetry_root: Path) -> Callable[[Scenario], IncidentWorld]:
    """Fresh world (clock at the alert, no interventions) over session-cached telemetry."""
    return lambda scenario: IncidentWorld.open(scenario, telemetry_root)
