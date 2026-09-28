"""DejaVu: the memory strategy backed by Hindsight (spec 6).

Before the first tool call it briefs the agent from memory (priors, discriminating checks, what to
avoid, stale knowledge). During the investigation `recall_memory` looks things up. Once the
incident is resolved it retains what happened (the alert timeline, its own first-person
investigation log, the outcome, the recent changes, the human feedback and the postmortem) and
settles the bank so the next incident sees what this one taught.
"""

import uuid

from dejavu.agent.schemas import AgentStep, Diagnosis
from dejavu.documents import Document
from dejavu.memory.hindsight_adapter import MemoryBackend
from dejavu.memory.reader import lookup, triage_brief
from dejavu.memory.settle import SettleReport, settle
from dejavu.memory.writer import document_item, incident_items
from dejavu.strategies.base import IncidentContext, MemoryBriefing, Resolution

_OPS_NAMESPACE = uuid.UUID("8a2d3c4e-5f60-4718-9a0b-1c2d3e4f5a6b")


class DejaVu:
    name = "dejavu"
    has_memory = True

    def __init__(self, memory: MemoryBackend, bank_id: str, *, settle_timeout_s: float = 900.0) -> None:
        self.memory = memory
        self.bank_id = bank_id
        self.settle_timeout_s = settle_timeout_s
        self.last_settle: SettleReport | None = None

    async def brief(self, incident: IncidentContext) -> MemoryBriefing | None:
        return await triage_brief(self.memory, self.bank_id, incident)

    async def lookup(self, query: str, incident: IncidentContext) -> str:
        return await lookup(self.memory, self.bank_id, query, incident)

    async def on_step(self, step: AgentStep, incident: IncidentContext) -> None:
        return None

    async def on_diagnosis(self, diagnosis: Diagnosis, incident: IncidentContext) -> None:
        return None

    async def on_resolution(self, resolution: Resolution) -> None:
        items = incident_items(resolution, resolution.changes)
        operation_id = str(uuid.uuid5(_OPS_NAMESPACE, f"{self.bank_id}/{resolution.incident.incident_id}"))
        ops = await self.memory.retain(self.bank_id, items, operation_id=operation_id)
        self.last_settle = await settle(self.memory, self.bank_id, ops, timeout_s=self.settle_timeout_s)

    async def remember_documents(self, docs: list[Document]) -> None:
        """Retain documents as the calendar reaches them (migration RFCs and announcements)."""
        ops = await self.memory.retain(self.bank_id, [document_item(d) for d in docs])
        self.last_settle = await settle(self.memory, self.bank_id, ops, timeout_s=self.settle_timeout_s)
