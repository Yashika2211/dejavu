"""Remediation outcomes per archetype, driven through the real `run_remediation` tool."""

import numpy as np
import pytest

from dejavu.agent.tools import execute
from dejavu.sim.remediation import OutcomeKind
from dejavu.sim.scenario import RemediationRule
from dejavu.sim.topology import NODES
from dejavu.sim.world import IncidentWorld
from dejavu.taxonomy import Remediation
from tests.sim.cases import CASES, PRE, scenario_for

START = 5.0


def _target(world: IncidentWorld, rule: RemediationRule) -> str:
    if rule.targets:
        return rule.targets[0]
    if rule.action == Remediation.NODE_DRAIN:
        return NODES[0].name
    return (
        world.scenario.spec.culprit_service
        if world.topology.get(world.scenario.spec.culprit_service)
        else "ledger-svc"
    )


def _apply(world: IncidentWorld, rule: RemediationRule) -> None:
    world.clock.advance(START - world.clock.elapsed_min)
    result = execute(world, "run_remediation", {"action": rule.action.value, "target": _target(world, rule)})
    assert result.ok, result.output


def _k_after(world: IncidentWorld, minutes_after_completion: float) -> float:
    completes = world.interventions[-1].completes_at
    return float(world.k(np.array([completes + minutes_after_completion]))[0])


@pytest.mark.parametrize(("archetype", "when"), CASES)
def test_correct_remediations_recover_the_alert_metric(archetype, when, open_world) -> None:
    rules = scenario_for(archetype, when).spec.correct_remediations
    for rule in rules:
        world = open_world(scenario_for(archetype, when))
        _apply(world, rule)
        assert world.interventions[-1].kind == OutcomeKind.RESOLVES, rule
        resolved = world.resolved_at_min
        assert resolved is not None
        world.clock.advance(resolved + 2 - world.clock.elapsed_min)
        alert = world.scenario.spec.alert
        assert world.metric_at(alert.metric_service, alert.metric, world.now_min) < alert.threshold, rule


@pytest.mark.parametrize(("archetype", "when"), CASES)
def test_ineffective_remediations_never_resolve(archetype, when, open_world) -> None:
    for rule in scenario_for(archetype, when).spec.ineffective_remediations:
        world = open_world(scenario_for(archetype, when))
        _apply(world, rule)
        assert world.resolved_at_min is None, rule
        if rule.relief_minutes is not None:
            assert _k_after(world, rule.relief_minutes / 2) == pytest.approx(rule.depth)
            assert _k_after(world, rule.relief_minutes + 1) == pytest.approx(1.0), "the incident must relapse"
        elif rule.depth < 1:
            assert _k_after(world, 10) == pytest.approx(rule.depth)
        else:
            assert _k_after(world, 10) == pytest.approx(1.0)


@pytest.mark.parametrize(("archetype", "when"), CASES)
def test_harmful_remediations_make_things_worse_and_delay_recovery(archetype, when, open_world) -> None:
    spec = scenario_for(archetype, when).spec
    for rule in spec.harmful_remediations:
        world = open_world(scenario_for(archetype, when))
        _apply(world, rule)
        assert world.interventions[-1].kind == OutcomeKind.HARMFUL
        assert _k_after(world, 1) > 1.0, rule
        if not spec.correct_remediations:
            continue
        fix = spec.correct_remediations[0]
        execute(world, "run_remediation", {"action": fix.action.value, "target": _target(world, fix)})
        harmed = world.resolved_at_min
        clean = open_world(scenario_for(archetype, when))
        _apply(clean, fix)
        harm = world.interventions[0]
        assert harmed is not None
        assert clean.resolved_at_min is not None
        assert harmed >= harm.completes_at + rule.consequence_minutes, "recovery waits out the consequence"
        assert harmed >= clean.resolved_at_min, "a harmful detour never speeds recovery up"


def test_unlisted_actions_have_no_effect(open_world) -> None:
    world = open_world(scenario_for("db_pool_exhaustion", PRE))
    result = execute(world, "run_remediation", {"action": "cert_rotation", "target": "ledger-svc"})
    assert result.ok
    assert world.interventions[-1].kind == OutcomeKind.NO_EFFECT
    assert world.resolved_at_min is None


def test_remediating_a_component_that_no_longer_exists_costs_little_and_does_nothing(open_world) -> None:
    world = open_world(scenario_for("cache_stampede", "2026-09-20T12:30"))
    result = execute(world, "run_remediation", {"action": "cache_warmup", "target": "redis-cache"})
    assert not result.ok  # redis-cache was replaced by valkey-cache on 10 Sep
    assert "valkey-cache" in result.output
    assert world.clock.elapsed_min == pytest.approx(0.25)
    assert world.interventions == []


def test_novel_archetypes_without_a_fix_stay_broken_until_a_human_steps_in(open_world) -> None:
    world = open_world(scenario_for("sms_quota_exhausted", PRE))
    result = execute(world, "page_human", {"team": "Messaging", "message": "smsbridge quota exhausted"})
    assert result.ends_run
    assert result.sim_minutes == 10
    assert world.resolved_at_min is None


def test_impact_stops_accruing_once_resolved(open_world) -> None:
    world = open_world(scenario_for("db_pool_exhaustion", PRE))
    _apply(world, scenario_for("db_pool_exhaustion", PRE).spec.correct_remediations[0])
    resolved = world.resolved_at_min
    assert resolved is not None
    assert world.inr_at_risk(resolved + 30) == pytest.approx(world.inr_at_risk(resolved), rel=1e-6)
    assert world.inr_at_risk(resolved) > world.inr_at_risk(0) > 0
