"""Foresight over the API: the pending list and a review that prevents the latent incident."""

from tests.agent.test_loop import call
from tests.api.harness import Api
from tests.foresight.test_foresight import HOLD


async def test_pending_changes_are_listed(api: Api) -> None:
    changes = (await api.http.get("/changes/pending")).json()
    assert {c["id"] for c in changes} >= {"pending-ledger-loyalty", "pending-refund-sms"}


async def test_holding_the_risky_deploy_prevents_the_incident(api: Api) -> None:
    api.memory.structured = HOLD
    body = (await api.http.post("/foresight/review", json={"change_id": "pending-ledger-loyalty"})).json()
    assert body["result"]["review"]["recommended_action"] == "hold"
    assert body["prevented"] is True
    assert body["inr_avoided"] > 0
    assert body["window_min"] == 30


async def test_the_baseline_ships_it_and_prevents_nothing(api: Api) -> None:
    api.groq.add(
        call("submit_review", "looks fine", risk="low", summary="Small change.", recommended_action="ship")
    )
    body = (
        await api.http.post(
            "/foresight/review", json={"change_id": "pending-ledger-loyalty", "strategy": "amnesiac"}
        )
    ).json()
    assert body["prevented"] is False
    assert body["inr_avoided"] is None


async def test_a_harmless_change_has_nothing_to_prevent(api: Api) -> None:
    api.memory.structured = {**HOLD, "risk": "low", "recommended_action": "ship", "safeguards": []}
    body = (await api.http.post("/foresight/review", json={"change_id": "pending-refund-sms"})).json()
    assert body["prevented"] is None
    assert (await api.http.post("/foresight/review", json={"change_id": "nope"})).status_code == 404
    assert (await api.http.post("/foresight/review", json={})).status_code == 422
