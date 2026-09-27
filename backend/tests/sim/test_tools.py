"""Agent tools: bounded, never peek into the future, and fail helpfully."""

import pytest
from conftest import POST_M2, PRE, scenario_for

from dejavu.agent.tools import MAX_TOKENS, TOOLS, execute
from dejavu.sim.scenario import archetype_ids
from dejavu.tokens import count_tokens


def _calls(scenario) -> list[tuple[str, dict]]:
    spec = scenario.spec
    services = list(
        dict.fromkeys([spec.culprit_service, spec.alert.service, spec.alert.metric_service, "ledger-svc"])
    )
    calls: list[tuple[str, dict]] = [
        ("get_alert", {}),
        ("get_topology", {}),
        ("list_changes", {"window_hours": 72}),
    ]
    for service in services:
        calls += [
            ("get_topology", {"service": service}),
            ("search_logs", {"service": service, "window_min": 180, "limit": 15}),
            ("search_logs", {"service": service, "level": "WARN"}),
            ("get_traces", {"service": service, "window_min": 60, "slowest": 10}),
            ("check_dependency", {"name": service}),
        ]
    calls += [("query_metrics", {"service": "nodes", "metric": "node_clock_offset_ms", "window_min": 180})]
    calls += [("get_runbook", {"topic": spec.culprit_service})]
    return calls


@pytest.mark.parametrize("archetype", archetype_ids())
@pytest.mark.parametrize("when", [PRE, POST_M2])
def test_every_tool_output_is_token_bounded(archetype, when, open_world) -> None:
    world = open_world(scenario_for(archetype, when))
    world.clock.advance(8)
    for name, args in _calls(world.scenario):
        output = execute(world, name, args).output
        assert count_tokens(output) <= MAX_TOKENS, (name, args, count_tokens(output))


def test_tools_never_show_data_after_now(open_world) -> None:
    world = open_world(scenario_for("db_pool_exhaustion", PRE))
    world.clock.advance(3)
    visible = world.metric("ledger-svc", "db_pool_pending")[""]
    assert visible.minutes.max() <= 3
    assert all(line.offset_s <= 3 * 60 for line in world.logs("ledger-svc", 30))
    assert all(s["start_offset_ms"] <= 3 * 60_000 for s in world.spans("ledger-svc", 15))
    assert all(c.at <= world.clock.now for c in world.changes(72))


def test_each_tool_advances_the_simulated_clock_by_its_cost(open_world) -> None:
    world = open_world(scenario_for("psp_rate_limit", PRE))
    for name, args in [
        ("get_alert", {}),
        ("query_metrics", {"service": "acquirerx", "metric": "psp_http_429_rate"}),
        ("search_logs", {"service": "payments-svc"}),
        ("get_traces", {"service": "payments-svc"}),
        ("list_changes", {}),
        ("get_runbook", {"topic": "psp"}),
        ("check_dependency", {"name": "acquirerx"}),
    ]:
        before = world.clock.elapsed_min
        result = execute(world, name, args)
        assert world.clock.elapsed_min - before == pytest.approx(TOOLS[name].minutes)
        assert result.sim_minutes == TOOLS[name].minutes


def test_bad_arguments_come_back_as_messages_not_exceptions(open_world) -> None:
    world = open_world(scenario_for("cert_expiry", PRE))
    cases = [
        ("query_metrics", {"service": "ledger-svc"}, "metric"),
        ("query_metrics", {"service": "postgres-ledger", "metric": "pg_cpu"}, "pg_cpu_pct"),
        ("search_logs", {"service": "mongodb"}, "Components"),
        ("search_logs", {"service": "acquirerx"}, "external provider"),
        ("run_remediation", {"action": "reboot", "target": "auth-svc"}, "Input should be"),
        ("no_such_tool", {}, "unknown tool"),
    ]
    for name, args, hint in cases:
        result = execute(world, name, args)
        assert not result.ok or "external provider" in result.output
        assert hint in result.output


def test_partial_names_resolve_when_unambiguous(open_world) -> None:
    world = open_world(scenario_for("cert_expiry", PRE))
    assert execute(world, "get_topology", {"service": "ledger"}).output.startswith("ledger-svc")
    assert execute(world, "get_topology", {"service": "ip-10-42-3-17"}).output.startswith("nodes")


def test_runbooks_are_stale_on_purpose(open_world) -> None:
    world = open_world(scenario_for("db_pool_exhaustion", POST_M2))
    ledger = execute(world, "get_runbook", {"topic": "ledger connection pool"}).output
    assert "from 20 to 40" in ledger  # predates the PgBouncer migration
    cache = execute(world, "get_runbook", {"topic": "cache failover"}).output
    assert "redis-cli -h redis-cache" in cache  # predates the Valkey migration
    assert "valkey-cache" in execute(world, "get_topology", {}).output


def test_status_page_lags_reality(open_world) -> None:
    world = open_world(scenario_for("psp_rate_limit", PRE))
    assert "All Systems Operational" in execute(world, "check_dependency", {"name": "acquirerx"}).output
    world.clock.advance(25)
    assert "Degraded" in execute(world, "check_dependency", {"name": "acquirerx"}).output


def test_rollback_reports_what_it_reverted(open_world) -> None:
    world = open_world(scenario_for("db_pool_exhaustion", PRE))
    output = execute(world, "run_remediation", {"action": "rollback", "target": "ledger-svc"}).output
    assert "rolled back" in output
    world = open_world(scenario_for("psp_rate_limit", PRE))
    output = execute(world, "run_remediation", {"action": "rollback", "target": "payments-svc"}).output
    assert "nothing was rolled back" in output


def test_actions_on_stateful_systems_record_owner_approval(open_world) -> None:
    world = open_world(scenario_for("disk_full_wal", PRE))
    output = execute(world, "run_remediation", {"action": "wal_cleanup", "target": "postgres-ledger"}).output
    assert "approved by Rohan Mehta" in output
