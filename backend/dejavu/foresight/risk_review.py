"""Risk reviews of pending changes (spec 8).

DejaVu recalls what memory holds about the touched service's changes, incidents and outcomes, then
reflects with the `RiskReview` schema, citing precedents. The amnesiac baseline gets the same change
and the same schema from the model alone. `recommended_action` and `safeguards` come from fixed
catalogs, so whether a review would have prevented an incident is decided by a rule, not a judge.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from dejavu.foresight.pending import PendingChange
from dejavu.llm.errors import LLMError
from dejavu.llm.toolcalling import ToolCaller, tool_spec
from dejavu.memory.hindsight_adapter import MemoryBackend, MemoryHit
from dejavu.sim.scenario import Safeguard, Scenario

Action = Literal["ship", "ship_with_canary", "hold", "block"]
GUARDED: frozenset[str] = frozenset({"ship_with_canary", "hold", "block"})
SAFEGUARDS = ", ".join(s.value for s in Safeguard)

MEMORY_QUESTION = (
    "A change is about to ship: {change} Based on past incidents, postmortems and changes: how risky is it, "
    "what could it break, and which past incidents does it resemble (cite incident IDs and dates)? Should we "
    "ship, ship with a canary, hold or block it, and which safeguards would have prevented similar incidents "
    f"(choose from: {SAFEGUARDS})?"
)
GENERIC_SYSTEM = (
    "You review production changes for Kestrel Pay, an Indian payments company. You know nothing about its "
    "past incidents. Judge each change from its description alone, then call submit_review."
)
GENERIC_QUESTION = (
    "A change is about to ship: {change} How risky is it and what could it break? Should we ship, ship with a "
    f"canary, hold or block it, and which safeguards would reduce the risk (choose from: {SAFEGUARDS})?"
)


class Precedent(BaseModel):
    incident_id: str
    date: str | None = None
    resemblance: str = Field(description="how this change resembles what happened then")


class RiskReview(BaseModel):
    risk: Literal["low", "medium", "high"]
    summary: str = Field(description="two sentences at most")
    failure_modes: list[str] = Field(default_factory=list, description="what could break, most likely first")
    precedents: list[Precedent] = Field(default_factory=list)
    recommended_action: Action
    safeguards: list[Safeguard] = Field(default_factory=list)


class ReviewResult(BaseModel):
    source: Literal["dejavu", "amnesiac"]
    review: RiskReview | None
    based_on: list[MemoryHit] = Field(default_factory=list)
    error: str | None = None


def describe(change: PendingChange) -> str:
    details = "; ".join(f"{k}: {v}" for k, v in change.details.items() if v not in (None, "", []))
    when = change.planned_at.strftime("%a %d %b %Y %H:%M")
    return f"{change.type.value} to {change.service} by {change.author}, planned for {when} IST. {change.summary}. {details}."


def _review(raw: dict[str, Any] | None) -> RiskReview | None:
    if not raw:
        return None
    try:
        return RiskReview.model_validate(raw)
    except ValidationError:
        return None


async def memory_review(memory: MemoryBackend, bank: str, change: PendingChange) -> ReviewResult:
    """DejaVu's review: evidence recalled for the service, then a reflect with the schema."""
    evidence = await memory.recall(
        bank,
        describe(change),
        types=["world", "experience", "observation"],
        tags=[f"service:{change.service}"],
        tags_match="any",
        budget="mid",
        max_tokens=1500,
        query_timestamp=change.planned_at,
    )
    answer = await memory.reflect(
        bank,
        MEMORY_QUESTION.format(change=describe(change)),
        budget="mid",
        response_schema=RiskReview.model_json_schema(),
        tags=[f"service:{change.service}"],
        tags_match="any",
    )
    review = _review(answer.structured)
    return ReviewResult(
        source="dejavu",
        review=review,
        based_on=answer.based_on or evidence,
        error=None if review else answer.structured_error or "memory returned no structured review",
    )


async def generic_review(caller: ToolCaller, change: PendingChange) -> ReviewResult:
    """The amnesiac baseline: the same change and schema, from the model alone."""
    spec = tool_spec("submit_review", "Submit the risk review of the change.", RiskReview)
    messages = [
        {"role": "system", "content": GENERIC_SYSTEM},
        {"role": "user", "content": GENERIC_QUESTION.format(change=describe(change))},
    ]
    try:
        decision = await caller.decide(messages, [spec], purpose="foresight")
    except LLMError as exc:
        return ReviewResult(source="amnesiac", review=None, error=f"{type(exc).__name__}: {exc}"[:300])
    args = {k: v for k, v in decision.calls[0].args.items() if k != "rationale"}
    review = _review(args)
    return ReviewResult(
        source="amnesiac", review=review, error=None if review else "the model's review did not validate"
    )


def prevents(review: RiskReview | None, latent: Scenario | None) -> bool | None:
    """Spec 8: a guarded action plus at least one of the latent incident's preventing safeguards.

    None when there is nothing to prevent (a harmless change) or no review to judge.
    """
    if latent is None or review is None:
        return None
    return review.recommended_action in GUARDED and bool(set(review.safeguards) & set(latent.spec.prevention))
