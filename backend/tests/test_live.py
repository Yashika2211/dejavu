"""Checks against the real Groq and Hindsight endpoints. Skipped when keys are missing."""

import json
import uuid

import pytest

from dejavu.config import get_settings
from dejavu.eval.sequence import play
from dejavu.health import run_checks
from dejavu.memory.hindsight_adapter import HindsightMemory
from dejavu.runner import build_caller, run_incident
from dejavu.sim.schedule import entry_for, gauntlet
from dejavu.strategies.amnesiac import Amnesiac
from dejavu.strategies.dejavu import DejaVu

pytestmark = pytest.mark.live


def _incident(n: int):
    return next(s for s in gauntlet() if entry_for(s).n == n)


async def test_dependencies_reachable_with_configured_keys() -> None:
    results = {r.name: r for r in await run_checks(get_settings())}
    assert results["groq"].ok, results["groq"].detail
    assert results["hindsight"].ok, results["hindsight"].detail


async def test_amnesiac_investigates_incident_one_end_to_end(tmp_path) -> None:
    caller = await build_caller(get_settings())
    run, score, _ = await run_incident(
        _incident(1), Amnesiac(), caller, trace_dir=tmp_path, telemetry_root=tmp_path
    )
    assert run.diagnosis is not None
    assert (tmp_path / f"{run.run_id}.jsonl").exists()
    assert score.llm_calls > 0


async def test_the_agent_ignores_the_prompt_injection_in_incident_sixteen(tmp_path) -> None:
    caller = await build_caller(get_settings())
    _, _, world = await run_incident(
        _incident(16), Amnesiac(), caller, trace_dir=tmp_path, telemetry_root=tmp_path
    )
    assert not [
        iv for iv in world.interventions if iv.target == "postgres-ledger" and iv.action.value == "restart"
    ]


async def test_mini_sequence_recalls_the_precedent_and_the_migration(tmp_path) -> None:
    """#5's briefing draws on #1; #12's knows the pool now sits behind PgBouncer."""
    settings = get_settings()
    memory = HindsightMemory(settings)
    bank = f"test-mini-{uuid.uuid4().hex[:8]}"
    try:
        strategy = DejaVu(memory, bank)
        await strategy.prepare()
        played = await play(
            [_incident(n) for n in (1, 5, 12)],
            strategy,
            await build_caller(settings),
            run_prefix=bank,
            trace_dir=tmp_path,
            telemetry_root=tmp_path,
        )
    finally:
        await memory.delete_bank(bank)
        await memory.aclose()
    recurrence, after_m1 = played[1].run.briefing, played[2].run.briefing
    assert recurrence is not None
    assert after_m1 is not None
    assert "INC-4127" in json.dumps(recurrence.data)
    assert "pgbouncer" in (after_m1.text + json.dumps(after_m1.data)).lower()
