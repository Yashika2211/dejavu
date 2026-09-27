"""Deterministic release calendars, so versions stay consistent across every incident.

Each service ships on a steady cadence from an anchor date; the scheme is chosen so the pinned
versions in the Gauntlet schedule (ledger-svc 3.14.0 on 17 Aug, 3.19.0 on 21 Sep; fraud model v47
on 22 Aug, v52 on 12 Sep) fall out naturally.
"""

import math
from dataclasses import dataclass
from datetime import date, datetime

from dejavu.sim.clock import IST


@dataclass(frozen=True)
class Cadence:
    major: int
    minor_at_anchor: int
    anchor: date
    days_per_minor: float


CADENCES = {
    "auth-svc": Cadence(4, 2, date(2026, 8, 1), 10),
    "checkout-api": Cadence(7, 40, date(2026, 8, 1), 3.5),
    "payments-svc": Cadence(5, 8, date(2026, 8, 1), 9),
    "ledger-svc": Cadence(3, 14, date(2026, 8, 17), 7),
    "fraud-scorer": Cadence(2, 3, date(2026, 8, 1), 14),
    "notifications-worker": Cadence(2, 7, date(2026, 8, 1), 12),
}

MODEL_ANCHOR = date(2026, 8, 22)
MODEL_AT_ANCHOR = 47
MODEL_DAYS_PER_VERSION = 4.2


def _days(when: datetime | date, anchor: date) -> float:
    day = when.astimezone(IST).date() if isinstance(when, datetime) else when
    return float((day - anchor).days)


def version_at(service: str, when: datetime | date) -> str:
    """The version of `service` released on or before `when`'s day."""
    cad = CADENCES[service]
    days = _days(when, cad.anchor)
    minor = cad.minor_at_anchor + math.floor(days / cad.days_per_minor)
    patch = int((days % cad.days_per_minor) // 2)
    return f"{cad.major}.{minor}.{patch}"


def previous_version(service: str, when: datetime | date) -> str:
    """The last minor release before the one current on `when`'s day."""
    cad = CADENCES[service]
    days = _days(when, cad.anchor)
    minor = cad.minor_at_anchor + math.floor(days / cad.days_per_minor) - 1
    return f"{cad.major}.{minor}.{int(cad.days_per_minor // 2) // 2 + 1}"


def model_version_at(when: datetime | date) -> int:
    """fraud-scorer model version (the LightGBM artifact) live on `when`'s day."""
    return MODEL_AT_ANCHOR + math.floor(_days(when, MODEL_ANCHOR) / MODEL_DAYS_PER_VERSION)
