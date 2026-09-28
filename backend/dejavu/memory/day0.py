"""Day-0 import: Marcus's postmortems, the handbook, the runbooks and two RFCs (spec 4.7, 6.4).

Markdown documents are retained with their original dates, so old runbooks stay old for temporal
ranking; the two documents marked `format: pdf` go through `retain_files` to exercise file
ingestion. The bank is settled before the first incident.
"""

import tempfile
from pathlib import Path

from dejavu.documents import day0_documents
from dejavu.memory.hindsight_adapter import MemoryBackend
from dejavu.memory.settle import SettleReport, settle
from dejavu.memory.writer import day0_payloads


async def import_day0(
    memory: MemoryBackend, bank_id: str, *, timeout_s: float = 1200.0, consolidate: bool = True
) -> SettleReport:
    with tempfile.TemporaryDirectory() as tmp:
        items, files = day0_payloads(list(day0_documents()), Path(tmp))
        ops = await memory.retain(bank_id, items)
        if files:
            ops += await memory.retain_files(bank_id, files)
    return await settle(memory, bank_id, ops, timeout_s=timeout_s, consolidate=consolidate)
