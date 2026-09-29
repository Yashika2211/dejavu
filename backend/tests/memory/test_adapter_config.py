"""Bank configuration survives an organisation without Memory Defense."""

from typing import Any

import pytest

from dejavu.memory.hindsight_adapter import HindsightMemory, MemoryUnavailableError


class StubSdk:
    """Records config updates; refuses Memory Defense the way Cloud does without the detector."""

    def __init__(self, refuse_defense: bool) -> None:
        self.refuse_defense = refuse_defense
        self.updates: list[dict[str, Any]] = []

    async def acreate_bank(self, bank_id: str, name: str) -> None:
        return None

    async def aclose(self) -> None:
        return None

    async def aupdate_bank_config(self, bank_id: str, **config: Any) -> None:
        if "memory_defense" in config and self.refuse_defense:
            raise RuntimeError("400, message='Bad Request'")
        self.updates.append(config)


@pytest.fixture
async def memory(settings):
    backend = HindsightMemory(settings)
    yield backend
    await backend.aclose()


@pytest.mark.parametrize("refuse", [True, False])
async def test_memory_defense_is_applied_separately(memory: HindsightMemory, refuse: bool) -> None:
    sdk = StubSdk(refuse_defense=refuse)
    memory._sdk = sdk  # type: ignore[assignment]
    await memory.configure_bank("b", retain_mission="m", memory_defense={"enabled": True})
    assert sdk.updates[0] == {"retain_mission": "m"}
    assert (len(sdk.updates) == 2) is not refuse


async def test_other_config_failures_still_raise(memory: HindsightMemory) -> None:
    class Broken(StubSdk):
        async def aupdate_bank_config(self, bank_id: str, **config: Any) -> None:
            raise RuntimeError("500")

    memory._sdk = Broken(refuse_defense=False)  # type: ignore[assignment]
    with pytest.raises(MemoryUnavailableError):
        await memory.configure_bank("b", retain_mission="m", memory_defense={"enabled": True})
