"""The human side of each Gauntlet incident, replayed in the simulator.

`data/fixtures/human_paths.yaml` records what Kestrel Pay's engineers did during each incident.
Replaying those steps yields resolution times, failed payments and rupees at risk, so the
human-voice fixtures (postmortems, Slack threads, feedback notes) never contain invented numbers.
"""

from datetime import timedelta
from functools import cache
from pathlib import Path

import numpy as np
import yaml
from pydantic import BaseModel, Field

from dejavu.config import REPO_ROOT
from dejavu.sim.clock import fmt_hm
from dejavu.sim.generators.metrics import NO_NODE
from dejavu.sim.migrations import M1, M2
from dejavu.sim.remediation import OutcomeKind
from dejavu.sim.scenario import EventEffect, Scenario, _fill
from dejavu.sim.telemetry import INCIDENTS_DIR
from dejavu.sim.topology import TEAMS
from dejavu.sim.world import IncidentWorld
from dejavu.taxonomy import Remediation

HUMAN_PATHS = REPO_ROOT / "data" / "fixtures" / "human_paths.yaml"
DETECTION_MIN = 3.0

OUTCOME_WORDS = {
    OutcomeKind.RESOLVES: "fixed it",
    OutcomeKind.TRANSIENT: "brief relief, then relapse",
    OutcomeKind.PARTIAL: "partial relief only",
    OutcomeKind.NO_EFFECT: "no effect",
    OutcomeKind.HARMFUL: "made it worse",
    OutcomeKind.INVALID: "target does not exist",
}


class HumanStep(BaseModel):
    at: float
    action: Remediation
    target: str
    params: dict[str, str] = Field(default_factory=dict)
    note: str


class Page(BaseModel):
    at: float
    team: str


class HumanPath(BaseModel):
    n: int
    oncall: str
    author: str
    steps: list[HumanStep] = Field(default_factory=list)
    page: Page | None = None
    external_resolution_at: float | None = None
    external_resolution: str | None = None


class StepFact(BaseModel):
    at: str
    minutes_after_alert: float
    action: str
    target: str
    params: dict[str, str]
    outcome: str
    note: str


class TriggerFact(BaseModel):
    change_id: str
    type: str
    service: str
    summary: str
    author: str
    at: str
    details: dict


class FactSheet(BaseModel):
    """Everything a human-voice fixture may state about one incident."""

    n: int
    incident_id: str
    date: str
    alert_at: str
    onset_at: str
    oncall: str
    author: str
    alert_name: str
    alert_description: str
    root_cause_category: str
    culprit_service: str
    culprit_owner_team: str | None
    trigger: TriggerFact | None
    discriminators: list[str]
    steps: list[StepFact]
    page: dict | None
    resolved_at: str
    minutes_alert_to_recovery: float
    mttr_min: float
    impact_minutes: float
    failed_payments: int
    inr_at_risk: int
    worked: list[str]
    did_not_work: list[str]
    made_worse: list[str]
    prevention: list[str]
    migration_context: str | None
    extras: list[str]
    external_resolution: str | None


@cache
def human_paths(path: Path = HUMAN_PATHS) -> dict[int, HumanPath]:
    return {p["n"]: HumanPath.model_validate(p) for p in yaml.safe_load(path.read_text())}


def _migration_context(scenario: Scenario) -> str | None:
    notes = []
    for m, label in ((M1, "PgBouncer migration (M1, 3 Sep)"), (M2, "Redis to Valkey migration (M2, 10 Sep)")):
        elapsed = scenario.alert_at - m.at
        if elapsed.total_seconds() < 0 or elapsed.days > 14:
            continue
        hours = round(elapsed.total_seconds() / 3600)
        when = f"{hours} hours" if elapsed.days < 1 else f"{elapsed.days} days"
        notes.append(f"{when} after the {label}")
    return "; ".join(notes) or None


def fact_sheet(n: int, scenario: Scenario, root: Path = INCIDENTS_DIR) -> FactSheet:
    """Replay the humans' actions for incident `n` and collect the facts their documents may use."""
    path = human_paths()[n]
    world = IncidentWorld.open(scenario, root)
    steps: list[StepFact] = []
    worked, did_not, worse = [], [], []
    for step in sorted(path.steps, key=lambda s: s.at):
        target = str(_fill(step.target, scenario.values))
        if step.at < world.clock.elapsed_min:
            raise ValueError(f"incident {n}: step at {step.at} overlaps the previous action")
        world.clock.advance(step.at - world.clock.elapsed_min)
        iv = world.apply(step.action, target, step.params)
        world.clock.advance(iv.completes_at - iv.started_at)
        outcome = OUTCOME_WORDS[iv.kind]
        steps.append(
            StepFact(
                at=fmt_hm(world.clock.at(step.at)),
                minutes_after_alert=step.at,
                action=step.action.value,
                target=target,
                params=step.params,
                outcome=outcome,
                note=step.note,
            )
        )
        label = f"{step.action.value} {target}"
        {OutcomeKind.RESOLVES: worked, OutcomeKind.HARMFUL: worse}.get(iv.kind, did_not).append(label)

    resolved = world.resolved_at_min
    if resolved is None:
        resolved = path.external_resolution_at
    if resolved is None:
        raise ValueError(f"incident {n}: the human path never resolves the incident")

    spec = scenario.spec
    trigger = next((e for e in spec.effects if isinstance(e, EventEffect) and e.trigger), None)
    series = world.store.metric("checkout-api", "payments_failed")[NO_NODE]
    minutes = np.arange(series.offsets[0], np.floor(resolved) + 1, dtype=float)
    excess = np.interp(minutes, series.offsets.astype(float), series.delta) * world.k(minutes)
    culprit = world.topology.get(spec.culprit_service)
    page = None
    if path.page:
        team = TEAMS.get(path.page.team)
        page = {
            "at": fmt_hm(world.clock.at(path.page.at)),
            "team": path.page.team,
            "lead": team.lead if team else None,
        }

    return FactSheet(
        n=n,
        incident_id=scenario.incident_id,
        date=f"{scenario.alert_at:%a %d %b %Y}",
        alert_at=fmt_hm(scenario.alert_at),
        onset_at=fmt_hm(scenario.alert_at + timedelta(minutes=spec.impact.start_offset)),
        oncall=path.oncall,
        author=path.author,
        alert_name=spec.alert.name,
        alert_description=world.store.alert["annotations"]["description"],
        root_cause_category=spec.category.value,
        culprit_service=spec.culprit_service,
        culprit_owner_team=culprit.team if culprit else None,
        trigger=TriggerFact(
            change_id=trigger.id or "",
            type=trigger.type.value,
            service=trigger.service,
            summary=trigger.summary,
            author=trigger.author,
            at=fmt_hm(scenario.alert_at + timedelta(minutes=trigger.at_offset)),
            details=trigger.details,
        )
        if trigger
        else None,
        discriminators=[d.text for d in spec.discriminators],
        steps=steps,
        page=page,
        resolved_at=fmt_hm(world.clock.at(resolved)),
        minutes_alert_to_recovery=round(resolved, 1),
        mttr_min=round(DETECTION_MIN + resolved, 1),
        impact_minutes=round(resolved - spec.impact.start_offset, 1),
        failed_payments=round(float(np.maximum(excess, 0).sum())),
        inr_at_risk=round(world.inr_at_risk(resolved)),
        worked=worked,
        did_not_work=did_not,
        made_worse=worse,
        prevention=[p.value for p in spec.prevention],
        migration_context=_migration_context(scenario),
        extras=scenario.extras,
        external_resolution=path.external_resolution,
    )
