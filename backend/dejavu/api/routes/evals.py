"""Gauntlet results for the Learning screen (spec 10, 11.2), straight from `data/eval/<run>/`.

Plain `def` routes: FastAPI runs them in its threadpool, so file reads never block the event loop.
"""

import json
from typing import Any

from fastapi import APIRouter, HTTPException

from dejavu.api.deps import Svc

router = APIRouter(prefix="/eval", tags=["eval"])


@router.get("/runs")
def runs(svc: Svc) -> list[dict[str, Any]]:
    """Every Gauntlet run, newest first, with how far it got."""
    out = []
    for run_json in sorted(svc.eval_dir.glob("*/run.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        run = json.loads(run_json.read_text())
        summary_path = run_json.parent / "summary.json"
        summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
        out.append(
            {
                "run_id": run["run_id"],
                "seed": run["seed"],
                "n": run["n"],
                "strategies": run["strategies"],
                "models": run["models"],
                "started_at": run["started_at"],
                "complete": summary.get("complete", False),
                "incidents_done": summary.get("incidents_done", {}),
            }
        )
    return out


@router.get("/runs/{run_id}")
def run(run_id: str, svc: Svc) -> dict[str, Any]:
    run_dir = svc.eval_dir / run_id
    summary, charts = run_dir / "summary.json", run_dir / "chart_data.json"
    if run_dir.parent != svc.eval_dir or not summary.exists() or not charts.exists():
        raise HTTPException(404, f"no results for run {run_id}")
    return {"summary": json.loads(summary.read_text()), "chart_data": json.loads(charts.read_text())}
