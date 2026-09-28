"""Bank setup is idempotent; settling waits for retains, consolidation and pending work."""

from datetime import UTC, datetime

import pytest

from dejavu.memory.bank_setup import setup_bank
from dejavu.memory.hindsight_adapter import MentalModelState
from dejavu.memory.mental_models import CORE_SERVICES, mental_model_specs
from dejavu.memory.missions import DIRECTIVES, RETAIN_MISSION
from dejavu.memory.settle import settle
from tests.llm.fakegroq import NoWait
from tests.memory.fakememory import FakeMemory


async def test_dejavu_profile_is_complete_and_idempotent() -> None:
    memory = FakeMemory()
    first = await setup_bank(memory, "b", "dejavu")
    second = await setup_bank(memory, "b", "dejavu")
    config = memory.config["b"]
    assert config["retain_mission"] == RETAIN_MISSION
    assert config["enable_observations"] is True
    assert config["memory_defense"]["enabled"] is True
    assert config["entity_labels"]
    assert memory.directives["b"] == {d.name for d in DIRECTIVES}
    assert len(memory.models["b"]) == len(CORE_SERVICES) + 3
    assert len(first) == len(CORE_SERVICES) + 3
    assert second == []


def test_service_models_see_untagged_material() -> None:
    for spec in mental_model_specs():
        assert spec.trigger["refresh_after_consolidation"] is True
        assert spec.trigger["mode"] == "delta"
        if spec.tags:
            assert spec.trigger["tags_match"] == "any"


async def test_rag_profile_is_a_plain_chunk_store() -> None:
    memory = FakeMemory()
    await setup_bank(memory, "r", "rag")
    assert memory.config["r"]["retain_extraction_mode"] == "chunks"
    assert memory.config["r"]["enable_observations"] is False
    assert not memory.directives["r"]
    assert not memory.models["r"]


async def test_settle_waits_for_pending_operations() -> None:
    memory = FakeMemory(pending_polls=3)
    time = NoWait()
    ops = await memory.retain("b", [])
    report = await settle(memory, "b", ops, poll_s=2, sleep=time.sleep, clock=time.clock)
    assert not report.timed_out
    assert report.failed == []
    assert time.slept == pytest.approx(
        [2, 2, 2, 2, 2, 2]
    )  # three polls for the retain, three for consolidation


async def test_settle_can_skip_consolidation() -> None:
    memory = FakeMemory(pending_polls=3)
    time = NoWait()
    ops = await memory.retain("b", [])
    report = await settle(memory, "b", ops, poll_s=2, consolidate=False, sleep=time.sleep, clock=time.clock)
    assert not report.timed_out
    assert time.slept == pytest.approx([2, 2, 2])  # the retain only
    assert len(memory.ops) == 1


async def test_settle_gives_up_at_the_timeout() -> None:
    memory = FakeMemory(pending_polls=100)
    time = NoWait()
    ops = await memory.retain("b", [])
    report = await settle(memory, "b", ops, timeout_s=10, poll_s=2, sleep=time.sleep, clock=time.clock)
    assert report.timed_out


async def test_settle_restarts_paused_mental_model_refreshes() -> None:
    memory = FakeMemory()
    await setup_bank(memory, "b", "dejavu")
    memory.failed_refresh["b"].add("triage-playbook")
    time = NoWait()
    report = await settle(memory, "b", [], sleep=time.sleep, clock=time.clock)
    assert report.refreshed == ["triage-playbook"]
    assert not any(m.refresh_paused for m in await memory.mental_models("b"))


def test_a_refresh_is_paused_only_while_the_last_attempt_failed() -> None:
    aug, sep = datetime(2026, 8, 30, tzinfo=UTC), datetime(2026, 9, 2, tzinfo=UTC)
    assert MentalModelState(id="m", last_refreshed_at=aug, last_refresh_failed_at=sep).refresh_paused
    assert MentalModelState(id="m", last_refresh_failed_at=sep).refresh_paused
    assert not MentalModelState(id="m", last_refreshed_at=sep, last_refresh_failed_at=aug).refresh_paused
    assert not MentalModelState(id="m", last_refreshed_at=sep).refresh_paused
