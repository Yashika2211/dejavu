"""Trace generator: sampled request traces through Kestrel Pay's call graph.

Children run sequentially, so a parent's duration is its self time plus its children's. Incident
delays (`trace_delay` effects) are stored separately from base durations and propagate to every
ancestor; remediation later scales them at query time.
"""

from dataclasses import dataclass, field

import numpy as np

from dejavu.sim.clock import WINDOW_AFTER_MIN
from dejavu.sim.generators.metrics import OFFSETS, diurnal_load
from dejavu.sim.rng import np_rng
from dejavu.sim.scenario import Scenario, TraceDelay

TRACE_START_MIN = -90
TRACES_PER_MIN = 10.0

SpanSpec = tuple[str, str, float, list["SpanSpec"]]  # component, operation, median self ms, children


def request_types(cache: str) -> dict[str, tuple[float, SpanSpec]]:
    """Request shapes with their share of traffic."""
    validate: SpanSpec = ("auth-svc", "ValidateToken", 3.0, [(cache, "GET session", 0.5, [])])
    checkout: SpanSpec = (
        "edge-gateway",
        "POST /v1/checkout",
        2.0,
        [
            (
                "checkout-api",
                "POST /v1/checkout",
                15.0,
                [
                    validate,
                    ("fraud-scorer", "POST /score", 25.0, [(cache, "GET features", 0.6, [])]),
                    ("payments-svc", "Charge", 8.0, [("acquirerx", "POST /v2/charges", 360.0, [])]),
                    (
                        "ledger-svc",
                        "POST /entries",
                        10.0,
                        [
                            ("ledger-svc", "HikariPool.getConnection", 0.4, []),
                            (
                                "ledger-svc",
                                "JDBC executeUpdate",
                                1.0,
                                [("postgres-ledger", "INSERT ledger_entries", 2.5, [])],
                            ),
                            (
                                "ledger-svc",
                                "JDBC executeQuery",
                                0.8,
                                [("postgres-ledger", "SELECT ledger_entries", 3.0, [])],
                            ),
                        ],
                    ),
                ],
            )
        ],
    )
    login: SpanSpec = (
        "edge-gateway",
        "POST /v1/auth/token",
        2.0,
        [("auth-svc", "IssueToken", 5.0, [(cache, "GET session", 0.5, []), (cache, "SET session", 0.6, [])])],
    )
    balance: SpanSpec = (
        "edge-gateway",
        "GET /v1/balance",
        2.0,
        [
            (
                "checkout-api",
                "GET /v1/balance",
                8.0,
                [validate, ("ledger-svc", "GET /balance", 3.0, [(cache, "GET balance", 0.5, [])])],
            )
        ],
    )
    return {"checkout": (0.45, checkout), "login": (0.3, login), "balance": (0.25, balance)}


@dataclass
class SpanRows:
    """Columnar span rows, ready for Arrow."""

    trace_id: list[str] = field(default_factory=list)
    span_id: list[str] = field(default_factory=list)
    parent_id: list[str] = field(default_factory=list)
    component: list[str] = field(default_factory=list)
    operation: list[str] = field(default_factory=list)
    start_offset_ms: list[float] = field(default_factory=list)
    base_ms: list[float] = field(default_factory=list)
    incident_ms: list[float] = field(default_factory=list)
    error: list[str] = field(default_factory=list)
    incident_error: list[bool] = field(default_factory=list)
    draw: list[float] = field(default_factory=list)


@dataclass
class _Span:
    component: str
    operation: str
    self_ms: float
    children: list["_Span"]
    span_id: str = ""
    added_ms: float = 0.0
    base_added_ms: float = 0.0
    error: str = ""
    incident_error: bool = False

    def base_total(self) -> float:
        return self.self_ms + self.base_added_ms + sum(c.base_total() for c in self.children)

    def incident_total(self) -> float:
        return self.added_ms + sum(c.incident_total() for c in self.children)


def _hex(rng: np.random.Generator, n: int) -> str:
    return "".join("0123456789abcdef"[i] for i in rng.integers(0, 16, n))


def _build(spec: SpanSpec, rng: np.random.Generator) -> _Span:
    comp, op, median, children = spec
    self_ms = float(median * np.exp(rng.normal(0, 0.35)))
    return _Span(comp, op, self_ms, [_build(c, rng) for c in children], span_id=_hex(rng, 16))


def _walk(span: _Span):
    yield span
    for child in span.children:
        yield from _walk(child)


def _ramp(effect: TraceDelay, t_min: float) -> float:
    t = t_min - effect.start_offset
    if t < 0 or (effect.duration is not None and t >= effect.duration):
        return 0.0
    return min(1.0, (t + 1) / max(effect.ramp_minutes, 1.0))


def _apply(root: _Span, t_min: float, effects: list[TraceDelay], rng: np.random.Generator) -> None:
    for effect in effects:
        weight = _ramp(effect, t_min)
        if weight == 0.0:
            continue
        for span in _walk(root):
            if span.component != effect.service or span.operation != effect.operation:
                continue
            if rng.random() < effect.share * weight:
                delay = float(rng.uniform(*effect.add_ms))
                if effect.incident:
                    span.added_ms += delay
                else:
                    span.base_added_ms += delay
            if effect.error and rng.random() < effect.error_share * weight:
                span.error, span.incident_error = effect.error, effect.incident


def _propagate_errors(span: _Span) -> tuple[str, bool]:
    """A failed child fails its parent (the HTTP call returns an error)."""
    for child in span.children:
        err, inc = _propagate_errors(child)
        if err and not span.error:
            span.error, span.incident_error = f"upstream {child.component}: {err}", inc
    return span.error, span.incident_error


def _emit(rows: SpanRows, trace_id: str, span: _Span, parent: str, start_ms: float, draw: float) -> None:
    rows.trace_id.append(trace_id)
    rows.span_id.append(span.span_id)
    rows.parent_id.append(parent)
    rows.component.append(span.component)
    rows.operation.append(span.operation)
    rows.start_offset_ms.append(round(start_ms, 3))
    rows.base_ms.append(round(span.base_total(), 3))
    rows.incident_ms.append(round(span.incident_total(), 3))
    rows.error.append(span.error)
    rows.incident_error.append(span.incident_error)
    rows.draw.append(round(draw, 6))
    cursor = start_ms + span.self_ms / 2
    for child in span.children:
        _emit(rows, trace_id, child, span.span_id, cursor, draw)
        cursor += child.base_total()


def generate_traces(scenario: Scenario) -> SpanRows:
    """Sampled traces from 90 minutes before the alert to the end of the window."""
    rng = np_rng(scenario.seed, scenario.incident_id, "traces")
    shapes = request_types(scenario.topology.cache)
    names = list(shapes)
    probs = np.array([shapes[n][0] for n in names])
    effects = [e for e in scenario.spec.effects if isinstance(e, TraceDelay)]
    load = dict(zip(OFFSETS.tolist(), diurnal_load(scenario), strict=True))
    rows = SpanRows()
    for minute in range(TRACE_START_MIN, WINDOW_AFTER_MIN + 1):
        for sec in np.sort(rng.uniform(0, 60, rng.poisson(TRACES_PER_MIN * (0.3 + load[minute])))):
            t_min = minute + sec / 60
            root = _build(shapes[names[int(rng.choice(len(names), p=probs))]][1], rng)
            _apply(root, t_min, effects, rng)
            _propagate_errors(root)
            _emit(rows, _hex(rng, 32), root, "", t_min * 60_000, float(rng.random()))
    return rows
