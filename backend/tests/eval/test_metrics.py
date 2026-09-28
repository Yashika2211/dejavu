"""Headline metrics: per-strategy summaries, paired comparisons, learning curves, incident kinds."""

import pytest

from dejavu.eval.metrics import compare, incident_labels, learning_curve, summarize
from dejavu.sim.schedule import gauntlet
from tests.eval.rows import row

ROWS = [
    row(1, "amnesiac", mttr=30),
    row(2, "amnesiac", correct=False, mttr=50, kind="recurrence", inr_at_risk=3_000_000.0),
    row(3, "amnesiac", mttr=40),
    row(1, "dejavu", mttr=20, precedent_precision=1.0),
    row(2, "dejavu", mttr=25, kind="recurrence", wasted_steps=0, precedent_precision=0.5),
]


def test_summary_per_strategy() -> None:
    amnesiac = summarize(ROWS, "amnesiac")
    assert amnesiac is not None
    assert (amnesiac.incidents, amnesiac.correct, amnesiac.accuracy) == (3, 2, 0.667)
    assert (amnesiac.mttr_mean, amnesiac.mttr_median) == (40.0, 40.0)
    assert amnesiac.inr_at_risk == 5_000_000
    assert amnesiac.precedent_precision is None
    assert amnesiac.by_kind["recurrence"].accuracy == 0.0
    assert amnesiac.by_kind["first"].incidents == 2
    dejavu = summarize(ROWS, "dejavu")
    assert dejavu is not None
    assert dejavu.precedent_precision == 0.75
    assert summarize(ROWS, "rag") is None


def test_comparison_is_paired() -> None:
    c = compare(ROWS, "dejavu")
    assert c is not None
    assert c.incidents == 2  # incident 3 has no dejavu run
    assert c.mttr_reduction_pct == pytest.approx(43.8)  # (80 - 45) / 80
    assert c.recurrence_mttr_reduction_pct == pytest.approx(50.0)
    assert c.accuracy_delta_pp == pytest.approx(50.0)
    assert c.wasted_steps_saved == 2
    assert c.inr_saved == 2_000_000
    assert compare(ROWS, "rag") is None


def test_learning_curve_accumulates_accuracy() -> None:
    curve = learning_curve(ROWS, "amnesiac")
    assert [p["n"] for p in curve] == [1, 2, 3]
    assert [p["cumulative_accuracy"] for p in curve] == [1.0, 0.5, 0.667]


def test_incident_kinds_follow_the_schedule() -> None:
    labels = incident_labels(gauntlet())
    kinds = {n: label.kind for n, label in labels.items()}
    assert [kinds[n] for n in (1, 5, 7, 10, 12, 18, 19, 22, 24)] == [
        "first",
        "recurrence",
        "look-alike",
        "look-alike",
        "recurrence",
        "recurrence",
        "novel",
        "first",
        "novel",
    ]
    assert {n for n, label in labels.items() if label.after_migration} == {12, 14}
