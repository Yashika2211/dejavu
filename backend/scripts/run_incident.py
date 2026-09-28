"""Investigate one incident with a strategy against the real model, then show the steps and the grade.

    uv run python scripts/run_incident.py --n 1                     # Gauntlet incident 1, amnesiac
    uv run python scripts/run_incident.py --n 5 --strategy dejavu   # briefed from kestrel-ops-live
    uv run python scripts/run_incident.py --demo race-pool-after-pgbouncer --strategy dejavu --bank <id>

DejaVu reads from `--bank` (default: the live bank) and only writes the outcome back with
`--learn`. The run trace is written to data/runs/<run-id>.jsonl.
"""

import argparse
import asyncio

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from dejavu.config import get_settings
from dejavu.documents import incident_documents
from dejavu.memory.hindsight_adapter import HindsightMemory
from dejavu.money import inr_words
from dejavu.runner import build_caller, build_resolution, run_incident
from dejavu.sim.schedule import demo, entry_for, gauntlet
from dejavu.strategies.amnesiac import Amnesiac
from dejavu.strategies.base import MemoryStrategy
from dejavu.strategies.dejavu import DejaVu

STRATEGIES = ("amnesiac", "dejavu")
console = Console()


async def main(
    n: int | None, demo_name: str | None, strategy_name: str, seed: int | None, bank: str | None, learn: bool
) -> None:
    settings = get_settings()
    scenario = (
        demo(demo_name) if demo_name else next(s for s in gauntlet(seed) if (e := entry_for(s)) and e.n == n)
    )
    memory = HindsightMemory(settings) if strategy_name == "dejavu" else None
    strategy: MemoryStrategy = (
        DejaVu(memory, bank or settings.dejavu_bank_live) if memory is not None else Amnesiac()
    )
    try:
        caller = await build_caller(settings)
        console.rule(f"{scenario.incident_id} with {strategy_name} ({', '.join(caller.models)})")
        run, score, world = await run_incident(scenario, strategy, caller)
        entry = entry_for(scenario)
        if learn and entry is not None:
            await strategy.on_resolution(build_resolution(run, score, world, incident_documents(entry.n)))
    finally:
        if memory is not None:
            await memory.aclose()

    if run.briefing:
        console.print(f"[bold]briefing[/] ({run.briefing.source}):\n{escape(run.briefing.text)}")
    table = Table(show_lines=False)
    for col in ("#", "t", "tool", "args", "rationale", "memory"):
        table.add_column(col, overflow="fold")
    for step in [*run.steps, *run.plan_steps]:
        args = ", ".join(f"{k}={v}" for k, v in step.args.items())
        table.add_row(
            str(step.index),
            f"{step.at_min:g}",
            step.tool,
            escape(args[:60]),
            escape(step.rationale),
            "yes" if step.memory_moment else "",
        )
    console.print(table)
    if run.diagnosis:
        d = run.diagnosis
        console.print(
            f"diagnosis: {d.root_cause_category.value} in {d.culprit_service} ({d.confidence:.0%}): {escape(d.summary)}"
        )
    console.print(
        f"[bold]{'correct' if score.correct else 'incorrect'}[/] (truth {score.archetype}) | ttd {score.ttd_min} min | "
        f"MTTR {score.mttr_min} min ({score.resolved_by}) | steps {score.steps}, wasted {score.wasted_steps}, "
        f"harmful {score.harmful_actions} | {inr_words(score.inr_at_risk)} at risk | "
        f"{score.tokens_in + score.tokens_out:,} tokens, ${score.usd_cost:.4f} | trace data/runs/{run.run_id}.jsonl"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--n", type=int, default=1, help="Gauntlet incident number (1-24)")
    parser.add_argument("--demo", help="a demo incident name from schedule.yaml")
    parser.add_argument("--strategy", default="amnesiac", choices=STRATEGIES)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--bank", help="DejaVu's memory bank (default: DEJAVU_BANK_LIVE)")
    parser.add_argument("--learn", action="store_true", help="retain the outcome into the bank afterwards")
    args = parser.parse_args()
    asyncio.run(main(args.n, args.demo, args.strategy, args.seed, args.bank, args.learn))
