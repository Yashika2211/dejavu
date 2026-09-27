"""Controlled vocabularies shared by the simulator, agent, grader and memory layer.

The root-cause taxonomy is handed to every strategy (like OpenRCA's allowed reason vocabulary)
so grading stays deterministic and fair.
"""

from enum import StrEnum


class RootCause(StrEnum):
    """Root-cause categories an agent may diagnose. `novel` covers anything outside the library."""

    DB_POOL_EXHAUSTION = "db_pool_exhaustion"
    MISSING_INDEX_SLOW_QUERY = "missing_index_slow_query"
    PSP_RATE_LIMIT = "psp_rate_limit"
    CPU_THROTTLING = "cpu_throttling"
    MEMORY_LEAK_OOM = "memory_leak_oom"
    RETRY_STORM = "retry_storm"
    CERT_EXPIRY = "cert_expiry"
    CLOCK_SKEW_JWT = "clock_skew_jwt"
    DNS_RESOLUTION_FAILURE = "dns_resolution_failure"
    KAFKA_REBALANCE_STORM = "kafka_rebalance_storm"
    CACHE_STAMPEDE = "cache_stampede"
    DISK_FULL_WAL = "disk_full_wal"
    NOVEL = "novel"


class SymptomClass(StrEnum):
    """Alert-level symptom classes; low-cardinality, used as `symptom:<class>` tags."""

    LATENCY_P99 = "latency_p99"
    ERROR_RATE_5XX = "error_rate_5xx"
    AUTH_FAILURES = "auth_failures"
    WRITE_FAILURES = "write_failures"


class Remediation(StrEnum):
    """Remediation families, used as `remediation:<kind>` entity labels."""

    ROLLBACK = "rollback"
    RESTART = "restart"
    SCALE_OUT = "scale_out"
    POOL_TUNING = "pool_tuning"
    PSP_FAILOVER = "psp_failover"
    FLAG_REVERT = "flag_revert"
    CERT_ROTATION = "cert_rotation"
    NODE_DRAIN = "node_drain"
    CACHE_WARMUP = "cache_warmup"
    WAL_CLEANUP = "wal_cleanup"
    ADD_INDEX = "add_index"
    LIMITS_REVERT = "limits_revert"
    CONFIG_TUNING = "config_tuning"


class Outcome(StrEnum):
    """What a remediation did, used as `outcome:<value>` entity labels."""

    WORKED = "worked"
    NO_EFFECT = "no_effect"
    MADE_WORSE = "made_worse"
