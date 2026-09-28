"""Pending changes for the Foresight screen (spec 8), and the latent incident behind each risky one.

A risky pending change is exactly the trigger change of a latent scenario, so what the reviewer sees
is what would ship; the scenario stays server-side and decides whether a review prevents it.
"""

from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from dejavu.sim.clock import ist
from dejavu.sim.generators.events import ChangeEvent, generate_events
from dejavu.sim.scenario import SCENARIO_DIR, ChangeType, Scenario, instantiate
from dejavu.sim.telemetry import INCIDENTS_DIR, ensure_telemetry
from dejavu.sim.world import IncidentWorld

PENDING_PATH = SCENARIO_DIR / "pending.yaml"
AVOIDED_WINDOW_MIN = 30


class PendingChange(BaseModel):
    """A change waiting to ship, as the change calendar shows it: no hint of what it would cause."""

    id: str
    type: ChangeType
    service: str
    author: str
    planned_at: datetime
    summary: str
    details: dict[str, Any]


def _from_event(pending_id: str, event: ChangeEvent) -> PendingChange:
    return PendingChange(
        id=pending_id,
        type=event.type,
        service=event.service,
        author=event.author,
        planned_at=event.at,
        summary=event.summary,
        details=event.details,
    )


def _latent(spec: dict[str, Any]) -> Scenario:
    return instantiate(
        spec["archetype"],
        seed=spec["seed"],
        incident_id=spec["incident_id"],
        alert_at=ist(spec["alert_at"]),
        overrides=spec.get("overrides"),
    )


@cache
def pending_changes() -> tuple[tuple[PendingChange, Scenario | None], ...]:
    """Every pending change with its latent incident (None for a harmless change), by planned time."""
    out = []
    for entry in yaml.safe_load(PENDING_PATH.read_text())["pending"]:
        if "latent" in entry:
            scenario = _latent(entry["latent"])
            trigger = next(e for e in generate_events(scenario) if e.id == scenario.trigger_change_id)
            out.append((_from_event(entry["id"], trigger), scenario))
        else:
            change = entry["change"]
            out.append((PendingChange(id=entry["id"], planned_at=ist(change.pop("at")), **change), None))
    return tuple(sorted(out, key=lambda pair: pair[0].planned_at))


def find(change_id: str) -> tuple[PendingChange, Scenario | None] | None:
    return next((pair for pair in pending_changes() if pair[0].id == change_id), None)


def impact_if_shipped(
    latent: Scenario, root: Path = INCIDENTS_DIR, window_min: float = AVOIDED_WINDOW_MIN
) -> float:
    """Simulated payments at risk if the change ships: the latent incident up to `window_min` after its alert."""
    ensure_telemetry(latent, root)
    return IncidentWorld.open(latent, root).inr_at_risk(window_min)
