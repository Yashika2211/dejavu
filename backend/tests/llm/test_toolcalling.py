import json

import pytest
from conftest import completion, groq_error
from pydantic import BaseModel

from dejavu.llm.toolcalling import NoDecisionError, ToolCaller, salvage, tool_spec


class QueryArgs(BaseModel):
    service: str
    metric: str


class NoArgs(BaseModel):
    pass


TOOLS = [
    tool_spec("query_metrics", "Summarise a metric.", QueryArgs),
    tool_spec("get_alert", "The alert.", NoArgs),
]
NAMES = {t.name for t in TOOLS}
MSG = [{"role": "user", "content": "investigate"}]


def test_tool_specs_require_a_rationale_and_inline_refs() -> None:
    spec = TOOLS[0].parameters
    assert spec["required"] == ["service", "metric", "rationale"]
    assert "$defs" not in json.dumps(spec)
    assert "title" not in spec


@pytest.mark.parametrize(
    "raw",
    [
        '{"name": "query_metrics", "arguments": {"service": "ledger-svc", "metric": "db_pool_pending"}}',
        '{"name": "query_metrics", "arguments": "{\\"service\\": \\"ledger-svc\\", \\"metric\\": \\"db_pool_pending\\"}"}',
        '<function=query_metrics>{"service": "ledger-svc", "metric": "db_pool_pending"}</function>',
        'to=functions.query_metrics <|constrain|>json<|message|>{"service": "ledger-svc", "metric": "db_pool_pending"}',
        'functions.query_metrics({"service": "ledger-svc", "metric": "db_pool_pending"',
        '{"tool": "query_metrics", "args": {"service": "ledger-svc", "metric": "db_pool_pending"}}',
    ],
)
def test_salvage_recovers_common_malformed_calls(raw: str) -> None:
    assert salvage(raw, NAMES) == ("query_metrics", {"service": "ledger-svc", "metric": "db_pool_pending"})


def test_salvage_gives_up_on_plain_text() -> None:
    assert salvage("I think the database is slow.", NAMES) is None


async def test_normal_tool_call(make_client, groq) -> None:
    client, _ = make_client()
    groq.add(completion(tool_calls=[("get_alert", {"rationale": "start"})]))
    decision = await ToolCaller(client, ["openai/gpt-oss-120b"]).decide(MSG, TOOLS)
    assert [c.name for c in decision.calls] == ["get_alert"]
    assert not decision.repaired
    assert groq.requests[0]["tool_choice"] == "required"


async def test_tool_use_failed_is_salvaged_without_another_request(make_client, groq) -> None:
    client, _ = make_client()
    raw = '{"name": "query_metrics", "arguments": {"service": "ledger-svc", "metric": "db_pool_pending"'
    groq.add(groq_error(400, "tool_use_failed", failed_generation=raw))
    decision = await ToolCaller(client, ["openai/gpt-oss-120b"]).decide(MSG, TOOLS)
    assert decision.calls[0].args == {"service": "ledger-svc", "metric": "db_pool_pending"}
    assert "salvaged" in decision.notes[0]
    assert len(groq.requests) == 1


async def test_plain_text_failure_is_reprompted(make_client, groq) -> None:
    client, _ = make_client()
    groq.add(groq_error(400, "tool_use_failed", failed_generation="Let me think about the database."))
    groq.add(completion(tool_calls=[("get_alert", {"rationale": "retry"})]))
    decision = await ToolCaller(client, ["openai/gpt-oss-120b"]).decide(MSG, TOOLS)
    assert decision.calls[0].name == "get_alert"
    assert "could not be parsed" in groq.requests[1]["messages"][-1]["content"]


async def test_text_reply_without_a_tool_is_reprompted(make_client, groq) -> None:
    client, _ = make_client()
    groq.add(completion("The pool is exhausted."), completion(tool_calls=[("get_alert", {"rationale": "x"})]))
    decision = await ToolCaller(client, ["openai/gpt-oss-120b"]).decide(MSG, TOOLS)
    assert decision.calls[0].name == "get_alert"
    assert groq.requests[1]["messages"][-2] == {"role": "assistant", "content": "The pool is exhausted."}


async def test_two_failures_fall_back_to_the_next_model(make_client, groq) -> None:
    client, _ = make_client()
    groq.add(completion("no tools"), completion("still no tools"))
    groq.add(completion(tool_calls=[("get_alert", {"rationale": "x"})], model="qwen/qwen3.8-27b"))
    decision = await ToolCaller(client, ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"]).decide(MSG, TOOLS)
    assert decision.model == "qwen/qwen3.8-27b"
    assert groq.requests[2]["model"] == "qwen/qwen3.8-27b"


async def test_unavailable_model_falls_back_immediately(make_client, groq) -> None:
    client, _ = make_client()
    groq.add(groq_error(404, "model_not_found"), completion(tool_calls=[("get_alert", {"rationale": "x"})]))
    decision = await ToolCaller(client, ["gone/model", "openai/gpt-oss-120b"]).decide(MSG, TOOLS)
    assert decision.model == "openai/gpt-oss-120b"


async def test_json_mode_is_the_last_resort(make_client, groq) -> None:
    client, _ = make_client()
    groq.add(completion("no"), completion("no"))
    groq.add(
        completion(
            '{"tool": "query_metrics", "args": {"service": "ledger-svc", "metric": "db_pool_pending"}}'
        )
    )
    decision = await ToolCaller(client, ["openai/gpt-oss-120b"]).decide(MSG, TOOLS)
    assert decision.calls[0].args["metric"] == "db_pool_pending"
    assert groq.requests[2]["response_format"] == {"type": "json_object"}
    assert "tools" not in groq.requests[2]


async def test_total_failure_raises_no_decision(make_client, groq) -> None:
    client, _ = make_client()
    groq.add(completion("no"), completion("no"), completion('{"answer": "none"}'))
    with pytest.raises(NoDecisionError):
        await ToolCaller(client, ["openai/gpt-oss-120b"]).decide(MSG, TOOLS)


async def test_several_calls_are_all_returned(make_client, groq) -> None:
    client, _ = make_client()
    groq.add(
        completion(
            tool_calls=[
                ("get_alert", {"rationale": "a"}),
                ("query_metrics", {"service": "s", "metric": "m", "rationale": "b"}),
            ]
        )
    )
    decision = await ToolCaller(client, ["openai/gpt-oss-120b"]).decide(MSG, TOOLS)
    assert [c.name for c in decision.calls] == ["get_alert", "query_metrics"]
