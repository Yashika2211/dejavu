"""DejaVu in the loop: the briefing is injected, recall_memory works, resolutions are retained,
and a memory outage degrades to an ordinary investigation instead of failing it."""

from dejavu.agent.loop import Investigator
from dejavu.documents import incident_documents
from dejavu.eval.grading import grade
from dejavu.llm.toolcalling import ToolCaller
from dejavu.runner import build_resolution, known_categories
from dejavu.sim.schedule import entry_for, gauntlet
from dejavu.strategies.dejavu import DejaVu
from tests.agent.test_loop import call, diagnosis
from tests.memory.fakememory import FakeMemory
from tests.memory.test_reader import BRIEF

INCIDENTS = {entry_for(s).n: s for s in gauntlet()}


def _agent(make_client, strategy) -> Investigator:
    client, _ = make_client()
    return Investigator(ToolCaller(client, ["openai/gpt-oss-120b"]), strategy)


async def test_briefing_and_recall_memory_in_the_loop(make_client, groq, open_world) -> None:
    memory = FakeMemory(structured=BRIEF)
    strategy = DejaVu(memory, "bank")
    groq.add(
        call("recall_memory", "seen this before?", query="ledger pool exhausted after deploy"),
        call("query_metrics", "the briefing's first check", service="ledger-svc", metric="db_pool_pending"),
        diagnosis("db_pool_exhaustion", "ledger-svc"),
    )
    result = await _agent(make_client, strategy).run(open_world(INCIDENTS[5]))

    first_request = groq.requests[0]
    assert "=== MEMORY BRIEFING" in first_request["messages"][1]["content"]
    assert "recall_memory" in [t["function"]["name"] for t in first_request["tools"]]
    assert result.steps[0].memory_moment
    assert result.steps[1].memory_moment  # it followed the briefing's first check
    assert result.briefing is not None


async def test_resolution_is_retained_and_settled(make_client, groq, open_world) -> None:
    memory = FakeMemory(structured=BRIEF)
    strategy = DejaVu(memory, "bank")
    world = open_world(INCIDENTS[1])
    groq.add(
        call("run_remediation", action="rollback", target="ledger-svc"),
        diagnosis("db_pool_exhaustion", "ledger-svc"),
    )
    run = await _agent(make_client, strategy).run(world)
    score = grade(run, INCIDENTS[1], world, known_categories())
    await strategy.on_resolution(build_resolution(run, score, world, incident_documents(1)))
    doc_ids = {i.document_id for i in memory.items["bank"]}
    assert {"inc-INC-4127-investigation", "inc-INC-4127-outcome", "pm-INC-4127", "fb-INC-4127"} <= doc_ids
    assert strategy.last_settle is not None
    assert not strategy.last_settle.timed_out


async def test_memory_outage_degrades_gracefully(make_client, groq, open_world) -> None:
    memory = FakeMemory()
    memory.down = True
    agent = _agent(make_client, DejaVu(memory, "bank"))
    groq.add(call("recall_memory", query="anything?"), diagnosis("db_pool_exhaustion", "ledger-svc"))
    result = await agent.run(open_world(INCIDENTS[5]))
    assert result.briefing is None
    assert result.ended == "diagnosed"
    assert "Memory is unavailable" in result.steps[0].output
    assert [e.type for e in agent.trace.events].count("degraded") == 2
