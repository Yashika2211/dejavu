"""The baseline: a capable agent that remembers nothing between incidents."""

from dejavu.agent.schemas import AgentStep, Diagnosis
from dejavu.documents import Document
from dejavu.strategies.base import IncidentContext, MemoryBriefing, Resolution


class Amnesiac:
    name = "amnesiac"
    has_memory = False

    async def brief(self, incident: IncidentContext) -> MemoryBriefing | None:
        return None

    async def lookup(self, query: str, incident: IncidentContext) -> str:
        return "No memory is available to this agent."

    async def on_step(self, step: AgentStep, incident: IncidentContext) -> None:
        return None

    async def on_diagnosis(self, diagnosis: Diagnosis, incident: IncidentContext) -> None:
        return None

    async def on_resolution(self, resolution: Resolution) -> None:
        return None

    async def remember(self, docs: list[Document]) -> None:
        return None
