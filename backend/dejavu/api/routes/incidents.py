"""Incidents, their live investigations, approvals and the on-call human's feedback (spec 10)."""

import asyncio
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from sse_starlette import EventSourceResponse

from dejavu.api.deps import Svc
from dejavu.api.feedback import Feedback, feedback_document
from dejavu.api.live import LiveRun
from dejavu.api.scenarios import UnknownScenarioError, demo_names, new_incident, scenario_of
from dejavu.api.services import STRATEGY_LABELS, Services
from dejavu.api.sse import run_messages, stream
from dejavu.memory.hindsight_adapter import MemoryUnavailableError
from dejavu.runner import build_resolution
from dejavu.sim.scenario import archetype_ids
from dejavu.sim.telemetry import ensure_telemetry
from dejavu.sim.world import IncidentWorld
from dejavu.store.db import FeedbackRecord, IncidentRecord, RunRecord
from dejavu.strategies.base import Resolution
from dejavu.strategies.dejavu import DejaVu

router = APIRouter(tags=["incidents"])


class NewIncident(BaseModel):
    scenario: str | None = None  # a demo name, an archetype id or "surprise"
    seed: int | None = None


class Approval(BaseModel):
    action_id: str
    approved: bool


def create_record(svc: Services, scenario: str | None, seed: int | None) -> IncidentRecord:
    try:
        record = new_incident(scenario, seed, {i.id for i in svc.store.incidents()})
    except UnknownScenarioError as exc:
        raise HTTPException(
            422,
            f"unknown scenario {exc}: use a demo ({', '.join(demo_names())}), an archetype id or 'surprise'",
        ) from exc
    if svc.store.incident(record.id) is None:
        svc.store.save(record)
    return record


def record_or_404(svc: Services, incident_id: str) -> IncidentRecord:
    record = svc.store.incident(incident_id)
    if record is None:
        raise HTTPException(404, f"no incident {incident_id}")
    return record


def run_summary(record: RunRecord) -> dict[str, Any]:
    return record.model_dump(exclude={"trace_path", "bank"})


def incident_summary(svc: Services, record: IncidentRecord) -> dict[str, Any]:
    alert = scenario_of(record).spec.alert
    return {
        "id": record.id,
        "source": record.source,
        "demo": record.requested if record.source == "demo" else None,
        "alert_at": record.alert_at,
        "created_at": record.created_at,
        "alert": {
            "name": alert.name,
            "service": alert.service,
            "severity": alert.severity,
            "summary": alert.summary,
        },
        "runs": [run_summary(r) for r in svc.store.runs(incident_id=record.id)],
    }


@router.get("/scenarios")
def scenarios() -> dict[str, list[str]]:
    """What the incident picker offers: the rehearsed demos, every archetype, and a surprise."""
    return {"demos": demo_names(), "archetypes": archetype_ids()}


@router.post("/incidents", status_code=201)
async def create_incident(body: NewIncident, svc: Svc) -> dict[str, str]:
    return {"incident_id": create_record(svc, body.scenario, body.seed).id}


@router.get("/incidents")
async def list_incidents(svc: Svc) -> list[dict[str, Any]]:
    return [incident_summary(svc, r) for r in svc.store.incidents()]


@router.get("/incidents/{incident_id}")
async def incident(incident_id: str, svc: Svc) -> dict[str, Any]:
    record = record_or_404(svc, incident_id)
    feedback = [f.model_dump() for f in svc.store.feedback(incident_id)]
    return {**incident_summary(svc, record), "feedback": feedback}


@router.get("/incidents/{incident_id}/changes")
async def changes(incident_id: str, svc: Svc, hours: float = 6.0) -> list[dict[str, Any]]:
    """The change log before the alert, as any responder would see it on the dashboard."""
    scenario = scenario_of(record_or_404(svc, incident_id))
    await asyncio.to_thread(ensure_telemetry, scenario, svc.runs.telemetry_root)
    world = IncidentWorld.open(scenario, svc.runs.telemetry_root)
    return [c.model_dump(mode="json") for c in reversed(world.changes(min(hours, 24.0)))]


@router.get("/incidents/{incident_id}/stream")
async def stream_incident(
    incident_id: str, svc: Svc, strategy: str = "dejavu", fresh: bool = False
) -> EventSourceResponse:
    """Stream the incident's latest run with `strategy`, starting one if there is none (or `fresh`)."""
    record = record_or_404(svc, incident_id)
    if strategy not in STRATEGY_LABELS:
        raise HTTPException(422, f"strategy must be one of {', '.join(STRATEGY_LABELS)}")
    run: LiveRun | None = None
    if not fresh:
        earlier = [
            r
            for r in svc.store.runs(incident_id=incident_id)
            if r.strategy == strategy and r.race_id is None and r.status in ("running", "done")
        ]
        run = svc.runs.get(earlier[-1].id) if earlier else None
    if run is None:
        run = svc.runs.start(
            scenario_of(record), svc.strategy(strategy), label=strategy, bank=svc.bank_for(strategy)
        )
    return stream(run_messages(run))


@router.post("/runs/{run_id}/approve")
async def approve(run_id: str, body: Approval, svc: Svc) -> dict[str, bool]:
    run = svc.runs.live.get(run_id)
    if run is None:
        raise HTTPException(404, f"no live run {run_id}")
    if not run.decide(body.action_id, body.approved):
        raise HTTPException(409, f"nothing is waiting for approval as {body.action_id}")
    return {"ok": True}


async def _retain(svc: Services, resolution: Resolution, feedback: FeedbackRecord) -> None:
    """What the live bank learns from the incident: DejaVu's run plus the human's feedback."""
    try:
        await DejaVu(svc.memory, svc.settings.dejavu_bank_live).on_resolution(resolution)
    except MemoryUnavailableError:
        return
    feedback.retained = True
    svc.store.save(feedback)


def _latest_dejavu_run(svc: Services, incident_id: str) -> LiveRun | None:
    """The latest finished War Room run of DejaVu on the live bank, if it is still in memory."""
    for record in reversed(svc.store.runs(incident_id=incident_id)):
        if record.strategy == "dejavu" and record.race_id is None and record.status == "done":
            run = svc.runs.live.get(record.id)
            if run is not None:
                return run
    return None


@router.post("/incidents/{incident_id}/feedback", status_code=202)
async def feedback(incident_id: str, body: Feedback, svc: Svc, background: BackgroundTasks) -> dict[str, Any]:
    """Save the feedback; if DejaVu investigated on the live bank, the bank learns from both."""
    record_or_404(svc, incident_id)
    run = _latest_dejavu_run(svc, incident_id)
    saved = svc.store.save(
        FeedbackRecord(
            incident_id=incident_id,
            run_id=run.id if run else None,
            correct=body.correct,
            actual_category=body.actual_category.value if body.actual_category else None,
            actual_service=body.actual_service,
            notes=body.notes,
        )
    )
    learning = False
    if run is not None and run.result is not None and run.score is not None and run.world is not None:
        document = feedback_document(run, body)
        resolution = build_resolution(run.result, run.score, run.world, {"feedback": document})
        background.add_task(_retain, svc, resolution, saved)
        learning = True
    return {"learning": learning}
