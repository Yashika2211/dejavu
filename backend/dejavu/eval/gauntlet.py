"""The Gauntlet (spec 7): 24 incidents over six simulated weeks, once per strategy, one seed.

    uv run python -m dejavu.eval.gauntlet --strategies amnesiac,rag,dejavu --seed 42 --n 24
    uv run python -m dejavu.eval.gauntlet --strategies amnesiac,dejavu --n 6       # quick mode
    uv run python -m dejavu.eval.gauntlet --resume                                 # continue the latest run
    uv run python -m dejavu.eval.gauntlet --n 24 --dry-run                         # estimate; needs no keys

Strategies take turns incident by incident, so a run stopped by a rate limit leaves every strategy
at the same point. Each finished (incident, strategy) pair is appended to `results.jsonl` at once
and memory banks persist, so `--resume` carries on exactly where the run stopped. A run the model
could not finish is not graded and memory learns nothing from it; it is retried on resume. All
strategies share one pinned model (no fallbacks), the prompts, the tools and the step budget.
"""

import argparse
import asyncio
import json
import subprocess
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from rich.console import Console

from dejavu.agent.loop import LoopConfig
from dejavu.agent.trace import RUNS_DIR
from dejavu.config import REPO_ROOT, Settings, get_settings
from dejavu.eval.metrics import IncidentLabel, incident_labels
from dejavu.eval.report import EVAL_DIR, latest_run, read_jsonl, write_run_report
from dejavu.eval.sequence import IncidentAbortedError, Played, play_incident
from dejavu.llm.client import LLMClient
from dejavu.llm.pricing import cost_usd
from dejavu.llm.toolcalling import ToolCaller
from dejavu.memory.hindsight_adapter import HindsightMemory, MemoryBackend, MemoryUnavailableError
from dejavu.memory.snapshots import snapshot
from dejavu.money import inr_words
from dejavu.sim.scenario import Scenario
from dejavu.sim.schedule import entry_for, gauntlet
from dejavu.sim.telemetry import INCIDENTS_DIR
from dejavu.strategies.amnesiac import Amnesiac
from dejavu.strategies.base import MemoryStrategy
from dejavu.strategies.dejavu import DejaVu
from dejavu.strategies.rag import NaiveRAG

STRATEGIES = ("amnesiac", "rag", "dejavu")
MEMORY_STRATEGIES: dict[str, type[DejaVu]] = {"dejavu": DejaVu, "rag": NaiveRAG}
console = Console()


class GauntletRun(BaseModel):
    """A run's configuration and progress, saved as `run.json` beside its results."""

    run_id: str
    seed: int
    n: int
    strategies: list[str]
    models: list[str]
    loop: dict[str, Any]
    started_at: datetime
    git_sha: str | None = None
    snapshots: bool = False
    banks: dict[str, str] = Field(default_factory=dict)
    prepared: list[str] = Field(default_factory=list)
    snapshots_taken: list[str] = Field(default_factory=list)


class Estimate(BaseModel):
    """Upper bounds from the step budget: one call per step plus a final diagnosis."""

    runs: int
    memory_runs: int
    max_llm_calls: int
    max_tokens_in: int
    max_tokens_out: int
    max_usd: float
    days_at_rpd: float
    hours_at_tpm: float


def git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip() or None


def new_run(
    seed: int, n: int, strategies: list[str], models: list[str], loop: LoopConfig, *, snapshots: bool
) -> GauntletRun:
    run_id = f"g{seed}-{datetime.now():%Y%m%d-%H%M%S}"
    return GauntletRun(
        run_id=run_id,
        seed=seed,
        n=n,
        strategies=strategies,
        models=models,
        loop=asdict(loop),
        started_at=datetime.now().astimezone(),
        git_sha=git_sha(),
        snapshots=snapshots,
        banks={s: f"gx-{run_id}-{s}" for s in strategies if s in MEMORY_STRATEGIES},
    )


def estimate(
    pairs: int, memory_pairs: int, loop: LoopConfig, settings: Settings, model: str, max_out: int = 1200
) -> Estimate:
    calls = pairs * (loop.max_steps + 1)
    tokens_in, tokens_out = calls * loop.context_tokens, calls * max_out
    return Estimate(
        runs=pairs,
        memory_runs=memory_pairs,
        max_llm_calls=calls,
        max_tokens_in=tokens_in,
        max_tokens_out=tokens_out,
        max_usd=round(cost_usd(model, tokens_in, tokens_out, settings), 2),
        days_at_rpd=round(calls / settings.llm_rpd, 1),
        hours_at_tpm=round((tokens_in + tokens_out) / settings.llm_tpm / 60, 1),
    )


def make_strategy(name: str, memory: MemoryBackend | None, bank: str | None) -> MemoryStrategy:
    if name == "amnesiac":
        return Amnesiac()
    if memory is None or bank is None:
        raise ValueError(f"{name} needs a memory backend and a bank")
    return MEMORY_STRATEGIES[name](memory, bank)


def result_row(
    played: Played, scenario: Scenario, label: IncidentLabel, strategy: MemoryStrategy
) -> dict[str, Any]:
    """One line of results.jsonl: the grade plus what memory did during the incident."""
    run, score = played.run, played.score
    settled = strategy.last_settle if isinstance(strategy, DejaVu) else None
    entry = entry_for(scenario)
    return {
        "n": played.n,
        **score.model_dump(mode="json"),
        "kind": label.kind,
        "after_migration": label.after_migration,
        "alert_at": scenario.alert_at.isoformat(),
        "tests": entry.tests if entry else "",
        "predicted": (
            {"category": run.diagnosis.root_cause_category.value, "culprit": run.diagnosis.culprit_service}
            if run.diagnosis
            else None
        ),
        "briefing": run.briefing is not None,
        "memory_moments": sum(s.memory_moment for s in run.steps),
        "delivered": played.delivered,
        "models": sorted({c["model"] for c in run.llm_calls}),
        "run_id": run.run_id,
        "settle_s": settled.seconds if settled else None,
        "settle_timed_out": settled.timed_out if settled else None,
    }


def _append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(row) + "\n")


class Gauntlet:
    """Plays a `GauntletRun` to completion, checkpointing after every (incident, strategy) pair."""

    def __init__(
        self,
        run: GauntletRun,
        run_dir: Path,
        *,
        caller: ToolCaller,
        memory: MemoryBackend | None,
        settings: Settings,
        trace_dir: Path | None,
        telemetry_root: Path = INCIDENTS_DIR,
    ) -> None:
        self.run = run
        self.dir = run_dir
        self.caller = caller
        self.memory = memory
        self.settings = settings
        self.trace_dir = trace_dir
        self.telemetry_root = telemetry_root
        self.loop = LoopConfig(**run.loop)
        self.strategies = {name: make_strategy(name, memory, run.banks.get(name)) for name in run.strategies}

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "run.json").write_text(self.run.model_dump_json(indent=2))

    async def _growth(self, n: int, name: str) -> None:
        strategy = self.strategies[name]
        if self.memory is None or not isinstance(strategy, DejaVu):
            return
        stats = await self.memory.stats(strategy.bank_id)
        counts = {k: v for k, v in stats.items() if isinstance(v, int | float) and not isinstance(v, bool)}
        _append(self.dir / "growth.jsonl", {"n": n, "strategy": name, **counts})

    async def _snapshot(self, label: str, name: str, target: str) -> None:
        strategy = self.strategies.get(name)
        if not self.run.snapshots or self.memory is None or not isinstance(strategy, DejaVu):
            return
        if label in self.run.snapshots_taken:
            return
        await snapshot(self.memory, strategy.bank_id, target)
        self.run.snapshots_taken.append(label)
        self.save()
        console.print(f"snapshot {strategy.bank_id} -> {target}")

    async def prepare(self) -> None:
        """Bank setup and the Day-0 import for every memory strategy that hasn't had them.

        The day1 snapshot is taken right after DejaVu's import, before the bank counts as prepared,
        so it can never contain an incident.
        """
        for name, strategy in self.strategies.items():
            if not isinstance(strategy, DejaVu) or name in self.run.prepared:
                continue
            report = await strategy.prepare()
            await self._growth(0, name)
            if name == "dejavu":
                await self._snapshot("day1", "dejavu", self.settings.dejavu_bank_day1)
            self.run.prepared.append(name)
            self.save()
            console.print(f"{name}: bank {strategy.bank_id} ready, Day-0 imported in {report.seconds}s")

    async def play(self) -> bool:
        """Play every pending pair in calendar order; True once the whole run is done."""
        results = self.dir / "results.jsonl"
        rows = read_jsonl(results)
        done = {(r["n"], r["strategy"]) for r in rows}
        since: dict[str, datetime | None] = {
            name: max(
                (datetime.fromisoformat(r["alert_at"]) for r in rows if r["strategy"] == name), default=None
            )
            for name in self.strategies
        }
        schedule = gauntlet(self.run.seed)
        labels = incident_labels(schedule)
        plan = [(entry.n, scenario) for scenario in schedule[: self.run.n] if (entry := entry_for(scenario))]
        for n, scenario in plan:
            for name, strategy in self.strategies.items():
                if (n, name) in done:
                    continue
                played = await play_incident(
                    scenario,
                    strategy,
                    self.caller,
                    since=since[name],
                    run_id=f"{self.run.run_id}-{n:02d}-{name}",
                    config=self.loop,
                    trace_dir=self.trace_dir,
                    telemetry_root=self.telemetry_root,
                )
                _append(results, result_row(played, scenario, labels[n], strategy))
                await self._growth(n, name)
                done.add((n, name))
                since[name] = scenario.alert_at
                s = played.score
                console.print(
                    f"#{n:02d} {scenario.incident_id} {name:<8} {'correct  ' if s.correct else 'incorrect'} "
                    f"MTTR {s.mttr_min:>5g} min ({s.resolved_by}) | wasted {s.wasted_steps}/{s.steps} | "
                    f"{inr_words(s.inr_at_risk)} | {s.tokens_in + s.tokens_out:,} tok"
                )
        complete = all((n, name) in done for n, _ in plan for name in self.strategies)
        if complete and len(plan) == len(schedule):
            await self._snapshot("trained", "dejavu", self.settings.dejavu_bank_trained)
            await self._snapshot("rag", "rag", self.settings.dejavu_bank_rag)
        return complete


async def pinned_caller(settings: Settings, models: list[str]) -> ToolCaller:
    """A tool caller over exactly `models`, after checking the key can use them."""
    client = LLMClient(settings)
    missing = [m for m in models if m not in await client.available_models()]
    if missing:
        raise SystemExit(f"not available to this Groq key: {', '.join(missing)}")
    return ToolCaller(client, models, reasoning_effort=settings.llm_reasoning_effort)


def _load_or_create(args: argparse.Namespace, settings: Settings) -> tuple[GauntletRun, Path]:
    if args.resume:
        run_dir = EVAL_DIR / args.run_id if args.run_id else latest_run()
        if run_dir is None or not (run_dir / "run.json").exists():
            raise SystemExit("no Gauntlet run to resume under data/eval")
        run = GauntletRun.model_validate_json((run_dir / "run.json").read_text())
        if args.n and args.n > run.n:
            run.n = args.n
        return run, run_dir
    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    unknown = [s for s in strategies if s not in STRATEGIES]
    if unknown:
        raise SystemExit(f"unknown strategies: {', '.join(unknown)} (choose from {', '.join(STRATEGIES)})")
    models = [m.strip() for m in args.models.split(",")] if args.models else [settings.llm_primary]
    run = new_run(args.seed, args.n or 24, strategies, models, LoopConfig(), snapshots=args.snapshots)
    return run, EVAL_DIR / run.run_id


def _print_estimate(run: GauntletRun, run_dir: Path, settings: Settings) -> None:
    done = {(r["n"], r["strategy"]) for r in read_jsonl(run_dir / "results.jsonl")}
    pairs = [(n, s) for n in range(1, run.n + 1) for s in run.strategies if (n, s) not in done]
    e = estimate(
        len(pairs),
        sum(s in MEMORY_STRATEGIES for _, s in pairs),
        LoopConfig(**run.loop),
        settings,
        run.models[0],
    )
    console.print(
        f"{e.runs} incident runs ({e.memory_runs} with memory) on {', '.join(run.models)}. From the step budget "
        f"(one call per step plus a final diagnosis; tool-call repairs add a few): up to {e.max_llm_calls:,} LLM "
        f"calls, {e.max_tokens_in:,} tokens in and {e.max_tokens_out:,} out, about ${e.max_usd:,.2f}. At "
        f"LLM_RPD={settings.llm_rpd} that is up to {e.days_at_rpd} days of requests; at "
        f"LLM_TPM={settings.llm_tpm}, up to {e.hours_at_tpm} hours."
    )


async def main(args: argparse.Namespace) -> int:
    settings = get_settings()
    run, run_dir = _load_or_create(args, settings)
    if args.dry_run:
        _print_estimate(run, run_dir, settings)
        return 0
    needs_memory = any(s in MEMORY_STRATEGIES for s in run.strategies)
    if settings.groq_api_key is None or (needs_memory and settings.hindsight_api_key is None):
        raise SystemExit("set GROQ_API_KEY (and HINDSIGHT_API_KEY for rag/dejavu) in .env first")
    memory = HindsightMemory(settings) if needs_memory else None
    gauntlet_run = Gauntlet(
        run,
        run_dir,
        caller=await pinned_caller(settings, run.models),
        memory=memory,
        settings=settings,
        trace_dir=RUNS_DIR / run.run_id,
    )
    gauntlet_run.save()
    console.rule(f"Gauntlet {run.run_id}: {', '.join(run.strategies)}, seed {run.seed}, {run.n} incidents")
    resume = f"uv run python -m dejavu.eval.gauntlet --resume --run-id {run.run_id}"
    complete = False
    try:
        await gauntlet_run.prepare()
        complete = await gauntlet_run.play()
    except (IncidentAbortedError, MemoryUnavailableError) as exc:
        console.print(f"[red]stopped:[/] {exc}\nresume with: {resume}")
    finally:
        if memory is not None:
            await memory.aclose()
        write_run_report(run_dir)
    if complete:
        console.print(
            f"done: data/eval/{run.run_id}/ (publish with: uv run python -m dejavu.eval.report "
            f"--run-id {run.run_id} --publish)"
        )
    return 0 if complete else 3


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--strategies", default="amnesiac,rag,dejavu")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n", type=int, default=None, help="first N incidents (default 24)")
    parser.add_argument("--models", help="comma-separated; default: LLM_PRIMARY only")
    parser.add_argument("--resume", action="store_true", help="continue a run (default: the latest)")
    parser.add_argument("--run-id", help="the run to resume")
    parser.add_argument("--snapshots", action="store_true", help="also write the day1 and trained banks")
    parser.add_argument("--dry-run", action="store_true", help="print an estimate and exit")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(parse_args())))
