"""The three-incident mini-sequence offline: pool exhaustion, its recurrence, and the recurrence
after the PgBouncer migration (Phase 3). A scripted model and the fake memory prove the plumbing:
what memory holds when each briefing is built. The live run is `scripts/mini_sequence.py`."""

from typing import Any

from dejavu.eval.sequence import documents_due, play
from dejavu.llm.toolcalling import ToolCaller
from dejavu.memory.day0 import import_day0
from dejavu.memory.hindsight_adapter import ReflectAnswer
from dejavu.sim.schedule import entry_for, gauntlet
from dejavu.strategies.dejavu import DejaVu
from tests.agent.test_loop import call, diagnosis
from tests.memory.fakememory import FakeMemory
from tests.memory.test_reader import BRIEF

INCIDENTS = {entry_for(s).n: s for s in gauntlet()}


class RecordingMemory(FakeMemory):
    """Remembers which documents were in the bank each time a briefing was reflected."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.seen: list[set[str]] = []

    async def reflect(self, bank_id: str, query: str, **kwargs: Any) -> ReflectAnswer:
        self.seen.append({i.document_id for i in self.items[bank_id]})
        return await super().reflect(bank_id, query, **kwargs)


def test_team_documents_arrive_with_the_calendar() -> None:
    assert documents_due(None, INCIDENTS[5].alert_at) == []
    between = documents_due(INCIDENTS[5].alert_at, INCIDENTS[12].alert_at)
    assert [d.id for d in between] == ["rfc-014", "rfc-015", "slack-m1"]
    assert [d.id for d in documents_due(INCIDENTS[12].alert_at, INCIDENTS[14].alert_at)] == ["slack-m2"]


async def test_each_briefing_sees_everything_earlier_and_nothing_later(
    make_client, groq, telemetry_root, tmp_path
) -> None:
    memory = RecordingMemory(structured=BRIEF)
    await import_day0(memory, "bank", timeout_s=5)
    for _ in range(3):
        groq.add(
            call("query_metrics", "first check", service="ledger-svc", metric="db_pool_pending"),
            diagnosis("db_pool_exhaustion", "ledger-svc"),
        )
    client, _ = make_client()
    played = await play(
        [INCIDENTS[n] for n in (1, 5, 12)],
        DejaVu(memory, "bank", settle_timeout_s=5),
        ToolCaller(client, ["openai/gpt-oss-120b"]),
        run_prefix="mini",
        trace_dir=tmp_path,
        telemetry_root=telemetry_root,
    )

    assert [p.n for p in played] == [1, 5, 12]
    assert [p.delivered for p in played] == [[], [], ["rfc-014", "rfc-015", "slack-m1"]]
    before_1, before_5, before_12 = memory.seen
    assert "pm-hist-3902" in before_1
    assert not any(doc.startswith("inc-") for doc in before_1)
    assert {"inc-INC-4127-investigation", "pm-INC-4127", "fb-INC-4127"} <= before_5
    assert "rfc-014" not in before_5
    assert {"inc-INC-4165-outcome", "rfc-014", "slack-m1"} <= before_12
    assert "inc-INC-4249-outcome" not in before_12
    assert all(p.run.steps[0].memory_moment for p in played)
    assert all(p.score.correct for p in played)
    assert (tmp_path / "mini-inc-4249-dejavu.jsonl").exists()
