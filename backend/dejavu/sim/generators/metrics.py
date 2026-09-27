"""Metric generator: 1-minute series per (component, metric, node) over the incident window.

Every series has two layers. `baseline` holds the diurnal load curve, noise, background blips and
red herrings; `delta` holds what the incident adds. Remediation scales `delta` by a severity curve
at query time, so fixes and relapses never require regenerating data.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

import numpy as np

from dejavu.sim.clock import IST, WINDOW_AFTER_MIN, WINDOW_BEFORE_MIN
from dejavu.sim.rng import np_rng
from dejavu.sim.scenario import MetricShift, Scenario
from dejavu.sim.topology import NODES

OFFSETS = np.arange(-WINDOW_BEFORE_MIN, WINDOW_AFTER_MIN + 1, dtype=np.int64)
AVG_TICKET_INR = 1850.0
NO_NODE = ""

UNITS: dict[str, str] = {
    "rps": "req/s",
    "latency_p50_ms": "ms",
    "latency_p99_ms": "ms",
    "error_rate_5xx": "%",
    "error_rate_4xx": "%",
    "cpu_cores": "cores",
    "cpu_throttle_ratio": "ratio",
    "mem_bytes": "bytes",
    "restarts": "restarts/5m",
    "gc_pause_p99_ms": "ms",
    "db_pool_active": "connections/pod",
    "db_pool_idle": "connections/pod",
    "db_pool_pending": "threads waiting/pod",
    "pgbouncer_cl_waiting": "clients",
    "pg_cpu_pct": "%",
    "pg_active_connections": "connections",
    "pg_slow_queries_per_min": "/min",
    "disk_used_pct": "%",
    "cache_hit_ratio": "ratio",
    "kafka_consumer_lag": "messages",
    "kafka_rebalances": "/min",
    "psp_http_429_rate": "%",
    "psp_latency_p99_ms": "ms",
    "dns_lookup_errors": "/min",
    "cert_days_remaining": "days",
    "node_clock_offset_ms": "ms",
    "payments_attempted": "/min",
    "payments_failed": "/min",
    "gmv_inr_per_min": "INR/min",
}

_RATIOS = {"cpu_throttle_ratio", "cache_hit_ratio"}
_PERCENTS = {"error_rate_5xx", "error_rate_4xx", "pg_cpu_pct", "disk_used_pct", "psp_http_429_rate"}
_SIGNED = {"node_clock_offset_ms", "cert_days_remaining"}


def _gauss(h: np.ndarray, mu: float, sigma: float) -> np.ndarray:
    d = np.minimum(np.abs(h - mu), 24 - np.abs(h - mu))
    return np.exp(-0.5 * (d / sigma) ** 2)


def _raw_curve(h: np.ndarray) -> np.ndarray:
    return (
        0.08
        + 0.62 * _gauss(h, 12.5, 1.7)
        + 0.92 * _gauss(h, 20.6, 1.5)
        + 0.22 * _gauss(h, 16.5, 2.5)
        + 0.12 * _gauss(h, 9.5, 1.2)
    )


_PEAK = float(_raw_curve(np.linspace(0, 24, 24 * 60, endpoint=False)).max())


def diurnal_load(scenario: Scenario) -> np.ndarray:
    """Traffic multiplier per minute: ~0.1 overnight, 1.0 at the 19:00-22:00 IST peak."""
    start = scenario.alert_at.astimezone(IST) + timedelta(minutes=int(OFFSETS[0]))
    hours = (start.hour + start.minute / 60 + (OFFSETS - OFFSETS[0]) / 60) % 24
    load = _raw_curve(hours) / _PEAK
    weekday = np.array([(start + timedelta(minutes=int(m))).weekday() for m in OFFSETS - OFFSETS[0]])
    return load * np.where(weekday >= 5, 0.86, 1.0)


def _ar_noise(rng: np.random.Generator, sigma: float, n: int, phi: float = 0.6) -> np.ndarray:
    """Multiplicative AR(1) noise around 1.0."""
    shocks = rng.normal(0.0, sigma * np.sqrt(1 - phi**2), n)
    e = np.empty(n)
    e[0] = rng.normal(0.0, sigma)
    for i in range(1, n):
        e[i] = phi * e[i - 1] + shocks[i]
    return np.exp(e)


Profile = Callable[[float, np.ndarray, np.random.Generator], np.ndarray]


def _scaled(lo: float, sigma: float) -> Profile:
    """base x (lo + (1 - lo) x load) x noise."""
    return lambda base, load, rng: base * (lo + (1 - lo) * load) * _ar_noise(rng, sigma, load.size)


def _flat(sigma: float) -> Profile:
    return lambda base, load, rng: base * _ar_noise(rng, sigma, load.size)


def _poisson(base: float, load: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    return rng.poisson(base * load).astype(float)


PROFILES: dict[str, Profile] = {
    "rps": _scaled(0.0, 0.04),
    "payments_attempted": _scaled(0.0, 0.04),
    "payments_failed": _scaled(0.0, 0.2),
    "latency_p50_ms": _scaled(0.8, 0.05),
    "latency_p99_ms": _scaled(0.7, 0.08),
    "error_rate_5xx": _scaled(0.6, 0.25),
    "error_rate_4xx": _flat(0.12),
    "cpu_cores": _scaled(0.18, 0.05),
    "cpu_throttle_ratio": _flat(0.3),
    "mem_bytes": _scaled(0.94, 0.01),
    "restarts": lambda base, load, rng: np.zeros(load.size),
    "gc_pause_p99_ms": _flat(0.12),
    "db_pool_active": _scaled(0.1, 0.15),
    "db_pool_idle": lambda base, load, rng: np.zeros(load.size),  # derived from active
    "db_pool_pending": lambda base, load, rng: np.zeros(load.size),
    "pgbouncer_cl_waiting": lambda base, load, rng: np.zeros(load.size),
    "pg_cpu_pct": _scaled(0.35, 0.06),
    "pg_active_connections": _scaled(0.5, 0.08),
    "pg_slow_queries_per_min": _poisson,
    "disk_used_pct": lambda base, load, rng: (
        base + 0.0008 * (OFFSETS - OFFSETS[0]) + rng.normal(0, 0.01, load.size)
    ),
    "cache_hit_ratio": lambda base, load, rng: base - 0.01 * load + rng.normal(0, 0.003, load.size),
    "kafka_consumer_lag": _scaled(0.5, 0.3),
    "kafka_rebalances": lambda base, load, rng: np.zeros(load.size),
    "psp_http_429_rate": _flat(0.4),
    "psp_latency_p99_ms": _scaled(0.9, 0.08),
    "dns_lookup_errors": _poisson,
    "cert_days_remaining": lambda base, load, rng: base - (OFFSETS - OFFSETS[0]) / 1440.0,
    "node_clock_offset_ms": lambda base, load, rng: rng.normal(0, 1.2, load.size),
    "gmv_inr_per_min": lambda base, load, rng: np.zeros(load.size),  # derived
}

Key = tuple[str, str, str]  # component, metric, node


@dataclass
class Series:
    baseline: np.ndarray
    total: np.ndarray

    @property
    def delta(self) -> np.ndarray:
        return self.total - self.baseline


def envelope(effect: MetricShift) -> np.ndarray:
    """0..1 weight of an effect per minute (for `linear`, the fraction of the way to `to`)."""
    t = (OFFSETS - effect.start_offset).astype(float)
    active = t >= 0
    if effect.duration is not None:
        active &= t < effect.duration
    ramp = max(effect.ramp_minutes, 1e-9)
    if effect.shape == "step":
        w = np.ones_like(t)
    elif effect.shape in ("ramp", "linear"):
        span = effect.duration if effect.shape == "linear" and effect.duration else ramp
        w = np.clip(t / span, 0, 1)
    elif effect.shape == "sawtooth":
        w = np.mod(t, effect.period) / effect.period
    elif effect.shape == "spike":
        w = (np.mod(t, effect.period) < ramp).astype(float)
    else:  # oscillate
        w = 0.5 + 0.5 * np.sin(2 * np.pi * t / effect.period)
    return np.where(active, w, 0.0)


def _apply(values: np.ndarray, effect: MetricShift, rng: np.random.Generator) -> np.ndarray:
    w = envelope(effect)
    jitter = 1 + rng.normal(0, effect.noise, values.size)
    if effect.mode == "add":
        return values + effect.magnitude * w * jitter
    if effect.mode == "multiply":
        return values * (1 + (effect.magnitude - 1) * w * jitter)
    if effect.shape == "linear":
        target = effect.magnitude + ((effect.to or 0.0) - effect.magnitude) * w
        return np.where(OFFSETS - effect.start_offset >= 0, target, values)
    return values * (1 - w) + effect.magnitude * w * jitter


def _clamp(metric: str, values: np.ndarray) -> np.ndarray:
    if metric in _SIGNED:
        return values
    if metric in _RATIOS:
        return np.clip(values, 0, 1)
    if metric in _PERCENTS:
        return np.clip(values, 0, 100)
    return np.maximum(values, 0)


def _background_blips(series: dict[Key, Series], scenario: Scenario, rng: np.random.Generator) -> None:
    """Harmless noise that is never the answer: JVM GC pauses and short latency wobbles."""
    for comp in ("ledger-svc", "notifications-worker"):
        key = (comp, "gc_pause_p99_ms", NO_NODE)
        if key not in series:
            continue
        for _ in range(rng.integers(1, 3)):
            at = rng.integers(0, OFFSETS.size - 2)
            bump = rng.uniform(160, 320)
            for s in (series[key].baseline, series[key].total):
                s[at : at + 2] += bump
    key = ("checkout-api", "latency_p99_ms", NO_NODE)
    if key in series:
        at = rng.integers(0, OFFSETS.size - 3)
        for s in (series[key].baseline, series[key].total):
            s[at : at + 3] *= 1.15


def generate_metrics(scenario: Scenario) -> dict[Key, Series]:
    """All metric series for one incident, keyed by (component, metric, node)."""
    topology = scenario.topology
    load = diurnal_load(scenario)
    series: dict[Key, Series] = {}
    for comp in topology.components.values():
        for metric, base in comp.metrics.items():
            nodes = [n.name for n in NODES] if metric == "node_clock_offset_ms" else [NO_NODE]
            for node in nodes:
                rng = np_rng(scenario.seed, scenario.incident_id, "metric", comp.name, metric, node)
                values = PROFILES[metric](base, load, rng)
                series[(comp.name, metric, node)] = Series(values, values.copy())

    _background_blips(series, scenario, np_rng(scenario.seed, scenario.incident_id, "blips"))

    for i, effect in enumerate(e for e in scenario.spec.effects if isinstance(e, MetricShift)):
        rng = np_rng(scenario.seed, scenario.incident_id, "effect", i)
        for comp in effect.service:
            keys = [k for k in series if k[0] == comp and k[1] == effect.metric]
            if effect.node is not None:
                keys = [k for k in keys if k[2] == effect.node]
            if not keys:
                raise ValueError(f"effect {i}: {comp} has no metric {effect.metric}")
            for key in keys:
                s = series[key]
                s.total = _apply(s.total, effect, rng)
                if not effect.incident:
                    s.baseline = _apply(s.baseline, effect, rng)

    _apply_impact(series, scenario)
    _derive(series, topology.pool_max, np_rng(scenario.seed, scenario.incident_id, "gmv"))
    for (_, metric, _), s in series.items():
        s.baseline = np.round(_clamp(metric, s.baseline), 4)
        s.total = np.round(_clamp(metric, s.total), 4)
    return series


def _apply_impact(series: dict[Key, Series], scenario: Scenario) -> None:
    """Failed payments: the incident's failure share of attempted payments, ramped in at onset."""
    impact = scenario.spec.impact
    attempted = series[("checkout-api", "payments_attempted", NO_NODE)].total
    t = OFFSETS - impact.start_offset
    ramp = np.clip(t / max(impact.ramp_minutes, 1e-9), 0, 1) * (t >= 0)
    rng = np_rng(scenario.seed, scenario.incident_id, "impact")
    extra = attempted * impact.failure_share * ramp * (1 + rng.normal(0, 0.05, OFFSETS.size))
    series[("checkout-api", "payments_failed", NO_NODE)].total += np.maximum(extra, 0)


def _derive(series: dict[Key, Series], pool_max: int, rng: np.random.Generator) -> None:
    """Metrics that follow from others: idle pool connections and GMV."""
    active = series.get(("ledger-svc", "db_pool_active", NO_NODE))
    if active is not None:
        active.baseline = np.minimum(active.baseline, pool_max)
        active.total = np.minimum(active.total, pool_max)
        idle = series[("ledger-svc", "db_pool_idle", NO_NODE)]
        idle.baseline = pool_max - active.baseline
        idle.total = pool_max - active.total
    attempted = series[("checkout-api", "payments_attempted", NO_NODE)]
    failed = series[("checkout-api", "payments_failed", NO_NODE)]
    gmv = series[("checkout-api", "gmv_inr_per_min", NO_NODE)]
    wobble = 1 + rng.normal(0, 0.03, OFFSETS.size)
    gmv.baseline = (attempted.baseline - failed.baseline) * AVG_TICKET_INR * wobble
    gmv.total = (attempted.total - failed.total) * AVG_TICKET_INR * wobble
