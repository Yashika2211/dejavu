"""Live investigations for the API (spec 10).

Each run executes in the background. Its trace events fan out to any number of SSE subscribers,
and a late subscriber gets the backlog first. A remediation on a critical target waits for the war
room to approve or deny it, and is declined if nobody answers in time. Finished runs are served
from their JSONL trace, so they survive an API restart.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import structlog

from dejavu.agent.loop import Investigator, LoopConfig, Proposal, RunResult
from dejavu.agent.trace import RUNS_DIR, Trace, TraceEvent
from dejavu.eval.grading import IncidentScore, grade
from dejavu.llm.toolcalling import ToolCaller
from dejavu.runner import known_categories
from dejavu.sim.scenario import Scenario
from dejavu.sim.telemetry import INCIDENTS_DIR, ensure_telemetry
from dejavu.sim.world import IncidentWorld
from dejavu.store.db import RunRecord, Store, now_iso
from dejavu.strategies.base import MemoryStrategy

log = structlog.get_logger(__name__)
API_RUNS_DIR = RUNS_DIR / "api"


class LiveRun:
    """One investigation's events, subscribers and pending approvals."""

    def __init__(
        self, record: RunRecord, trace: Trace, *, auto_approve: bool, approval_timeout_s: float
    ) -> None:
        self.record = record
        self.trace = trace
        self.auto_approve = auto_approve
        self.approval_timeout_s = approval_timeout_s
        self.finished = False
        self.result: RunResult | None = None
        self.score: IncidentScore | None = None
        self.world: IncidentWorld | None = None
        self._signals: set[asyncio.Queue[None]] = set()
        self._approvals: dict[str, asyncio.Future[bool]] = {}
        trace.subscribe(lambda _event: self._notify())

    @property
    def id(self) -> str:
        return self.record.id

    @property
    def pending_approvals(self) -> list[str]:
        return list(self._approvals)

    def _notify(self) -> None:
        for signal in self._signals:
            signal.put_nowait(None)

    def finish(self) -> None:
        self.finished = True
        self._notify()

    async def events(self) -> AsyncIterator[TraceEvent]:
        """Every event so far, then each new one as it happens, until the run has finished."""
        signal: asyncio.Queue[None] = asyncio.Queue()
        self._signals.add(signal)
        try:
            index = 0
            while True:
                while index < len(self.trace.events):
                    yield self.trace.events[index]
                    index += 1
                if self.finished:
                    return
                await signal.get()
        finally:
            self._signals.discard(signal)

    async def approve(self, proposal: Proposal) -> bool:
        """The loop's approver: critical targets wait for the war room, the rest go ahead."""
        if self.auto_approve or not proposal.needs_approval:
            return True
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._approvals[proposal.action_id] = future
        try:
            approved, by = await asyncio.wait_for(future, self.approval_timeout_s), "human"
        except TimeoutError:
            approved, by = False, "timeout"
        finally:
            self._approvals.pop(proposal.action_id, None)
        at = self.trace.events[-1].at_min if self.trace.events else 0.0
        self.trace.emit("approval", at, action_id=proposal.action_id, approved=approved, by=by)
        return approved

    def decide(self, action_id: str, approved: bool) -> bool:
        """Answer a pending approval; False when nothing with that id is waiting."""
        future = self._approvals.get(action_id)
        if future is None or future.done():
            return False
        future.set_result(approved)
        return True


class RunManager:
    """Starts runs in the background and keeps the live ones; finished runs come from traces."""

    def __init__(
        self,
        store: Store,
        caller: Callable[[], Awaitable[ToolCaller]],
        *,
        approval_timeout_s: float,
        trace_dir: Path = API_RUNS_DIR,
        telemetry_root: Path = INCIDENTS_DIR,
    ) -> None:
        self.store = store
        self._caller = caller
        self.approval_timeout_s = approval_timeout_s
        self.trace_dir = trace_dir
        self.telemetry_root = telemetry_root
        self.live: dict[str, LiveRun] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._telemetry_locks: dict[str, asyncio.Lock] = {}

    def start(
        self,
        scenario: Scenario,
        strategy: MemoryStrategy,
        *,
        label: str,
        bank: str | None,
        race_id: str | None = None,
        lane: str | None = None,
        auto_approve: bool = False,
        config: LoopConfig | None = None,
    ) -> LiveRun:
        run_id = f"{scenario.incident_id.lower()}-{label}-{uuid.uuid4().hex[:6]}"
        trace = Trace(run_id, directory=self.trace_dir)
        record = RunRecord(
            id=run_id,
            incident_id=scenario.incident_id,
            strategy=label,
            bank=bank,
            race_id=race_id,
            lane=lane,
            trace_path=str(trace.path) if trace.path else None,
        )
        self.store.save(record)
        run = LiveRun(record, trace, auto_approve=auto_approve, approval_timeout_s=self.approval_timeout_s)
        self.live[run_id] = run
        task = asyncio.create_task(self._execute(run, scenario, strategy, config))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return run

    async def _execute(
        self, run: LiveRun, scenario: Scenario, strategy: MemoryStrategy, config: LoopConfig | None = None
    ) -> None:
        status: str = "error"
        try:
            caller = await self._caller()
            lock = self._telemetry_locks.setdefault(scenario.incident_id, asyncio.Lock())
            async with lock:  # race lanes share an incident; generate its telemetry once
                await asyncio.to_thread(ensure_telemetry, scenario, self.telemetry_root)
            run.world = IncidentWorld.open(scenario, self.telemetry_root)
            investigator = Investigator(
                caller, strategy, config=config, trace=run.trace, approver=run.approve, run_id=run.id
            )
            run.result = await investigator.run(run.world)
            run.score = grade(run.result, scenario, run.world, known_categories())
            run.trace.emit("scored", run.world.clock.elapsed_min, **run.score.model_dump(mode="json"))
            status = "error" if run.result.ended == "error" else "done"
        except Exception as exc:  # whatever failed, the run must end with an event and a status
            log.exception("run failed", run=run.id)
            run.trace.emit("error", 0.0, error=f"{type(exc).__name__}: {exc}"[:500])
        finally:
            self.store.update_run(
                run.id,
                status=status,
                ended_at=now_iso(),
                score=run.score.model_dump(mode="json") if run.score else None,
            )
            run.finish()

    def get(self, run_id: str) -> LiveRun | None:
        if run_id in self.live:
            return self.live[run_id]
        record = self.store.run(run_id)
        if record is None or record.trace_path is None or not Path(record.trace_path).exists():
            return None
        trace = Trace(run_id, directory=None)
        trace.events = Trace.load(Path(record.trace_path))
        run = LiveRun(record, trace, auto_approve=True, approval_timeout_s=0)
        run.finish()
        return run

    async def aclose(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
