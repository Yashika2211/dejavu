"""Agent-facing tools over an IncidentWorld (spec 4.6).

Each tool costs simulated minutes and returns compact text bounded to ~700 tokens: summaries
(baseline vs now, change points, sparklines, log templates, critical paths), never raw dumps.
The strategy-specific `recall_memory` and the hypothesis / diagnosis tools live with the loop.
"""

import difflib
import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field, field_validator

from dejavu.sim.analysis import change_point, sparkline
from dejavu.sim.clock import fmt_day_hm, fmt_hm, fmt_hms
from dejavu.sim.generators.alerts import fmt_value
from dejavu.sim.generators.metrics import NO_NODE, UNITS
from dejavu.sim.logmine import mine
from dejavu.sim.remediation import OutcomeKind, requires_approval
from dejavu.sim.runbooks import all_runbooks, find
from dejavu.sim.scenario import ChangeType, Level
from dejavu.sim.topology import NODES, TEAMS, Kind
from dejavu.sim.world import IncidentWorld
from dejavu.taxonomy import Remediation
from dejavu.tokens import clip, fit_blocks

MAX_TOKENS = 700


class ToolResult(BaseModel):
    tool: str
    output: str
    sim_minutes: float
    ok: bool = True
    ends_run: bool = False
    clock_advanced: bool = False
    data: dict[str, Any] = Field(default_factory=dict)


class ToolError(Exception):
    """Bad arguments the model can fix; the message goes back as the tool result."""


# argument models ------------------------------------------------------------------------------


class NoArgs(BaseModel):
    pass


class TopologyArgs(BaseModel):
    service: str | None = Field(None, description="Component name; omit for the whole topology")


class MetricsArgs(BaseModel):
    service: str = Field(description="Component, e.g. ledger-svc, postgres-ledger, acquirerx, nodes")
    metric: str = Field(description="Metric name, e.g. latency_p99_ms, db_pool_pending, pg_cpu_pct")
    window_min: int = Field(60, ge=5, le=180, description="Minutes back from now")


class LogsArgs(BaseModel):
    service: str
    query: str | None = Field(None, description="Case-insensitive substring to match")
    level: Literal["DEBUG", "INFO", "WARN", "ERROR"] | None = Field(None, description="Minimum level")
    window_min: int = Field(30, ge=1, le=180)
    limit: int = Field(8, ge=1, le=15, description="Maximum templates to show")


class TracesArgs(BaseModel):
    service: str
    operation: str | None = None
    window_min: int = Field(15, ge=1, le=60)
    slowest: int = Field(5, ge=1, le=10)


class ChangesArgs(BaseModel):
    window_hours: float = Field(6, gt=0, le=72)
    service: str | None = None


class RunbookArgs(BaseModel):
    topic: str = Field(description="What you need, e.g. 'ledger connection pool' or a runbook id")


class DependencyArgs(BaseModel):
    name: str = Field(description="External provider, e.g. acquirerx, paynova, smsbridge")


class RemediationArgs(BaseModel):
    action: Remediation
    target: str = Field(description="Component, or a node name for node_drain")
    params: dict[str, str] = Field(
        default_factory=dict, description="e.g. {'setting': 'default_pool_size', 'value': '40'}"
    )

    @field_validator("params", mode="before")
    @classmethod
    def _stringify(cls, value: Any) -> Any:
        return {str(k): str(v) for k, v in value.items()} if isinstance(value, dict) else value


class PageArgs(BaseModel):
    team: str = Field(description="Team to page, e.g. Core Ledger, Payments, Platform")
    message: str


# helpers -----------------------------------------------------------------------------------------


def resolve(world: IncidentWorld, name: str) -> str:
    """Exact component name, or a unique partial match; otherwise a helpful error."""
    wanted = name.strip().lower()
    names = world.topology.names()
    if wanted in names:
        return wanted
    if wanted in {n.name for n in NODES}:
        return "nodes"
    for candidates in ([n for n in names if n.startswith(wanted)], [n for n in names if wanted in n]):
        if wanted and len(candidates) == 1:
            return candidates[0]
    raise ToolError(f"unknown component {name!r}. Components: {', '.join(names)}")


def _now_hm(world: IncidentWorld) -> str:
    return fmt_hm(world.clock.at(world.now_min))


def _hm_at(world: IncidentWorld, minute: float) -> str:
    return fmt_hm(world.clock.at(minute))


def _num(value: float, unit: str) -> str:
    """Numbers inside a metric summary: keep short units, drop long ones (they are in the header)."""
    return fmt_value(value, unit if unit in ("ms", "%", "bytes", "ratio") else "")


def _series_summary(
    world: IncidentWorld, minutes: np.ndarray, values: np.ndarray, window: int, unit: str
) -> list[str]:
    now = world.now_min
    in_win = minutes > now - window
    win_m, win_v = minutes[in_win], values[in_win]
    before = (minutes <= now - window) & (minutes > now - window - 60)
    base_v = values[before] if before.any() else values[: max(5, len(values) // 10)]
    lines = [
        f"now {_num(float(win_v[-3:].mean()), unit)} | window min {_num(float(win_v.min()), unit)}"
        f" p50 {_num(float(np.median(win_v)), unit)} max {_num(float(win_v.max()), unit)}"
        f" | baseline (hour before window) p50 {_num(float(np.median(base_v)), unit)}",
    ]
    cp = change_point(win_v)
    if cp:
        lines.append(
            f"change point {_hm_at(world, float(win_m[cp.index]))} IST: {_num(cp.before, unit)} -> {_num(cp.after, unit)}"
        )
    else:
        lines.append("no significant change point in window")
    lines.append(f"{sparkline(win_v)}  ({window / 24:g}m buckets, oldest to newest)")
    return lines


# tools ---------------------------------------------------------------------------------------------


def get_alert(world: IncidentWorld, _: NoArgs) -> str:
    return json.dumps(world.store.alert, indent=1)


def get_topology(world: IncidentWorld, a: TopologyArgs) -> str:
    topo = world.topology
    if a.service is None:
        lines = [f"Kestrel Pay prod-aps1 topology ({len(topo.components)} components):"]
        for c in topo.components.values():
            owner = f"{c.team} ({c.owner})" if c.team else "external"
            deps = f" -> {', '.join(c.depends_on)}" if c.depends_on else ""
            lines.append(f"- {c.name} [{c.kind}] {owner}{deps}")
        return "\n".join(lines)
    c = topo.get(resolve(world, a.service))
    assert c is not None
    lines = [
        f"{c.name} [{c.kind}] {c.stack}",
        f"team: {c.team or 'external provider'}" + (f", owner {c.owner}" if c.owner else ""),
        f"depends on: {', '.join(c.depends_on) or 'nothing'}",
        f"used by: {', '.join(topo.dependents(c.name)) or 'nothing'}",
    ]
    if c.kind not in (Kind.EXTERNAL, Kind.NODES):
        lines.append(
            f"replicas: {c.replicas}" + (" (stateful; changes need owner approval)" if c.stateful else "")
        )
    if c.slo:
        lines.append(f"SLO: {c.slo}")
    lines += [f"note: {n}" for n in c.notes]
    lines.append(f"metrics: {', '.join(world.store.metrics_of(c.name))}")
    return "\n".join(lines)


def query_metrics(world: IncidentWorld, a: MetricsArgs) -> str:
    comp = resolve(world, a.service)
    available = world.store.metrics_of(comp)
    if a.metric not in available:
        close = difflib.get_close_matches(a.metric, available, n=3)
        hint = f" Did you mean {', '.join(close)}?" if close else ""
        raise ToolError(f"{comp} has no metric {a.metric!r}.{hint} Available: {', '.join(available)}")
    unit = UNITS[a.metric]
    series = world.metric(comp, a.metric)
    start, end = _hm_at(world, world.now_min - a.window_min), _now_hm(world)
    header = f"{comp} {a.metric} [{unit}], {start}-{end} IST ({a.window_min}m)"
    if list(series) == [NO_NODE]:
        s = series[NO_NODE]
        return "\n".join([header, *_series_summary(world, s.minutes, s.values, a.window_min, unit)])
    blocks = []
    for node, s in series.items():
        zone = next(n.zone for n in NODES if n.name == node)
        win = s.values[s.minutes > world.now_min - a.window_min]
        blocks.append(
            f"{node} ({zone}): now {_num(float(win[-3:].mean()), unit)}, window min {_num(float(win.min()), unit)}"
            f" max {_num(float(win.max()), unit)}  {sparkline(win, 12)}"
        )
    return "\n".join([header, *blocks])


def search_logs(world: IncidentWorld, a: LogsArgs) -> str:
    comp = resolve(world, a.service)
    component = world.topology.get(comp)
    if component is not None and component.kind == Kind.EXTERNAL:
        return (
            f"{comp} is an external provider; there are no logs of its own. Search the logs of the service "
            f"that calls it (see get_topology), or use check_dependency."
        )
    levels = [lvl.value for lvl in Level if lvl.rank >= Level(a.level).rank] if a.level else None
    rows = world.logs(comp, a.window_min, levels=levels, contains=a.query)
    templates = mine([(r.offset_s, r.level, r.message, r.line) for r in rows])
    start, end = _hm_at(world, world.now_min - a.window_min), _now_hm(world)
    filters = "".join([f", level>={a.level}" if a.level else "", f", query {a.query!r}" if a.query else ""])
    header = f"{comp} logs {start}-{end} IST ({a.window_min}m{filters}): {len(rows):,} lines, {len(templates)} templates"
    if not templates:
        return header + "\n(no matching lines)"
    blocks = []
    for i, t in enumerate(templates[: a.limit], 1):
        first, last = world.clock.at(t.first_s / 60), world.clock.at(t.last_s / 60)
        blocks.append(
            f"[{i}] {t.count:,}x {t.level} first {fmt_hms(first)} last {fmt_hms(last)}\n"
            f"    {t.pattern[:170]}\n    e.g. {t.example[:230]}"
        )
    return fit_blocks(header, blocks, max_tokens=MAX_TOKENS, more="templates")


def _self_times(spans: list[dict[str, Any]]) -> dict[str, float]:
    child_total: dict[str, float] = defaultdict(float)
    for s in spans:
        if s["parent_id"]:
            child_total[s["parent_id"]] += s["duration_ms"]
    return {s["span_id"]: max(s["duration_ms"] - child_total[s["span_id"]], 0.0) for s in spans}


def get_traces(world: IncidentWorld, a: TracesArgs) -> str:
    comp = resolve(world, a.service)
    all_spans = world.spans(comp, a.window_min + 30, a.operation)
    by_trace: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in all_spans:
        by_trace[s["trace_id"]].append(s)
    cutoff = (world.now_min - a.window_min) * 60_000
    roots = {tid: next(s for s in spans if not s["parent_id"]) for tid, spans in by_trace.items()}
    recent = {tid: r for tid, r in roots.items() if r["start_offset_ms"] >= cutoff}
    earlier = [r["duration_ms"] for r in roots.values() if r["start_offset_ms"] < cutoff]
    what = f"{comp}" + (f" {a.operation}" if a.operation else "")
    head = f"traces touching {what}, {_hm_at(world, world.now_min - a.window_min)}-{_now_hm(world)} IST ({a.window_min}m): {len(recent)} traces"
    if not recent:
        return head + "\n(no traces in window)"
    durations = np.array([r["duration_ms"] for r in recent.values()])
    slowest = sorted(recent, key=lambda t: -recent[t]["duration_ms"])[: a.slowest]
    lines = [
        head,
        f"root duration p50 {np.median(durations):,.0f} ms, p99 {np.percentile(durations, 99):,.0f} ms"
        + (f" | 30m before window p50 {np.median(earlier):,.0f} ms" if earlier else ""),
    ]
    shares: dict[tuple[str, str], float] = defaultdict(float)
    total_root = 0.0
    errors: dict[str, int] = defaultdict(int)
    for tid in slowest:
        spans = by_trace[tid]
        selfs = _self_times(spans)
        total_root += recent[tid]["duration_ms"]
        for s in spans:
            shares[(s["component"], s["operation"])] += selfs[s["span_id"]]
        leaf_errors = [s for s in spans if s["error"] and not s["error"].startswith("upstream")]
        for s in leaf_errors[:1]:
            errors[f"{s['component']} {s['operation']}: {s['error'][:90]}"] += 1
    lines.append(f"self-time share across the {len(slowest)} slowest:")
    for (c, op), ms in sorted(shares.items(), key=lambda kv: -kv[1])[:6]:
        lines.append(f"  {ms / total_root:4.0%}  {c}  {op}  (avg {ms / len(slowest):,.0f} ms)")
    worst = by_trace[slowest[0]]
    root = recent[slowest[0]]
    lines.append(f"slowest trace {slowest[0][:12]}… {root['duration_ms']:,.0f} ms:")
    depth = {root["span_id"]: 0}
    for s in worst:
        if s["parent_id"]:
            depth[s["span_id"]] = depth.get(s["parent_id"], 0) + 1
        if s["duration_ms"] >= 0.05 * root["duration_ms"]:
            err = (
                f"  [error: {s['error'][:80]}]"
                if s["error"] and not s["error"].startswith("upstream")
                else ""
            )
            lines.append(
                f"  {'  ' * depth[s['span_id']]}{s['component']} {s['operation']} {s['duration_ms']:,.0f} ms{err}"
            )
    if errors:
        lines.append("errors in slowest traces: " + "; ".join(f"{n}x {e}" for e, n in errors.items()))
    return clip("\n".join(lines), MAX_TOKENS)


def list_changes(world: IncidentWorld, a: ChangesArgs) -> str:
    service = resolve(world, a.service) if a.service else None
    events = list(reversed(world.changes(a.window_hours, service)))
    start = world.clock.at(world.now_min - a.window_hours * 60)
    scope = f" for {service}" if service else ""
    header = (
        f"changes{scope} {fmt_day_hm(start)} - {fmt_day_hm(world.clock.at(world.now_min))} IST "
        f"({a.window_hours:g}h), newest first: {len(events)} found"
    )
    if not events:
        return header
    blocks = []
    for e in events:
        d = e.details
        block = [f"{fmt_day_hm(e.at)} {e.id} {e.type.value} {e.service}: {e.summary} (by {e.author})"]
        if "pr" in d:
            block.append(
                f'    PR #{d["pr"]} "{d.get("pr_title", "")}" commit {d.get("commit", "?")} ({d.get("lines", "?")})'
            )
        if d.get("diff"):
            block.append(f"    diff: {d['diff']}")
        if d.get("files"):
            block.append(f"    files: {', '.join(d['files'])}")
        blocks.append("\n".join(block))
    return fit_blocks(header, blocks, max_tokens=MAX_TOKENS, more="older changes")


def get_runbook(world: IncidentWorld, a: RunbookArgs) -> str:
    rb = find(a.topic)
    if rb is None:
        available = "; ".join(f"{r.id} ({r.title})" for r in all_runbooks())
        return f"no runbook matches {a.topic!r}. Runbooks: {available}"
    return clip(
        f"{rb.id}: {rb.title} (last edited {rb.last_edited:%d %b %Y} by {rb.author})\n\n{rb.body}", MAX_TOKENS
    )


def check_dependency(world: IncidentWorld, a: DependencyArgs) -> str:
    comp = resolve(world, a.name)
    page = world.status_page(comp)
    if page is None:
        return f"{comp} is internal and has no status page; use query_metrics and search_logs."
    posted = f" (posted {_hm_at(world, page.posted_at_min)} IST)" if page.posted_at_min is not None else ""
    body = f"\n{page.message}" if page.message else ""
    return f"{page.name}, checked {_now_hm(world)} IST\nstatus: {page.title}{posted}{body}"


def _rollback_detail(world: IncidentWorld, target: str) -> str:
    rollbackable = {ChangeType.DEPLOY, ChangeType.MODEL_RELEASE, ChangeType.HELM, ChangeType.SCHEMA_MIGRATION}
    recent = [e for e in world.changes(24, target) if e.type in rollbackable]
    if not recent:
        return (
            f"no deploy, model release or Helm change for {target} in the last 24h; nothing was rolled back"
        )
    last = recent[-1]
    d = last.details
    if "prev_version" in d:
        return f"{target} rolled back {d.get('version')} -> {d['prev_version']} (reverting {last.id})"
    return f"reverted {last.id}: {last.summary}"


def run_remediation(world: IncidentWorld, a: RemediationArgs) -> ToolResult:
    target = a.target.strip()
    if a.action != Remediation.NODE_DRAIN:
        target = resolve(world, target)
    start = world.clock.elapsed_min
    iv = world.apply(a.action, target, a.params)
    minutes = iv.completes_at - start
    world.clock.advance(minutes)
    if iv.kind == OutcomeKind.INVALID:
        nodes = ", ".join(n.name for n in NODES)
        return ToolResult(
            tool="run_remediation",
            ok=False,
            sim_minutes=minutes,
            clock_advanced=True,
            output=f"cannot {a.action.value} {a.target!r}: no such target. Components: {', '.join(world.topology.names())}; nodes: {nodes}",
        )
    comp = world.topology.get(target)
    lines = [
        f"{a.action.value} {target}{' ' + json.dumps(a.params) if a.params else ''}: started {_hm_at(world, start)} IST,"
        f" completed {_hm_at(world, iv.completes_at)} IST ({minutes:g} min)"
    ]
    if requires_approval(world.topology, target) and comp and comp.team:
        lines.append(f"stateful system: approved by {TEAMS[comp.team].lead} ({comp.team}) before execution")
    if a.action == Remediation.ROLLBACK:
        lines.append(_rollback_detail(world, target))
    alert = world.scenario.spec.alert
    value = world.metric_at(alert.metric_service, alert.metric, world.now_min)
    lines.append(
        f"{alert.metric_service} {alert.metric} now {fmt_value(value, UNITS[alert.metric])} "
        f"(alert threshold {fmt_value(alert.threshold, UNITS[alert.metric])})"
    )
    return ToolResult(
        tool="run_remediation",
        output="\n".join(lines),
        sim_minutes=minutes,
        clock_advanced=True,
        data={"action": a.action.value, "target": target, "outcome": iv.kind.value},
    )


def page_human(world: IncidentWorld, a: PageArgs) -> ToolResult:
    team = next((t for t in TEAMS.values() if t.name.lower() == a.team.strip().lower()), None)
    who = f"{team.name} on-call ({team.lead})" if team else f"{a.team} on-call"
    return ToolResult(
        tool="page_human",
        output=f"Paged {who}: {a.message[:200]}\nThe autonomous investigation ends here; a human takes over.",
        sim_minutes=10,
        ends_run=True,
    )


# registry and execution ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    minutes: float
    fn: Callable[[IncidentWorld, Any], str | ToolResult]


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in (
        Tool("get_alert", "The alert payload that paged you.", NoArgs, 0.5, get_alert),
        Tool(
            "get_topology",
            "Dependencies, owners, SLOs and notes for one component, or the whole system.",
            TopologyArgs,
            0.5,
            get_topology,
        ),
        Tool(
            "query_metrics",
            "Summary of one metric over a window: baseline vs now, change point, min/p50/max, sparkline.",
            MetricsArgs,
            1.5,
            query_metrics,
        ),
        Tool(
            "search_logs",
            "Log templates with counts, first/last seen and one example each, for one component.",
            LogsArgs,
            3,
            search_logs,
        ),
        Tool(
            "get_traces",
            "Critical-path breakdown of the slowest traces touching a component.",
            TracesArgs,
            2,
            get_traces,
        ),
        Tool(
            "list_changes",
            "Deploys, config, flags, Helm changes and migrations in a window, with diff summaries.",
            ChangesArgs,
            1,
            list_changes,
        ),
        Tool(
            "get_runbook",
            "The team's runbook for a topic. Runbooks can be out of date.",
            RunbookArgs,
            2,
            get_runbook,
        ),
        Tool(
            "check_dependency",
            "An external provider's public status page.",
            DependencyArgs,
            1,
            check_dependency,
        ),
        Tool(
            "run_remediation",
            "Apply a remediation action; takes simulated minutes depending on the action.",
            RemediationArgs,
            0,
            run_remediation,
        ),
        Tool(
            "page_human",
            "Escalate to a team's on-call human; ends the autonomous run.",
            PageArgs,
            10,
            page_human,
        ),
    )
}


def execute(world: IncidentWorld, name: str, raw_args: dict[str, Any]) -> ToolResult:
    """Validate arguments, run a tool, bound its output and advance the simulated clock."""
    tool = TOOLS.get(name)
    if tool is None:
        return ToolResult(
            tool=name, ok=False, sim_minutes=0.0, output=f"unknown tool {name!r}; tools: {', '.join(TOOLS)}"
        )
    try:
        args = tool.args.model_validate(raw_args)
        out = tool.fn(world, args)
    except ToolError as exc:
        world.clock.advance(0.25)
        return ToolResult(tool=name, ok=False, sim_minutes=0.25, clock_advanced=True, output=str(exc))
    result = (
        out if isinstance(out, ToolResult) else ToolResult(tool=name, output=out, sim_minutes=tool.minutes)
    )
    result = result.model_copy(update={"output": clip(result.output, MAX_TOKENS)})
    if not result.clock_advanced:
        world.clock.advance(result.sim_minutes)
    return result
