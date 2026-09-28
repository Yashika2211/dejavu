"""The Gauntlet end to end with a scripted model and the fake memory: strategies take turns,
results are checkpointed per pair, an unreachable model stops the run without grading it, and a
resumed run finishes exactly the pairs that are missing."""

import httpx2
import pytest

from dejavu.agent.loop import LoopConfig
from dejavu.eval.gauntlet import Gauntlet, GauntletRun, estimate, new_run
from dejavu.eval.report import read_jsonl
from dejavu.eval.sequence import IncidentAbortedError
from dejavu.llm.toolcalling import ToolCaller
from tests.agent.test_loop import call, diagnosis
from tests.memory.fakememory import FakeMemory
from tests.memory.test_reader import BRIEF

MODEL = "openai/gpt-oss-120b"
STRATEGIES = ["amnesiac", "rag", "dejavu"]


def _quota() -> httpx2.Response:
    return httpx2.Response(
        429,
        headers={"retry-after": "5400"},
        json={"error": {"message": "tokens per day", "code": "rate_limit_exceeded"}},
    )


def _investigation(category: str, culprit: str) -> list[dict]:
    return [
        call("query_metrics", "first look", service="checkout-api", metric="latency_p99_ms"),
        diagnosis(category, culprit),
    ]


def test_estimate_is_an_upper_bound_from_the_step_budget(settings) -> None:
    e = estimate(6, 3, LoopConfig(), settings, MODEL)
    assert e.max_llm_calls == 6 * 17
    assert e.max_tokens_in == 6 * 17 * 6000
    assert e.max_tokens_out == 6 * 17 * 1200
    assert e.max_usd == pytest.approx(round((e.max_tokens_in * 0.15 + e.max_tokens_out * 0.60) / 1e6, 2))


def test_new_runs_get_a_bank_per_memory_strategy() -> None:
    run = new_run(42, 6, STRATEGIES, [MODEL], LoopConfig(), snapshots=False)
    assert run.run_id.startswith("g42-")
    assert run.banks == {"rag": f"gx-{run.run_id}-rag", "dejavu": f"gx-{run.run_id}-dejavu"}
    assert run.loop["max_steps"] == 16


async def test_a_stopped_run_resumes_where_it_stopped(
    make_client, groq, settings, telemetry_root, tmp_path
) -> None:
    memory = FakeMemory(structured=BRIEF)
    run = new_run(42, 2, STRATEGIES, [MODEL], LoopConfig(), snapshots=False)
    run_dir = tmp_path / run.run_id

    def session(saved: GauntletRun) -> Gauntlet:
        client, _ = make_client()
        return Gauntlet(
            saved,
            run_dir,
            caller=ToolCaller(client, [MODEL]),
            memory=memory,
            settings=settings,
            trace_dir=tmp_path / "traces",
            telemetry_root=telemetry_root,
        )

    for _ in STRATEGIES:
        groq.add(*_investigation("db_pool_exhaustion", "ledger-svc"))
    groq.add(*_investigation("psp_rate_limit", "acquirerx"), *[_quota()] * 4)
    first = session(run)
    first.save()
    await first.prepare()
    with pytest.raises(IncidentAbortedError, match="429 retry-after 5400s"):
        await first.play()

    rows = read_jsonl(run_dir / "results.jsonl")
    assert [(r["n"], r["strategy"]) for r in rows] == [
        (1, "amnesiac"),
        (1, "rag"),
        (1, "dejavu"),
        (2, "amnesiac"),
    ]

    saved = GauntletRun.model_validate_json((run_dir / "run.json").read_text())
    assert saved.prepared == ["rag", "dejavu"]
    groq.add(*_investigation("psp_rate_limit", "acquirerx"), *_investigation("psp_rate_limit", "acquirerx"))
    second = session(saved)
    await second.prepare()  # already prepared: nothing happens
    assert await second.play()

    rows = read_jsonl(run_dir / "results.jsonl")
    assert sorted((r["n"], r["strategy"]) for r in rows) == sorted((n, s) for n in (1, 2) for s in STRATEGIES)
    by_pair = {(r["n"], r["strategy"]): r for r in rows}
    assert by_pair[(1, "dejavu")]["briefing"]
    assert not by_pair[(1, "amnesiac")]["briefing"]
    assert by_pair[(2, "rag")]["correct"]
    assert by_pair[(1, "dejavu")]["kind"] == "first"
    assert by_pair[(1, "rag")]["models"] == [MODEL]
    growth = read_jsonl(run_dir / "growth.jsonl")
    assert sorted((g["n"], g["strategy"]) for g in growth) == sorted(
        (n, s) for n in (0, 1, 2) for s in ("rag", "dejavu")
    )
    assert groq.queue == []


async def test_day1_snapshot_holds_only_the_day0_import(
    make_client, settings, telemetry_root, tmp_path
) -> None:
    memory = FakeMemory()
    run = new_run(42, 1, ["amnesiac", "dejavu"], [MODEL], LoopConfig(), snapshots=True)
    client, _ = make_client()
    gauntlet = Gauntlet(
        run,
        tmp_path / run.run_id,
        caller=ToolCaller(client, [MODEL]),
        memory=memory,
        settings=settings,
        trace_dir=None,
        telemetry_root=telemetry_root,
    )
    await gauntlet.prepare()

    assert run.snapshots_taken == ["day1"]
    day1 = {i.document_id for i in memory.items[settings.dejavu_bank_day1]}
    assert day1 == {i.document_id for i in memory.items[run.banks["dejavu"]]}
    assert "pm-hist-3902" in day1
    assert not any(doc.startswith("inc-") for doc in day1)
