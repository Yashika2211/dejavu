"""A live incident: its telemetry, the investigation clock and the interventions applied so far.

Everything the agent can observe goes through here, and nothing later than `now` is visible.
The incident layer of every signal is scaled by the severity curve k(t), so remediation shows up
in metrics, logs and traces without regenerating anything.
"""

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np

from dejavu.sim.clock import WINDOW_AFTER_MIN, WINDOW_BEFORE_MIN, SimClock
from dejavu.sim.generators.events import ChangeEvent
from dejavu.sim.generators.metrics import AVG_TICKET_INR, NO_NODE
from dejavu.sim.remediation import Intervention, OutcomeKind, intervene, resolved_at, severity
from dejavu.sim.scenario import ChangeType, Scenario, StatusUpdate
from dejavu.sim.telemetry import INCIDENTS_DIR, TelemetryStore
from dejavu.sim.topology import Topology
from dejavu.taxonomy import Remediation

AGENT_NAME = "DejaVu"


@dataclass(frozen=True)
class Visible:
    """A metric series as observable now: minutes (offsets) and values."""

    minutes: np.ndarray
    values: np.ndarray


@dataclass(frozen=True)
class LogLine:
    offset_s: float
    level: str
    message: str
    line: str


@dataclass(frozen=True)
class StatusPage:
    name: str
    status: str
    title: str
    message: str
    posted_at_min: float | None


class IncidentWorld:
    """One incident as one strategy experiences it (each run gets its own world)."""

    def __init__(self, scenario: Scenario, store: TelemetryStore) -> None:
        self.scenario = scenario
        self.store = store
        self.clock = SimClock(scenario.alert_at)
        self.interventions: list[Intervention] = []
        self._agent_changes: list[ChangeEvent] = []

    @classmethod
    def open(cls, scenario: Scenario, root: Path = INCIDENTS_DIR) -> "IncidentWorld":
        return cls(scenario, TelemetryStore.for_scenario(scenario, root))

    @property
    def topology(self) -> Topology:
        return self.scenario.topology

    @property
    def now_min(self) -> float:
        """Minutes since the alert, capped at the end of the generated window."""
        return min(self.clock.elapsed_min, float(WINDOW_AFTER_MIN))

    def k(self, minutes: np.ndarray) -> np.ndarray:
        return severity(self.interventions, np.asarray(minutes, dtype=float))

    # metrics -----------------------------------------------------------------------------

    def metric(self, component: str, metric: str) -> dict[str, Visible]:
        """Observed series per node ("" for plain metrics), up to now."""
        out: dict[str, Visible] = {}
        for node, s in self.store.metric(component, metric).items():
            mask = s.offsets <= np.floor(self.now_min)
            minutes = s.offsets[mask].astype(float)
            out[node] = Visible(minutes, s.baseline[mask] + s.delta[mask] * self.k(minutes))
        return out

    def metric_at(self, component: str, metric: str, minute: float, node: str = NO_NODE) -> float:
        """Observed value at one past minute (used by discriminator checks and summaries)."""
        visible = self.metric(component, metric)[node]
        idx = int(np.searchsorted(visible.minutes, np.floor(minute), side="right")) - 1
        return float(visible.values[max(idx, 0)])

    # logs --------------------------------------------------------------------------------

    def logs(
        self,
        component: str,
        window_min: float,
        *,
        levels: list[str] | None = None,
        contains: str | None = None,
    ) -> list[LogLine]:
        """Log lines from the last `window_min` minutes; incident lines thin out as k(t) falls."""
        end_s = self.now_min * 60
        rows = self.store.logs(component, end_s - window_min * 60, end_s, levels=levels, contains=contains)
        if not rows:
            return []
        k = self.k(np.array([r[0] / 60 for r in rows]))
        return [
            LogLine(r[0], r[1], r[2], r[3])
            for r, kk in zip(rows, k, strict=True)
            if not r[4] or r[5] < min(kk, 1.0)
        ]

    # traces ------------------------------------------------------------------------------

    def spans(self, component: str, window_min: float, operation: str | None = None) -> list[dict[str, Any]]:
        """Spans of traces touching `component` in the window, with incident delays scaled by k(t)."""
        end_ms = self.now_min * 60_000
        spans = self.store.traces_touching(component, end_ms - window_min * 60_000, end_ms, operation)
        if not spans:
            return []
        k = self.k(np.array([s["start_offset_ms"] / 60_000 for s in spans]))
        for span, kk in zip(spans, k, strict=True):
            span["duration_ms"] = span["base_ms"] + span["incident_ms"] * kk
            if span["error"] and span["incident_error"] and span["draw"] >= min(kk, 1.0):
                span["error"] = ""
        return spans

    # changes and status pages -------------------------------------------------------------

    def changes(self, window_hours: float, service: str | None = None) -> list[ChangeEvent]:
        now = self.clock.at(self.now_min)
        start = now - timedelta(hours=window_hours)
        events = [e for e in [*self.store.events, *self._agent_changes] if start <= e.at <= now]
        if service:
            events = [e for e in events if e.service == service]
        return sorted(events, key=lambda e: e.at)

    def status_page(self, name: str) -> StatusPage | None:
        comp = self.topology.get(name)
        if comp is None or comp.status_page is None:
            return None
        onset = self.scenario.spec.impact.start_offset
        elapsed = self.now_min - onset
        posted: list[StatusUpdate] = [
            u for u in self.scenario.spec.status_updates.get(name, []) if u.after_onset_min <= elapsed
        ]
        if not posted:
            return StatusPage(comp.status_page, "operational", "All Systems Operational", "", None)
        latest = posted[-1]
        return StatusPage(
            comp.status_page, latest.status, latest.title, latest.message, onset + latest.after_onset_min
        )

    # remediation ---------------------------------------------------------------------------

    def apply(self, action: Remediation, target: str, params: dict[str, str]) -> Intervention:
        """Apply an action now. The caller advances the clock by the action's duration."""
        iv = intervene(self.scenario, action, target, params, self.clock.elapsed_min)
        self.interventions.append(iv)
        if iv.kind != OutcomeKind.INVALID:
            detail = ", ".join(f"{k}={v}" for k, v in params.items())
            self._agent_changes.append(
                ChangeEvent(
                    id=f"act-{len(self.interventions):02d}",
                    at=self.clock.at(iv.started_at),
                    type=ChangeType.REMEDIATION,
                    service=target,
                    author=f"{AGENT_NAME} (on-call agent)",
                    summary=f"{action.value} {target}" + (f" ({detail})" if detail else ""),
                    details={"action": action.value, **params},
                )
            )
        return iv

    @property
    def resolved_at_min(self) -> float | None:
        return resolved_at(self.interventions)

    # impact ----------------------------------------------------------------------------------

    def inr_at_risk(self, until_min: float) -> float:
        """Excess failed payments x average ticket, from the start of the window until `until_min`."""
        series = self.store.metric("checkout-api", "payments_failed")[NO_NODE]
        minutes = np.arange(-WINDOW_BEFORE_MIN, np.floor(until_min) + 1, dtype=float)
        delta = np.interp(
            minutes, series.offsets.astype(float), series.delta, right=float(series.delta[-10:].mean())
        )
        return float(np.sum(np.maximum(delta, 0) * self.k(minutes)) * AVG_TICKET_INR)
