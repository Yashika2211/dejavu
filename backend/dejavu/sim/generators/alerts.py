"""Alertmanager-style alert payloads. The description quotes the simulated metric at the alert."""

from typing import Any
from urllib.parse import quote

import numpy as np

from dejavu.sim.generators.metrics import NO_NODE, OFFSETS, UNITS, Key, Series
from dejavu.sim.rng import hex_id, py_rng
from dejavu.sim.scenario import Scenario
from dejavu.sim.topology import CLUSTER, NAMESPACE


def fmt_value(value: float, unit: str) -> str:
    """Human formatting used by alerts and tools: `4,812 ms`, `12.4%`, `0.03`."""
    if unit == "%":
        return f"{value:.1f}%"
    if unit == "ratio":
        return f"{value:.2f}"
    if unit == "bytes":
        return f"{value / 2**30:.2f} GiB"
    if abs(value) >= 100:
        return f"{value:,.0f} {unit}".strip()
    return f"{value:,.1f} {unit}".strip()


def alert_value(scenario: Scenario, metrics: dict[Key, Series]) -> float:
    """Mean of the alert metric over the five minutes before it fired (the `for: 5m` window)."""
    spec = scenario.spec.alert
    series = metrics[(spec.metric_service, spec.metric, NO_NODE)].total
    window = (OFFSETS > -5) & (OFFSETS <= 0)
    return float(np.mean(series[window]))


def generate_alert(scenario: Scenario, metrics: dict[Key, Series]) -> dict[str, Any]:
    spec = scenario.spec.alert
    value = fmt_value(alert_value(scenario, metrics), UNITS[spec.metric])
    rng = py_rng(scenario.seed, scenario.incident_id, "alert")
    return {
        "receiver": "pagerduty-oncall",
        "status": "firing",
        "labels": {
            "alertname": spec.name,
            "severity": spec.severity,
            "service": spec.service,
            "namespace": NAMESPACE,
            "cluster": CLUSTER,
            **spec.labels,
        },
        "annotations": {
            "summary": spec.summary,
            "description": spec.description.replace("{value}", value),
            "runbook_url": f"https://runbooks.kestrelpay.internal/{spec.runbook}",
        },
        "startsAt": scenario.alert_at.isoformat(),
        "endsAt": "0001-01-01T00:00:00Z",
        "generatorURL": f"http://prometheus.{CLUSTER}.kestrelpay.internal/graph?g0.expr={quote(spec.expr)}&g0.tab=1",
        "fingerprint": hex_id(rng, 16),
    }
