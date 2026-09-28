"""Token prices (USD per million tokens) for cost accounting in run traces and the eval report.

Override with `LLM_PRICES='{"model": [input, output], ...}'`. gpt-oss-120b's price is the one in
the build spec; the others are estimates (see DECISIONS.md) and marked as such in reports.
"""

from dejavu.config import Settings

DEFAULT_PRICES: dict[str, tuple[float, float]] = {
    "openai/gpt-oss-120b": (0.15, 0.60),
    "openai/gpt-oss-20b": (0.075, 0.30),
    "qwen/qwen3.8-27b": (0.29, 0.59),
}


def price_of(model: str, settings: Settings) -> tuple[float, float]:
    override = settings.llm_prices.get(model)
    if override:
        return float(override[0]), float(override[1])
    return DEFAULT_PRICES.get(model, (0.0, 0.0))


def cost_usd(model: str, tokens_in: int, tokens_out: int, settings: Settings) -> float:
    price_in, price_out = price_of(model, settings)
    return (tokens_in * price_in + tokens_out * price_out) / 1_000_000
