"""The two infrastructure migrations that make old fixes stale (spec 4.5)."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from dejavu.sim.clock import ist


class Phase(StrEnum):
    """Scenario conditions that depend on which migrations have happened."""

    PRE_M1 = "pre_m1"
    POST_M1 = "post_m1"
    PRE_M2 = "pre_m2"
    POST_M2 = "post_m2"


@dataclass(frozen=True)
class Migration:
    id: str
    slug: str
    at: datetime
    service: str
    author: str
    summary: str


M1 = Migration(
    id="M1",
    slug="ledger-pgbouncer",
    at=ist("2026-09-03T14:00:00"),
    service="ledger-svc",
    author="Rohan Mehta",
    summary=(
        "ledger-svc now reaches postgres-ledger through pgbouncer-ledger (pool_mode=transaction, "
        "default_pool_size=20); HikariCP maximum-pool-size reduced 20 -> 10 per pod"
    ),
)

M2 = Migration(
    id="M2",
    slug="redis-to-valkey",
    at=ist("2026-09-10T14:00:00"),
    service="valkey-cache",
    author="Sara Kim",
    summary=(
        "redis-cache (Redis 7.2 Sentinel) replaced by valkey-cache (Valkey 8.0 Sentinel); clients "
        "repointed to valkey-cache.prod.svc.cluster.local, master name unchanged (kestrel-cache)"
    ),
)

MIGRATIONS = (M1, M2)


def phases_at(when: datetime) -> frozenset[Phase]:
    """Which side of each migration a moment falls on."""
    return frozenset(
        {
            Phase.POST_M1 if when >= M1.at else Phase.PRE_M1,
            Phase.POST_M2 if when >= M2.at else Phase.PRE_M2,
        }
    )
