"""NaiveRAG: the same documents as DejaVu, in the same order, retrieved by similarity alone."""

from dejavu.agent.loop import Investigator
from dejavu.documents import incident_documents, migration_documents
from dejavu.eval.grading import grade
from dejavu.llm.toolcalling import ToolCaller
from dejavu.runner import build_resolution, known_categories
from dejavu.sim.schedule import entry_for, gauntlet
from dejavu.strategies.amnesiac import Amnesiac
from dejavu.strategies.dejavu import DejaVu
from dejavu.strategies.rag import NaiveRAG
from dejavu.tokens import count_tokens
from tests.agent.test_loop import diagnosis
from tests.memory.fakememory import FakeMemory
from tests.memory.test_reader import BRIEF, CTX

INCIDENTS = {entry_for(s).n: s for s in gauntlet()}


async def test_rag_gets_exactly_what_dejavu_gets(make_client, groq, open_world) -> None:
    memory = FakeMemory(structured=BRIEF)
    dejavu, rag = DejaVu(memory, "d", settle_timeout_s=5), NaiveRAG(memory, "r", settle_timeout_s=5)
    for strategy in (dejavu, rag):
        await strategy.prepare()
    world = open_world(INCIDENTS[1])
    groq.add(diagnosis("db_pool_exhaustion", "ledger-svc"))
    client, _ = make_client()
    run = await Investigator(ToolCaller(client, ["openai/gpt-oss-120b"]), Amnesiac()).run(world)
    score = grade(run, INCIDENTS[1], world, known_categories())
    resolution = build_resolution(run, score, world, incident_documents(1))
    announcement = [d for d in migration_documents() if d.id == "slack-m1"]
    for strategy in (dejavu, rag):
        await strategy.on_resolution(resolution)
        await strategy.remember(announcement)

    assert [i.model_dump() for i in memory.items["d"]] == [i.model_dump() for i in memory.items["r"]]
    assert [f.document_id for f in memory.files["d"]] == [f.document_id for f in memory.files["r"]]
    assert memory.config["r"]["retain_extraction_mode"] == "chunks"
    assert not memory.models["r"]


async def test_rag_briefs_by_similarity_without_reflect_or_consolidation() -> None:
    memory = FakeMemory(structured=BRIEF)
    rag = NaiveRAG(memory, "r", settle_timeout_s=5)
    await rag.prepare()
    briefing = await rag.brief(CTX)

    assert briefing is not None
    assert briefing.source == "rag"
    assert briefing.first_checks == []
    assert briefing.data["chunks"]
    assert count_tokens(briefing.text) <= 700
    assert memory.reflects == []
    assert memory.consolidations == 0
    recall = memory.recalls[-1]
    assert "tags" not in recall
    assert recall["query_timestamp"] == CTX.alert_at


async def test_rag_lookup_searches_the_agents_query() -> None:
    memory = FakeMemory()
    rag = NaiveRAG(memory, "r", settle_timeout_s=5)
    await rag.prepare()
    text = await rag.lookup("hikaricp pool connection not available", CTX)
    assert text.startswith("Passages most similar to")
    assert await rag.lookup("zzzz qqqq", CTX) == "No passages match 'zzzz qqqq'."
