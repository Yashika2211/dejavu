"""Foresight: pending changes are their latent incidents' triggers, reviews validate against the
schema with or without memory, and prevention follows the fixed rule of spec 8."""

from dejavu.foresight.pending import find, impact_if_shipped, pending_changes
from dejavu.foresight.risk_review import RiskReview, generic_review, memory_review, prevents
from dejavu.llm.toolcalling import ToolCaller
from dejavu.sim.scenario import archetype_ids
from tests.agent.test_loop import call
from tests.memory.fakememory import FakeMemory

HOLD = {
    "risk": "high",
    "summary": "Adds a remote call inside the posting transaction, like the pool exhaustions in August.",
    "failure_modes": ["ledger connection pool exhaustion"],
    "precedents": [
        {"incident_id": "INC-4127", "date": "2026-08-17", "resemblance": "per-entry call in @Transactional"}
    ],
    "recommended_action": "hold",
    "safeguards": ["canary_rollout", "pool_config_review"],
}


def test_pending_changes_show_the_change_and_nothing_of_what_it_would_cause() -> None:
    changes = pending_changes()
    assert [c.id for c, _ in changes][:2] == ["pending-ledger-loyalty", "pending-refund-sms"]
    assert sum(latent is not None for _, latent in changes) == 4
    for change, latent in changes:
        shown = change.model_dump_json()
        assert not any(archetype in shown for archetype in archetype_ids())
        if latent is not None:
            assert change.planned_at < latent.alert_at
            assert change.service in shown


def test_prevention_needs_a_guarded_action_and_a_matching_safeguard() -> None:
    _, latent = find("pending-ledger-loyalty") or (None, None)
    assert latent is not None
    hold = RiskReview.model_validate(HOLD)
    assert prevents(hold, latent) is True
    assert prevents(hold.model_copy(update={"recommended_action": "ship"}), latent) is False
    assert prevents(hold.model_copy(update={"safeguards": ["revert"]}), latent) is False
    assert prevents(hold, None) is None
    assert prevents(None, latent) is None


def test_the_latent_incident_puts_payments_at_risk(telemetry_root) -> None:
    _, latent = find("pending-ledger-loyalty") or (None, None)
    assert latent is not None
    assert impact_if_shipped(latent, telemetry_root) > 0


async def test_dejavu_reviews_from_memory_with_provenance() -> None:
    memory = FakeMemory(structured=HOLD)
    await memory.retain("bank", [])
    change, _ = find("pending-ledger-loyalty") or (None, None)
    assert change is not None
    result = await memory_review(memory, "bank", change)
    assert result.review is not None
    assert result.review.precedents[0].incident_id == "INC-4127"
    assert memory.reflects[-1]["tags"] == ["service:ledger-svc"]
    assert memory.recalls[0]["query_timestamp"] == change.planned_at  # the evidence recall


async def test_a_review_that_does_not_validate_is_reported_not_invented() -> None:
    change, _ = find("pending-ledger-loyalty") or (None, None)
    assert change is not None
    result = await memory_review(FakeMemory(structured={"risk": "catastrophic"}), "bank", change)
    assert result.review is None
    assert result.error


async def test_the_amnesiac_reviews_from_the_model_alone(make_client, groq) -> None:
    change, _ = find("pending-retry-flag") or (None, None)
    assert change is not None
    groq.add(
        call(
            "submit_review",
            "flag flip",
            risk="medium",
            summary="Retries amplify load.",
            recommended_action="ship",
            safeguards=[],
        )
    )
    client, _ = make_client()
    result = await generic_review(ToolCaller(client, ["openai/gpt-oss-120b"]), change)
    assert result.review is not None
    assert result.review.recommended_action == "ship"
    prompt = groq.requests[0]["messages"][1]["content"]
    assert "checkout.retry_policy" in prompt
    assert "INC-" not in prompt
