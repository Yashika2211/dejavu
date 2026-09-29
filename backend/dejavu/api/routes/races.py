"""Race mode (spec 11.2): two strategies on the same incident, side by side, in real time.

Both lanes run concurrently on separate copies of the world. The simulated on-call human approves
every action in a race, as in the Gauntlet, so the consequences show up in the scoreboard.
"""

import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette import EventSourceResponse

from dejavu.agent.loop import LoopConfig
from dejavu.api.deps import Svc
from dejavu.api.live import LiveRun
from dejavu.api.routes.incidents import create_record, run_summary
from dejavu.api.scenarios import scenario_of
from dejavu.api.sse import race_messages, stream
from dejavu.store.db import RaceRecord

router = APIRouter(tags=["race"])
# Two lanes share one model's rate limit, so races get a tighter budget than the War Room.
RACE_LOOP = LoopConfig(max_steps=10, context_tokens=4500)


class NewRace(BaseModel):
    scenario: str = "race-pool-after-pgbouncer"
    seed: int | None = None
    left: Literal["amnesiac", "rag", "day1"] = "amnesiac"
    right: Literal["dejavu"] = "dejavu"


@router.post("/race", status_code=201)
async def start_race(body: NewRace, svc: Svc) -> dict[str, Any]:
    record = create_record(svc, body.scenario, body.seed)
    scenario = scenario_of(record)
    race_id = f"race-{uuid.uuid4().hex[:8]}"
    svc.store.save(RaceRecord(id=race_id, incident_id=record.id, left=body.left, right=body.right))
    runs = {
        lane: svc.runs.start(
            scenario,
            svc.strategy(label),
            label=label,
            bank=svc.bank_for(label),
            race_id=race_id,
            lane=lane,
            auto_approve=True,
            config=RACE_LOOP,
        )
        for lane, label in (("left", body.left), ("right", body.right))
    }
    return {
        "race_id": race_id,
        "incident_id": record.id,
        "runs": {lane: run.id for lane, run in runs.items()},
    }


@router.get("/races/{race_id}")
async def race(race_id: str, svc: Svc) -> dict[str, Any]:
    record = svc.store.race(race_id)
    if record is None:
        raise HTTPException(404, f"no race {race_id}")
    return {**record.model_dump(), "runs": [run_summary(r) for r in svc.store.runs(race_id=race_id)]}


@router.get("/races/{race_id}/stream")
async def race_stream(race_id: str, svc: Svc) -> EventSourceResponse:
    lanes: dict[str, LiveRun] = {}
    for record in svc.store.runs(race_id=race_id):
        run = svc.runs.get(record.id)
        if run is not None and record.lane is not None:
            lanes[record.lane] = run
    if not lanes:
        raise HTTPException(404, f"no race {race_id}")
    return stream(race_messages(lanes))
