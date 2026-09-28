"""Idempotent bank setup for the two memory profiles (spec 6.1, 6.2, 6.8).

- `dejavu`: missions, dispositions, observations, the entity-label vocabulary, Memory Defense,
  the five reflect directives and the mental models.
- `rag`: the naive-RAG ablation, a plain chunk store with observations off and nothing on top.

Running it twice changes nothing: the bank config is an upsert, directives are matched by name and
mental models by id.
"""

from typing import Literal

from dejavu.memory.hindsight_adapter import MemoryBackend
from dejavu.memory.mental_models import ensure_mental_models
from dejavu.memory.missions import (
    DIRECTIVES,
    DISPOSITION,
    ENTITY_LABELS,
    MEMORY_DEFENSE,
    OBSERVATIONS_MISSION,
    REFLECT_MISSION,
    RETAIN_MISSION,
)

Profile = Literal["dejavu", "rag"]


async def setup_bank(memory: MemoryBackend, bank_id: str, profile: Profile = "dejavu") -> list[str]:
    """Configure `bank_id`; returns operation ids of anything created asynchronously."""
    if profile == "rag":
        await memory.configure_bank(
            bank_id, retain_extraction_mode="chunks", enable_observations=False, memory_defense=MEMORY_DEFENSE
        )
        return []
    await memory.configure_bank(
        bank_id,
        retain_mission=RETAIN_MISSION,
        observations_mission=OBSERVATIONS_MISSION,
        reflect_mission=REFLECT_MISSION,
        enable_observations=True,
        entity_labels=ENTITY_LABELS,
        memory_defense=MEMORY_DEFENSE,
        **DISPOSITION,
    )
    existing = await memory.directive_names(bank_id)
    for directive in DIRECTIVES:
        if directive.name not in existing:
            await memory.add_directive(bank_id, directive.name, directive.content)
    return await ensure_mental_models(memory, bank_id)
