"""Remediation engine: how the world responds to an action.

An action takes simulated minutes. When it completes, the archetype's rules decide what it does to
the incident's severity k(t), where 1 is the incident at full strength and 0 is recovered:

    resolves   k eases to 0 over `recovery_minutes` (never before harmful consequences end)
    transient  k x depth for `relief_minutes`, then the incident relapses
    partial    k x depth from then on
    no_effect  nothing changes
    harmful    k x worsen (for `worsen_minutes`, or until resolved); recovery waits out
               `consequence_minutes`

Telemetry keeps the incident as a separate layer, so every query simply scales it by k(t).
Once an incident has recovered, later actions no longer change telemetry (the grader still counts
harmful ones).
"""

from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np

from dejavu.sim.scenario import RemediationRule, Scenario
from dejavu.sim.topology import NODES, Topology
from dejavu.taxonomy import Remediation

ACTION_MINUTES: dict[Remediation, float] = {
    Remediation.FLAG_REVERT: 1,
    Remediation.PSP_FAILOVER: 2,
    Remediation.SCALE_OUT: 3,
    Remediation.POOL_TUNING: 3,
    Remediation.CONFIG_TUNING: 3,
    Remediation.CACHE_WARMUP: 3,
    Remediation.RESTART: 4,
    Remediation.LIMITS_REVERT: 4,
    Remediation.CERT_ROTATION: 5,
    Remediation.ROLLBACK: 6,
    Remediation.NODE_DRAIN: 6,
    Remediation.WAL_CLEANUP: 8,
    Remediation.ADD_INDEX: 15,
}
INVALID_TARGET_MINUTES = 0.5


class OutcomeKind(StrEnum):
    RESOLVES = "resolves"
    TRANSIENT = "transient"
    PARTIAL = "partial"
    NO_EFFECT = "no_effect"
    HARMFUL = "harmful"
    INVALID = "invalid"


@dataclass(frozen=True)
class Intervention:
    """One applied action and what it did."""

    action: Remediation
    target: str
    params: dict[str, str]
    started_at: float
    completes_at: float
    kind: OutcomeKind
    rule: RemediationRule | None = field(default=None, compare=False)

    @property
    def note(self) -> str:
        return self.rule.note if self.rule else ""


def valid_target(topology: Topology, action: Remediation, target: str) -> bool:
    if action == Remediation.NODE_DRAIN:
        return target in {n.name for n in NODES}
    return topology.get(target) is not None


def requires_approval(topology: Topology, target: str) -> bool:
    """Actions on stateful systems (databases, cache, Kafka, PgBouncer) need the owning team's approval."""
    comp = topology.get(target)
    return bool(comp and comp.stateful)


def _matches(rule: RemediationRule, action: Remediation, target: str, params: dict[str, str]) -> bool:
    if rule.action != action:
        return False
    if rule.targets is not None and target not in rule.targets:
        return False
    return all(want.lower() in str(params.get(key, "")).lower() for key, want in rule.params.items())


def classify(
    scenario: Scenario, action: Remediation, target: str, params: dict[str, str]
) -> tuple[OutcomeKind, RemediationRule | None]:
    """What this action would do in this incident. Unlisted actions have no effect."""
    if not valid_target(scenario.topology, action, target):
        return OutcomeKind.INVALID, None
    spec = scenario.spec
    for rule in spec.correct_remediations:
        if _matches(rule, action, target, params):
            return OutcomeKind.RESOLVES, rule
    for rule in spec.harmful_remediations:
        if _matches(rule, action, target, params):
            return OutcomeKind.HARMFUL, rule
    for rule in spec.ineffective_remediations:
        if _matches(rule, action, target, params):
            if rule.relief_minutes is not None:
                return OutcomeKind.TRANSIENT, rule
            return (OutcomeKind.PARTIAL if rule.depth < 1 else OutcomeKind.NO_EFFECT), rule
    return OutcomeKind.NO_EFFECT, None


def intervene(
    scenario: Scenario, action: Remediation, target: str, params: dict[str, str], started_at: float
) -> Intervention:
    kind, rule = classify(scenario, action, target, params)
    minutes = INVALID_TARGET_MINUTES if kind == OutcomeKind.INVALID else ACTION_MINUTES[action]
    return Intervention(action, target, dict(params), started_at, started_at + minutes, kind, rule)


def recovery_start(interventions: list[Intervention]) -> float | None:
    """When the first resolving action starts to take effect (after any harmful consequences)."""
    resolving = [i for i in interventions if i.kind == OutcomeKind.RESOLVES]
    if not resolving:
        return None
    first = min(resolving, key=lambda i: i.completes_at)
    blocked = [
        h.completes_at + (h.rule.consequence_minutes if h.rule else 0.0)
        for h in interventions
        if h.kind == OutcomeKind.HARMFUL and h.completes_at <= first.completes_at
    ]
    return max([first.completes_at, *blocked])


def resolved_at(interventions: list[Intervention]) -> float | None:
    """Minute (after the alert) at which the incident has fully recovered, if it has."""
    start = recovery_start(interventions)
    if start is None:
        return None
    first = min((i for i in interventions if i.kind == OutcomeKind.RESOLVES), key=lambda i: i.completes_at)
    return start + (first.rule.recovery_minutes if first.rule else 4.0)


def severity(interventions: list[Intervention], minutes: np.ndarray) -> np.ndarray:
    """k(t) for each minute in `minutes` (float offsets relative to the alert)."""
    k = np.ones_like(minutes, dtype=float)
    end = resolved_at(interventions)
    for iv in sorted(interventions, key=lambda i: i.completes_at):
        c, rule = iv.completes_at, iv.rule
        after = minutes >= c
        if iv.kind == OutcomeKind.TRANSIENT and rule is not None:
            window = after & (minutes < c + (rule.relief_minutes or 0))
            k[window] *= rule.depth
        elif iv.kind == OutcomeKind.PARTIAL and rule is not None:
            k[after] *= rule.depth
        elif iv.kind == OutcomeKind.HARMFUL and rule is not None:
            stop = c + rule.worsen_minutes if rule.worsen_minutes is not None else (end or np.inf)
            k[after & (minutes < stop)] *= rule.worsen
    start = recovery_start(interventions)
    if start is not None and end is not None:
        frac = np.clip((minutes - start) / max(end - start, 1e-9), 0, 1)
        k *= 1 - (3 * frac**2 - 2 * frac**3)  # smoothstep ease-out of the incident
    return k
