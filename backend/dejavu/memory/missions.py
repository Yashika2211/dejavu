"""Bank missions, reflect directives and the entity-label vocabulary for the `dejavu` profile.

Mission text is verbatim from the build spec (Section 6.2); tune it with the prompt-preview
API rather than editing it blind.
"""

from dataclasses import dataclass
from typing import Any

from dejavu.taxonomy import Outcome, Remediation, RootCause, SymptomClass

RETAIN_MISSION = (
    "Extract operational knowledge for incident response at Kestrel Pay: symptoms (metric and log "
    "signatures, alert names), root causes, triggers (deploys, config changes, feature flags, external "
    "providers, infrastructure events), the signals that distinguished the true cause from look-alike "
    "causes, every remediation attempted and whether it worked, did nothing, or made things worse, time "
    "wasted on wrong hypotheses, infrastructure migrations and what they changed, service ownership, and "
    "team rules. Ignore greetings, small talk, scheduling logistics and raw metric dumps."
)

OBSERVATIONS_MISSION = (
    "Maintain durable, evidence-backed operational beliefs: the recurring failure modes of each service "
    "and how often they occur; which signals discriminate between look-alike root causes; which fixes "
    "work, which don't, and which are dangerous; how migrations changed what works (always state before "
    "and after, with dates); which kinds of changes tend to precede incidents. Ignore one-off noise."
)

REFLECT_MISSION = (
    "I am DejaVu, the on-call SRE agent for Kestrel Pay. I have been on call for every incident since I "
    "was deployed, and I inherited Marcus Oyelaran's postmortems and runbooks. I reason like a skeptical "
    "senior SRE: memories are hypotheses to verify against live telemetry, recent evidence outranks old "
    "evidence, migrations can invalidate old fixes, and I cite the incident IDs behind every claim."
)

DISPOSITION = {"disposition_skepticism": 4, "disposition_literalism": 3, "disposition_empathy": 2}

MEMORY_DEFENSE: dict[str, Any] = {
    "enabled": True,
    "rules": [{"on": "sensitive_data", "action": "redact"}],
}


@dataclass(frozen=True)
class Directive:
    """A hard rule Hindsight applies during reflect."""

    name: str
    content: str


DIRECTIVES: tuple[Directive, ...] = (
    Directive(
        "evidence-over-memory",
        "Never present a remembered pattern as the confirmed root cause; state what live evidence "
        "confirms or refutes it.",
    ),
    Directive(
        "cite-precedents",
        "Any claim derived from past incidents must cite incident IDs and dates.",
    ),
    Directive(
        "respect-negative-history",
        "Never recommend a fix that a past incident recorded as ineffective or harmful without flagging "
        "that history.",
    ),
    Directive(
        "stateful-systems",
        "Never recommend restarting, failing over or modifying postgres-ledger, the cache or Kafka "
        "without stating that approval from the owning team is required.",
    ),
    Directive(
        "temporal-validity",
        "When a remembered fix predates a migration that touched the same component, say so and prefer "
        "post-migration evidence.",
    ),
)


def _enum_group(key: str, description: str, values: list[str], *, multi: bool) -> dict[str, Any]:
    return {
        "key": key,
        "description": description,
        "type": "multi-values" if multi else "value",
        "optional": True,
        "values": [{"value": v} for v in values],
    }


ENTITY_LABELS: list[dict[str, Any]] = [
    _enum_group(
        "failure_mode",
        "Root-cause category the fact is about, if any.",
        [c.value for c in RootCause],
        multi=True,
    ),
    _enum_group(
        "symptom",
        "Alert-level symptom class the fact describes.",
        [s.value for s in SymptomClass],
        multi=True,
    ),
    _enum_group(
        "remediation",
        "Kind of remediation the fact describes being attempted or recommended.",
        [r.value for r in Remediation],
        multi=True,
    ),
    _enum_group(
        "outcome",
        "What a remediation did: worked, had no effect, or made things worse.",
        [o.value for o in Outcome],
        multi=False,
    ),
]
