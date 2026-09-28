"""The write path follows the conventions: tags, scopes, timestamps, first person, redaction."""

import pytest

from dejavu.agent.loop import Investigator
from dejavu.documents import day0_documents, incident_documents, migration_documents
from dejavu.eval.grading import grade
from dejavu.llm.toolcalling import ToolCaller
from dejavu.memory.writer import AGENT_CONTEXT, day0_payloads, document_item, incident_items
from dejavu.runner import build_resolution, known_categories
from dejavu.sim.schedule import entry_for, gauntlet
from dejavu.strategies.amnesiac import Amnesiac
from dejavu.strategies.base import Resolution
from tests.agent.test_loop import call, diagnosis

INCIDENT_ONE = next(s for s in gauntlet() if entry_for(s).n == 1)


def _assert_conventions(item) -> None:
    assert "org:kestrel" in item.tags
    assert any(t.startswith("kind:") for t in item.tags)
    assert not any(t.startswith("incident:") for t in item.tags), item.tags
    assert item.timestamp.tzinfo is not None


def test_day0_items_keep_their_dates_and_two_become_pdfs(tmp_path) -> None:
    docs = list(day0_documents())
    items, files = day0_payloads(docs, tmp_path)
    assert len(items) + len(files) == len(docs)
    assert len(files) == 2
    assert all(f.path.read_bytes().startswith(b"%PDF") for f in files)
    by_id = {d.id: d for d in docs}
    for item in items:
        _assert_conventions(item)
        assert item.timestamp == by_id[item.document_id].date


def test_historical_postmortems_scope_observations_per_service_and_symptom() -> None:
    doc = next(d for d in day0_documents() if d.id == "pm-hist-3902")
    item = document_item(doc)
    assert item.context == "historical postmortem by Marcus Oyelaran"
    assert ["service:ledger-svc"] in item.observation_scopes
    assert ["symptom:latency_p99"] in item.observation_scopes
    assert ("Marcus Oyelaran", "PERSON") in item.entities


def test_migration_documents_are_tagged_as_migrations() -> None:
    for doc in migration_documents():
        item = document_item(doc)
        _assert_conventions(item)
        assert "kind:migration" in item.tags


@pytest.fixture
async def resolution(make_client, groq, open_world) -> Resolution:
    world = open_world(INCIDENT_ONE)
    groq.add(
        call("search_logs", "look for pool errors", service="ledger-svc", level="WARN"),
        call("run_remediation", "roll back the deploy", action="restart", target="ledger-svc"),
        call("run_remediation", "that relapsed; roll back", action="rollback", target="ledger-svc"),
        diagnosis("db_pool_exhaustion", "ledger-svc"),
    )
    client, _ = make_client()
    run = await Investigator(ToolCaller(client, ["openai/gpt-oss-120b"]), Amnesiac()).run(world)
    score = grade(run, INCIDENT_ONE, world, known_categories())
    return build_resolution(run, score, world, incident_documents(1))


async def test_incident_items_cover_the_write_path(resolution) -> None:
    items = incident_items(resolution, resolution.changes)
    ids = [i.document_id for i in items]
    assert ids.count("inc-INC-4127-timeline") == 2
    assert all(i.update_mode == "append" for i in items if i.document_id == "inc-INC-4127-timeline")
    for doc_id in (
        "inc-INC-4127-investigation",
        "inc-INC-4127-outcome",
        "changes-INC-4127",
        "fb-INC-4127",
        "pm-INC-4127",
    ):
        assert doc_id in ids
    for item in items:
        _assert_conventions(item)
        assert item.metadata.get("incident_id") == "INC-4127"
        assert item.observation_scopes
    assert [i.timestamp for i in items] == sorted(i.timestamp for i in items)


async def test_the_investigation_log_is_first_person_and_admits_mistakes(resolution) -> None:
    log = next(
        i for i in incident_items(resolution, resolution.changes) if i.document_id.endswith("investigation")
    )
    assert log.context == AGENT_CONTEXT.format(incident="INC-4127")
    assert log.content.startswith("I was paged at 03:07 IST")
    assert "brief relief, then relapse" in log.content
    assert "fixed it" in log.content


async def test_outcome_states_what_worked_and_the_cost(resolution) -> None:
    outcome = next(
        i for i in incident_items(resolution, resolution.changes) if i.document_id.endswith("outcome")
    )
    assert "rollback ledger-svc: fixed it" in outcome.content
    assert "restart ledger-svc: brief relief, then relapse" in outcome.content
    assert "MTTR" in outcome.content


async def test_secrets_never_reach_memory(resolution) -> None:
    token = "eyJhbGciOiJIUzI1NiJ9" + ".eyJzdWIiOiJ0ZXN0MTIzNDU2In0" + ".c2lnbmF0dXJlLWJ5dGVzLWhlcmU"
    leaky = resolution.model_copy(
        update={
            "steps": [
                resolution.steps[0].model_copy(update={"output": f"header\nAuthorization: Bearer {token}"}),
                *resolution.steps[1:],
            ]
        }
    )
    for item in incident_items(leaky, leaky.changes):
        assert token not in item.content
