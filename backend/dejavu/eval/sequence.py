"""Live through incidents in calendar order with one strategy, as a team would (spec 7.2).

Before each incident the strategy receives the team documents the calendar has reached since the
previous one (migration RFCs and announcements). After it, the strategy receives the resolution
with the same human feedback and postmortem every strategy gets; the amnesiac simply can't keep
them. Memory never sees ground truth except through what the team wrote.
"""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from dejavu.agent.loop import LoopConfig, RunResult
from dejavu.agent.trace import RUNS_DIR
from dejavu.documents import Document, incident_documents, migration_documents
from dejavu.eval.grading import IncidentScore
from dejavu.llm.toolcalling import ToolCaller
from dejavu.runner import build_resolution, run_incident
from dejavu.sim.scenario import Scenario
from dejavu.sim.schedule import entry_for
from dejavu.sim.telemetry import INCIDENTS_DIR
from dejavu.strategies.base import MemoryStrategy


class Played(BaseModel):
    """One incident of a sequence: the run, its grade and the documents delivered before it."""

    n: int | None
    run: RunResult
    score: IncidentScore
    delivered: list[str]


class IncidentAbortedError(Exception):
    """The model could not be reached, so the run says nothing about the agent: don't grade it."""

    def __init__(self, run: RunResult) -> None:
        detail = next((c["error"] for c in reversed(run.llm_calls) if c.get("error")), "no usable decision")
        super().__init__(f"{run.incident_id} ({run.strategy}) aborted: {detail}")
        self.run = run


def documents_due(after: datetime | None, until: datetime) -> list[Document]:
    """Team documents published in (`after`, `until`], oldest first."""
    return [d for d in migration_documents() if (after is None or d.date > after) and d.date <= until]


async def play_incident(
    scenario: Scenario,
    strategy: MemoryStrategy,
    caller: ToolCaller,
    *,
    since: datetime | None,
    run_id: str,
    config: LoopConfig | None = None,
    trace_dir: Path | None = RUNS_DIR,
    telemetry_root: Path = INCIDENTS_DIR,
) -> Played:
    """Deliver due documents, investigate, grade, then hand the strategy the resolution.

    Raises `IncidentAbortedError` before anything is learned if the model was unreachable.
    """
    docs = documents_due(since, scenario.alert_at)
    if docs:
        await strategy.remember(docs)
    run, score, world = await run_incident(
        scenario,
        strategy,
        caller,
        config=config,
        run_id=run_id,
        trace_dir=trace_dir,
        telemetry_root=telemetry_root,
    )
    if run.ended == "error":
        raise IncidentAbortedError(run)
    entry = entry_for(scenario)
    written = incident_documents(entry.n) if entry else {}
    await strategy.on_resolution(build_resolution(run, score, world, written))
    return Played(n=entry.n if entry else None, run=run, score=score, delivered=[d.id for d in docs])


async def play(
    scenarios: list[Scenario],
    strategy: MemoryStrategy,
    caller: ToolCaller,
    *,
    run_prefix: str,
    since: datetime | None = None,
    config: LoopConfig | None = None,
    trace_dir: Path | None = RUNS_DIR,
    telemetry_root: Path = INCIDENTS_DIR,
) -> list[Played]:
    """Play `scenarios` in order; `since` is when the strategy last received documents."""
    played = []
    for scenario in sorted(scenarios, key=lambda s: s.alert_at):
        played.append(
            await play_incident(
                scenario,
                strategy,
                caller,
                since=since,
                run_id=f"{run_prefix}-{scenario.incident_id.lower()}-{strategy.name}",
                config=config,
                trace_dir=trace_dir,
                telemetry_root=telemetry_root,
            )
        )
        since = scenario.alert_at
    return played
