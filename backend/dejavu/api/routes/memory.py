"""What DejaVu remembers (spec 10, 11.2): living runbooks and their belief timelines, the
explorer with curation, bank growth, briefings and Ask DejaVu.

Reads default to the live bank and can name another (`?bank=trained|day1|rag`); curation only
ever touches the live bank.
"""

import asyncio
import json
import time
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dejavu.api.deps import Svc
from dejavu.api.routes.incidents import record_or_404
from dejavu.api.scenarios import scenario_of
from dejavu.api.services import Services
from dejavu.eval.report import latest_run, read_jsonl
from dejavu.memory.hindsight_adapter import BeliefChange, MentalModelDetail
from dejavu.memory.reader import triage_brief
from dejavu.sim.telemetry import ensure_telemetry
from dejavu.sim.world import IncidentWorld
from dejavu.strategies.base import IncidentContext

router = APIRouter(prefix="/memory", tags=["memory"])
ask_router = APIRouter(tags=["memory"])
BankName = Literal["live", "trained", "day1", "rag"]


class Question(BaseModel):
    question: str


class Invalidation(BaseModel):
    reason: str = "marked wrong or outdated in the war room"


def bank_id(svc: Services, bank: BankName) -> str:
    s = svc.settings
    return {
        "live": s.dejavu_bank_live,
        "trained": s.dejavu_bank_trained,
        "day1": s.dejavu_bank_day1,
        "rag": s.dejavu_bank_rag,
    }[bank]


def belief_versions(model: MentalModelDetail, history: list[BeliefChange]) -> list[dict[str, Any]]:
    """Newest first: the current content, then each version it replaced, with when it held."""
    ordered = sorted(history, key=lambda c: c.changed_at.isoformat() if c.changed_at else "", reverse=True)
    versions = [
        {"content": model.content or "", "since": ordered[0].changed_at if ordered else None, "until": None}
    ]
    for i, change in enumerate(ordered):
        since = ordered[i + 1].changed_at if i + 1 < len(ordered) else None
        versions.append({"content": change.previous_content, "since": since, "until": change.changed_at})
    return versions


@router.get("/models")
async def models(svc: Svc, bank: BankName = "live") -> list[dict[str, Any]]:
    return [m.model_dump(mode="json") for m in await svc.memory.mental_models(bank_id(svc, bank))]


PLACEHOLDER = "Generating content"
ON_DEMAND_TTL_S = 600.0
_on_demand: dict[tuple[str, str], tuple[float, str]] = {}


async def _content_on_demand(svc: Services, bank: str, model: MentalModelDetail) -> str | None:
    """A model still showing its placeholder is answered by reflect on the model's own question.

    On our Hindsight Cloud organisation mental models never leave "Generating content..."
    (`no_sources_in_scope`), while reflect over the same bank works (HINDSIGHT_NOTES.md)."""
    cached = _on_demand.get((bank, model.id))
    if cached and time.monotonic() - cached[0] < ON_DEMAND_TTL_S:
        return cached[1]
    if not model.source_query:
        return None
    answer = await svc.memory.reflect(
        bank, model.source_query, budget="mid", tags=model.tags or None, tags_match="any"
    )
    _on_demand[(bank, model.id)] = (time.monotonic(), answer.text)
    return answer.text


@router.get("/models/{model_id}")
async def model(model_id: str, svc: Svc, bank: BankName = "live") -> dict[str, Any]:
    target = bank_id(svc, bank)
    detail, history = await asyncio.gather(
        svc.memory.mental_model(target, model_id), svc.memory.mental_model_history(target, model_id)
    )
    on_demand = False
    if not detail.content or detail.content.startswith(PLACEHOLDER):
        text = await _content_on_demand(svc, target, detail)
        if text:
            detail, on_demand = detail.model_copy(update={"content": text}), True
    return {
        "model": detail.model_dump(mode="json"),
        "versions": belief_versions(detail, history),
        "on_demand": on_demand,
    }


@router.get("/search")
async def search(
    svc: Svc, q: str = "", state: str | None = None, type: str | None = None, bank: BankName = "live"
) -> list[dict[str, Any]]:
    """Semantic recall for a query; plain listing (including invalidated memories) otherwise."""
    target = bank_id(svc, bank)
    if q and state is None:
        types = [type] if type else ["world", "experience", "observation"]
        hits = await svc.memory.recall(target, q, types=types, budget="mid", max_tokens=2000)
        return [{**h.model_dump(), "state": "valid"} for h in hits]
    units = await svc.memory.list_memories(target, query=q or None, state=state, fact_type=type)
    return [u.model_dump() for u in units]


@router.post("/{memory_id}/invalidate")
async def invalidate(memory_id: str, body: Invalidation, svc: Svc) -> dict[str, str]:
    await svc.memory.set_memory_state(svc.settings.dejavu_bank_live, memory_id, "invalidated", body.reason)
    return {"id": memory_id, "state": "invalidated"}


@router.post("/{memory_id}/restore")
async def restore(memory_id: str, svc: Svc) -> dict[str, str]:
    await svc.memory.set_memory_state(svc.settings.dejavu_bank_live, memory_id, "valid")
    return {"id": memory_id, "state": "valid"}


@router.get("/stats")
async def stats(svc: Svc, bank: BankName = "live") -> dict[str, Any]:
    """Bank counts now, plus the growth series of the latest Gauntlet run, if there is one."""
    run_dir = latest_run(svc.eval_dir)
    growth = [g for g in read_jsonl(run_dir / "growth.jsonl") if g["strategy"] == "dejavu"] if run_dir else []
    return {
        "bank": bank_id(svc, bank),
        "stats": await svc.memory.stats(bank_id(svc, bank)),
        "growth": {"run_id": run_dir.name if run_dir else None, "points": growth},
    }


@router.get("/briefing/{incident_id}")
async def briefing(incident_id: str, svc: Svc) -> dict[str, Any]:
    """The briefing DejaVu gave for the incident, or a fresh one from the live bank."""
    for record in reversed(svc.store.runs(incident_id=incident_id)):
        run = svc.runs.get(record.id) if record.strategy == "dejavu" else None
        given = run.trace.of_type("briefing") if run else []
        if given:
            return json.loads(given[0].model_dump_json())["data"]
    scenario = scenario_of(record_or_404(svc, incident_id))
    await asyncio.to_thread(ensure_telemetry, scenario, svc.runs.telemetry_root)
    world = IncidentWorld.open(scenario, svc.runs.telemetry_root)
    ctx = IncidentContext.from_alert(incident_id, world.store.alert, scenario.alert_at)
    brief = await triage_brief(svc.memory, svc.settings.dejavu_bank_live, ctx)
    return {"source": brief.source, "text": brief.text, "data": brief.data}


@ask_router.post("/ask")
async def ask(body: Question, svc: Svc) -> dict[str, Any]:
    """Ask DejaVu: a free-form reflect over the live bank, with the memories it rests on."""
    if not body.question.strip():
        raise HTTPException(422, "ask a question")
    answer = await svc.memory.reflect(svc.settings.dejavu_bank_live, body.question, budget="high")
    return {"answer": answer.text, "based_on": [h.model_dump() for h in answer.based_on]}
