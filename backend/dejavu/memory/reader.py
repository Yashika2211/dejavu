"""The read path (spec 6.5): the triage briefing before the first tool call, and `recall_memory`.

Briefing: observations recalled for the alert's service and symptom (`tags_match="any"`, so
untagged Day-0 material stays visible), then a reflect with the TriageBrief schema and `based_on`
citations. If reflect returns no structured output it is retried once, then the briefing falls
back to the recalled observations. Lookups recall facts, experiences and observations at a low
budget. Every recall passes `query_timestamp` = the incident time, anchoring temporal ranking;
reflect has no such parameter (0.10.1), so the triage query states the time in its text.
"""

from pydantic import ValidationError

from dejavu.agent.schemas import TriageBrief
from dejavu.llm.toolcalling import inline_schema
from dejavu.memory.hindsight_adapter import MemoryBackend, MemoryHit, ReflectAnswer
from dejavu.sim.clock import fmt_hm
from dejavu.strategies.base import IncidentContext, MemoryBriefing
from dejavu.tokens import clip, fit_blocks

MAX_BRIEF_TOKENS = 700
MAX_LOOKUP_TOKENS = 700
TRIAGE_QUERY = (
    "It is {time}. Alert: {alert}. Affected service: {service}. Based on everything learned from past "
    "incidents: which root causes are most likely and with what prior; which cheap checks best discriminate "
    "between them; which fixes worked, failed or made things worse; and is any of that knowledge stale because "
    "of later migrations or changes? Cite incident IDs and dates."
)


def read_tags(ctx: IncidentContext) -> list[str]:
    tags = [f"service:{ctx.service}"]
    if ctx.symptom:
        tags.append(f"symptom:{ctx.symptom.value}")
    return tags


def hit_line(hit: MemoryHit) -> str:
    where = ", ".join(x for x in (hit.when[:10] if hit.when else "", hit.document_id or "") if x)
    kind = f"[{hit.type}] " if hit.type else ""
    return f"- {kind}{hit.text.strip()}" + (f" ({where})" if where else "")


def render_brief(brief: TriageBrief) -> str:
    parts = []
    if brief.likely_causes:
        lines = ["Likely causes (priors from memory):"]
        for c in sorted(brief.likely_causes, key=lambda c: -c.prior)[:4]:
            refs = ", ".join(c.precedent_incident_ids) or "no precedent cited"
            valid = {"yes": "still valid", "no": "NO LONGER VALID", "unknown": "validity unknown"}[
                c.still_valid
            ]
            note = f" ({c.validity_note})" if c.validity_note else ""
            seen = f", last seen {c.last_seen}" if c.last_seen else ""
            lines.append(
                f"- {c.cause} in {c.service}: prior {c.prior:.0%}. {c.why} [{refs}{seen}; {valid}{note}]"
            )
        parts.append("\n".join(lines))
    if brief.first_checks:
        parts.append(
            "Cheapest discriminating checks:\n"
            + "\n".join(f"- {c.check}: {c.reason}" for c in brief.first_checks[:4])
        )
    if brief.avoid:
        parts.append(
            "Avoid:\n"
            + "\n".join(
                f"- {a.action}: {a.reason}"
                + (f" [{', '.join(a.precedent_incident_ids)}]" if a.precedent_incident_ids else "")
                for a in brief.avoid[:4]
            )
        )
    if brief.stale_knowledge_warnings:
        parts.append("Stale knowledge:\n" + "\n".join(f"- {w}" for w in brief.stale_knowledge_warnings[:3]))
    if brief.novel_signals:
        parts.append("Not seen before:\n" + "\n".join(f"- {s}" for s in brief.novel_signals[:3]))
    return "\n\n".join(parts) or "Memory has nothing specific about this alert."


def _structured(answer: ReflectAnswer | None) -> TriageBrief | None:
    if answer is None or not answer.structured:
        return None
    try:
        return TriageBrief.model_validate(answer.structured)
    except ValidationError:
        return None


async def triage_brief(memory: MemoryBackend, bank_id: str, ctx: IncidentContext) -> MemoryBriefing:
    tags = read_tags(ctx)
    observations = await memory.recall(
        bank_id,
        f"{ctx.alert_name}. {ctx.summary}",
        types=["observation"],
        tags=tags,
        tags_match="any",
        budget="mid",
        max_tokens=1500,
        query_timestamp=ctx.alert_at,
        include_source_facts=True,
    )
    query = TRIAGE_QUERY.format(
        time=f"{fmt_hm(ctx.alert_at)} IST on {ctx.alert_at:%a %d %b %Y}",
        alert=ctx.summary,
        service=ctx.service,
    )
    answer: ReflectAnswer | None = None
    brief: TriageBrief | None = None
    for _ in range(2):
        answer = await memory.reflect(
            bank_id,
            query,
            budget="mid",
            response_schema=inline_schema(TriageBrief),
            tags=tags,
            tags_match="any",
        )
        brief = _structured(answer)
        if brief is not None:
            break
    if brief is not None:
        text = render_brief(brief)
    elif observations:
        text = "What past incidents suggest (observations):\n" + "\n".join(
            hit_line(h) for h in observations[:8]
        )
    else:
        text = "Memory has nothing about this alert yet."
    return MemoryBriefing(
        source="dejavu",
        text=clip(text, MAX_BRIEF_TOKENS),
        first_checks=[c.check for c in brief.first_checks] if brief else [],
        data={
            "brief": brief.model_dump(mode="json") if brief else None,
            "based_on": [h.model_dump() for h in (answer.based_on if answer else [])],
            "observations": [h.model_dump() for h in observations],
            "structured_error": answer.structured_error if answer and brief is None else None,
        },
    )


async def lookup(memory: MemoryBackend, bank_id: str, query: str, ctx: IncidentContext) -> str:
    hits = await memory.recall(
        bank_id,
        query,
        types=["observation", "world", "experience"],
        budget="low",
        max_tokens=800,
        query_timestamp=ctx.alert_at,
    )
    if not hits:
        return f"Nothing in memory matches {query!r}."
    return fit_blocks(
        f"Memory results for {query!r} (priors, not facts):",
        [hit_line(h) for h in hits],
        max_tokens=MAX_LOOKUP_TOKENS,
        more="results",
    )
