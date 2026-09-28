"""Races, memory screens, eval results and the demo reset over the API."""

import json
from datetime import UTC, datetime
from pathlib import Path

from dejavu.documents import day0_documents
from dejavu.memory.bank_setup import setup_bank
from dejavu.memory.hindsight_adapter import BeliefChange
from dejavu.memory.writer import document_item
from tests.agent.test_loop import diagnosis
from tests.api.harness import Api, sse


async def test_a_race_streams_both_lanes_and_keeps_the_scores(api: Api) -> None:
    api.groq.add(diagnosis("db_pool_exhaustion", "ledger-svc"), diagnosis("db_pool_exhaustion", "ledger-svc"))
    started = (await api.http.post("/race", json={"left": "amnesiac"})).json()
    assert started["incident_id"] == "INC-4499"

    events = sse((await api.http.get(f"/races/{started['race_id']}/stream")).text)
    scored = {d["lane"]: d["data"] for t, d in events if t == "scored"}
    assert set(scored) == {"left", "right"}
    assert {d["lane"] for t, d in events if t == "briefing"} == {"right"}  # only DejaVu remembers
    assert events[-1][0] == "end"

    race = (await api.http.get(f"/races/{started['race_id']}")).json()
    assert {(r["lane"], r["strategy"], r["status"]) for r in race["runs"]} == {
        ("left", "amnesiac", "done"),
        ("right", "dejavu", "done"),
    }
    assert (await api.http.post("/race", json={"left": "dejavu"})).status_code == 422


async def test_runbooks_timeline_explorer_and_curation(api: Api) -> None:
    bank = api.services.settings.dejavu_bank_live
    await setup_bank(api.memory, bank)
    await api.memory.retain(bank, [document_item(d) for d in day0_documents()])
    api.memory.history[(bank, "triage-playbook")] = [
        BeliefChange(previous_content="restart ledger-svc first", changed_at=datetime(2026, 9, 6, tzinfo=UTC))
    ]

    models = (await api.http.get("/memory/models")).json()
    assert "triage-playbook" in {m["id"] for m in models}
    model = (await api.http.get("/memory/models/triage-playbook")).json()
    assert [v["content"] for v in model["versions"]][1] == "restart ledger-svc first"
    assert model["versions"][0]["until"] is None

    hits = (await api.http.get("/memory/search", params={"q": "hikaricp pool connection"})).json()
    target = hits[0]["id"]
    assert (await api.http.post(f"/memory/{target}/invalidate", json={"reason": "stale"})).json()[
        "state"
    ] == "invalidated"
    retired = (await api.http.get("/memory/search", params={"state": "invalidated"})).json()
    assert [m["id"] for m in retired] == [target]
    assert target not in {
        h["id"]
        for h in (await api.http.get("/memory/search", params={"q": "hikaricp pool connection"})).json()
    }
    await api.http.post(f"/memory/{target}/restore")
    assert (await api.http.get("/memory/search", params={"state": "invalidated"})).json() == []

    answer = (await api.http.post("/ask", json={"question": "why does checkout latency spike?"})).json()
    assert answer["answer"]
    assert (await api.http.post("/ask", json={"question": " "})).status_code == 422


async def test_memory_offline_is_a_503_the_ui_can_show(api: Api) -> None:
    api.memory.down = True
    response = await api.http.get("/memory/models")
    assert response.status_code == 503
    assert response.json()["detail"] == "Memory offline: running without memory"


def _write_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True)
    run = {
        "run_id": "g42-test",
        "seed": 42,
        "n": 24,
        "strategies": ["amnesiac"],
        "models": ["m"],
        "started_at": "x",
    }
    (run_dir / "run.json").write_text(json.dumps(run))
    (run_dir / "summary.json").write_text(json.dumps({"complete": False, "incidents_done": {"amnesiac": 3}}))
    (run_dir / "chart_data.json").write_text(json.dumps({"incidents": []}))


async def test_eval_results_come_from_the_run_directory(api: Api) -> None:
    _write_run(api.services.eval_dir / "g42-test")
    runs = (await api.http.get("/eval/runs")).json()
    assert [(r["run_id"], r["complete"], r["incidents_done"]) for r in runs] == [
        ("g42-test", False, {"amnesiac": 3})
    ]
    detail = (await api.http.get("/eval/runs/g42-test")).json()
    assert detail["chart_data"] == {"incidents": []}
    assert (await api.http.get("/eval/runs/nope")).status_code == 404


async def test_demo_reset_reclones_the_live_bank(api: Api) -> None:
    settings = api.services.settings
    await api.memory.retain(settings.dejavu_bank_trained, [document_item(next(iter(day0_documents())))])
    body = (await api.http.post("/demo/reset")).json()
    assert body == {"live": settings.dejavu_bank_live, "cloned_from": settings.dejavu_bank_trained}
    assert len(api.memory.items[settings.dejavu_bank_live]) == 1
