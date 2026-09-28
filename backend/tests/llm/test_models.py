import pytest

from dejavu.config import Settings
from dejavu.llm.models import usable_models


def _models(*ids: str) -> dict:
    return {
        "object": "list",
        "data": [{"id": i, "object": "model", "created": 0, "owned_by": "x", "active": True} for i in ids],
    }


async def test_unavailable_models_are_dropped_in_order(make_client, groq) -> None:
    client, _ = make_client()
    groq.add(_models("qwen/qwen3.8-27b", "openai/gpt-oss-120b"))
    settings = Settings(
        _env_file=None, llm_primary="openai/gpt-oss-120b", llm_fallbacks=["gone/model", "qwen/qwen3.8-27b"]
    )
    assert await usable_models(client, settings) == ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"]


async def test_no_usable_model_is_an_error(make_client, groq) -> None:
    client, _ = make_client()
    groq.add(_models("something/else"))
    with pytest.raises(RuntimeError, match="none of the configured models"):
        await usable_models(client, Settings(_env_file=None))
