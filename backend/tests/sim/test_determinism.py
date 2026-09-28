"""Same seed, byte-identical telemetry; different seed, different telemetry."""

import pytest

from dejavu.sim.schedule import gauntlet
from dejavu.sim.telemetry import content_hash, ensure_telemetry, fingerprint, write_telemetry
from tests.sim.cases import POST_M2, PRE, scenario_for


@pytest.mark.parametrize(
    ("archetype", "when"), [("db_pool_exhaustion", PRE), ("cache_stampede", POST_M2), ("cert_expiry", PRE)]
)
def test_same_seed_gives_byte_identical_telemetry(archetype, when, tmp_path) -> None:
    write_telemetry(scenario_for(archetype, when), tmp_path / "a")
    write_telemetry(scenario_for(archetype, when), tmp_path / "b")
    assert content_hash(tmp_path / "a") == content_hash(tmp_path / "b")


def test_different_seed_gives_different_telemetry(tmp_path) -> None:
    write_telemetry(scenario_for("db_pool_exhaustion", PRE, seed=42), tmp_path / "a")
    write_telemetry(scenario_for("db_pool_exhaustion", PRE, seed=7), tmp_path / "b")
    assert content_hash(tmp_path / "a") != content_hash(tmp_path / "b")


def test_instantiation_is_deterministic() -> None:
    first = [fingerprint(s) for s in gauntlet()]
    assert first == [fingerprint(s) for s in gauntlet()]
    assert first != [fingerprint(s) for s in gauntlet(seed=7)]
    assert [s.incident_id for s in gauntlet()] == [s.incident_id for s in gauntlet(seed=7)]


def test_cached_telemetry_is_reused_until_the_scenario_changes(tmp_path) -> None:
    scenario = scenario_for("retry_storm", PRE)
    directory = ensure_telemetry(scenario, tmp_path)
    before = (directory / "logs.parquet").stat().st_mtime_ns
    assert ensure_telemetry(scenario, tmp_path) == directory
    assert (directory / "logs.parquet").stat().st_mtime_ns == before
