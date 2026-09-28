"""The contract every memory strategy implements (spec 5.1).

All strategies share the same loop, prompts, tools and step budget; they differ only in what they
bring to an incident (the briefing and `recall_memory`) and what they keep afterwards.
"""

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field

from dejavu.agent.schemas import AgentStep, Diagnosis
from dejavu.documents import Document
from dejavu.sim.generators.events import ChangeEvent
from dejavu.taxonomy import SymptomClass

# Alert names are observable, so mapping them to a symptom class leaks nothing about the cause.
ALERT_SYMPTOMS: dict[str, SymptomClass] = {
    "CheckoutLatencyP99High": SymptomClass.LATENCY_P99,
    "LedgerLatencyP99High": SymptomClass.LATENCY_P99,
    "PaymentsErrorRateHigh": SymptomClass.ERROR_RATE_5XX,
    "EdgeGateway5xxHigh": SymptomClass.ERROR_RATE_5XX,
    "AuthFailureRateHigh": SymptomClass.AUTH_FAILURES,
    "LedgerWriteErrorsHigh": SymptomClass.WRITE_FAILURES,
}


class IncidentContext(BaseModel):
    """What any responder knows when paged: the alert, the time, the service it names."""

    incident_id: str
    alert: dict[str, Any]
    alert_at: datetime
    service: str
    symptom: SymptomClass | None

    @property
    def alert_name(self) -> str:
        return str(self.alert["labels"]["alertname"])

    @property
    def summary(self) -> str:
        return f"{self.alert_name}: {self.alert['annotations']['description']}"

    @classmethod
    def from_alert(cls, incident_id: str, alert: dict[str, Any], alert_at: datetime) -> "IncidentContext":
        name = alert["labels"]["alertname"]
        return cls(
            incident_id=incident_id,
            alert=alert,
            alert_at=alert_at,
            service=alert["labels"]["service"],
            symptom=ALERT_SYMPTOMS.get(name),
        )


class MemoryBriefing(BaseModel):
    """What a strategy injects before the first tool call, as a delimited block."""

    source: str
    text: str
    first_checks: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class Resolution(BaseModel):
    """Everything a team knows once an incident is over; what memory strategies learn from."""

    incident: IncidentContext
    diagnosis: Diagnosis | None
    steps: list[AgentStep]
    outcome: dict[str, Any]
    documents: dict[str, Document]
    resolved_at: datetime
    changes: list[ChangeEvent] = Field(default_factory=list)


class MemoryStrategy(Protocol):
    name: str
    has_memory: bool

    async def brief(self, incident: IncidentContext) -> MemoryBriefing | None: ...

    async def lookup(self, query: str, incident: IncidentContext) -> str: ...

    async def on_step(self, step: AgentStep, incident: IncidentContext) -> None: ...

    async def on_diagnosis(self, diagnosis: Diagnosis, incident: IncidentContext) -> None: ...

    async def on_resolution(self, resolution: Resolution) -> None: ...

    async def remember(self, docs: list[Document]) -> None:
        """Team documents published as the calendar reaches them (migration RFCs, announcements)."""
        ...
