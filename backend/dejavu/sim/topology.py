"""Kestrel Pay's production topology (spec 4.1), as it stood at a given moment.

Migrations change the topology: after M1 ledger-svc reaches Postgres through pgbouncer-ledger with
a smaller HikariCP pool; after M2 the cache component is valkey-cache instead of redis-cache.
"""

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum

from dejavu.sim.migrations import Phase, phases_at


class Kind(StrEnum):
    SERVICE = "service"
    DATASTORE = "datastore"
    INFRA = "infra"
    EXTERNAL = "external"
    NODES = "nodes"


class LogFormat(StrEnum):
    """How a component's log lines look; each maps to a formatter in `generators.logs`."""

    SPRING = "spring"  # Spring Boot / logback (Java, Kotlin)
    ZAP = "zap"  # Go zap JSON
    PINO = "pino"  # Node pino JSON
    STRUCTLOG = "structlog"  # Python structlog JSON
    ENVOY = "envoy"  # Envoy access and application logs
    POSTGRES = "postgres"
    PGBOUNCER = "pgbouncer"
    REDIS = "redis"  # Redis / Valkey server and Sentinel
    KAFKA = "kafka"  # broker log4j
    COREDNS = "coredns"
    JOURNAL = "journal"  # node systemd journal
    NONE = "none"  # external: no logs of our own


@dataclass(frozen=True)
class Team:
    name: str
    lead: str
    members: tuple[str, ...]


TEAMS = {
    "Platform": Team("Platform", "Sara Kim", ("Sara Kim", "Deepak Rao")),
    "Identity": Team("Identity", "Arjun Nair", ("Arjun Nair", "Meera Pillai")),
    "Payments": Team("Payments", "Priya Raman", ("Priya Raman", "Tomás Ortega")),
    "Core Ledger": Team("Core Ledger", "Ananya Iyer", ("Ananya Iyer", "Farhan Qureshi")),
    "Risk ML": Team("Risk ML", "Vikram Shetty", ("Vikram Shetty", "Ishita Bose")),
    "Messaging": Team("Messaging", "Lena Fischer", ("Lena Fischer", "Kofi Mensah")),
    "Data Platform": Team("Data Platform", "Rohan Mehta", ("Rohan Mehta", "Neha Kulkarni")),
}

ENGINEERING_MANAGER = "Kabir Malhotra"
FORMER_STAFF_SRE = "Marcus Oyelaran"
ON_CALL = "Priya Raman"

CLUSTER = "prod-aps1"
REGION = "ap-south-1"
NAMESPACE = "prod"
DNS_SERVICE_IP = "172.20.0.10"


@dataclass(frozen=True)
class Node:
    name: str
    zone: str
    ip: str


NODES = (
    Node("ip-10-42-1-23", "ap-south-1a", "10.42.1.23"),
    Node("ip-10-42-2-14", "ap-south-1b", "10.42.2.14"),
    Node("ip-10-42-3-17", "ap-south-1c", "10.42.3.17"),
    Node("ip-10-42-4-9", "ap-south-1b", "10.42.4.9"),
    Node("ip-10-42-5-31", "ap-south-1a", "10.42.5.31"),
    Node("ip-10-42-6-8", "ap-south-1c", "10.42.6.8"),
)


@dataclass(frozen=True)
class Component:
    """One thing the agent can ask about: a service, datastore, infra piece or external provider.

    `metrics` maps each metric this component exports to its baseline value at peak load.
    """

    name: str
    kind: Kind
    stack: str
    team: str | None
    depends_on: tuple[str, ...]
    log_format: LogFormat
    metrics: dict[str, float]
    replicas: int = 1
    slo: str | None = None
    notes: tuple[str, ...] = ()
    stateful: bool = False
    status_page: str | None = None
    owner_override: str | None = field(default=None, repr=False)

    @property
    def owner(self) -> str | None:
        if self.owner_override:
            return self.owner_override
        return TEAMS[self.team].lead if self.team else None


_WEB = {"rps": 0.0, "latency_p50_ms": 0.0, "latency_p99_ms": 0.0, "error_rate_5xx": 0.08}


def _web(rps: float, p50: float, p99: float, **extra: float) -> dict[str, float]:
    return {**_WEB, "rps": rps, "latency_p50_ms": p50, "latency_p99_ms": p99, **extra}


_BASE: tuple[Component, ...] = (
    Component(
        "edge-gateway",
        Kind.SERVICE,
        "Envoy 1.31",
        "Platform",
        ("auth-svc", "checkout-api"),
        LogFormat.ENVOY,
        _web(
            950,
            38,
            260,
            error_rate_4xx=2.1,
            cpu_cores=3.2,
            mem_bytes=0.9e9,
            restarts=0,
            cert_days_remaining=54,
        ),
        replicas=3,
        slo="99.95% success, p99 < 400 ms",
        notes=("mTLS to auth-svc with client certificate edge-gateway-mtls (cert-manager)",),
    ),
    Component(
        "auth-svc",
        Kind.SERVICE,
        "Go 1.23",
        "Identity",
        ("redis-cache",),
        LogFormat.ZAP,
        _web(
            420,
            6,
            45,
            error_rate_4xx=2.6,
            cpu_cores=1.8,
            mem_bytes=0.6e9,
            restarts=0,
            dns_lookup_errors=0.2,
            cert_days_remaining=61,
        ),
        replicas=3,
        slo="99.9% success, p99 < 100 ms",
        notes=("issues and validates JWTs (RS256); OTP step-up verification for UPI payments",),
    ),
    Component(
        "checkout-api",
        Kind.SERVICE,
        "Node.js 22 / TypeScript",
        "Payments",
        ("auth-svc", "payments-svc", "ledger-svc", "fraud-scorer"),
        LogFormat.PINO,
        _web(
            310,
            180,
            620,
            error_rate_4xx=1.4,
            cpu_cores=2.6,
            mem_bytes=1.6e9,
            restarts=0,
            dns_lookup_errors=0.2,
            payments_attempted=2400,
            payments_failed=14.4,
            gmv_inr_per_min=0.0,
        ),
        replicas=4,
        slo="99.9% success, p99 < 1,500 ms",
        notes=("fraud-scorer timeout 1.5 s, then falls back to manual review",),
    ),
    Component(
        "payments-svc",
        Kind.SERVICE,
        "Go 1.23",
        "Payments",
        ("acquirerx", "paynova", "ledger-svc"),
        LogFormat.ZAP,
        _web(
            120,
            95,
            480,
            error_rate_4xx=0.9,
            cpu_cores=2.2,
            cpu_throttle_ratio=0.01,
            mem_bytes=0.8e9,
            restarts=0,
            dns_lookup_errors=0.1,
        ),
        replicas=4,
        slo="99.9% success, p99 < 800 ms",
        notes=(
            "PSP routing: primary acquirerx, secondary paynova (flag psp.primary)",
            "resources.limits.cpu 2000m per pod",
        ),
        owner_override="Tomás Ortega",
    ),
    Component(
        "ledger-svc",
        Kind.SERVICE,
        "Java 21 / Spring Boot 3.3, HikariCP",
        "Core Ledger",
        ("postgres-ledger", "redis-cache"),
        LogFormat.SPRING,
        _web(
            260,
            14,
            120,
            cpu_cores=3.0,
            mem_bytes=4.2e9,
            restarts=0,
            gc_pause_p99_ms=45,
            db_pool_active=6,
            db_pool_idle=14,
            db_pool_pending=0,
            dns_lookup_errors=0.1,
        ),
        replicas=3,
        slo="99.95% success, p99 < 250 ms",
        notes=("HikariCP maximum-pool-size 20 per pod, connecting directly to postgres-ledger",),
    ),
    Component(
        "fraud-scorer",
        Kind.SERVICE,
        "Python 3.12 / FastAPI + LightGBM",
        "Risk ML",
        ("redis-cache",),
        LogFormat.STRUCTLOG,
        _web(110, 28, 140, cpu_cores=4.5, mem_bytes=0.9e9, restarts=0),
        replicas=3,
        slo="p99 < 300 ms",
        notes=("memory limit 2Gi per pod",),
    ),
    Component(
        "notifications-worker",
        Kind.SERVICE,
        "Kotlin, Kafka consumer",
        "Messaging",
        ("kafka", "smsbridge"),
        LogFormat.SPRING,
        {
            "rps": 45,
            "error_rate_5xx": 0.1,
            "cpu_cores": 1.1,
            "mem_bytes": 1.1e9,
            "restarts": 0,
            "gc_pause_p99_ms": 30,
            "kafka_consumer_lag": 120,
            "kafka_rebalances": 0,
        },
        replicas=4,
        slo="99% of OTPs delivered within 10 s",
        notes=(
            "consumer group notifications on topic otp-requests (12 partitions); "
            "max.poll.interval.ms=300000, max.poll.records=500",
        ),
    ),
    Component(
        "postgres-ledger",
        Kind.DATASTORE,
        "PostgreSQL 16, primary + 1 replica",
        "Data Platform",
        (),
        LogFormat.POSTGRES,
        {"pg_cpu_pct": 28, "pg_active_connections": 22, "pg_slow_queries_per_min": 0.5, "disk_used_pct": 71},
        replicas=2,
        stateful=True,
        notes=("max_connections 200; logical replication enabled",),
    ),
    Component(
        "redis-cache",
        Kind.DATASTORE,
        "Redis 7.2 Sentinel",
        "Platform",
        (),
        LogFormat.REDIS,
        {"rps": 5200, "latency_p99_ms": 2.2, "cache_hit_ratio": 0.955, "cpu_cores": 0.9, "mem_bytes": 3.1e9},
        replicas=3,
        stateful=True,
        notes=("Sentinel master name kestrel-cache; 1 primary + 2 replicas, 3 sentinels",),
    ),
    Component(
        "kafka",
        Kind.DATASTORE,
        "Kafka 3.7, 3 brokers",
        "Platform",
        (),
        LogFormat.KAFKA,
        {"rps": 380, "cpu_cores": 2.4, "disk_used_pct": 38},
        replicas=3,
        stateful=True,
    ),
    Component(
        "coredns",
        Kind.INFRA,
        "CoreDNS 1.11 (kube-system)",
        "Platform",
        (),
        LogFormat.COREDNS,
        {"rps": 1400, "latency_p99_ms": 6, "dns_lookup_errors": 0.3, "cpu_cores": 0.4, "restarts": 0},
        replicas=2,
        notes=("pods use ndots:5 (Kubernetes default)",),
    ),
    Component(
        "acquirerx",
        Kind.EXTERNAL,
        "external primary card/UPI processor",
        None,
        (),
        LogFormat.NONE,
        {"psp_http_429_rate": 0.05, "psp_latency_p99_ms": 420, "error_rate_5xx": 0.05},
        status_page="status.acquirerx.com",
    ),
    Component(
        "paynova",
        Kind.EXTERNAL,
        "external secondary processor",
        None,
        (),
        LogFormat.NONE,
        {"psp_http_429_rate": 0.03, "psp_latency_p99_ms": 610, "error_rate_5xx": 0.04},
        status_page="status.paynova.io",
    ),
    Component(
        "smsbridge",
        Kind.EXTERNAL,
        "external SMS/OTP provider",
        None,
        (),
        LogFormat.NONE,
        {"latency_p99_ms": 900, "error_rate_4xx": 0.3},
        status_page="status.smsbridge.in",
    ),
    Component(
        "nodes",
        Kind.NODES,
        f"EKS worker nodes ({len(NODES)}) in {REGION}",
        "Platform",
        (),
        LogFormat.JOURNAL,
        {"node_clock_offset_ms": 0.0},
        replicas=len(NODES),
        notes=tuple(f"{n.name} ({n.zone})" for n in NODES),
    ),
)

_PGBOUNCER = Component(
    "pgbouncer-ledger",
    Kind.INFRA,
    "PgBouncer 1.23, pool_mode=transaction",
    "Data Platform",
    ("postgres-ledger",),
    LogFormat.PGBOUNCER,
    {"pgbouncer_cl_waiting": 0, "cpu_cores": 0.3},
    replicas=2,
    stateful=True,
    notes=("default_pool_size=20, max_db_connections=40, max_client_conn=2000",),
)


@dataclass(frozen=True)
class Topology:
    """The components that existed at one moment, keyed by name."""

    components: dict[str, Component]
    phases: frozenset[Phase]

    @property
    def cache(self) -> str:
        return "valkey-cache" if Phase.POST_M2 in self.phases else "redis-cache"

    @property
    def pool_max(self) -> int:
        """HikariCP maximum-pool-size per ledger-svc pod."""
        return 10 if Phase.POST_M1 in self.phases else 20

    def get(self, name: str) -> Component | None:
        return self.components.get(name)

    def dependents(self, name: str) -> list[str]:
        return sorted(c.name for c in self.components.values() if name in c.depends_on)

    def names(self) -> list[str]:
        return list(self.components)


def _swap_dep(c: Component, old: str, new: str) -> Component:
    return replace(c, depends_on=tuple(new if d == old else d for d in c.depends_on))


def topology_at(when: datetime) -> Topology:
    """The topology as it stood at `when`, with M1 / M2 applied if they had happened."""
    phases = phases_at(when)
    comps = {c.name: c for c in _BASE}
    if Phase.POST_M1 in phases:
        ledger = _swap_dep(comps["ledger-svc"], "postgres-ledger", "pgbouncer-ledger")
        comps["ledger-svc"] = replace(
            ledger,
            metrics={**ledger.metrics, "db_pool_active": 4, "db_pool_idle": 6},
            notes=(
                "connects through pgbouncer-ledger (transaction pooling) since 3 Sep 2026",
                "HikariCP maximum-pool-size 10 per pod",
            ),
        )
        comps["pgbouncer-ledger"] = _PGBOUNCER
    if Phase.POST_M2 in phases:
        valkey = replace(
            comps.pop("redis-cache"),
            name="valkey-cache",
            stack="Valkey 8.0 Sentinel",
            notes=("replaced redis-cache on 10 Sep 2026; Sentinel master name kestrel-cache",),
        )
        comps = {n: _swap_dep(c, "redis-cache", "valkey-cache") for n, c in comps.items()}
        comps["valkey-cache"] = valkey
    return Topology(components=comps, phases=phases)
