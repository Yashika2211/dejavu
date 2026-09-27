"""Async REST client for Hindsight endpoints the high-level SDK (v0.10.1) does not wrap.

Covers operation polling, memory curation (invalidate / restore), memory listing, the memory
graph, entities, bank stats, consolidation and observation scopes. Everything else goes
through `hindsight_client.Hindsight`.
"""

import asyncio
import time
from types import TracebackType
from typing import Any, Literal, Self
from urllib.parse import quote

import httpx

TERMINAL_STATES = frozenset({"completed", "failed", "cancelled"})

MemoryState = Literal["valid", "invalidated"]


class OperationTimeoutError(TimeoutError):
    """An async Hindsight operation did not reach a terminal state in time."""


class HindsightRest:
    """Minimal typed wrapper around the Hindsight HTTP API (tenant `default`)."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        *,
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._base = base_url.rstrip("/")
        self._headers = headers

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    def _bank(self, bank_id: str) -> str:
        return f"{self._base}/v1/default/banks/{quote(bank_id, safe='')}"

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        resp = await self._client.request(method, url, params=clean, json=json, headers=self._headers)
        resp.raise_for_status()
        return resp.json() if resp.content else None

    # operations -------------------------------------------------------------------------

    async def operation(self, bank_id: str, operation_id: str) -> dict[str, Any]:
        """Current status of one async operation."""
        return await self._request("GET", f"{self._bank(bank_id)}/operations/{operation_id}")

    async def wait_for_operation(
        self, bank_id: str, operation_id: str, *, timeout_s: float = 300.0, poll_s: float = 1.0
    ) -> dict[str, Any]:
        """Poll until the operation is completed, failed or cancelled."""
        deadline = time.monotonic() + timeout_s
        while True:
            status = await self.operation(bank_id, operation_id)
            if status["status"] in TERMINAL_STATES:
                return status
            if time.monotonic() >= deadline:
                raise OperationTimeoutError(f"operation {operation_id} still {status['status']}")
            await asyncio.sleep(poll_s)

    # memories ---------------------------------------------------------------------------

    async def list_memories(self, bank_id: str, **filters: Any) -> dict[str, Any]:
        """List memory units; filters map to the endpoint's query params (type, state, tags...)."""
        return await self._request("GET", f"{self._bank(bank_id)}/memories/list", params=filters)

    async def get_memory(self, bank_id: str, memory_id: str) -> dict[str, Any]:
        return await self._request("GET", f"{self._bank(bank_id)}/memories/{memory_id}")

    async def memory_history(self, bank_id: str, memory_id: str) -> Any:
        """Version history of an observation (how a belief changed)."""
        return await self._request("GET", f"{self._bank(bank_id)}/memories/{memory_id}/history")

    async def set_memory_state(
        self, bank_id: str, memory_id: str, state: MemoryState, reason: str | None = None
    ) -> Any:
        """Curate a world/experience fact: `invalidated` soft-retires it, `valid` restores it."""
        body: dict[str, Any] = {"state": state}
        if reason:
            body["reason"] = reason
        return await self._request("PATCH", f"{self._bank(bank_id)}/memories/{memory_id}", json=body)

    async def get_document(self, bank_id: str, document_id: str) -> dict[str, Any]:
        """Stored document, including its (Memory Defense-scrubbed) original text."""
        return await self._request(
            "GET", f"{self._bank(bank_id)}/documents/{quote(document_id, safe='')}"
        )

    # graph and entities -----------------------------------------------------------------

    async def graph(self, bank_id: str, **params: Any) -> dict[str, Any]:
        return await self._request("GET", f"{self._bank(bank_id)}/graph", params=params)

    async def entities(self, bank_id: str, *, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        return await self._request(
            "GET", f"{self._bank(bank_id)}/entities", params={"limit": limit, "offset": offset}
        )

    # bank-level -------------------------------------------------------------------------

    async def stats(self, bank_id: str) -> dict[str, Any]:
        """Node / link / observation counts plus pending operations and consolidation backlog."""
        return await self._request("GET", f"{self._bank(bank_id)}/stats")

    async def consolidate(self, bank_id: str) -> dict[str, Any]:
        """Trigger consolidation now; returns `{operation_id, deduplicated}`."""
        return await self._request("POST", f"{self._bank(bank_id)}/consolidate", json={})

    async def observation_scopes(self, bank_id: str, *, limit: int = 100) -> dict[str, Any]:
        return await self._request(
            "GET", f"{self._bank(bank_id)}/observations/scopes", params={"limit": limit}
        )
