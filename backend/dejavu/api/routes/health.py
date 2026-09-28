"""GET /health: Groq and Hindsight reachability, degraded flags and the demo mode (spec 10, 13)."""

from typing import Any

from fastapi import APIRouter

from dejavu.api.deps import Svc

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(svc: Svc) -> dict[str, Any]:
    checks = {c.name: c for c in await svc.checks()}
    groq, hindsight = checks.get("groq"), checks.get("hindsight")
    return {
        "mode": svc.settings.demo_mode,
        "checks": [c.model_dump() for c in checks.values()],
        "degraded": {"llm": not (groq and groq.ok), "memory": not (hindsight and hindsight.ok)},
    }
