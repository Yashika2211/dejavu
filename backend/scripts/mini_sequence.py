"""Phase 3's live check: Gauntlet incidents 1, 5 and 12 in order, with DejaVu on a fresh bank.

    uv run python scripts/mini_sequence.py          # throwaway bank mini-<time>, deleted afterwards
    uv run python scripts/mini_sequence.py --keep   # keep the bank for inspection

It sets up the bank, imports Day-0, then plays pool exhaustion (#1), its recurrence (#5) and the
recurrence after the PgBouncer migration (#12). For each incident it prints the briefing's likely
causes and the memory moments; for #12 it checks temporal validity: since M1 the HikariCP pool is
no longer the bottleneck, so the old fix (raise it) must not come back.
"""

import argparse
import asyncio
import sys
from datetime import datetime

from rich.console import Console
from rich.markup import escape

from dejavu.config import get_settings
from dejavu.eval.sequence import Played, play
from dejavu.memory.hindsight_adapter import HindsightMemory
from dejavu.money import inr_words
from dejavu.runner import build_caller
from dejavu.sim.schedule import entry_for, gauntlet
from dejavu.strategies.dejavu import DejaVu

SEQUENCE = (1, 5, 12)
console = Console()


def temporal_validity(played: Played) -> dict[str, bool]:
    """What incident 12 must show: memory knows about M1, and the stale HikariCP fix stays unused."""
    briefing = played.run.briefing.text.lower() if played.run.briefing else ""
    steps = [*played.run.steps, *played.run.plan_steps]
    return {
        "briefing mentions PgBouncer": "pgbouncer" in briefing,
        "checked pgbouncer-ledger": any(s.args.get("service") == "pgbouncer-ledger" for s in steps),
        "did not raise the HikariCP pool": not any(
            s.tool == "run_remediation"
            and s.args.get("action") == "pool_tuning"
            and s.args.get("target") == "ledger-svc"
            for s in steps
        ),
    }


def show(played: Played) -> None:
    run, score = played.run, played.score
    console.rule(f"#{played.n} {run.incident_id}")
    if played.delivered:
        console.print(f"documents delivered first: {', '.join(played.delivered)}")
    brief = (run.briefing.data.get("brief") if run.briefing else None) or {}
    for cause in brief.get("likely_causes", []):
        refs = ", ".join(cause.get("precedent_incident_ids") or []) or "no precedent"
        console.print(
            f"  likely: {escape(cause['cause'])} in {cause['service']} "
            f"({cause['prior']:.0%}; {refs}; still valid: {cause.get('still_valid', 'unknown')})"
        )
    for step in [*run.steps, *run.plan_steps]:
        if step.memory_moment:
            args = ", ".join(f"{k}={v}" for k, v in step.args.items())
            console.print(
                f"  memory moment, step {step.index}: {step.tool}({escape(args)}): {escape(step.rationale)}"
            )
    console.print(
        f"  {'correct' if score.correct else 'incorrect'} | ttd {score.ttd_min} min | MTTR {score.mttr_min} min "
        f"({score.resolved_by}) | wasted {score.wasted_steps}/{score.steps} | {inr_words(score.inr_at_risk)} at risk"
    )


async def main(keep: bool) -> int:
    settings = get_settings()
    bank = f"mini-{datetime.now():%Y%m%d-%H%M%S}"
    memory = HindsightMemory(settings)
    try:
        strategy = DejaVu(memory, bank)
        report = await strategy.prepare()
        console.print(f"Day-0 imported into {bank} in {report.seconds}s ({report.observations} observations)")
        scenarios = [s for s in gauntlet() if (e := entry_for(s)) and e.n in SEQUENCE]
        played = await play(scenarios, strategy, await build_caller(settings), run_prefix=bank)
        for p in played:
            show(p)
        checks = temporal_validity(played[-1])
        console.rule("temporal validity (#12, after M1)")
        for name, ok in checks.items():
            console.print(f"  [{'green' if ok else 'red'}]{'PASS' if ok else 'FAIL'}[/] {name}")
        console.print(f"traces: data/runs/{bank}-*.jsonl")
        return 0 if all(checks.values()) else 1
    finally:
        if not keep:
            await memory.delete_bank(bank)
        await memory.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--keep", action="store_true", help="keep the bank for inspection")
    sys.exit(asyncio.run(main(parser.parse_args().keep)))
