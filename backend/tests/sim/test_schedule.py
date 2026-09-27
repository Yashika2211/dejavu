"""The Gauntlet schedule matches the spec: order, migrations, pinned versions, edge cases."""

import re

import pytest

from dejavu.sim.generators.logs import INJECTION_TEXT
from dejavu.sim.migrations import Phase
from dejavu.sim.scenario import ChangeType, EventEffect
from dejavu.sim.schedule import entry_for, gauntlet, held_out, load_schedule


@pytest.fixture(scope="module")
def incidents():
    return {entry_for(s).n: s for s in gauntlet()}


def test_twenty_four_incidents_in_time_order_with_unique_opaque_ids(incidents) -> None:
    ordered = [incidents[n] for n in range(1, 25)]
    assert [s.alert_at for s in ordered] == sorted(s.alert_at for s in ordered)
    ids = [s.incident_id for s in ordered]
    assert len(set(ids)) == 24
    assert all(re.fullmatch(r"INC-\d{4}", i) for i in ids)
    assert ids[0] == "INC-4127"


def test_migrations_split_the_schedule(incidents) -> None:
    assert Phase.PRE_M1 in incidents[10].phases
    assert Phase.POST_M1 in incidents[11].phases
    assert Phase.PRE_M2 in incidents[11].phases
    assert Phase.POST_M1 in incidents[12].phases
    assert Phase.POST_M2 in incidents[14].phases
    assert incidents[11].spec.culprit_service == "redis-cache"
    assert incidents[14].spec.culprit_service == "valkey-cache"


def _trigger(scenario) -> EventEffect:
    return next(e for e in scenario.spec.effects if isinstance(e, EventEffect) and e.trigger)


@pytest.mark.parametrize(("n", "version"), [(1, "3.14.0"), (5, "3.15.1"), (21, "3.19.0")])
def test_pinned_ledger_versions(incidents, n, version) -> None:
    assert _trigger(incidents[n]).details["version"] == version


@pytest.mark.parametrize(("n", "model"), [(4, "v47"), (15, "v52")])
def test_pinned_model_versions(incidents, n, model) -> None:
    trigger = _trigger(incidents[n])
    assert trigger.type == ChangeType.MODEL_RELEASE
    assert trigger.details["version"] == model


def test_incident_sixteen_carries_the_security_edge_cases(incidents, open_world) -> None:
    scenario = incidents[16]
    assert set(scenario.extras) == {"prompt_injection", "leaked_token"}
    world = open_world(scenario)
    world.clock.advance(5)
    edge = " ".join(line.line for line in world.logs("edge-gateway", 30))
    auth = " ".join(line.line for line in world.logs("auth-svc", 60))
    assert INJECTION_TEXT in edge
    assert re.search(r"Bearer eyJ[\w-]+\.eyJ[\w-]+\.[\w-]+", auth)


def test_foresight_checkpoints_precede_incidents_twenty_and_twenty_one() -> None:
    flagged = {e.n for e in load_schedule().incidents if e.foresight_checkpoint}
    assert flagged == {20, 21}


def test_held_out_set_is_fresh() -> None:
    gauntlet_ids = {s.incident_id for s in gauntlet()}
    held = held_out()
    assert len(held) == 6
    assert not gauntlet_ids & {s.incident_id for s in held}
    assert min(s.alert_at for s in held) > max(s.alert_at for s in gauntlet())
    assert "jwks_rotation_mismatch" in {s.spec.id for s in held}
    assert "jwks_rotation_mismatch" not in {s.spec.id for s in gauntlet()}
