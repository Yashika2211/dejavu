"""POST /demo/reset: re-clone the live bank from the trained snapshot (spec 6.1, 13)."""

from fastapi import APIRouter

from dejavu.api.deps import Svc
from dejavu.memory.snapshots import snapshot

router = APIRouter(tags=["demo"])


@router.post("/demo/reset")
async def reset(svc: Svc) -> dict[str, str]:
    source, target = svc.settings.dejavu_bank_trained, svc.settings.dejavu_bank_live
    await snapshot(svc.memory, source, target)
    return {"live": target, "cloned_from": source}
