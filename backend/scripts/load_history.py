"""Load the team's written history into a bank: what a real on-call team would have written down.

    uv run python scripts/load_history.py --bank kestrel-ops-live          # incidents 1-24
    uv run python scripts/load_history.py --bank kestrel-ops-live --n 12   # up to incident 12

In calendar order: the migration RFCs and announcements as they were published, then each Gauntlet
incident's postmortem, Slack thread and on-call feedback, exactly as the humans wrote them
(`data/fixtures/incidents/`). This is not a Gauntlet run: DejaVu's own investigations are not
included and no numbers come out of it. It gives the live war room a bank with the team's history.
"""

import argparse
import asyncio

from rich.console import Console

from dejavu.config import get_settings
from dejavu.documents import incident_documents, migration_documents
from dejavu.memory.hindsight_adapter import HindsightMemory
from dejavu.memory.settle import settle
from dejavu.memory.writer import document_item
from dejavu.sim.schedule import entry_for, gauntlet

BATCH = 20


async def main(bank: str, n: int) -> None:
    console = Console()
    docs = list(migration_documents())
    for scenario in gauntlet()[:n]:
        entry = entry_for(scenario)
        if entry is not None:
            docs += incident_documents(entry.n).values()
    docs.sort(key=lambda d: d.date)
    memory = HindsightMemory(get_settings())
    try:
        ops: list[str] = []
        for start in range(0, len(docs), BATCH):
            ops += await memory.retain(bank, [document_item(d) for d in docs[start : start + BATCH]])
        console.print(f"retained {len(docs)} documents into {bank}; settling…")
        report = await settle(memory, bank, ops, timeout_s=1800)
        console.print(
            f"settled in {report.seconds}s ({report.observations} observations, timed out: {report.timed_out})"
        )
    finally:
        await memory.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bank", default=get_settings().dejavu_bank_live)
    parser.add_argument("--n", type=int, default=24, help="load incidents 1..n")
    args = parser.parse_args()
    asyncio.run(main(args.bank, args.n))
