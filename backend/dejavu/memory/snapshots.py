"""Bank snapshots (spec 6.1): `kestrel-ops-day1` after the Day-0 import, `kestrel-ops-trained`
after the Gauntlet, and the live bank that "Reset demo" re-clones from trained."""

from contextlib import suppress

from dejavu.memory.hindsight_adapter import MemoryBackend, MemoryUnavailableError
from dejavu.memory.settle import SettleReport, settle


async def snapshot(memory: MemoryBackend, source: str, target: str, *, timeout_s: float = 900.0) -> None:
    """Replace `target` with a copy of `source`. Cloning needs a target that doesn't exist yet."""
    with suppress(MemoryUnavailableError):
        await memory.delete_bank(target)
    op = await memory.clone_bank(source, target)
    report: SettleReport
    try:
        report = await settle(memory, source, [op], timeout_s=timeout_s, consolidate=False)
    except MemoryUnavailableError:  # the clone operation may be tracked under the new bank
        report = await settle(memory, target, [op], timeout_s=timeout_s, consolidate=False)
    if report.timed_out or report.failed:
        raise MemoryUnavailableError(f"cloning {source} to {target} did not complete")
