"""Unit tests for the simulator's small pure pieces."""

from datetime import date

import numpy as np
import pytest

from dejavu.sim.analysis import change_point, sparkline
from dejavu.sim.clock import SimClock, ist
from dejavu.sim.logmine import mine, template_of
from dejavu.sim.releases import model_version_at, previous_version, version_at
from dejavu.sim.rng import np_rng, stable_hash
from dejavu.sim.runbooks import all_runbooks, find
from dejavu.sim.scenario import VarSpec, _fill
from dejavu.sim.topology import topology_at


def test_stable_hash_and_streams_are_reproducible() -> None:
    assert stable_hash("a", 1) == stable_hash("a", 1) != stable_hash("a", 2)
    assert np.array_equal(np_rng(42, "x").random(5), np_rng(42, "x").random(5))


def test_clock_only_moves_forward() -> None:
    clock = SimClock(ist("2026-08-17T03:07"))
    clock.advance(2.5)
    assert clock.now == ist("2026-08-17T03:09:30")
    with pytest.raises(ValueError, match="backwards"):
        clock.advance(-1)


def test_release_calendars_hit_the_pinned_versions() -> None:
    assert version_at("ledger-svc", date(2026, 8, 17)) == "3.14.0"
    assert version_at("ledger-svc", date(2026, 9, 21)) == "3.19.0"
    assert (
        previous_version("ledger-svc", date(2026, 8, 17))
        == version_at("ledger-svc", date(2026, 8, 16))
        == "3.13.3"
    )
    assert (
        previous_version("ledger-svc", date(2026, 8, 27)) == "3.15.0"
    )  # same version the day before: one patch back
    assert (model_version_at(date(2026, 8, 22)), model_version_at(date(2026, 9, 12))) == (47, 52)


def test_topology_follows_the_migrations() -> None:
    before, after_m1, after_m2 = (
        topology_at(ist(d)) for d in ("2026-09-02T12:00", "2026-09-05T12:00", "2026-09-11T12:00")
    )
    assert before.pool_max == 20
    assert before.get("pgbouncer-ledger") is None
    assert after_m1.pool_max == 10
    assert "pgbouncer-ledger" in after_m1.components["ledger-svc"].depends_on
    assert after_m2.cache == "valkey-cache"
    assert after_m2.get("redis-cache") is None
    assert "valkey-cache" in after_m2.components["auth-svc"].depends_on


def test_placeholders_support_offsets_and_keep_types() -> None:
    filled = _fill(
        {"a": "{{onset - 3}}", "b": "v{{version}}", "c": ["{{n}}"]}, {"onset": -10, "version": "3.1", "n": 4}
    )
    assert filled == {"a": -13, "b": "v3.1", "c": [4]}


def test_var_spec_needs_exactly_one_generator() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        VarSpec(randint=(1, 2), hex=4)


def test_change_point_finds_a_level_shift_and_ignores_noise() -> None:
    rng = np.random.default_rng(0)
    assert change_point(100 + rng.normal(0, 2, 60)) is None
    shift = np.r_[rng.normal(0, 0.5, 40), 140 + rng.normal(0, 5, 20)]
    cp = change_point(shift)
    assert cp is not None
    assert 38 <= cp.index <= 41
    assert cp.after > 100


def test_sparkline_keeps_noise_flat() -> None:
    assert set(sparkline(np.full(60, 50.0))) == {sparkline(np.full(60, 50.0))[0]}
    assert sparkline(np.r_[np.zeros(30), np.full(30, 10.0)])[-1] == "█"


def test_log_templates_mask_variables_but_keep_meaning() -> None:
    a = template_of("HikariPool-1 - Connection is not available (total=20, active=20, idle=0, waiting=143)")
    b = template_of("HikariPool-1 - Connection is not available (total=20, active=20, idle=0, waiting=97)")
    assert a == b
    ok = template_of('"POST /v1/checkout HTTP/2" 200 - 0 1893 212 199 "49.36.112.18"')
    failed = template_of('"POST /v1/checkout HTTP/2" 503 - 0 1893 212 199 "49.36.112.18"')
    assert ok != failed


def test_mine_groups_and_orders_by_count() -> None:
    rows = [(1.0, "WARN", f"waiting={n}", f"line {n}") for n in range(5)] + [(2.0, "INFO", "ok", "ok")]
    templates = mine(rows)
    assert templates[0].count == 5
    assert templates[0].first_s == 1.0
    assert templates[0].example == "line 4"


def test_runbooks_load_and_match_topics() -> None:
    assert len(all_runbooks()) == 8
    assert find("hikari pool saturation").id == "RB-ledger-pool"
    assert find("status page 429 acquirerx").id == "RB-psp-degradation"
    assert find("nothing relevant at all") is None
