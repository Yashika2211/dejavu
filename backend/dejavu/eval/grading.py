"""Deterministic grading of one run against the scenario's ground truth (spec 7.3).

- correct: predicted category and culprit service both match (listed aliases accepted).
- ttd_min: simulated minutes from the alert to the diagnosis.
- mttr_min: 3 minutes of detection plus the time until recovery. Recovery comes from the world
  (a fix applied during the investigation or from the remediation plan). With no working fix a
  human fixes it at ttd + 45, delayed by any harmful action's consequence; after an escalation
  the human fixes it at ttd + 40.
- wasted_steps: evidence calls outside the scenario's relevant evidence and the generic triage
  set, plus remediations that did not fix anything (harmful ones are counted separately).
- precedent_precision: the share of cited incident IDs whose true category matches.
- inr_at_risk: excess failed payments x ₹1,850 until recovery.
"""

from typing import Any, Literal

from pydantic import BaseModel

from dejavu.agent.loop import RunResult
from dejavu.agent.schemas import AgentStep
from dejavu.sim.remediation import OutcomeKind
from dejavu.sim.runbooks import find
from dejavu.sim.scenario import Scenario
from dejavu.sim.topology import NODES
from dejavu.sim.world import IncidentWorld
from dejavu.taxonomy import RootCause

DETECTION_MIN = 3.0
HUMAN_FIX_AFTER_MIN = 45.0
ESCALATION_FIX_AFTER_MIN = 40.0
GENERIC_TRIAGE = {"get_alert", "get_topology", "list_changes"}
PROCESS_TOOLS = {"update_hypotheses", "submit_diagnosis", "recall_memory", "page_human"}

# Day-0 incidents, as the team later understood them (INC-3517 was acquirerx, not DNS).
HISTORICAL_CATEGORIES: dict[str, RootCause] = {
    "INC-3517": RootCause.PSP_RATE_LIMIT,
    "INC-3688": RootCause.DISK_FULL_WAL,
    "INC-3790": RootCause.MEMORY_LEAK_OOM,
    "INC-3845": RootCause.CERT_EXPIRY,
    "INC-3902": RootCause.DB_POOL_EXHAUSTION,
    "INC-3951": RootCause.CACHE_STAMPEDE,
}


class IncidentScore(BaseModel):
    incident_id: str
    archetype: str
    strategy: str
    correct: bool
    category_correct: bool
    culprit_correct: bool
    ended: str
    ttd_min: float | None
    mttr_min: float
    resolved_by: Literal["agent", "plan", "human", "escalation"]
    steps: int
    wasted_steps: int
    harmful_actions: int
    remediations: list[dict[str, Any]]
    tokens_in: int
    tokens_out: int
    usd_cost: float
    wall_clock_s: float
    llm_calls: int
    cited: list[str]
    precedent_precision: float | None
    inr_at_risk: float
    prevented: bool = False


def _node_names() -> set[str]:
    return {n.name for n in NODES}


def culprit_matches(predicted: str, scenario: Scenario) -> bool:
    wanted = {scenario.spec.culprit_service, *scenario.spec.culprit_aliases}
    guess = predicted.strip().lower()
    return guess in wanted or (guess in _node_names() and "nodes" in wanted)


def _relevant(step_tool: str, args: dict[str, Any], scenario: Scenario) -> bool:
    if step_tool in GENERIC_TRIAGE or step_tool in PROCESS_TOOLS:
        return True
    pairs = {(e.tool, e.service) for e in scenario.spec.relevant_evidence}
    if step_tool == "get_runbook":
        runbook = find(str(args.get("topic", "")))
        return runbook is not None and any(("get_runbook", s) in pairs for s in runbook.services)
    service = str(args.get("service") or args.get("name") or "").strip().lower()
    if service in _node_names():
        service = "nodes"
    return (step_tool, service) in pairs


INEFFECTIVE = {OutcomeKind.NO_EFFECT, OutcomeKind.TRANSIENT, OutcomeKind.PARTIAL, OutcomeKind.INVALID}


def _wasted(step: AgentStep, scenario: Scenario) -> bool:
    if step.tool == "run_remediation":
        return not step.ok or step.outcome in INEFFECTIVE
    return not step.ok or not _relevant(step.tool, step.args, scenario)


def grade(
    run: RunResult, scenario: Scenario, world: IncidentWorld, known: dict[str, RootCause]
) -> IncidentScore:
    """Score one run. `known` maps incident IDs the agent may cite to their true categories."""
    spec = scenario.spec
    diagnosis = run.diagnosis
    category_ok = diagnosis is not None and diagnosis.root_cause_category == spec.category
    culprit_ok = diagnosis is not None and culprit_matches(diagnosis.culprit_service, scenario)

    harmful = [iv for iv in world.interventions if iv.kind == OutcomeKind.HARMFUL]
    ttd = run.ttd_min if run.ttd_min is not None else world.clock.elapsed_min
    resolved = world.resolved_at_min
    if run.ended == "escalated" and (resolved is None or resolved > ttd):
        recovery, by = ttd + ESCALATION_FIX_AFTER_MIN, "escalation"
    elif resolved is not None:
        fix = min(
            (iv for iv in world.interventions if iv.kind == OutcomeKind.RESOLVES),
            key=lambda iv: iv.completes_at,
        )
        recovery, by = resolved, "agent" if fix.started_at < ttd else "plan"
    else:
        penalty = sum(iv.rule.consequence_minutes for iv in harmful if iv.rule)
        recovery, by = ttd + HUMAN_FIX_AFTER_MIN + penalty, "human"

    wasted = sum(_wasted(s, scenario) for s in run.steps)

    cited = sorted(
        {
            *(diagnosis.precedent_incident_ids if diagnosis else []),
            *(i for s in run.steps for i in s.cited_incidents),
        }
    )
    graded = [c for c in cited if c in known]
    precision = sum(known[c] == spec.category for c in graded) / len(graded) if graded else None

    calls = run.llm_calls
    return IncidentScore(
        incident_id=scenario.incident_id,
        archetype=spec.id,
        strategy=run.strategy,
        correct=category_ok and culprit_ok,
        category_correct=category_ok,
        culprit_correct=culprit_ok,
        ended=run.ended,
        ttd_min=round(ttd, 2),
        mttr_min=round(DETECTION_MIN + recovery, 2),
        resolved_by=by,
        steps=len(run.steps),
        wasted_steps=wasted,
        harmful_actions=len(harmful),
        remediations=[
            {
                "action": iv.action.value,
                "target": iv.target,
                "outcome": iv.kind.value,
                "at_min": round(iv.started_at, 2),
                "note": iv.note,
            }
            for iv in world.interventions
        ],
        tokens_in=sum(c["tokens_in"] for c in calls),
        tokens_out=sum(c["tokens_out"] for c in calls),
        usd_cost=round(sum(c["cost_usd"] for c in calls), 6),
        wall_clock_s=run.wall_clock_s,
        llm_calls=len(calls),
        cited=cited,
        precedent_precision=precision,
        inr_at_risk=round(world.inr_at_risk(recovery), 2),
    )
