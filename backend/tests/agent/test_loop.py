"""The investigation loop, driven end to end by a scripted model over real simulated incidents."""

import json

import pytest

from dejavu.agent.loop import Investigator, LoopConfig, Proposal, system_prompt
from dejavu.agent.trace import Trace
from dejavu.llm.toolcalling import ToolCaller
from dejavu.sim.fake_secrets import fake_jwt
from dejavu.sim.generators.logs import INJECTION_TEXT
from dejavu.sim.schedule import entry_for, gauntlet
from dejavu.strategies.amnesiac import Amnesiac
from dejavu.tokens import count_tokens
from tests.llm.fakegroq import completion, groq_error
from tests.sim.cases import PRE, scenario_for

MODEL = "openai/gpt-oss-120b"


def call(name: str, rationale: str = "check", **args) -> dict:
    return completion(tool_calls=[(name, {**args, "rationale": rationale})])


def diagnosis(category: str, culprit: str, plan: list[dict] | None = None, **extra) -> dict:
    return call(
        "submit_diagnosis",
        "done",
        root_cause_category=category,
        culprit_service=culprit,
        summary=f"{category} in {culprit}",
        confidence=0.8,
        remediation_plan=plan or [],
        **extra,
    )


@pytest.fixture
def investigator(make_client, tmp_path):
    def build(config: LoopConfig | None = None) -> Investigator:
        client, _ = make_client()
        trace = Trace("test-run", directory=tmp_path)
        return Investigator(
            ToolCaller(client, [MODEL]), Amnesiac(), config=config, trace=trace, run_id="test-run"
        )

    return build


def _tool_messages(groq, index: int) -> list[str]:
    return [m["content"] for m in groq.requests[index]["messages"] if m["role"] == "tool"]


async def test_happy_path_diagnoses_fixes_and_traces(investigator, groq, open_world) -> None:
    world = open_world(scenario_for("db_pool_exhaustion", PRE))
    groq.add(
        call("get_alert"),
        call("list_changes"),
        call("query_metrics", service="ledger-svc", metric="db_pool_pending"),
        call(
            "update_hypotheses",
            hypotheses=[
                {
                    "id": "h1",
                    "statement": "pool exhausted by the deploy",
                    "category": "db_pool_exhaustion",
                    "service": "ledger-svc",
                    "probability": 0.8,
                }
            ],
        ),
        call("run_remediation", "roll back the deploy", action="rollback", target="ledger-svc"),
        diagnosis("db_pool_exhaustion", "ledger-svc", plan=[{"action": "rollback", "target": "ledger-svc"}]),
    )
    agent = investigator()
    result = await agent.run(world)

    assert result.ended == "diagnosed"
    assert [s.tool for s in result.steps] == [
        "get_alert",
        "list_changes",
        "query_metrics",
        "update_hypotheses",
        "run_remediation",
        "submit_diagnosis",
    ]
    assert result.ttd_min == pytest.approx(0.5 + 1 + 1.5 + 0 + 6)
    assert world.resolved_at_min is not None
    assert result.plan_steps == []  # already resolved before the plan ran
    assert result.hypotheses[0].id == "h1"
    assert len(result.llm_calls) == 6
    types = [e.type for e in Trace.load(agent.trace.path)]
    for expected in (
        "run_started",
        "tool_call",
        "tool_result",
        "hypotheses",
        "remediation_applied",
        "diagnosis",
        "resolved",
    ):
        assert expected in types
    assert '<tool_output source="get_alert" untrusted="true">' in _tool_messages(groq, 1)[0]


async def test_invalid_arguments_are_returned_without_costing_a_step(investigator, groq, open_world) -> None:
    world = open_world(scenario_for("psp_rate_limit", PRE))
    groq.add(
        call("query_metrics", service="acquirerx"),
        call("query_metrics", service="acquirerx", metric="psp_http_429_rate"),
        diagnosis("psp_rate_limit", "acquirerx"),
    )
    result = await investigator().run(world)
    assert [s.tool for s in result.steps] == ["query_metrics", "submit_diagnosis"]
    assert "invalid arguments for query_metrics" in _tool_messages(groq, 1)[0]


async def test_budget_exhaustion_asks_for_a_final_diagnosis(investigator, groq, open_world) -> None:
    world = open_world(scenario_for("cert_expiry", PRE))
    groq.add(*[call("get_alert")] * 3, diagnosis("cert_expiry", "edge-gateway"))
    result = await investigator(LoopConfig(max_steps=3)).run(world)
    assert result.ended == "budget"
    assert result.diagnosis is not None
    assert result.diagnosis.root_cause_category == "cert_expiry"
    final = groq.requests[-1]
    assert [t["function"]["name"] for t in final["tools"]] == ["submit_diagnosis"]
    assert "budget is exhausted" in final["messages"][-1]["content"]


async def test_a_model_that_never_diagnoses_gets_a_novel_fallback(investigator, groq, open_world) -> None:
    world = open_world(scenario_for("cert_expiry", PRE))
    groq.add(*[call("get_alert")] * 2, completion("no idea"), completion("still no idea"), completion("{}"))
    result = await investigator(LoopConfig(max_steps=2)).run(world)
    assert result.diagnosis is not None
    assert result.diagnosis.root_cause_category == "novel"
    assert result.diagnosis.confidence == 0


async def test_escalation_ends_the_run(investigator, groq, open_world) -> None:
    world = open_world(scenario_for("sms_quota_exhausted", PRE))
    groq.add(call("page_human", team="Messaging", message="smsbridge quota"))
    result = await investigator().run(world)
    assert result.ended == "escalated"
    assert result.diagnosis is None
    assert result.ttd_min == pytest.approx(10)


async def test_remediation_plan_runs_after_the_diagnosis(investigator, groq, open_world) -> None:
    world = open_world(scenario_for("db_pool_exhaustion", PRE))
    plan = [
        {"action": "restart", "target": "ledger-svc"},
        {"action": "rollback", "target": "ledger-svc"},
        {"action": "restart", "target": "postgres-ledger"},
    ]
    groq.add(diagnosis("db_pool_exhaustion", "ledger-svc", plan=plan))
    result = await investigator().run(world)
    assert [s.args["action"] for s in result.plan_steps] == ["restart", "rollback"]  # stops once resolved
    assert world.resolved_at_min == pytest.approx(4 + 6 + 4)


async def test_injection_and_leaked_token_never_reach_the_model(investigator, groq, open_world) -> None:
    scenario = next(s for s in gauntlet() if entry_for(s).n == 16)
    world = open_world(scenario)
    world.clock.advance(8)
    groq.add(
        call("search_logs", service="edge-gateway", query="auth/token"),
        call("search_logs", service="auth-svc", level="DEBUG", window_min=60),
        diagnosis("cert_expiry", "edge-gateway"),
    )
    await investigator().run(world)
    sent = json.dumps(groq.requests)
    assert INJECTION_TEXT not in sent
    assert "run_remediation(action='restart'" not in sent
    assert fake_jwt(scenario.seed + 16) not in sent
    assert "[REDACTED:" in sent


async def test_salvaged_tool_calls_run_in_the_loop(investigator, groq, open_world) -> None:
    world = open_world(scenario_for("retry_storm", PRE))
    raw = '{"name": "list_changes", "arguments": {"window_hours": 2, "rationale": "flags?"'
    groq.add(
        groq_error(400, "tool_use_failed", failed_generation=raw), diagnosis("retry_storm", "checkout-api")
    )
    result = await investigator().run(world)
    assert result.steps[0].tool == "list_changes"
    assert result.steps[0].repaired
    assert any("salvaged" in n for n in result.notes)


async def test_citing_an_incident_marks_a_memory_moment(investigator, groq, open_world) -> None:
    world = open_world(scenario_for("db_pool_exhaustion", PRE))
    groq.add(
        call("query_metrics", "same shape as INC-4127", service="ledger-svc", metric="db_pool_pending"),
        diagnosis("db_pool_exhaustion", "ledger-svc"),
    )
    result = await investigator().run(world)
    assert result.steps[0].memory_moment
    assert result.steps[0].cited_incidents == ["INC-4127"]


async def test_requests_stay_within_the_context_budget(investigator, groq, open_world) -> None:
    world = open_world(scenario_for("dns_resolution_failure", PRE))
    services = ["edge-gateway", "checkout-api", "payments-svc", "ledger-svc", "auth-svc", "coredns"]
    groq.add(
        *[call("search_logs", service=s, window_min=60, limit=15) for s in services],
        diagnosis("dns_resolution_failure", "coredns"),
    )
    await investigator(LoopConfig(context_tokens=6000)).run(world)
    for request in groq.requests:
        payload = json.dumps(request["messages"]) + json.dumps(request.get("tools", []))
        assert count_tokens(payload) <= 6000


def test_system_prompt_lists_the_taxonomy_and_rules() -> None:
    prompt = system_prompt(LoopConfig())
    assert "db_pool_exhaustion" in prompt
    assert "novel" in prompt
    assert "untrusted" in prompt
    assert "{" not in prompt.replace("<tool_output", "")


async def test_the_approver_sees_each_proposal_and_can_decline(
    make_client, groq, open_world, tmp_path
) -> None:
    seen: list[Proposal] = []

    async def decline(proposal: Proposal) -> bool:
        seen.append(proposal)
        return False

    client, _ = make_client()
    agent = Investigator(
        ToolCaller(client, [MODEL]),
        Amnesiac(),
        approver=decline,
        trace=Trace("t", directory=tmp_path),
        run_id="t",
    )
    groq.add(
        call("run_remediation", "roll back the deploy", action="rollback", target="ledger-svc"),
        diagnosis("db_pool_exhaustion", "ledger-svc", plan=[{"action": "rollback", "target": "ledger-svc"}]),
    )
    world = open_world(scenario_for("db_pool_exhaustion", PRE))
    result = await agent.run(world)

    assert [(p.action_id, p.action.value, p.target) for p in seen] == [
        ("r1", "rollback", "ledger-svc"),
        ("r2", "rollback", "ledger-svc"),
    ]
    assert "declined by the on-call human" in result.steps[0].output
    assert world.interventions == []
    proposed = agent.trace.of_type("remediation_proposed")
    assert [e.data["action_id"] for e in proposed] == ["r1", "r2"]
    assert proposed[0].data["needs_approval"] == seen[0].needs_approval
