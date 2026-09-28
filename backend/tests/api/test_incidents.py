"""Incidents over the API: creation, a streamed investigation, approvals, feedback that teaches."""

import asyncio

from dejavu.api.scenarios import FIRST_LIVE_NUMBER
from tests.agent.test_loop import call, diagnosis
from tests.api.harness import Api, sse

DEMO = "race-pool-after-pgbouncer"


async def test_health_reports_what_is_degraded(api: Api) -> None:
    body = (await api.http.get("/health")).json()
    assert body["mode"] == "live"
    assert body["degraded"] == {"llm": False, "memory": True}


async def test_incidents_come_from_demos_archetypes_or_a_surprise(api: Api) -> None:
    demo = (await api.http.post("/incidents", json={"scenario": DEMO})).json()["incident_id"]
    again = (await api.http.post("/incidents", json={"scenario": DEMO})).json()["incident_id"]
    assert demo == again == "INC-4499"
    made = (await api.http.post("/incidents", json={"scenario": "cert_expiry", "seed": 7})).json()[
        "incident_id"
    ]
    assert int(made.removeprefix("INC-")) >= FIRST_LIVE_NUMBER
    assert (await api.http.post("/incidents", json={"scenario": "nope"})).status_code == 422

    listed = await api.http.get("/incidents")
    assert {i["id"] for i in listed.json()} == {demo, made}
    assert "cert_expiry" not in listed.text  # the ground truth stays hidden
    detail = (await api.http.get(f"/incidents/{made}")).json()
    assert detail["alert"]["name"]
    assert detail["runs"] == []


async def test_an_investigation_streams_and_is_recorded(api: Api) -> None:
    incident = (await api.http.post("/incidents", json={"scenario": DEMO})).json()["incident_id"]
    api.groq.add(
        call("query_metrics", "pool pressure?", service="ledger-svc", metric="db_pool_pending"),
        diagnosis("db_pool_exhaustion", "ledger-svc"),
    )
    body = (await api.http.get(f"/incidents/{incident}/stream", params={"strategy": "amnesiac"})).text
    types = [t for t, _ in sse(body)]
    assert types[0] == "run_started"
    assert {"tool_call", "tool_result", "diagnosis", "scored"} <= set(types)
    assert types[-1] == "end"

    runs = (await api.http.get(f"/incidents/{incident}")).json()["runs"]
    assert [(r["strategy"], r["status"]) for r in runs] == [("amnesiac", "done")]
    assert runs[0]["score"]["correct"]

    replay = (await api.http.get(f"/incidents/{incident}/stream", params={"strategy": "amnesiac"})).text
    assert [t for t, _ in sse(replay)] == types  # the same run again, no new model calls
    assert (
        await api.http.get(f"/incidents/{incident}/stream", params={"strategy": "nope"})
    ).status_code == 422


async def test_a_critical_remediation_waits_for_the_human(api: Api) -> None:
    incident = (await api.http.post("/incidents", json={"scenario": DEMO})).json()["incident_id"]
    api.groq.add(
        call("run_remediation", "restart the primary", action="restart", target="postgres-ledger"),
        diagnosis("db_pool_exhaustion", "ledger-svc"),
    )
    streaming = asyncio.create_task(
        api.http.get(f"/incidents/{incident}/stream", params={"strategy": "amnesiac"})
    )
    for _ in range(200):
        live = list(api.services.runs.live.values())
        if live and live[0].pending_approvals:
            break
        await asyncio.sleep(0.05)
    run = live[0]
    assert run.pending_approvals == ["r1"]
    assert (
        await api.http.post(f"/runs/{run.id}/approve", json={"action_id": "r9", "approved": True})
    ).status_code == 409
    assert (
        await api.http.post(f"/runs/{run.id}/approve", json={"action_id": "r1", "approved": False})
    ).status_code == 200

    events = sse((await streaming).text)
    approvals = [d["data"] for t, d in events if t == "approval"]
    assert approvals == [{"action_id": "r1", "approved": False, "by": "human"}]
    assert not [t for t, _ in events if t == "remediation_applied"]


async def test_feedback_teaches_the_live_bank(api: Api) -> None:
    incident = (await api.http.post("/incidents", json={"scenario": DEMO})).json()["incident_id"]
    api.groq.add(diagnosis("db_pool_exhaustion", "ledger-svc"))
    await api.http.get(f"/incidents/{incident}/stream", params={"strategy": "dejavu"})

    answer = await api.http.post(
        f"/incidents/{incident}/feedback",
        json={"correct": True, "notes": "PgBouncer default_pool_size was the fix."},
    )
    assert answer.status_code == 202
    assert answer.json() == {"learning": True}
    live_bank = api.services.settings.dejavu_bank_live
    docs = {i.document_id: i for i in api.memory.items[live_bank]}
    assert {f"fb-{incident}", f"inc-{incident}-investigation", f"inc-{incident}-outcome"} <= set(docs)
    assert "Priya Raman (on-call) confirmed" in docs[f"fb-{incident}"].content
    feedback = (await api.http.get(f"/incidents/{incident}")).json()["feedback"]
    assert [(f["correct"], f["retained"]) for f in feedback] == [(True, True)]


async def test_the_picker_and_the_change_log(api: Api) -> None:
    offered = (await api.http.get("/scenarios")).json()
    assert DEMO in offered["demos"]
    assert "cert_expiry" in offered["archetypes"]
    assert "pending" not in offered["archetypes"]

    incident = (await api.http.post("/incidents", json={"scenario": DEMO})).json()["incident_id"]
    changes = (await api.http.get(f"/incidents/{incident}/changes")).json()
    assert changes
    assert changes[0]["at"] >= changes[-1]["at"]  # newest first
    assert any(c["service"] == "ledger-svc" and c["type"] == "deploy" for c in changes)
