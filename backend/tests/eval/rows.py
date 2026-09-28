"""Synthetic results rows for testing the metrics and the report. Never shown as results."""

from typing import Any


def row(
    n: int, strategy: str, *, correct: bool = True, mttr: float = 20.0, kind: str = "first", **extra: Any
) -> dict:
    return {
        "n": n,
        "incident_id": f"INC-{4100 + n}",
        "archetype": "db_pool_exhaustion",
        "strategy": strategy,
        "correct": correct,
        "category_correct": correct,
        "culprit_correct": correct,
        "ended": "diagnosed",
        "ttd_min": 8.0,
        "mttr_min": mttr,
        "resolved_by": "agent",
        "steps": 8,
        "wasted_steps": 2,
        "harmful_actions": 0,
        "remediations": [],
        "tokens_in": 30_000,
        "tokens_out": 3_000,
        "usd_cost": 0.0063,
        "wall_clock_s": 40.0,
        "llm_calls": 9,
        "cited": [],
        "precedent_precision": None,
        "inr_at_risk": 1_000_000.0,
        "prevented": False,
        "kind": kind,
        "after_migration": False,
        "alert_at": f"2026-08-{16 + n:02d}T10:00:00+05:30",
        "tests": "",
        **extra,
    }
