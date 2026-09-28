"""Which configured models can actually be used (spec 5.4).

At startup the model chain (primary, then fallbacks) is checked against Groq's `GET /models`;
models the key cannot use are dropped with a warning instead of failing mid-incident. Groq
deprecated qwen3-32b and llama-3.3-70b for free and developer tiers in 2026, so nothing here
hardcodes a model: the chain comes from settings.
"""

import structlog

from dejavu.config import Settings
from dejavu.llm.client import LLMClient

log = structlog.get_logger(__name__)


async def usable_models(client: LLMClient, settings: Settings) -> list[str]:
    """The agent's model chain, primary first, restricted to models the key can use now."""
    chain = list(dict.fromkeys([settings.llm_primary, *settings.llm_fallbacks]))
    available = await client.available_models()
    usable = [m for m in chain if m in available]
    for missing in (m for m in chain if m not in available):
        log.warning("model unavailable, disabled", model=missing)
    if not usable:
        raise RuntimeError(f"none of the configured models are available: {', '.join(chain)}")
    return usable
