"""The Gauntlet schedule, the held-out set and the demo incidents, as instantiable scenarios.

Incident IDs are assigned deterministically but look like a real ticket sequence (increasing,
with gaps for the incidents DejaVu never saw), and they never encode the archetype.
"""

from datetime import datetime
from functools import cache
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

from dejavu.sim.clock import ist
from dejavu.sim.rng import py_rng
from dejavu.sim.scenario import SCENARIO_DIR, Scenario, instantiate

SCHEDULE_PATH = SCENARIO_DIR / "schedule.yaml"


class Entry(BaseModel):
    n: int
    at: datetime
    archetype: str
    overrides: dict[str, Any] = Field(default_factory=dict)
    extras: list[str] = Field(default_factory=list)
    tests: str = ""
    foresight_checkpoint: bool = False

    @field_validator("at", mode="before")
    @classmethod
    def _ist(cls, value: Any) -> Any:
        return ist(value) if isinstance(value, str) else value


class HeldOut(BaseModel):
    seed: int
    first_incident_number: int
    incidents: list[Entry]


class Demo(BaseModel):
    name: str
    at: datetime
    archetype: str
    seed: int

    @field_validator("at", mode="before")
    @classmethod
    def _ist(cls, value: Any) -> Any:
        return ist(value) if isinstance(value, str) else value


class Schedule(BaseModel):
    seed: int
    first_incident_number: int
    incidents: list[Entry]
    held_out: HeldOut
    demos: list[Demo]


@cache
def load_schedule() -> Schedule:
    return Schedule.model_validate(yaml.safe_load(SCHEDULE_PATH.read_text()))


def incident_ids(entries: list[Entry], seed: int, first: int) -> dict[int, str]:
    """Increasing ticket numbers with random gaps: INC-4127, INC-4131, INC-4150, ..."""
    rng = py_rng(seed, "incident-ids")
    ids, number = {}, first
    for entry in sorted(entries, key=lambda e: e.at):
        ids[entry.n] = f"INC-{number}"
        number += rng.randint(3, 19)
    return ids


def gauntlet(seed: int | None = None) -> list[Scenario]:
    """The 24 Gauntlet incidents in time order, for `seed` (default: the schedule's seed)."""
    schedule = load_schedule()
    seed = schedule.seed if seed is None else seed
    ids = incident_ids(schedule.incidents, seed, schedule.first_incident_number)
    return [
        instantiate(
            e.archetype,
            seed=seed,
            incident_id=ids[e.n],
            alert_at=e.at,
            overrides=e.overrides,
            extras=e.extras,
        )
        for e in sorted(schedule.incidents, key=lambda e: e.at)
    ]


def held_out() -> list[Scenario]:
    h = load_schedule().held_out
    ids = incident_ids(h.incidents, h.seed, h.first_incident_number)
    return [instantiate(e.archetype, seed=h.seed, incident_id=ids[e.n], alert_at=e.at) for e in h.incidents]


def demo(name: str) -> Scenario:
    d = next(d for d in load_schedule().demos if d.name == name)
    number = 4400 + py_rng(d.seed, "demo-id").randint(0, 99)
    return instantiate(d.archetype, seed=d.seed, incident_id=f"INC-{number}", alert_at=d.at)


def entry_for(scenario: Scenario) -> Entry | None:
    """The schedule entry a Gauntlet scenario came from (for its `tests` note and checkpoint flag)."""
    return next((e for e in load_schedule().incidents if e.at == scenario.alert_at), None)
