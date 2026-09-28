import httpx
import pytest
import respx

from dejavu.config import Settings
from dejavu.health import check_groq, check_hindsight


def _models(*ids: str, inactive: tuple[str, ...] = ()) -> dict:
    return {
        "object": "list",
        "data": [{"id": i, "active": True} for i in ids] + [{"id": i, "active": False} for i in inactive],
    }


@respx.mock
async def test_groq_ok_reports_missing_fallbacks(settings: Settings) -> None:
    respx.get("https://groq.test/openai/v1/models").respond(
        json=_models("openai/gpt-oss-120b", "openai/gpt-oss-20b", inactive=("qwen/qwen3.8-27b",))
    )
    async with httpx.AsyncClient() as client:
        result = await check_groq(client, settings)
    assert result.ok
    assert result.data["missing"] == ["qwen/qwen3.8-27b"]


@respx.mock
async def test_groq_fails_without_primary(settings: Settings) -> None:
    respx.get("https://groq.test/openai/v1/models").respond(json=_models("openai/gpt-oss-20b"))
    async with httpx.AsyncClient() as client:
        result = await check_groq(client, settings)
    assert not result.ok
    assert "openai/gpt-oss-120b" in result.data["missing"]


@respx.mock
async def test_groq_sends_bearer_key(settings: Settings) -> None:
    route = respx.get("https://groq.test/openai/v1/models").respond(json=_models("openai/gpt-oss-120b"))
    async with httpx.AsyncClient() as client:
        await check_groq(client, settings)
    assert route.calls.last.request.headers["Authorization"] == "Bearer test-groq-key"


async def test_groq_without_key_fails_fast() -> None:
    s = Settings(_env_file=None, groq_api_key=None)
    async with httpx.AsyncClient() as client:
        result = await check_groq(client, s)
    assert not result.ok
    assert "not set" in result.detail


@respx.mock
@pytest.mark.parametrize("status", [401, 503])
async def test_groq_http_errors_are_reported(settings: Settings, status: int) -> None:
    respx.get("https://groq.test/openai/v1/models").respond(status_code=status)
    async with httpx.AsyncClient() as client:
        result = await check_groq(client, settings)
    assert not result.ok


@respx.mock
async def test_hindsight_version_and_disabled_features(settings: Settings) -> None:
    respx.get("https://hindsight.test/version").respond(
        json={"api_version": "0.10.1", "features": {"observations": True, "worker": False}}
    )
    banks = respx.get("https://hindsight.test/v1/default/banks").respond(json={"banks": []})
    async with httpx.AsyncClient() as client:
        result = await check_hindsight(client, settings)
    assert result.ok
    assert "0.10.1" in result.detail
    assert "worker" in result.detail
    assert banks.calls.last.request.headers["Authorization"] == "Bearer test-hindsight-key"


@respx.mock
async def test_hindsight_needs_a_key_that_works(settings: Settings) -> None:
    respx.get("https://hindsight.test/version").respond(json={"api_version": "0.10.1"})
    respx.get("https://hindsight.test/v1/default/banks").respond(401)
    async with httpx.AsyncClient() as client:
        rejected = await check_hindsight(client, settings)
        missing = await check_hindsight(client, settings.model_copy(update={"hindsight_api_key": None}))
    assert (rejected.ok, rejected.detail) == (False, "HINDSIGHT_API_KEY rejected")
    assert (missing.ok, missing.detail) == (False, "HINDSIGHT_API_KEY not set")


@respx.mock
async def test_hindsight_unreachable(settings: Settings) -> None:
    respx.get("https://hindsight.test/version").mock(side_effect=httpx.ConnectError("down"))
    async with httpx.AsyncClient() as client:
        result = await check_hindsight(client, settings)
    assert not result.ok
