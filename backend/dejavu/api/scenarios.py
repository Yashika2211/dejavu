"""Which scenario a new war-room incident gets, and how a stored incident is rebuilt.

Named demos keep their canonical incident id, so every rehearsal replays the same variant.
Archetypes and "surprise" get a fresh seed (unless one is given), a time on the demo day (after
both migrations) and a ticket number above every Gauntlet, held-out and demo id.
"""

import random
from datetime import date, datetime, time

from dejavu.sim.clock import IST
from dejavu.sim.rng import py_rng
from dejavu.sim.scenario import Scenario, archetype_ids, instantiate
from dejavu.sim.schedule import demo, load_schedule
from dejavu.store.db import IncidentRecord

DEMO_DAY = date(2026, 9, 27)
FIRST_LIVE_NUMBER = 4501


class UnknownScenarioError(ValueError):
    """Neither a demo name, an archetype id nor "surprise"."""


def demo_names() -> list[str]:
    return [d.name for d in load_schedule().demos]


def new_incident(requested: str | None, seed: int | None, existing: set[str]) -> IncidentRecord:
    """The record for a new incident; `existing` holds the incident ids already taken."""
    requested = requested or "surprise"
    demos = {d.name: d for d in load_schedule().demos}
    if requested in demos:
        d = demos[requested]
        return IncidentRecord(
            id=demo(requested).incident_id,
            source="demo",
            requested=requested,
            archetype=d.archetype,
            seed=d.seed,
            alert_at=d.at.isoformat(),
        )
    seed = seed if seed is not None else random.randrange(1_000_000)
    rng = py_rng(seed, "war-room")
    if requested == "surprise":
        archetype, source = rng.choice(sorted(archetype_ids())), "surprise"
    elif requested in archetype_ids():
        archetype, source = requested, "archetype"
    else:
        raise UnknownScenarioError(requested)
    alert_at = datetime.combine(DEMO_DAY, time(rng.randint(0, 23), rng.randint(0, 59)), tzinfo=IST)
    taken = [int(i.removeprefix("INC-")) for i in existing if i.removeprefix("INC-").isdigit()]
    number = max([FIRST_LIVE_NUMBER - 1, *taken]) + rng.randint(1, 4)
    return IncidentRecord(
        id=f"INC-{number}",
        source=source,
        requested=requested,
        archetype=archetype,
        seed=seed,
        alert_at=alert_at.isoformat(),
    )


def scenario_of(record: IncidentRecord) -> Scenario:
    if record.source == "demo":
        return demo(record.requested)
    return instantiate(
        record.archetype,
        seed=record.seed,
        incident_id=record.id,
        alert_at=datetime.fromisoformat(record.alert_at),
    )
