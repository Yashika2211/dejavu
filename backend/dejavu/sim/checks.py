"""Evaluate an archetype's machine-checkable discriminator signals against a live world.

This is what makes the environment fair: every discriminator must be observable in telemetry
alone, a few minutes after the alert, before any memory is involved.
"""

import operator
from collections.abc import Callable

import numpy as np

from dejavu.sim.scenario import Discriminator, Signal
from dejavu.sim.world import IncidentWorld

_OPS: dict[str, Callable[[float, float], bool]] = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}


def _stat(values: np.ndarray, stat: str) -> float:
    if stat == "max":
        return float(values.max())
    if stat == "min":
        return float(values.min())
    return float(values[-3:].mean())


def check_signal(world: IncidentWorld, sig: Signal) -> tuple[bool, str]:
    """Whether the signal holds now, plus what was observed."""
    service = sig.service or ""
    if sig.kind == "metric":
        metric, compare, threshold = str(sig.metric), _OPS[str(sig.op)], float(sig.value or 0.0)
        observed = []
        for node, series in world.metric(service, metric).items():
            start = world.now_min - sig.window_min
            window = series.values[series.minutes > start]
            value = _stat(window, sig.stat)
            if sig.relative:
                before = series.values[(series.minutes <= start) & (series.minutes > start - 60)]
                value /= max(float(np.median(before)), 1e-9)
            observed.append((node, value))
        hits = [(n, v) for n, v in observed if compare(v, threshold)]
        node, value = hits[0] if hits else observed[0]
        where = f" on {node}" if node else ""
        return bool(hits), f"{service} {metric} {sig.stat}={value:.2f}{where}"
    if sig.kind == "log":
        lines = world.logs(service, sig.window_min, contains=sig.contains)
        return len(lines) >= sig.min_count, f"{len(lines)} {service} lines contain {sig.contains!r}"
    if sig.kind == "trace":
        spans = [s for s in world.spans(service, sig.window_min, sig.operation) if s["component"] == service]
        if sig.operation:
            spans = [s for s in spans if s["operation"] == sig.operation]
        if sig.contains:
            hit = [s for s in spans if sig.contains in s["error"]]
            return bool(hit), f"{len(hit)} {service} spans with error {sig.contains!r}"
        slow = [s for s in spans if s["duration_ms"] >= (sig.min_delay_ms or 0)]
        return bool(slow), f"{len(slow)} {service} {sig.operation} spans >= {sig.min_delay_ms} ms"
    changes = world.changes(sig.window_min / 60, sig.service)
    hit = [c for c in changes if sig.change_type is None or c.type == sig.change_type]
    return bool(hit), f"{len(hit)} {sig.change_type or 'any'} changes for {service or 'any service'}"


def check_discriminators(world: IncidentWorld) -> list[tuple[Discriminator, bool, str]]:
    return [(d, *check_signal(world, d.signal)) for d in world.scenario.spec.discriminators]
