"""Run one incident end to end: world, strategy, model chain, investigation, grade.

The CLI (`scripts/run_incident.py`), the Gauntlet and the API all go through here, so every run
is produced and scored the same way.
"""

from datetime import timedelta
from pathlib import Path

from dejavu.agent.loop import Approver, Investigator, LoopConfig, RunResult, auto_approve
from dejavu.agent.trace import RUNS_DIR, Trace
from dejavu.config import Settings
from dejavu.documents import Document
from dejavu.eval.grading import DETECTION_MIN, HISTORICAL_CATEGORIES, IncidentScore, grade
from dejavu.llm.client import LLMClient
from dejavu.llm.models import usable_models
from dejavu.llm.toolcalling import ToolCaller
from dejavu.sim.scenario import Scenario
from dejavu.sim.schedule import gauntlet
from dejavu.sim.telemetry import INCIDENTS_DIR
from dejavu.sim.world import IncidentWorld
from dejavu.strategies.base import IncidentContext, MemoryStrategy, Resolution
from dejavu.taxonomy import RootCause


async def build_caller(settings: Settings, client: LLMClient | None = None) -> ToolCaller:
    """The agent's tool caller over every configured model the key can use, primary first."""
    client = client or LLMClient(settings)
    return ToolCaller(
        client, await usable_models(client, settings), reasoning_effort=settings.llm_reasoning_effort
    )


def known_categories() -> dict[str, RootCause]:
    """True categories of every incident an agent could cite (for precedent precision)."""
    return {s.incident_id: s.spec.category for s in gauntlet()} | HISTORICAL_CATEGORIES


async def run_incident(
    scenario: Scenario,
    strategy: MemoryStrategy,
    caller: ToolCaller,
    *,
    config: LoopConfig | None = None,
    approver: Approver = auto_approve,
    run_id: str | None = None,
    trace_dir: Path | None = RUNS_DIR,
    telemetry_root: Path = INCIDENTS_DIR,
) -> tuple[RunResult, IncidentScore, IncidentWorld]:
    world = IncidentWorld.open(scenario, telemetry_root)
    run_id = run_id or f"{scenario.incident_id.lower()}-{strategy.name}"
    investigator = Investigator(
        caller,
        strategy,
        config=config,
        approver=approver,
        run_id=run_id,
        trace=Trace(run_id, directory=trace_dir),
    )
    result = await investigator.run(world)
    return result, grade(result, scenario, world, known_categories()), world


def build_resolution(
    run: RunResult, score: IncidentScore, world: IncidentWorld, documents: dict[str, Document]
) -> Resolution:
    """What the team knows once the incident is over: the run, its outcome and their write-ups."""
    alert_at = world.scenario.alert_at
    return Resolution(
        incident=IncidentContext.from_alert(world.scenario.incident_id, world.store.alert, alert_at),
        diagnosis=run.diagnosis,
        steps=run.steps,
        outcome=score.model_dump(mode="json"),
        documents=documents,
        resolved_at=alert_at + timedelta(minutes=score.mttr_min - DETECTION_MIN),
        changes=world.changes(6),
    )
