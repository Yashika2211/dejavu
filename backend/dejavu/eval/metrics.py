"""Headline numbers from Gauntlet results (spec 7.3), computed only from `results.jsonl` rows.

Everything the README, the UI and the article quote comes from these functions over a real run.
Comparisons are paired: a strategy is compared with the baseline only on incidents both finished.
"""

from collections.abc import Iterable
from statistics import mean, median
from typing import Any, Literal

from pydantic import BaseModel

from dejavu.sim.scenario import Scenario
from dejavu.sim.schedule import entry_for

Kind = Literal["first", "recurrence", "look-alike", "novel"]
KINDS: tuple[Kind, ...] = ("first", "recurrence", "look-alike", "novel")
Row = dict[str, Any]


class IncidentLabel(BaseModel):
    """How an incident relates to the ones before it in the Gauntlet."""

    n: int
    kind: Kind
    after_migration: bool


def incident_labels(scenarios: Iterable[Scenario]) -> dict[int, IncidentLabel]:
    """First occurrence, recurrence, look-alike or novel, from the schedule's notes and order."""
    seen: set[str] = set()
    labels = {}
    for scenario in sorted(scenarios, key=lambda s: s.alert_at):
        entry = entry_for(scenario)
        if entry is None:
            continue
        note = entry.tests.lower()
        kind: Kind
        if note.startswith("novel"):
            kind = "novel"
        elif "look-alike" in note:
            kind = "look-alike"
        elif scenario.spec.id in seen:
            kind = "recurrence"
        else:
            kind = "first"
        seen.add(scenario.spec.id)
        labels[entry.n] = IncidentLabel(n=entry.n, kind=kind, after_migration="migration" in note)
    return labels


class KindSummary(BaseModel):
    incidents: int
    accuracy: float
    mttr_mean: float


class StrategySummary(BaseModel):
    strategy: str
    incidents: int
    correct: int
    accuracy: float
    mttr_mean: float
    mttr_median: float
    ttd_mean: float | None
    steps_mean: float
    wasted_steps: int
    harmful_actions: int
    inr_at_risk: float
    tokens: int
    usd_cost: float
    wall_clock_s: float
    precedent_precision: float | None
    prevented: int
    by_kind: dict[str, KindSummary]


class Comparison(BaseModel):
    """A strategy against the baseline, over the incidents both finished."""

    strategy: str
    baseline: str
    incidents: int
    mttr_reduction_pct: float | None
    recurrence_mttr_reduction_pct: float | None
    accuracy_delta_pp: float
    wasted_steps_saved: int
    inr_saved: float


def _rows(rows: list[Row], strategy: str) -> list[Row]:
    return sorted((r for r in rows if r["strategy"] == strategy), key=lambda r: r["n"])


def _accuracy(rows: list[Row]) -> float:
    return round(sum(bool(r["correct"]) for r in rows) / len(rows), 3)


def summarize(rows: list[Row], strategy: str) -> StrategySummary | None:
    mine = _rows(rows, strategy)
    if not mine:
        return None
    ttds = [r["ttd_min"] for r in mine if r["ttd_min"] is not None]
    precisions = [r["precedent_precision"] for r in mine if r["precedent_precision"] is not None]
    by_kind = {
        kind: KindSummary(
            incidents=len(group),
            accuracy=_accuracy(group),
            mttr_mean=round(mean(r["mttr_min"] for r in group), 1),
        )
        for kind in KINDS
        if (group := [r for r in mine if r["kind"] == kind])
    }
    return StrategySummary(
        strategy=strategy,
        incidents=len(mine),
        correct=sum(bool(r["correct"]) for r in mine),
        accuracy=_accuracy(mine),
        mttr_mean=round(mean(r["mttr_min"] for r in mine), 1),
        mttr_median=round(median(r["mttr_min"] for r in mine), 1),
        ttd_mean=round(mean(ttds), 1) if ttds else None,
        steps_mean=round(mean(r["steps"] for r in mine), 1),
        wasted_steps=sum(r["wasted_steps"] for r in mine),
        harmful_actions=sum(r["harmful_actions"] for r in mine),
        inr_at_risk=round(sum(r["inr_at_risk"] for r in mine)),
        tokens=sum(r["tokens_in"] + r["tokens_out"] for r in mine),
        usd_cost=round(sum(r["usd_cost"] for r in mine), 4),
        wall_clock_s=round(sum(r["wall_clock_s"] for r in mine), 1),
        precedent_precision=round(mean(precisions), 3) if precisions else None,
        prevented=sum(bool(r.get("prevented")) for r in mine),
        by_kind=by_kind,
    )


def _reduction(before: float, after: float) -> float | None:
    return round(100 * (before - after) / before, 1) if before else None


def compare(rows: list[Row], strategy: str, baseline: str = "amnesiac") -> Comparison | None:
    base = {r["n"]: r for r in _rows(rows, baseline)}
    mine = {r["n"]: r for r in _rows(rows, strategy)}
    common = sorted(base.keys() & mine.keys())
    if not common:
        return None
    recurring = [n for n in common if base[n]["kind"] == "recurrence"]

    def total(side: dict[int, Row], key: str, ns: list[int]) -> float:
        return sum(side[n][key] for n in ns)

    return Comparison(
        strategy=strategy,
        baseline=baseline,
        incidents=len(common),
        mttr_reduction_pct=_reduction(total(base, "mttr_min", common), total(mine, "mttr_min", common)),
        recurrence_mttr_reduction_pct=(
            _reduction(total(base, "mttr_min", recurring), total(mine, "mttr_min", recurring))
            if recurring
            else None
        ),
        accuracy_delta_pp=round(
            100 * (_accuracy([mine[n] for n in common]) - _accuracy([base[n] for n in common])), 1
        ),
        wasted_steps_saved=int(total(base, "wasted_steps", common) - total(mine, "wasted_steps", common)),
        inr_saved=round(total(base, "inr_at_risk", common) - total(mine, "inr_at_risk", common)),
    )


def learning_curve(rows: list[Row], strategy: str) -> list[dict[str, Any]]:
    """Per incident, in order: MTTR, correctness and accuracy so far."""
    points, correct = [], 0
    for i, r in enumerate(_rows(rows, strategy), 1):
        correct += bool(r["correct"])
        points.append(
            {
                "n": r["n"],
                "incident_id": r["incident_id"],
                "kind": r["kind"],
                "correct": bool(r["correct"]),
                "mttr_min": r["mttr_min"],
                "cumulative_accuracy": round(correct / i, 3),
                "steps": r["steps"],
                "wasted_steps": r["wasted_steps"],
                "usd_cost": r["usd_cost"],
            }
        )
    return points
