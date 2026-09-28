"""Reports are generated from results files only: summary, chart data, charts and EVAL_RESULTS.md."""

import json
from pathlib import Path

from dejavu.eval.report import publish, write_run_report
from tests.eval.rows import row

RUN = {
    "run_id": "g42-test",
    "seed": 42,
    "n": 3,
    "strategies": ["amnesiac", "dejavu"],
    "models": ["openai/gpt-oss-120b"],
    "loop": {"max_steps": 16, "sim_budget_min": 90.0},
    "started_at": "2026-09-28T10:00:00+05:30",
    "git_sha": "abc1234",
}


def _run_dir(tmp_path: Path, rows: list[dict], growth: list[dict] | None = None) -> Path:
    run_dir = tmp_path / "g42-test"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(json.dumps(RUN))
    (run_dir / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (run_dir / "growth.jsonl").write_text("".join(json.dumps(g) + "\n" for g in growth or []))
    return run_dir


def _rows(dejavu_incidents: int = 3) -> list[dict]:
    dates = ["2026-09-01T22:10:00+05:30", "2026-09-04T02:14:00+05:30", "2026-09-06T18:55:00+05:30"]
    rows = [row(n, "amnesiac", mttr=30 + n, alert_at=dates[n - 1]) for n in (1, 2, 3)]
    rows += [row(n, "dejavu", mttr=20 + n, alert_at=dates[n - 1]) for n in range(1, dejavu_incidents + 1)]
    return rows


def test_run_report_writes_summary_chart_data_and_charts(tmp_path: Path) -> None:
    growth = [
        {"n": n, "strategy": "dejavu", "total_nodes": 100 + 10 * n, "total_observations": 5 * n}
        for n in range(4)
    ]
    run_dir = _run_dir(tmp_path, _rows(), growth)
    summary = write_run_report(run_dir)

    assert summary is not None
    assert summary["complete"]
    assert summary["strategies"]["dejavu"]["mttr_mean"] == 22.0  # 21, 22, 23
    assert summary["comparisons"]["dejavu"]["incidents"] == 3
    data = json.loads((run_dir / "chart_data.json").read_text())
    assert [m["id"] for m in data["migrations"]] == ["M1"]
    assert data["migrations"][0]["x"] == 1.5  # M1 (3 Sep) falls between incidents 1 and 2
    assert len(data["growth"]["dejavu"]) == 4
    charts = {p.name for p in (run_dir / "charts").glob("*.png")}
    assert charts == {"mttr.png", "accuracy.png", "steps.png", "cost.png", "memory_growth.png"}


def test_nothing_is_written_before_the_first_result(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path, [])
    assert write_run_report(run_dir) is None
    assert not (run_dir / "summary.json").exists()


def test_published_results_say_how_far_the_run_got(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path, _rows(dejavu_incidents=2))
    docs = tmp_path / "docs"
    doc = publish(run_dir, docs)

    text = doc.read_text()
    assert "partial: amnesiac 3 of 3, dejavu 2 of 3" in text
    assert "| dejavu | 2/2 (100%) |" in text
    assert "## Limitations" in text
    assert "![MTTR per incident](eval/mttr.png)" in text
    assert (docs / "eval" / "mttr.png").exists()
    assert "{{" not in text
