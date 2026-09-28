"""Foresight (spec 8, 10): pending changes and their risk reviews, with or without memory."""

import asyncio
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dejavu.api.deps import Svc
from dejavu.foresight.pending import (
    AVOIDED_WINDOW_MIN,
    PendingChange,
    find,
    impact_if_shipped,
    pending_changes,
)
from dejavu.foresight.risk_review import generic_review, memory_review, prevents
from dejavu.sim.clock import IST
from dejavu.sim.scenario import ChangeType, Scenario

router = APIRouter(tags=["foresight"])


class ReviewRequest(BaseModel):
    change_id: str | None = None
    diff_text: str | None = None  # or review any change described by hand
    service: str | None = None
    strategy: Literal["dejavu", "amnesiac"] = "dejavu"


@router.get("/changes/pending")
def pending() -> list[dict[str, Any]]:
    return [change.model_dump(mode="json") for change, _ in pending_changes()]


def _change(body: ReviewRequest) -> tuple[PendingChange, Scenario | None]:
    if body.change_id:
        found = find(body.change_id)
        if found is None:
            raise HTTPException(404, f"no pending change {body.change_id}")
        return found
    if body.diff_text and body.service:
        change = PendingChange(
            id="ad-hoc",
            type=ChangeType.DEPLOY,
            service=body.service,
            author="the reviewer",
            planned_at=datetime.now(IST),
            summary=body.diff_text.strip().splitlines()[0][:120],
            details={"diff": body.diff_text.strip()},
        )
        return change, None
    raise HTTPException(422, "give a change_id, or a diff_text and its service")


@router.post("/foresight/review")
async def review(body: ReviewRequest, svc: Svc) -> dict[str, Any]:
    """The review, and whether following it would have prevented the latent incident (spec 8)."""
    change, latent = _change(body)
    if body.strategy == "dejavu":
        result = await memory_review(svc.memory, svc.settings.dejavu_bank_live, change)
    else:
        result = await generic_review(await svc.caller(), change)
    prevented = prevents(result.review, latent)
    avoided = None
    if prevented and latent is not None:
        avoided = await asyncio.to_thread(impact_if_shipped, latent, svc.runs.telemetry_root)
    return {
        "change": change.model_dump(mode="json"),
        "result": result.model_dump(mode="json"),
        "prevented": prevented,
        "inr_avoided": round(avoided) if avoided is not None else None,
        "window_min": AVOIDED_WINDOW_MIN,
    }
