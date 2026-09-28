"""Investigate one incident with a strategy against the real model, then show the steps and the grade.

    uv run python scripts/run_incident.py --n 1                     # Gauntlet incident 1, amnesiac
    uv run python scripts/run_incident.py --demo race-pool-after-pgbouncer

The run trace is written to data/runs/<run-id>.jsonl.
"""

import argparse
import asyncio

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from dejavu.config import get_settings
from dejavu.money import inr_words
from dejavu.runner import build_caller, run_incident
from dejavu.sim.schedule import demo, entry_for, gauntlet
from dejavu.strategies.amnesiac import Amnesiac

STRATEGIES = {"amnesiac": Amnesiac}
console = Console()


async def main(n: int | None, demo_name: str | None, strategy_name: str, seed: int | None) -> None:
    settings = get_settings()
    scenario = (
        demo(demo_name) if demo_name else next(s for s in gauntlet(seed) if (e := entry_for(s)) and e.n == n)
    )
    caller = await build_caller(settings)
    console.rule(f"{scenario.incident_id} with {strategy_name} ({', '.join(caller.models)})")
    run, score, _ = await run_incident(scenario, STRATEGIES[strategy_name](), caller)

    table = Table(show_lines=False)
    for col in ("#", "t", "tool", "args", "rationale"):
        table.add_column(col, overflow="fold")
    for step in [*run.steps, *run.plan_steps]:
        args = ", ".join(f"{k}={v}" for k, v in step.args.items())
        table.add_row(
            str(step.index), f"{step.at_min:g}", step.tool, escape(args[:60]), escape(step.rationale)
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
    parser.add_argument("--strategy", default="amnesiac", choices=sorted(STRATEGIES))
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(main(args.n, args.demo, args.strategy, args.seed))
