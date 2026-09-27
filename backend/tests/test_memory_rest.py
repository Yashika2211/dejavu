import json

import httpx
import pytest
import respx

from dejavu.memory.rest import HindsightRest, OperationTimeoutError

BASE = "https://hindsight.test/v1/default/banks/kestrel-ops-live"


@pytest.fixture
async def rest():
    async with HindsightRest("https://hindsight.test/", "k") as client:
        yield client


@respx.mock
async def test_wait_for_operation_polls_until_terminal(rest: HindsightRest) -> None:
    route = respx.get(f"{BASE}/operations/op-1").mock(
        side_effect=[
            httpx.Response(200, json={"operation_id": "op-1", "status": "pending"}),
            httpx.Response(200, json={"operation_id": "op-1", "status": "processing"}),
            httpx.Response(200, json={"operation_id": "op-1", "status": "completed"}),
        ]
    )
    status = await rest.wait_for_operation("kestrel-ops-live", "op-1", poll_s=0)
    assert status["status"] == "completed"
    assert route.call_count == 3
    assert route.calls.last.request.headers["Authorization"] == "Bearer k"


@respx.mock
async def test_wait_for_operation_times_out(rest: HindsightRest) -> None:
    respx.get(f"{BASE}/operations/op-2").respond(json={"operation_id": "op-2", "status": "pending"})
    with pytest.raises(OperationTimeoutError):
        await rest.wait_for_operation("kestrel-ops-live", "op-2", timeout_s=0, poll_s=0)


@respx.mock
async def test_invalidate_and_restore_send_state(rest: HindsightRest) -> None:
    route = respx.patch(f"{BASE}/memories/m-9").respond(json={"id": "m-9"})
    await rest.set_memory_state("kestrel-ops-live", "m-9", "invalidated", reason="wrong root cause")
    await rest.set_memory_state("kestrel-ops-live", "m-9", "valid")
    bodies = [json.loads(call.request.content) for call in route.calls]
    assert bodies == [{"state": "invalidated", "reason": "wrong root cause"}, {"state": "valid"}]


@respx.mock
async def test_list_memories_drops_none_filters(rest: HindsightRest) -> None:
    route = respx.get(f"{BASE}/memories/list").respond(json={"items": [], "total": 0})
    await rest.list_memories("kestrel-ops-live", document_id="pm-1", type=None, limit=5)
    params = route.calls.last.request.url.params
    assert dict(params) == {"document_id": "pm-1", "limit": "5"}


@respx.mock
async def test_document_ids_are_url_quoted(rest: HindsightRest) -> None:
    route = respx.get(f"{BASE}/documents/pm%2Fodd%20id").respond(json={"id": "pm/odd id"})
    await rest.get_document("kestrel-ops-live", "pm/odd id")
    assert route.called


@respx.mock
async def test_http_errors_raise(rest: HindsightRest) -> None:
    respx.get(f"{BASE}/stats").respond(status_code=404)
    with pytest.raises(httpx.HTTPStatusError):
        await rest.stats("kestrel-ops-live")
