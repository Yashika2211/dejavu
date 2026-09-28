"""Change events: deploys, config and flag changes, Helm values, migrations.

Three sources: the scenario's own events (the trigger and any archetype red herrings), the M1/M2
migrations, and 1-3 unrelated changes per day. Background changes are seeded by date rather than
by incident, so incidents whose windows overlap see the same deploys.
"""

from datetime import datetime, time, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict

from dejavu.sim.clock import IST
from dejavu.sim.migrations import MIGRATIONS
from dejavu.sim.releases import CADENCES, pr_number, previous_version, version_at
from dejavu.sim.rng import hex_id, py_rng
from dejavu.sim.scenario import ChangeType, EventEffect, Scenario
from dejavu.sim.topology import TEAMS, topology_at

LOOKBACK_DAYS = 3
BACKGROUND_SEED = 7_1717  # background changes are a property of the calendar, not of an incident


class ChangeEvent(BaseModel):
    """One change as the change log records it."""

    model_config = ConfigDict(frozen=True)

    id: str
    at: datetime
    type: ChangeType
    service: str
    author: str
    summary: str
    details: dict[str, Any] = {}


_DEPLOYS: dict[str, list[tuple[str, list[str], str]]] = {
    "checkout-api": [
        (
            "Add idempotency-key header to refund API",
            ["src/routes/refunds.ts", "src/middleware/idempotency.ts"],
            "+88 -12",
        ),
        ("Upgrade pino to 9.4.0", ["package.json", "pnpm-lock.yaml"], "+14 -14"),
        ("Copy change on UPI intent screen (i18n)", ["locales/en.json", "locales/hi.json"], "+6 -6"),
    ],
    "payments-svc": [
        (
            "Verify paynova webhook signatures (v2)",
            ["psp/paynova/webhook.go", "psp/paynova/webhook_test.go"],
            "+120 -31",
        ),
        ("Refactor merchant config loader", ["config/merchant.go"], "+64 -58"),
    ],
    "auth-svc": [
        ("Add OTP channel label to metrics", ["otp/metrics.go"], "+9 -2"),
        ("Bump golang-jwt to v5.2.1", ["go.mod", "go.sum"], "+2 -2"),
    ],
    "ledger-svc": [
        (
            "Add read-only reconciliation report endpoint",
            ["ReconciliationController.java", "ReconciliationService.java"],
            "+141 -3",
        ),
        ("Upgrade Spring Boot 3.3.3 -> 3.3.4", ["build.gradle.kts"], "+1 -1"),
    ],
    "fraud-scorer": [
        ("Log a feature-importance sample at DEBUG", ["fraud_scorer/explain.py"], "+22 -1"),
        ("Pin lightgbm 4.5.0", ["pyproject.toml", "uv.lock"], "+3 -3"),
    ],
    "notifications-worker": [
        ("Bump kotlin-logging to 7.0.0", ["build.gradle.kts"], "+1 -1"),
        ("Add Hindi OTP template", ["templates/otp_hi.hbs", "OtpTemplateRegistry.kt"], "+37 -0"),
    ],
}

_OTHER: list[tuple[ChangeType, str, str, dict[str, Any]]] = [
    (
        ChangeType.FLAG,
        "checkout-api",
        "flag checkout.upi_intent_v2 rollout 10% -> 25%",
        {"flag": "checkout.upi_intent_v2", "from": "10%", "to": "25%"},
    ),
    (
        ChangeType.FLAG,
        "checkout-api",
        "flag checkout.show_emi_options enabled for 5% of users",
        {"flag": "checkout.show_emi_options", "from": "off", "to": "5%"},
    ),
    (
        ChangeType.CONFIG,
        "edge-gateway",
        "route /v1/refunds/{id}: timeout 3s, retries 1",
        {"key": "routes./v1/refunds.timeout", "from": "unset", "to": "3s"},
    ),
    (
        ChangeType.HELM,
        "fraud-scorer",
        "HPA maxReplicas 6 -> 8",
        {"key": "autoscaling.maxReplicas", "from": 6, "to": 8},
    ),
    (
        ChangeType.CONFIG,
        "notifications-worker",
        "smsbridge sender id KSTLPY -> KSTPAY",
        {"key": "smsbridge.sender_id", "from": "KSTLPY", "to": "KSTPAY"},
    ),
]


def _team_member(service: str, at: datetime, rng: Any) -> str:
    comp = topology_at(at).get(service)
    team = TEAMS[comp.team] if comp and comp.team else TEAMS["Platform"]
    return rng.choice(team.members)


def _background_day(day: datetime, avoid: set[str]) -> list[ChangeEvent]:
    """Unrelated changes on one calendar day (weekends are quieter)."""
    rng = py_rng(BACKGROUND_SEED, day.date().isoformat())
    count = rng.choice((0, 1)) if day.weekday() >= 5 else rng.choice((1, 2, 2, 3))
    events: list[ChangeEvent] = []
    used: set[str] = set()
    for _ in range(count):
        at = day + timedelta(minutes=rng.randint(10 * 60, 19 * 60 + 30))
        if rng.random() < 0.65:
            service = rng.choice(sorted(set(_DEPLOYS) - avoid - used) or ["checkout-api"])
            if service in avoid or service in used:
                continue
            used.add(service)
            title, files, lines = rng.choice(_DEPLOYS[service])
            new, old = version_at(service, at), previous_version(service, at)
            events.append(
                ChangeEvent(
                    id=f"chg-{hex_id(rng, 6)}",
                    at=at,
                    type=ChangeType.DEPLOY,
                    service=service,
                    author=_team_member(service, at, rng),
                    summary=f"{service} {old} -> {new}",
                    details={
                        "version": new,
                        "prev_version": old,
                        "commit": hex_id(rng, 7),
                        "pr": pr_number(service, at, salt=rng.randint(0, 2)),
                        "pr_title": title,
                        "files": files,
                        "lines": lines,
                    },
                )
            )
        else:
            kind, service, summary, details = rng.choice(_OTHER)
            if service in avoid:
                continue
            events.append(
                ChangeEvent(
                    id=f"chg-{hex_id(rng, 6)}",
                    at=at,
                    type=kind,
                    service=service,
                    author=_team_member(service, at, rng),
                    summary=summary,
                    details=details,
                )
            )
    return events


def _scenario_event(e: EventEffect, scenario: Scenario) -> ChangeEvent:
    rng = py_rng(scenario.seed, scenario.incident_id, "event", e.id)
    details = dict(e.details)
    if e.type == ChangeType.DEPLOY:
        details.setdefault("commit", hex_id(rng, 7))
        details.setdefault("pr", pr_number(e.service, scenario.alert_at + timedelta(minutes=e.at_offset)))
    return ChangeEvent(
        id=e.id or f"chg-{hex_id(rng, 6)}",
        at=scenario.alert_at + timedelta(minutes=e.at_offset),
        type=e.type,
        service=e.service,
        author=e.author,
        summary=e.summary,
        details=details,
    )


def generate_events(scenario: Scenario) -> list[ChangeEvent]:
    """Every change in the lookback window before the alert (and the window after it)."""
    alert = scenario.alert_at
    start = alert - timedelta(days=LOOKBACK_DAYS)
    own = [_scenario_event(e, scenario) for e in scenario.spec.effects if isinstance(e, EventEffect)]
    avoid = {scenario.spec.culprit_service} | {e.service for e in own}
    avoid &= set(CADENCES) | {"edge-gateway"}

    events = list(own)
    day = datetime.combine(start.astimezone(IST).date(), time(0), IST)
    while day <= alert + timedelta(hours=2):
        events += [e for e in _background_day(day, avoid) if start <= e.at <= alert + timedelta(hours=2)]
        day += timedelta(days=1)
    for m in MIGRATIONS:
        if start <= m.at <= alert + timedelta(hours=2):
            events.append(
                ChangeEvent(
                    id=f"chg-{m.slug}",
                    at=m.at,
                    type=ChangeType.MIGRATION,
                    service=m.service,
                    author=m.author,
                    summary=m.summary,
                    details={"migration": m.id},
                )
            )
    return sorted(events, key=lambda e: (e.at, e.id))
