"""Run traces: every event of an investigation, in order, as JSONL and to live subscribers.

Event types follow the API's SSE stream (spec 10): run_started, briefing, tool_call, tool_result,
hypotheses, memory_moment, remediation_applied, diagnosis, resolved, clock, degraded, error, plus
llm_call for accounting. Traces are replayable: replay mode reads them back event by event,
paced by `wall_ms`.
"""

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from dejavu.config import REPO_ROOT

RUNS_DIR = REPO_ROOT / "data" / "runs"


class TraceEvent(BaseModel):
    seq: int
    type: str
    at_min: float  # simulated minutes after the alert
    wall_ms: int  # real milliseconds since the run started
    data: dict[str, Any]


class Trace:
    """Collects events for one run; optionally appends them to `data/runs/<run_id>.jsonl`."""

    def __init__(self, run_id: str, *, directory: Path | None = RUNS_DIR) -> None:
        self.run_id = run_id
        self.events: list[TraceEvent] = []
        self._start = time.perf_counter()
        self._subscribers: list[Callable[[TraceEvent], None]] = []
        self.path = None
        if directory is not None:
            directory.mkdir(parents=True, exist_ok=True)
            self.path = directory / f"{run_id}.jsonl"
            self.path.write_text("")

    def subscribe(self, callback: Callable[[TraceEvent], None]) -> None:
        self._subscribers.append(callback)

    def emit(self, type_: str, at_min: float, **data: Any) -> TraceEvent:
        event = TraceEvent(
            seq=len(self.events),
            type=type_,
            at_min=round(at_min, 2),
            wall_ms=round((time.perf_counter() - self._start) * 1000),
            data=data,
        )
        self.events.append(event)
        if self.path is not None:
            with self.path.open("a") as fh:
                fh.write(event.model_dump_json() + "\n")
        for callback in self._subscribers:
            callback(event)
        return event

    def of_type(self, type_: str) -> list[TraceEvent]:
        return [e for e in self.events if e.type == type_]

    @staticmethod
    def load(path: Path) -> list[TraceEvent]:
        return [TraceEvent.model_validate(json.loads(line)) for line in path.read_text().splitlines() if line]
