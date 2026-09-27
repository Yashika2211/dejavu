"""Simulated time. Everything in an incident is measured in minutes relative to the alert (T0).

India has no DST, so IST is a fixed +05:30 offset; that keeps generated telemetry independent of
the host's timezone database.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), "IST")

WINDOW_BEFORE_MIN = 180
WINDOW_AFTER_MIN = 120


def ist(value: str) -> datetime:
    """Parse an ISO timestamp; naive values are taken as IST."""
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=IST)


def fmt_hm(dt: datetime) -> str:
    """`03:07` in IST."""
    return dt.astimezone(IST).strftime("%H:%M")


def fmt_hms(dt: datetime) -> str:
    """`03:07:12` in IST."""
    return dt.astimezone(IST).strftime("%H:%M:%S")


def fmt_day_hm(dt: datetime) -> str:
    """`17 Aug 03:07` in IST."""
    return dt.astimezone(IST).strftime("%d %b %H:%M")


def utc(dt: datetime) -> datetime:
    return dt.astimezone(UTC)


@dataclass
class SimClock:
    """The investigation clock: starts at the alert and only moves forward."""

    alert_at: datetime
    elapsed_min: float = 0.0

    @property
    def now(self) -> datetime:
        return self.at(self.elapsed_min)

    def at(self, offset_min: float) -> datetime:
        """Wall time for an offset (minutes) relative to the alert."""
        return self.alert_at + timedelta(minutes=offset_min)

    def offset_of(self, dt: datetime) -> float:
        """Minutes between the alert and `dt` (negative before the alert)."""
        return (dt - self.alert_at).total_seconds() / 60.0

    def advance(self, minutes: float) -> None:
        if minutes < 0:
            raise ValueError("the simulated clock cannot run backwards")
        self.elapsed_min += minutes
