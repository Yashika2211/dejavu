"""Mental models: per-dimension, self-refreshing summaries of what the bank has learned (spec 6.6).

One "everything" model is as useful as none, so there is one per core service plus a triage
playbook, a change-risk register and team conventions. They refresh after consolidation (delta
mode, at most once a minute). Tagged models default to `all_strict` on the server, which would hide
untagged Day-0 material, so service models ask for `tags_match: any`.
"""

from dataclasses import dataclass, field
from typing import Any

from dejavu.memory.hindsight_adapter import MemoryBackend

CORE_SERVICES = (
    "ledger-svc",
    "checkout-api",
    "payments-svc",
    "auth-svc",
    "fraud-scorer",
    "notifications-worker",
    "postgres-ledger",
    "edge-gateway",
)
TRIGGER: dict[str, Any] = {
    "refresh_after_consolidation": True,
    "mode": "delta",
    "min_refresh_interval_seconds": 60,
}
SERVICE_QUERY = (
    "What are the known failure modes of {svc}, which signals distinguish them, which fixes work today (after "
    "any migrations), and which fixes failed or made things worse? Cite incident IDs and dates."
)


@dataclass(frozen=True)
class MentalModelSpec:
    id: str
    name: str
    source_query: str
    tags: list[str] = field(default_factory=list)
    trigger: dict[str, Any] = field(default_factory=lambda: dict(TRIGGER))


def mental_model_specs() -> list[MentalModelSpec]:
    services = [
        MentalModelSpec(
            id=f"svc-{svc}-failure-modes",
            name=f"{svc}: failure modes and what works now",
            source_query=SERVICE_QUERY.format(svc=svc),
            tags=[f"service:{svc}"],
            trigger={**TRIGGER, "tags_match": "any"},
        )
        for svc in CORE_SERVICES
    ]
    return [
        *services,
        MentalModelSpec(
            "triage-playbook",
            "Triage playbook",
            "For each symptom class, what should on-call check first, in what order, and why?",
        ),
        MentalModelSpec(
            "change-risk-register",
            "Change risk register",
            "Which kinds of changes have preceded incidents, in which services, and which safeguards "
            "would have prevented them?",
        ),
        MentalModelSpec(
            "team-conventions",
            "Team conventions",
            "What rules and preferences does the team apply during incidents and in postmortems?",
        ),
    ]


async def ensure_mental_models(memory: MemoryBackend, bank_id: str) -> list[str]:
    """Create the models the bank does not have yet; returns the creation operation ids."""
    existing = {m.id for m in await memory.mental_models(bank_id)}
    ops = []
    for spec in mental_model_specs():
        if spec.id in existing:
            continue
        op = await memory.create_mental_model(
            bank_id, spec.id, spec.name, spec.source_query, spec.tags, spec.trigger
        )
        if op:
            ops.append(op)
    return ops
