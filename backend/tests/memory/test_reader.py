"""The read path: briefing from reflect with a fallback, lookups, and how both are anchored."""

from dejavu.memory.hindsight_adapter import RetainItem
from dejavu.memory.reader import lookup, triage_brief
from dejavu.sim.clock import ist
from dejavu.strategies.base import IncidentContext
from dejavu.tokens import count_tokens
from tests.memory.fakememory import FakeMemory

BANK = "test-bank"
CTX = IncidentContext.from_alert(
    "INC-4165",
    {
        "labels": {"alertname": "CheckoutLatencyP99High", "service": "checkout-api"},
        "annotations": {"description": "checkout-api p99 latency is 7,744 ms on POST /v1/checkout"},
    },
    ist("2026-08-24T19:42"),
)
BRIEF = {
    "likely_causes": [
        {
            "cause": "connection pool exhaustion after a deploy",
            "service": "ledger-svc",
            "prior": 0.7,
            "why": "INC-4127 had the same alert after ledger-svc 3.14.0",
            "precedent_incident_ids": ["INC-4127"],
            "last_seen": "2026-08-17",
            "still_valid": "yes",
        },
        {
            "cause": "acquirerx rate limiting",
            "service": "acquirerx",
            "prior": 0.2,
            "why": "INC-4133",
            "precedent_incident_ids": ["INC-4133"],
        },
    ],
    "first_checks": [
        {"check": "query_metrics ledger-svc db_pool_pending", "reason": "pinned pool means exhaustion"}
    ],
    "avoid": [
        {
            "action": "restart ledger-svc",
            "reason": "relapsed after three minutes",
            "precedent_incident_ids": ["INC-4127"],
        }
    ],
}


async def _seed(memory: FakeMemory) -> None:
    await memory.retain(
        BANK,
        [
            RetainItem(
                content="checkout p99 latency: ledger-svc HikariCP pool exhausted after deploy 3.14.0; rollback fixed it",
                context="incident outcome",
                timestamp=ist("2026-08-17T03:31"),
                document_id="inc-INC-4127-outcome",
                tags=["org:kestrel", "service:ledger-svc", "symptom:latency_p99", "kind:outcome"],
            )
        ],
    )


async def test_briefing_renders_the_structured_triage_brief() -> None:
    memory = FakeMemory(structured=BRIEF)
    await _seed(memory)
    briefing = await triage_brief(memory, BANK, CTX)
    assert "Likely causes" in briefing.text
    assert "prior 70%" in briefing.text
    assert "INC-4127" in briefing.text
    assert "Avoid" in briefing.text
    assert briefing.first_checks == ["query_metrics ledger-svc db_pool_pending"]
    assert briefing.data["based_on"]


async def test_reads_are_anchored_to_the_incident_and_scoped_by_service_and_symptom() -> None:
    memory = FakeMemory(structured=BRIEF)
    await triage_brief(memory, BANK, CTX)
    recall = memory.recalls[0]
    assert recall["types"] == ["observation"]
    assert recall["tags"] == ["service:checkout-api", "symptom:latency_p99"]
    assert recall["tags_match"] == "any"
    assert recall["query_timestamp"] == CTX.alert_at
    reflect = memory.reflects[0]
    assert reflect["budget"] == "mid"
    assert reflect["response_schema"]["title"] == "TriageBrief"


async def test_without_structured_output_it_retries_once_then_falls_back_to_observations() -> None:
    memory = FakeMemory(structured=None)
    await _seed(memory)
    briefing = await triage_brief(memory, BANK, CTX)
    assert len(memory.reflects) == 2
    assert briefing.text.startswith("What past incidents suggest")
    assert briefing.first_checks == []
    assert briefing.data["structured_error"]


async def test_lookup_is_low_budget_bounded_and_honest_when_empty() -> None:
    memory = FakeMemory()
    assert "Nothing in memory" in await lookup(memory, BANK, "x509 certificate expired", CTX)
    await _seed(memory)
    text = await lookup(memory, BANK, "ledger pool exhausted", CTX)
    assert "inc-INC-4127-outcome" in text
    assert count_tokens(text) <= 700
    assert memory.recalls[-1]["budget"] == "low"
