"""The grader scores runs deterministically from the simulator and ground truth."""

import pytest

from dejavu.agent.loop import Investigator, LoopConfig
from dejavu.eval.grading import HISTORICAL_CATEGORIES, grade
from dejavu.llm.toolcalling import ToolCaller
from dejavu.sim.schedule import gauntlet
from dejavu.strategies.amnesiac import Amnesiac
from tests.agent.test_loop import call, diagnosis
from tests.sim.cases import PRE, scenario_for

KNOWN = {s.incident_id: s.spec.category for s in gauntlet()} | HISTORICAL_CATEGORIES


@pytest.fixture
def run_and_grade(make_client, groq, open_world):
    async def go(archetype: str, *script: dict, when: str = PRE):
        scenario = scenario_for(archetype, when)
        world = open_world(scenario)
        groq.add(*script)
        client, _ = make_client()
        run = await Investigator(
            ToolCaller(client, ["openai/gpt-oss-120b"]), Amnesiac(), config=LoopConfig()
        ).run(world)
        return grade(run, scenario, world, KNOWN), world

    return go


async def test_correct_diagnosis_fixed_by_the_agent(run_and_grade) -> None:
    score, world = await run_and_grade(
        "db_pool_exhaustion",
        call("query_metrics", service="ledger-svc", metric="db_pool_pending"),
        call("run_remediation", action="rollback", target="ledger-svc"),
        diagnosis("db_pool_exhaustion", "ledger-svc"),
    )
    assert score.correct
    assert score.resolved_by == "agent"
    assert score.mttr_min == pytest.approx(3 + world.resolved_at_min)
    assert score.ttd_min == pytest.approx(1.5 + 6)
    assert score.wasted_steps == 0
    assert score.harmful_actions == 0


async def test_wrong_category_is_incorrect(run_and_grade) -> None:
    score, _ = await run_and_grade("db_pool_exhaustion", diagnosis("missing_index_slow_query", "ledger-svc"))
    assert not score.correct
    assert not score.category_correct
    assert score.culprit_correct


async def test_listed_culprit_aliases_are_accepted(run_and_grade) -> None:
    score, _ = await run_and_grade("psp_rate_limit", diagnosis("psp_rate_limit", "payments-svc"))
    assert score.correct


async def test_a_node_name_counts_for_node_level_causes(run_and_grade) -> None:
    scenario = scenario_for("clock_skew_jwt", PRE)
    node = scenario.values["skew_node"]
    score, _ = await run_and_grade("clock_skew_jwt", diagnosis("clock_skew_jwt", node))
    assert score.culprit_correct


async def test_without_a_fix_the_human_fixes_it_after_45_minutes(run_and_grade) -> None:
    score, _ = await run_and_grade("cert_expiry", call("get_alert"), diagnosis("cert_expiry", "edge-gateway"))
    assert score.resolved_by == "human"
    assert score.mttr_min == pytest.approx(3 + 0.5 + 45)


async def test_harmful_actions_are_counted_and_delay_the_human_fix(run_and_grade) -> None:
    score, _ = await run_and_grade(
        "missing_index_slow_query",
        call("run_remediation", action="restart", target="postgres-ledger"),
        diagnosis("missing_index_slow_query", "postgres-ledger"),
    )
    assert score.harmful_actions == 1
    assert score.mttr_min == pytest.approx(3 + 4 + 45 + 8)


async def test_escalation_hands_over_after_40_minutes(run_and_grade) -> None:
    score, _ = await run_and_grade(
        "sms_quota_exhausted", call("page_human", team="Messaging", message="quota")
    )
    assert score.resolved_by == "escalation"
    assert score.mttr_min == pytest.approx(3 + 10 + 40)
    assert not score.correct


async def test_remediation_plan_fixes_count_as_plan(run_and_grade) -> None:
    score, _ = await run_and_grade(
        "db_pool_exhaustion",
        diagnosis("db_pool_exhaustion", "ledger-svc", plan=[{"action": "rollback", "target": "ledger-svc"}]),
    )
    assert score.resolved_by == "plan"
    assert score.mttr_min == pytest.approx(3 + 0 + 6 + 4)


async def test_wasted_steps(run_and_grade) -> None:
    score, _ = await run_and_grade(
        "db_pool_exhaustion",
        call("get_alert"),  # generic triage
        call("get_runbook", topic="ledger connection pool"),  # relevant runbook
        call("query_metrics", service="kafka", metric="rps"),  # irrelevant
        call("run_remediation", action="restart", target="ledger-svc"),  # transient: wasted
        call("run_remediation", action="cache_warmup", target="redis"),  # rejected target: wasted
        diagnosis("db_pool_exhaustion", "ledger-svc"),
    )
    assert score.wasted_steps == 3


async def test_precedent_precision(run_and_grade) -> None:
    score, _ = await run_and_grade(
        "db_pool_exhaustion",
        diagnosis("db_pool_exhaustion", "ledger-svc", precedent_incident_ids=["INC-4127", "INC-4133"]),
    )
    assert score.cited == ["INC-4127", "INC-4133"]
    assert score.precedent_precision == pytest.approx(0.5)


async def test_rupees_at_risk_grow_with_recovery_time(run_and_grade) -> None:
    fixed, _ = await run_and_grade(
        "db_pool_exhaustion",
        call("run_remediation", action="rollback", target="ledger-svc"),
        diagnosis("db_pool_exhaustion", "ledger-svc"),
    )
    unfixed, _ = await run_and_grade("db_pool_exhaustion", diagnosis("db_pool_exhaustion", "ledger-svc"))
    assert unfixed.inr_at_risk > fixed.inr_at_risk > 0


async def test_token_and_cost_accounting(run_and_grade) -> None:
    score, _ = await run_and_grade("retry_storm", call("get_alert"), diagnosis("retry_storm", "checkout-api"))
    assert score.llm_calls == 2
    assert score.tokens_in == 200
    assert score.usd_cost > 0
