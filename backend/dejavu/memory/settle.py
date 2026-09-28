"""Settle the bank before the next incident (spec 6.4).

Hindsight's docs warn against retaining and recalling in the same turn; the next incident must see
what the last one taught. After each incident: wait for the retain operations, trigger
consolidation, then wait until nothing is pending (which also covers mental-model refreshes that
consolidation queues). A failed refresh pauses a model's automatic refreshes until a manual one
succeeds, so paused models are refreshed by hand. Every wait has a timeout and ends with one log line.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable

import structlog
from pydantic import BaseModel

from dejavu.memory.hindsight_adapter import MemoryBackend

log = structlog.get_logger(__name__)
TERMINAL = {"completed", "failed", "cancelled"}


class SettleReport(BaseModel):
    seconds: float
    operations: int
    failed: list[str]
    observations: int | None
    timed_out: bool
    refreshed: list[str] = []


async def settle(
    memory: MemoryBackend,
    bank_id: str,
    operation_ids: list[str],
    *,
    timeout_s: float = 900.0,
    poll_s: float = 2.0,
    consolidate: bool = True,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> SettleReport:
    """Wait for `operation_ids`, then (with `consolidate`) for a consolidation pass and its fallout."""
    start = clock()
    deadline = start + timeout_s
    failed: list[str] = []
    timed_out = False

    async def wait_for(ops: list[str]) -> bool:
        pending = set(ops)
        while pending:
            for op in sorted(pending):
                status = await memory.operation_status(bank_id, op)
                if status in TERMINAL:
                    pending.discard(op)
                    if status != "completed":
                        failed.append(op)
            if pending:
                if clock() >= deadline:
                    return False
                await sleep(poll_s)
        return True

    timed_out = not await wait_for(operation_ids)
    stats: dict = {}
    if consolidate and not timed_out:
        timed_out = not await wait_for([await memory.consolidate(bank_id)])
    while not timed_out:
        stats = await memory.stats(bank_id)
        if not stats.get("pending_consolidation") and not stats.get("pending_operations"):
            break
        if clock() >= deadline:
            timed_out = True
            break
        await sleep(poll_s)

    refreshed: list[str] = []
    if consolidate and not timed_out:
        refreshed = [m.id for m in await memory.mental_models(bank_id) if m.refresh_paused]
        if refreshed:
            log.warning("mental model refresh had failed; refreshing by hand", bank=bank_id, models=refreshed)
            ops = [op for m in refreshed if (op := await memory.refresh_mental_model(bank_id, m))]
            timed_out = not await wait_for(ops)

    report = SettleReport(
        seconds=round(clock() - start, 1),
        operations=len(operation_ids),
        failed=failed,
        observations=stats.get("total_observations"),
        timed_out=timed_out,
        refreshed=refreshed,
    )
    log.info("memory settled", bank=bank_id, **report.model_dump())
    return report
