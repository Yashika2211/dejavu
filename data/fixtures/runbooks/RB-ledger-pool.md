---
id: RB-ledger-pool
title: ledger-svc connection pool saturation
services: [ledger-svc, postgres-ledger]
keywords: [ledger, pool, hikari, hikaricp, connection, connections, db_pool, pending, saturation, latency]
author: Marcus Oyelaran
last_edited: 2026-03-02
---
# ledger-svc connection pool saturation

Symptoms: ledger-svc and checkout-api latency up, `HikariPool-1 - Connection is not available` in ledger-svc logs, db_pool_pending above zero.

1. Check db_pool_active, db_pool_idle and db_pool_pending for ledger-svc. Active pinned at 20 with pending climbing means the pool is exhausted.
2. Check postgres-ledger pg_cpu_pct. If Postgres is fine (below ~60%), the pool is the bottleneck.
3. Raise `spring.datasource.hikari.maximum-pool-size` from 20 to 40 in the ledger-svc Helm values and roll it out. Postgres has max_connections 200, so 3 pods x 40 is safe.
4. Restarting ledger-svc pods buys a few minutes if you need time, but it will come back.
5. If a ledger-svc deploy went out in the last hour, consider rolling it back.
6. Page Core Ledger (Ananya Iyer) if it is not better in 15 minutes.
