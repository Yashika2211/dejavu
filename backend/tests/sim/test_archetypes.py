"""Every archetype is fair: its discriminators are observable, its alert fires, nothing leaks."""

import json

import pyarrow.parquet as pq
import pytest

from dejavu.agent.tools import execute
from dejavu.sim.checks import check_discriminators
from dejavu.sim.generators.alerts import alert_value
from dejavu.sim.generators.metrics import generate_metrics
from dejavu.sim.scenario import archetype_ids
from dejavu.taxonomy import RootCause
from tests.sim.cases import CASES, scenario_for

NOVEL = {"sms_quota_exhausted", "az_network_partition", "jwks_rotation_mismatch"}


def test_library_has_twelve_archetypes_and_three_novel() -> None:
    ids = set(archetype_ids())
    assert ids - NOVEL == {c.value for c in RootCause if c != RootCause.NOVEL}
    assert ids >= NOVEL
    for novel in NOVEL:
        assert scenario_for(novel, "2026-09-20T12:30").spec.category == RootCause.NOVEL


@pytest.mark.parametrize(("archetype", "when"), CASES)
def test_discriminators_are_observable_five_minutes_after_the_alert(archetype, when, open_world) -> None:
    world = open_world(scenario_for(archetype, when))
    world.clock.advance(5)
    failed = [(d.text, observed) for d, ok, observed in check_discriminators(world) if not ok]
    assert not failed, failed


@pytest.mark.parametrize(("archetype", "when"), CASES)
def test_alert_metric_really_crossed_its_threshold(archetype, when) -> None:
    scenario = scenario_for(archetype, when)
    assert alert_value(scenario, generate_metrics(scenario)) > scenario.spec.alert.threshold


@pytest.mark.parametrize(("archetype", "when"), CASES)
def test_archetype_identity_never_appears_in_telemetry_or_tools(
    archetype, when, open_world, telemetry_root
) -> None:
    scenario = scenario_for(archetype, when)
    world = open_world(scenario)
    directory = telemetry_root / scenario.incident_id
    corpus = [
        " ".join(pq.read_table(directory / "logs.parquet", columns=["line"]).column("line").to_pylist()),
        json.dumps(pq.read_table(directory / "spans.parquet", columns=["operation", "error"]).to_pylist()),
        (directory / "events.json").read_text(),
        (directory / "alert.json").read_text(),
    ]
    for service in {scenario.spec.culprit_service, scenario.spec.alert.service}:
        for tool, args in [("search_logs", {"service": service}), ("list_changes", {"window_hours": 72})]:
            corpus.append(execute(world, tool, args).output)
    text = "\n".join(corpus)
    assert archetype not in text
    assert scenario.spec.title not in text
    assert archetype not in scenario.incident_id


def test_every_discriminator_has_a_relevant_evidence_entry() -> None:
    for archetype in archetype_ids():
        spec = scenario_for(archetype, "2026-09-20T12:30").spec
        services = {e.service for e in spec.relevant_evidence}
        for d in spec.discriminators:
            if d.signal.kind in ("metric", "log", "trace"):
                assert d.signal.service in services, (archetype, d.text)
