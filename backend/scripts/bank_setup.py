"""Create or update a memory bank for a profile, idempotently (spec 6.1).

uv run python scripts/bank_setup.py --bank kestrel-ops-live --profile dejavu
uv run python scripts/bank_setup.py --bank kestrel-ops-live --profile dejavu --day0   # also import Day-0
"""

import argparse
import asyncio

from rich.console import Console

from dejavu.config import get_settings
from dejavu.memory.bank_setup import setup_bank
from dejavu.memory.day0 import import_day0
from dejavu.memory.hindsight_adapter import HindsightMemory
from dejavu.memory.settle import settle


async def main(bank: str, profile: str, day0: bool) -> None:
    console = Console()
    memory = HindsightMemory(get_settings())
    try:
        ops = await setup_bank(memory, bank, profile)  # type: ignore[arg-type]
        console.print(f"bank {bank} ({profile}) configured; {len(ops)} mental models created")
        if ops:
            report = await settle(memory, bank, ops)
            console.print(f"mental models settled in {report.seconds}s")
        if day0:
            report = await import_day0(memory, bank)
            console.print(
                f"Day-0 history imported in {report.seconds}s ({report.observations} observations, failed {report.failed})"
            )
    finally:
        await memory.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bank", required=True)
    parser.add_argument("--profile", choices=["dejavu", "rag"], default="dejavu")
    parser.add_argument("--day0", action="store_true", help="also import the Day-0 history")
    args = parser.parse_args()
    asyncio.run(main(args.bank, args.profile, args.day0))
