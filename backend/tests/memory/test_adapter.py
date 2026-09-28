"""The adapter's REST-backed calls: memory listing for the Explorer, curation, degraded mode."""

import json

import httpx
import pytest
import respx

from dejavu.memory.hindsight_adapter import HindsightMemory, MemoryUnavailableError

BASE = "https://hindsight.test/v1/default/banks/kestrel-ops-live"


@pytest.fixture
async def memory(settings):
    backend = HindsightMemory(settings)
    yield backend
    await backend.aclose()


@respx.mock
async def test_listing_maps_units_and_filters(memory: HindsightMemory) -> None:
    route = respx.get(f"{BASE}/memories/list").respond(
        json={
            "items": [
                {
                    "id": "m1",
                    "text": "INC-3517 was blamed on DNS",
                    "fact_type": "world",
                    "mentioned_at": "2026-04-02T10:00:00+05:30",
                    "document_id": "pm-hist-3517",
                    "tags": ["service:checkout-api"],
                    "state": "invalidated",
                    "invalidation_reason": "it was acquirerx",
                }
            ],
            "total": 1,
        }
    )
    units = await memory.list_memories("kestrel-ops-live", query="dns", state="invalidated")
    assert [(u.id, u.type, u.state, u.invalidation_reason) for u in units] == [
        ("m1", "world", "invalidated", "it was acquirerx")
    ]
    assert units[0].when == "2026-04-02T10:00:00+05:30"
    params = route.calls.last.request.url.params
    assert (params["q"], params["state"], params["limit"]) == ("dns", "invalidated", "50")
    assert "type" not in params


@respx.mock
async def test_invalidation_sends_the_reason(memory: HindsightMemory) -> None:
    route = respx.patch(f"{BASE}/memories/m1").respond(json={"id": "m1", "state": "invalidated"})
    await memory.set_memory_state("kestrel-ops-live", "m1", "invalidated", reason="wrong root cause")
    assert json.loads(route.calls.last.request.content) == {
        "state": "invalidated",
        "reason": "wrong root cause",
    }


@respx.mock
async def test_server_errors_become_memory_unavailable(memory: HindsightMemory) -> None:
    respx.get(f"{BASE}/memories/list").mock(return_value=httpx.Response(503))
    with pytest.raises(MemoryUnavailableError):
        await memory.list_memories("kestrel-ops-live")
