"""Scenario DSL (spec 4.3): archetypes are declarative YAML, instantiated once per incident.

An archetype file declares effects layered on the baseline world, plus everything needed to grade
an investigation: discriminators, relevant evidence, remediation outcomes and prevention.
`{{name}}` (or `{{name - 3}}`) placeholders are filled at instantiation from seed-randomised `variants`, schedule
overrides and the world at that moment (`cache`, `pool_max`, release versions, pods, nodes).
Effects, discriminators and remediation rules can carry `when: pre_m1 | post_m1 | pre_m2 | post_m2`.
"""

import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dejavu.sim.migrations import Phase
from dejavu.sim.releases import CADENCES, model_version_at, previous_version, version_at
from dejavu.sim.rng import hex_id, pod_suffix, py_rng, replicaset_hash
from dejavu.sim.topology import NODES, Kind, LogFormat, Topology, topology_at
from dejavu.taxonomy import Remediation, RootCause, SymptomClass

SCENARIO_DIR = Path(__file__).parent / "scenarios"
_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*(?:([+-])\s*(\d+(?:\.\d+)?))?\s*\}\}")


class Level(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    FATAL = "FATAL"

    @property
    def rank(self) -> int:
        return list(Level).index(self)


class ChangeType(StrEnum):
    DEPLOY = "deploy"
    CONFIG = "config"
    FLAG = "flag"
    HELM = "helm"
    SCHEMA_MIGRATION = "schema_migration"
    MODEL_RELEASE = "model_release"
    MIGRATION = "migration"
    INFRA = "infra"
    REMEDIATION = "remediation"


class Safeguard(StrEnum):
    """Foresight safeguard catalog (spec 8)."""

    CANARY_ROLLOUT = "canary_rollout"
    FLAG_GUARD = "flag_guard"
    LOAD_TEST = "load_test"
    QUERY_PLAN_REVIEW = "query_plan_review"
    POOL_CONFIG_REVIEW = "pool_config_review"
    OWNER_REVIEW = "owner_review"
    REVERT = "revert"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


@dataclass(frozen=True)
class SampleContext:
    """What a variable generator may draw from: this incident's pods and nodes."""

    pods: Mapping[str, Sequence[str]]
    pod_nodes: Mapping[str, str]
    pod_ips: Mapping[str, str]
    alert_at: datetime


class VarSpec(_Model):
    """One random variable. Exactly one generator key is set."""

    randint: tuple[int, int] | None = None
    uniform: tuple[float, float] | None = None
    choice: list[Any] | None = None
    hex: int | None = None
    pod: str | None = None
    pod_ip: str | None = None
    node: str | None = None  # "any", or "of:<service>" for a node hosting that service
    utc_at: float | None = None  # a fixed moment (minutes after the alert) as an ISO UTC timestamp
    fmt: str | None = None

    @model_validator(mode="after")
    def _one_generator(self) -> "VarSpec":
        keys = ("randint", "uniform", "choice", "hex", "pod", "pod_ip", "node", "utc_at")
        if sum(getattr(self, k) is not None for k in keys) != 1:
            raise ValueError(f"exactly one of {keys} must be set")
        return self

    def sample(self, rng: random.Random, ctx: SampleContext) -> Any:
        value: Any
        if self.randint is not None:
            value = rng.randint(*self.randint)
        elif self.uniform is not None:
            value = rng.uniform(*self.uniform)
        elif self.choice is not None:
            value = rng.choice(self.choice)
        elif self.hex is not None:
            value = hex_id(rng, self.hex)
        elif self.pod is not None:
            value = rng.choice(list(ctx.pods[self.pod]))
        elif self.pod_ip is not None:
            value = ctx.pod_ips[rng.choice(list(ctx.pods[self.pod_ip]))]
        elif self.utc_at is not None:
            value = f"{(ctx.alert_at + timedelta(minutes=self.utc_at)).astimezone(UTC):%Y-%m-%dT%H:%M:%SZ}"
        else:
            value = _sample_node(str(self.node), rng, ctx)
        return format(value, self.fmt) if self.fmt else value


def _sample_node(spec: str, rng: random.Random, ctx: SampleContext) -> str:
    if spec == "any":
        return rng.choice([n.name for n in NODES])
    if spec.startswith("of:"):
        return ctx.pod_nodes[rng.choice(list(ctx.pods[spec[3:]]))]
    raise ValueError(f"unknown node spec {spec!r}")


def _as_list(value: Any) -> Any:
    return [value] if isinstance(value, str) else value


# effects ---------------------------------------------------------------------------------


class _Effect(_Model):
    when: Phase | None = None
    incident: bool = True  # False: background / red herring, unaffected by remediation


class MetricShift(_Effect):
    kind: Literal["metric_shift"]
    service: list[str]
    metric: str
    shape: Literal["step", "ramp", "sawtooth", "spike", "oscillate", "linear"]
    magnitude: float
    mode: Literal["add", "multiply", "set"] = "add"
    start_offset: float
    duration: float | None = None
    ramp_minutes: float = 3.0
    period: float = 10.0
    to: float | None = None
    node: str | None = None
    noise: float = 0.04

    _list = field_validator("service", mode="before")(_as_list)


class LogInject(_Effect):
    kind: Literal["log_inject"]
    service: list[str]
    template: str
    level: Level
    rate_per_min: float
    start_offset: float
    duration: float | None = None
    ramp_minutes: float = 2.0
    vars: dict[str, VarSpec] = Field(default_factory=dict)
    fields: dict[str, Any] = Field(default_factory=dict)
    logger: str | None = None
    thread: str | None = None
    caller: str | None = None
    format: LogFormat | Literal["k8s_event"] | None = None
    pod: str | None = None  # pin every line to one pod (or node, for the nodes component)
    exact: bool = False  # emit exactly `rate_per_min` lines per minute instead of a Poisson draw

    _list = field_validator("service", mode="before")(_as_list)


class TraceDelay(_Effect):
    kind: Literal["trace_delay"]
    service: str
    operation: str
    add_ms: tuple[float, float]
    share: float = 1.0
    start_offset: float
    duration: float | None = None
    ramp_minutes: float = 2.0
    error_share: float = 0.0
    error: str | None = None

    @field_validator("add_ms", mode="before")
    @classmethod
    def _pair(cls, value: Any) -> Any:
        return (value, value) if isinstance(value, int | float) else value


class EventEffect(_Effect):
    kind: Literal["event"]
    type: ChangeType
    service: str
    at_offset: float
    author: str
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
    trigger: bool = False
    id: str | None = None


Effect = Annotated[MetricShift | LogInject | TraceDelay | EventEffect, Field(discriminator="kind")]


# alert, impact, grading -------------------------------------------------------------------


class AlertSpec(_Model):
    name: str
    severity: str = "sev2"
    service: str
    summary: str
    description: str  # `{value}` is filled from `metric` at the alert
    metric_service: str
    metric: str
    threshold: float
    expr: str
    runbook: str
    labels: dict[str, str] = Field(default_factory=dict)


class Impact(_Model):
    """Share of payments that fail at full severity; drives the ₹-at-risk model."""

    failure_share: float
    start_offset: float
    ramp_minutes: float = 4.0


class Signal(_Model):
    """A machine-checkable discriminator, evaluated against the world a few minutes after the alert."""

    kind: Literal["metric", "log", "trace", "change"]
    service: str | None = None
    metric: str | None = None
    stat: Literal["now", "max", "min"] = "now"
    op: Literal[">", ">=", "<", "<="] | None = None
    value: float | None = None
    contains: str | None = None
    operation: str | None = None
    min_delay_ms: float | None = None
    change_type: ChangeType | None = None
    window_min: float = 15.0
    min_count: int = 1
    relative: bool = False  # divide the stat by the median of the 20 minutes before the window

    @model_validator(mode="after")
    def _complete(self) -> "Signal":
        needed = {
            "metric": ("service", "metric", "op", "value"),
            "log": ("service", "contains"),
            "trace": ("service",),
            "change": (),
        }[self.kind]
        missing = [f for f in needed if getattr(self, f) is None]
        if missing:
            raise ValueError(f"{self.kind} signal needs {missing}")
        return self


class Discriminator(_Model):
    text: str
    signal: Signal
    when: Phase | None = None


class Evidence(_Model):
    tool: str
    service: str

    @model_validator(mode="before")
    @classmethod
    def _from_pair(cls, value: Any) -> Any:
        if isinstance(value, list | tuple):
            return {"tool": value[0], "service": value[1]}
        return value


class RemediationRule(_Model):
    """How the world responds to an action. `targets: null` matches any target.

    Outcome knobs: `relief_minutes` + `depth` for transient relief (restart, then relapse); `depth`
    alone for persistent partial relief; `worsen` (+ `worsen_minutes`, default until resolved) and
    `consequence_minutes` (added to recovery) for harmful actions.
    """

    action: Remediation
    targets: list[str] | None = None
    params: dict[str, str] = Field(default_factory=dict)
    when: Phase | None = None
    recovery_minutes: float = 4.0
    relief_minutes: float | None = None
    depth: float = 1.0
    worsen: float = 1.0
    worsen_minutes: float | None = None
    consequence_minutes: float = 0.0
    note: str = ""

    @model_validator(mode="before")
    @classmethod
    def _target_alias(cls, value: Any) -> Any:
        if isinstance(value, dict) and "target" in value:
            value = dict(value)
            value["targets"] = _as_list(value.pop("target"))
        return value


class StatusUpdate(_Model):
    """External status page entry, published `after_onset_min` after the problem started."""

    after_onset_min: float
    status: Literal["operational", "degraded", "partial_outage", "major_outage"]
    title: str
    message: str = ""


class Archetype(_Model):
    """A validated, instantiated archetype (placeholders already filled)."""

    id: str
    title: str
    category: RootCause
    symptom_class: SymptomClass
    look_alike_group: str | None = None
    culprit_service: str
    culprit_aliases: list[str] = Field(default_factory=list)
    trigger: Literal["deploy", "config", "flag", "external", "infra", "time"]
    alert: AlertSpec
    impact: Impact
    effects: list[Effect]
    discriminators: list[Discriminator]
    relevant_evidence: list[Evidence]
    correct_remediations: list[RemediationRule] = Field(default_factory=list)
    ineffective_remediations: list[RemediationRule] = Field(default_factory=list)
    harmful_remediations: list[RemediationRule] = Field(default_factory=list)
    prevention: list[Safeguard] = Field(default_factory=list)
    status_updates: dict[str, list[StatusUpdate]] = Field(default_factory=dict)


class Scenario(_Model):
    """One incident: an archetype instantiated for a seed, a moment and the world at that moment."""

    incident_id: str
    seed: int
    alert_at: datetime
    spec: Archetype
    values: dict[str, Any]
    phases: frozenset[Phase]
    pods: dict[str, list[str]]
    pod_nodes: dict[str, str]
    pod_ips: dict[str, str]
    extras: list[str] = Field(default_factory=list)

    @property
    def trigger_change_id(self) -> str | None:
        return next((e.id for e in self.spec.effects if isinstance(e, EventEffect) and e.trigger), None)

    @property
    def sample_context(self) -> SampleContext:
        return SampleContext(self.pods, self.pod_nodes, self.pod_ips, self.alert_at)

    @property
    def topology(self) -> Topology:
        return topology_at(self.alert_at)


# loading and instantiation -------------------------------------------------------------------


@cache
def load_archetype(archetype_id: str) -> dict[str, Any]:
    """Raw archetype YAML (placeholders unfilled)."""
    path = SCENARIO_DIR / f"{archetype_id}.yaml"
    return yaml.safe_load(path.read_text())


def archetype_ids() -> list[str]:
    return sorted(p.stem for p in SCENARIO_DIR.glob("*.yaml") if p.stem != "schedule")


def _pods(topology: Topology, seed: int, incident_id: str) -> tuple[dict, dict, dict]:
    rng = py_rng(seed, incident_id, "pods")
    pods: dict[str, list[str]] = {}
    for comp in topology.components.values():
        if comp.kind in (Kind.EXTERNAL, Kind.NODES):
            continue
        if comp.stateful and comp.name != "pgbouncer-ledger":
            pods[comp.name] = [f"{comp.name}-{i}" for i in range(comp.replicas)]
        else:
            rs = replicaset_hash(rng)
            pods[comp.name] = [f"{comp.name}-{rs}-{pod_suffix(rng)}" for _ in range(comp.replicas)]
    pod_nodes, pod_ips = {}, {}
    for name in sorted(p for ps in pods.values() for p in ps):
        node = rng.choice(NODES)
        pod_nodes[name] = node.name
        pod_ips[name] = f"10.42.{node.ip.split('.')[2]}.{rng.randint(2, 250)}"
    return pods, pod_nodes, pod_ips


def _world_values(topology: Topology, culprit: str, alert_at: datetime) -> dict[str, Any]:
    values: dict[str, Any] = {
        "cache": topology.cache,
        "pool_max": topology.pool_max,
        "model_version": model_version_at(alert_at),
        "prev_model_version": model_version_at(alert_at) - 1,
        "az_b_nodes": [n.name for n in NODES if n.zone == "ap-south-1b"],
    }
    for service in CADENCES:
        key = service.replace("-", "_")
        values[f"version_{key}"] = version_at(service, alert_at)
        values[f"prev_version_{key}"] = previous_version(service, alert_at)
    if culprit in CADENCES:
        values["version"] = version_at(culprit, alert_at)
        values["prev_version"] = previous_version(culprit, alert_at)
    return values


def _resolve(match: re.Match[str], values: Mapping[str, Any]) -> Any:
    """`{{name}}` or `{{name + 3}}` / `{{name - 2.5}}`."""
    value = values[match.group(1)]
    if match.group(2):
        delta = float(match.group(3))
        if isinstance(value, int) and delta.is_integer():
            delta = int(delta)
        value = value + delta if match.group(2) == "+" else value - delta
    return value


def _fill(node: Any, values: Mapping[str, Any]) -> Any:
    if isinstance(node, dict):
        return {k: _fill(v, values) for k, v in node.items()}
    if isinstance(node, list):
        return [_fill(v, values) for v in node]
    if isinstance(node, str):
        whole = _PLACEHOLDER.fullmatch(node.strip())
        if whole:
            return _resolve(whole, values)
        return _PLACEHOLDER.sub(lambda m: str(_resolve(m, values)), node)
    return node


def _normalise_effects(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """`- metric_shift: {...}` becomes `{"kind": "metric_shift", ...}`."""
    out = []
    for item in raw:
        ((kind, body),) = item.items()
        out.append({"kind": kind, **body})
    return out


def _applies(item: Any, phases: frozenset[Phase]) -> bool:
    return item.when is None or item.when in phases


def instantiate(
    archetype_id: str,
    *,
    seed: int,
    incident_id: str,
    alert_at: datetime,
    overrides: Mapping[str, Any] | None = None,
    extras: Sequence[str] = (),
) -> Scenario:
    """Build one incident from an archetype: sample variants, fill placeholders, apply phases."""
    raw = dict(load_archetype(archetype_id))
    topology = topology_at(alert_at)
    pods, pod_nodes, pod_ips = _pods(topology, seed, incident_id)
    ctx = SampleContext(pods, pod_nodes, pod_ips, alert_at)

    rng = py_rng(seed, incident_id, "variants")
    variants = {k: VarSpec.model_validate(v) for k, v in raw.pop("variants", {}).items()}
    values = _world_values(topology, raw["culprit_service"], alert_at)
    values |= {name: spec.sample(rng, ctx) for name, spec in variants.items()}
    values |= dict(overrides or {})

    filled = _fill(raw, values)
    filled["effects"] = _normalise_effects(filled["effects"])
    id_rng = py_rng(seed, incident_id, "change-ids")
    for effect in filled["effects"]:
        if effect["kind"] == "event":
            effect["id"] = f"chg-{hex_id(id_rng, 6)}"
    filled.setdefault("category", archetype_id if archetype_id in RootCause else RootCause.NOVEL)
    spec = Archetype.model_validate(filled)

    phases = topology.phases
    spec = spec.model_copy(
        update={
            "effects": [e for e in spec.effects if _applies(e, phases)],
            "discriminators": [d for d in spec.discriminators if _applies(d, phases)],
            "correct_remediations": [r for r in spec.correct_remediations if _applies(r, phases)],
            "ineffective_remediations": [r for r in spec.ineffective_remediations if _applies(r, phases)],
            "harmful_remediations": [r for r in spec.harmful_remediations if _applies(r, phases)],
        }
    )
    return Scenario(
        incident_id=incident_id,
        seed=seed,
        alert_at=alert_at,
        spec=spec,
        values=values,
        phases=phases,
        pods=pods,
        pod_nodes=pod_nodes,
        pod_ips=pod_ips,
        extras=list(extras),
    )
