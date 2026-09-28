import httpx2
import pytest

from dejavu.llm.errors import (
    ContextTooLongError,
    ModelUnavailableError,
    QuotaExhaustedError,
    RetriesExhaustedError,
    ToolUseFailedError,
)
from tests.llm.fakegroq import completion, groq_error

MSG = [{"role": "user", "content": "hi"}]


async def test_tool_calls_usage_and_cost_are_parsed(make_client, groq, records) -> None:
    client, _ = make_client()
    groq.add(completion(tool_calls=[("get_alert", {"rationale": "start"})], tokens=(1000, 200)))
    resp = await client.complete(model="openai/gpt-oss-120b", messages=MSG, tools=[{"type": "function"}])
    assert [c.name for c in resp.tool_calls] == ["get_alert"]
    assert (resp.tokens_in, resp.tokens_out) == (1000, 200)
    assert records[-1].cost_usd == pytest.approx((1000 * 0.15 + 200 * 0.60) / 1e6)
    assert groq.requests[0]["tool_choice"] == "auto"
    assert "parallel_tool_calls" not in groq.requests[0]  # gpt-oss on Groq does not support it


async def test_rate_limit_honours_retry_after(make_client, groq, records) -> None:
    client, waits = make_client()
    groq.add(
        httpx2.Response(
            429,
            headers={"retry-after": "7"},
            json={"error": {"message": "rate limited", "code": "rate_limit_exceeded"}},
        )
    )
    groq.add(completion("ok"))
    resp = await client.complete(model="openai/gpt-oss-120b", messages=MSG)
    assert resp.content == "ok"
    assert resp.retries == 1
    assert 7 in waits.slept  # the limiter paused the model for the server's retry-after
    assert records[0].error == "429 retry-after 7s"


async def test_a_daily_cap_is_raised_instead_of_waited_out(make_client, groq, records) -> None:
    client, waits = make_client()
    groq.add(
        httpx2.Response(
            429,
            headers={"retry-after": "5400"},
            json={"error": {"message": "tokens per day exceeded", "code": "rate_limit_exceeded"}},
        )
    )
    with pytest.raises(QuotaExhaustedError) as info:
        await client.complete(model="openai/gpt-oss-120b", messages=MSG)
    assert info.value.wait_s == 5400
    assert waits.slept == []
    assert records[-1].error == "429 retry-after 5400s"


@pytest.mark.parametrize("status", [500, 502, 503])
async def test_server_errors_are_retried_with_backoff(make_client, groq, status) -> None:
    client, waits = make_client()
    groq.add(groq_error(status, "server_error"), groq_error(status, "server_error"), completion("ok"))
    resp = await client.complete(model="openai/gpt-oss-120b", messages=MSG)
    assert resp.content == "ok"
    assert resp.retries == 2
    assert len(waits.slept) == 2


async def test_retries_are_bounded(make_client, groq) -> None:
    client, _ = make_client(max_attempts=3)
    groq.add(*[groq_error(503, "unavailable")] * 3)
    with pytest.raises(RetriesExhaustedError):
        await client.complete(model="openai/gpt-oss-120b", messages=MSG)


async def test_413_asks_the_caller_to_trim(make_client, groq) -> None:
    client, _ = make_client()
    groq.add(groq_error(413, "request_too_large"))
    with pytest.raises(ContextTooLongError):
        await client.complete(model="openai/gpt-oss-120b", messages=MSG)


async def test_tool_use_failed_carries_the_failed_generation(make_client, groq) -> None:
    client, _ = make_client()
    raw = '{"name": "query_metrics", "arguments": {"service": "ledger-svc"'
    groq.add(groq_error(400, "tool_use_failed", "Failed to call a function", failed_generation=raw))
    with pytest.raises(ToolUseFailedError) as info:
        await client.complete(model="openai/gpt-oss-120b", messages=MSG, tools=[{"type": "function"}])
    assert info.value.failed_generation == raw


async def test_unknown_model_is_reported_for_fallback(make_client, groq) -> None:
    client, _ = make_client()
    groq.add(groq_error(404, "model_not_found"))
    with pytest.raises(ModelUnavailableError):
        await client.complete(model="qwen/qwen3-32b", messages=MSG)


async def test_available_models_skip_inactive(make_client, groq) -> None:
    client, _ = make_client()
    groq.add(
        {
            "object": "list",
            "data": [
                {
                    "id": "openai/gpt-oss-120b",
                    "object": "model",
                    "created": 0,
                    "owned_by": "openai",
                    "active": True,
                },
                {
                    "id": "qwen/qwen3-32b",
                    "object": "model",
                    "created": 0,
                    "owned_by": "qwen",
                    "active": False,
                },
            ],
        }
    )
    assert await client.available_models() == {"openai/gpt-oss-120b"}


async def test_gpt_oss_gets_reasoning_effort_and_qwen_hides_reasoning_with_tools(make_client, groq) -> None:
    client, _ = make_client()
    groq.add(completion("a"), completion("b", model="qwen/qwen3.8-27b"))
    await client.complete(model="openai/gpt-oss-120b", messages=MSG, reasoning_effort="medium")
    await client.complete(
        model="qwen/qwen3.8-27b",
        messages=MSG,
        tools=[{"type": "function", "function": {"name": "x", "parameters": {}}}],
    )
    assert groq.requests[0]["reasoning_effort"] == "medium"
    assert groq.requests[1]["reasoning_format"] == "hidden"
    assert "reasoning_effort" not in groq.requests[1]
