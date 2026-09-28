"""NaiveRAG: the ablation that keeps every document but learns nothing from them (spec 6.8).

It receives exactly what DejaVu receives, in the same order, because it inherits DejaVu's write
path; its bank is a plain chunk store (no fact extraction, no observations, no mental models, no
reflect). The briefing is the chunks most similar to the alert text, and `recall_memory` is the
same similarity search over the agent's own query. No tags and no synthesis.
"""

from dejavu.memory.bank_setup import Profile
from dejavu.memory.hindsight_adapter import MemoryHit
from dejavu.memory.reader import hit_line
from dejavu.strategies.base import IncidentContext, MemoryBriefing
from dejavu.strategies.dejavu import DejaVu
from dejavu.tokens import clip, fit_blocks

MAX_TOKENS = 700
PASSAGE_TOKENS = 250  # chunks can be long; show several rather than one


def _passages(hits: list[MemoryHit]) -> list[str]:
    return [clip(hit_line(h), PASSAGE_TOKENS) for h in hits]


class NaiveRAG(DejaVu):
    name = "rag"
    profile: Profile = "rag"
    consolidate = False

    async def brief(self, incident: IncidentContext) -> MemoryBriefing | None:
        hits = await self.memory.recall(
            self.bank_id,
            f"{incident.alert_name}. {incident.summary}",
            budget="low",
            max_tokens=1500,
            query_timestamp=incident.alert_at,
        )
        if not hits:
            return None
        text = fit_blocks(
            "Most similar passages from past documents (retrieved by text similarity):",
            _passages(hits),
            max_tokens=MAX_TOKENS,
            more="passages",
        )
        return MemoryBriefing(source="rag", text=text, data={"chunks": [h.model_dump() for h in hits]})

    async def lookup(self, query: str, incident: IncidentContext) -> str:
        hits = await self.memory.recall(
            self.bank_id, query, budget="low", max_tokens=800, query_timestamp=incident.alert_at
        )
        if not hits:
            return f"No passages match {query!r}."
        return fit_blocks(
            f"Passages most similar to {query!r}:",
            _passages(hits),
            max_tokens=MAX_TOKENS,
            more="passages",
        )
