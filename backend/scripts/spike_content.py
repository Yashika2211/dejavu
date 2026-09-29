"""Test documents for the Hindsight spike: small, realistic Kestrel Pay artifacts.

Each constant exercises one part of the memory contract (third-person postmortem, stale runbook,
untagged handbook, first-person investigation log, upsert pair, append pair, migration RFC).
"""

import json

HIST_POSTMORTEM = """# Postmortem: checkout p99 latency, 14 Jul 2026 (INC-3902)
Author: Marcus Oyelaran. Severity: SEV-2. Duration: 41 minutes.

Summary: checkout-api p99 rose from 380 ms to 9.2 s. ledger-svc 3.11.2 added a per-row account
lookup inside the posting transaction, so every request held a HikariCP connection for about two
seconds. The pool (max 20) sat at active=20 with 140+ requests waiting; postgres-ledger CPU stayed
at 35%.

What we tried: restarting the ledger-svc pods gave three minutes of relief, then latency returned.
Resolution: rolled ledger-svc back to 3.11.1; p99 recovered within four minutes.
Discriminator: db_pool_pending above zero with active pinned at max while pg_cpu_pct stays normal
means pool exhaustion, not a slow query.
"""

STALE_RUNBOOK = """# RB-ledger-pool: ledger-svc connection pool saturation
Last edited 2 Mar 2026 by Marcus Oyelaran.

1. Check db_pool_active and db_pool_pending for ledger-svc.
2. If pending stays above zero for five minutes, raise spring.datasource.hikari.maximum-pool-size
   from 20 to 40 through the Helm values and redeploy.
3. If that does not help within ten minutes, page Core Ledger (Ananya Iyer).
"""

HANDBOOK = (
    "Kestrel Pay on-call handbook: any action on postgres-ledger needs approval from the DBA on call "
    "(Rohan Mehta's Data Platform team). Post a status update in #inc-bridge every 15 minutes."
)

INVESTIGATION_LOG = (
    "I started with DNS because the alert mentioned timeouts; that cost me six minutes and found "
    "nothing. I then restarted two ledger-svc pods, which helped for three minutes before latency "
    "returned, another eight minutes wasted. What finally discriminated was db_pool_pending at 143 with "
    "db_pool_active pinned at 20 while pg_cpu_pct stayed at 31%. I rolled ledger-svc back from 3.14.0 "
    "to 3.13.2 and checkout p99 recovered."
)
INVESTIGATION_CONTEXT = (
    "DejaVu, the on-call agent that owns this memory bank, is speaking: its own first-person "
    "investigation log for INC-4127"
)

OUTCOME = (
    "Outcome of INC-4127 (17 Aug 2026, SEV-2, checkout p99): root cause db_pool_exhaustion in "
    "ledger-svc, triggered by deploy 3.14.0. Restarting ledger-svc pods: no effect after three "
    "minutes. Rolling ledger-svc back to 3.13.2: worked, recovered in five minutes. MTTR 34 minutes."
)

UPSERT_V1 = (
    "Postmortem draft for INC-4188 (19 Aug 2026): the checkout payment failures were caused by CoreDNS "
    "timeouts in cluster prod-aps1."
)
UPSERT_V2 = (
    "Postmortem final for INC-4188 (19 Aug 2026): the checkout payment failures were caused by acquirerx "
    "rate limiting (HTTP 429 with retry_after 2s). We failed routing over to paynova."
)

ALERT_FIRING = json.dumps(
    {
        "status": "firing",
        "labels": {
            "alertname": "CheckoutLatencyP99High",
            "service": "checkout-api",
            "severity": "sev2",
            "cluster": "prod-aps1",
        },
        "annotations": {"summary": "checkout-api p99 latency above 2s for 5 minutes"},
        "startsAt": "2026-08-17T03:07:00+05:30",
    }
)
ALERT_RESOLVED = "INC-4127 resolved at 03:41 IST after rolling ledger-svc back to 3.13.2."

RFC_PGBOUNCER_LINES = (
    "RFC-014: Move ledger-svc behind PgBouncer",
    "Author: Rohan Mehta. Status: accepted. Rollout: 3 Sep 2026.",
    "ledger-svc will connect through PgBouncer in transaction pooling mode.",
    "The HikariCP pool shrinks to 10 by design; PgBouncer default_pool_size governs server connections.",
    "After the rollout, pool pressure shows up as pgbouncer_cl_waiting, not db_pool_pending.",
)


def secret_debug_line(token: str) -> str:
    """A debug log line that leaks a bearer token (the token is generated at runtime)."""
    return (
        "2026-09-13 21:05:44.102 DEBUG acquirerx client request headers "
        f'{{"Authorization": "Bearer {token}", "X-Request-Id": "7f3a91c2"}}'
    )


POST_MIGRATION_OUTCOME = (
    "Outcome of INC-4249 (Sun 6 Sep 2026, CheckoutLatencyP99High): connection pool exhaustion in "
    "ledger-svc after 3.16.3, three days after ledger-svc moved behind PgBouncer. Raising the HikariCP "
    "pool had no effect: the queue now forms in PgBouncer (pgbouncer_cl_waiting climbed, "
    "query_wait_timeout in its logs). Raising PgBouncer default_pool_size and rolling back 3.16.3 fixed it."
)
