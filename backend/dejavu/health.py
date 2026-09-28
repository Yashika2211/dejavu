"""Reachability checks for DejaVu's two external dependencies: Groq and Hindsight.

Run as a script (`python -m dejavu.health`) to print a status table; exit code 1 if either
dependency is unusable.
"""

import asyncio
import sys
import time
from typing import Any

import httpx
from pydantic import BaseModel, Field
from rich.console import Console
from rich.table import Table

from dejavu.config import Settings, get_settings


class CheckResult(BaseModel):
    """Outcome of one dependency check."""

    name: str
    ok: bool
    detail: str
    latency_ms: float | None = None
    data: dict[str, Any] = Field(default_factory=dict)


def _bearer(secret: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret.get_secret_value()}"} if secret else {}


async def list_groq_models(client: httpx.AsyncClient, settings: Settings) -> set[str]:
    """Return the ids of all active models the Groq key can use."""
    resp = await client.get(f"{settings.groq_base_url}/models", headers=_bearer(settings.groq_api_key))
    resp.raise_for_status()
    return {m["id"] for m in resp.json().get("data", []) if m.get("active", True)}


async def check_groq(client: httpx.AsyncClient, settings: Settings) -> CheckResult:
    """Groq is healthy when the key works and the primary model is available."""
    if settings.groq_api_key is None:
        return CheckResult(name="groq", ok=False, detail="GROQ_API_KEY not set")
    start = time.perf_counter()
    try:
        available = await list_groq_models(client, settings)
    except httpx.HTTPError as exc:
        return CheckResult(name="groq", ok=False, detail=f"list models failed: {exc!r}")
    latency = (time.perf_counter() - start) * 1000
    missing = [m for m in settings.configured_models if m not in available]
    ok = settings.llm_primary in available
    detail = f"{len(available)} models; configured missing: {', '.join(missing) or 'none'}"
    return CheckResult(
        name="groq",
        ok=ok,
        detail=detail,
        latency_ms=latency,
        data={"available": sorted(available), "missing": missing},
    )


async def check_hindsight(client: httpx.AsyncClient, settings: Settings) -> CheckResult:
    """Hindsight is healthy when `/version` answers and our credentials can list banks.

    `/version` is public on Cloud, so on its own it says nothing about the key.
    """
    base = settings.hindsight_base_url.rstrip("/")
    headers = _bearer(settings.hindsight_api_key)
    start = time.perf_counter()
    try:
        resp = await client.get(f"{base}/version", headers=headers)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        return CheckResult(name="hindsight", ok=False, detail=f"version failed: {exc!r}")
    latency = (time.perf_counter() - start) * 1000
    try:
        banks = await client.get(f"{base}/v1/default/banks", headers=headers, params={"limit": 1})
    except httpx.HTTPError as exc:
        return CheckResult(name="hindsight", ok=False, detail=f"listing banks failed: {exc!r}")
    if banks.status_code in (401, 403):
        missing = (
            "HINDSIGHT_API_KEY not set"
            if settings.hindsight_api_key is None
            else "HINDSIGHT_API_KEY rejected"
        )
        return CheckResult(name="hindsight", ok=False, detail=missing, latency_ms=latency)
    if banks.is_error:
        return CheckResult(
            name="hindsight", ok=False, detail=f"listing banks failed: HTTP {banks.status_code}"
        )
    body = resp.json()
    features = body.get("features", {})
    off = sorted(k for k, v in features.items() if v is False)
    detail = f"api {body.get('api_version', '?')}; features off: {', '.join(off) or 'none'}"
    return CheckResult(name="hindsight", ok=True, detail=detail, latency_ms=latency, data=body)


async def run_checks(settings: Settings) -> list[CheckResult]:
    """Run both checks concurrently."""
    async with httpx.AsyncClient(timeout=settings.http_timeout_s) as client:
        return list(await asyncio.gather(check_groq(client, settings), check_hindsight(client, settings)))


def main() -> int:
    """Print a status table and return a process exit code."""
    results = asyncio.run(run_checks(get_settings()))
    table = Table(title="DejaVu dependency health")
    for col in ("service", "status", "latency", "detail"):
        table.add_column(col)
    for r in results:
        latency = f"{r.latency_ms:.0f} ms" if r.latency_ms is not None else "-"
        table.add_row(r.name, "[green]OK[/]" if r.ok else "[red]FAIL[/]", latency, r.detail)
    Console().print(table)
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
