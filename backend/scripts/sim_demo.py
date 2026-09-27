"""Print a readable investigation of one Gauntlet incident, driven by its discriminators.

An oracle walkthrough: the tool calls an expert would make (alert, recent changes, each
discriminating signal), then the known-good remediation and the recovery. It shows that the
answer is findable from telemetry alone and what the agent-facing tools look like.

    uv run python scripts/sim_demo.py            # incident 12 (post-PgBouncer pool exhaustion)
    uv run python scripts/sim_demo.py --n 7      # any incident number from the schedule
"""

import argparse

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

from dejavu.agent.tools import execute
from dejavu.sim.clock import fmt_hm
from dejavu.sim.schedule import entry_for, gauntlet
from dejavu.sim.world import IncidentWorld

console = Console()


def _call(world: IncidentWorld, tool: str, args: dict) -> None:
    at = fmt_hm(world.clock.now)
    result = execute(world, tool, args)
    title = f"[bold]{tool}[/] {args or ''}  [dim]{at} IST, +{result.sim_minutes:g} sim-min[/]"
    console.print(
        Panel(
            escape(result.output),
            title=title,
            title_align="left",
            border_style="cyan" if result.ok else "red",
        )
    )


def _plan(world: IncidentWorld) -> list[tuple[str, dict]]:
    calls: list[tuple[str, dict]] = [("get_alert", {}), ("list_changes", {"window_hours": 6})]
    for d in world.scenario.spec.discriminators:
        s = d.signal
        if s.kind == "metric":
            calls.append(("query_metrics", {"service": s.service, "metric": s.metric, "window_min": 60}))
        elif s.kind == "log":
            calls.append(("search_logs", {"service": s.service, "query": s.contains, "window_min": 30}))
        elif s.kind == "trace":
            calls.append(("get_traces", {"service": s.service, "operation": s.operation}))
    unique: dict[tuple, tuple[str, dict]] = {}
    for tool, args in calls:
        unique.setdefault((tool, tuple(sorted(args.items()))), (tool, args))
    return list(unique.values())


def main(n: int) -> None:
    scenario = next(s for s in gauntlet() if (e := entry_for(s)) and e.n == n)
    world = IncidentWorld.open(scenario)
    spec = scenario.spec
    console.rule(
        f"[bold]{scenario.incident_id}[/]  alert {fmt_hm(scenario.alert_at)} IST, {scenario.alert_at:%a %d %b %Y}"
    )
    for tool, args in _plan(world):
        _call(world, tool, args)

    if spec.correct_remediations:
        rule = spec.correct_remediations[0]
        target = (rule.targets or [spec.culprit_service])[0]
        _call(world, "run_remediation", {"action": rule.action.value, "target": target})
        world.clock.advance(6)
        alert = spec.alert
        _call(
            world,
            "query_metrics",
            {"service": alert.metric_service, "metric": alert.metric, "window_min": 30},
        )
    else:
        _call(world, "page_human", {"team": "Messaging", "message": "vendor-side problem, needs a human"})

    resolved = world.resolved_at_min
    until = resolved if resolved is not None else world.now_min
    console.rule("ground truth (never visible to the agent)")
    console.print(
        f"root cause: [bold]{spec.category.value}[/] in [bold]{spec.culprit_service}[/] (trigger change {scenario.trigger_change_id or 'none'})"
    )
    console.print(f"schedule note: {entry_for(scenario).tests or '-'}")
    console.print(
        f"resolved at: {'+' + format(resolved, 'g') + ' min' if resolved is not None else 'not resolved'}"
    )
    console.print(f"INR at risk until then: ₹{world.inr_at_risk(until):,.0f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--n", type=int, default=12, help="Gauntlet incident number (1-24)")
    main(parser.parse_args().n)
