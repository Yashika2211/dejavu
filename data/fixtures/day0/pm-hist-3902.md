---
id: pm-hist-3902
kind: postmortem
title: "INC-3902: checkout p99 latency from ledger connection pool exhaustion"
author: Marcus Oyelaran
date: 2026-07-14T16:30:00+05:30
services: [ledger-svc, checkout-api, postgres-ledger]
symptom: latency_p99
format: md
---
# INC-3902: checkout p99 latency from ledger connection pool exhaustion

**Date:** Tue 14 Jul 2026 · **Severity:** SEV-2 · **Author:** Marcus Oyelaran · **Status:** final

## Summary
checkout-api p99 rose from 380 ms to 9.2 s for 41 minutes. ledger-svc 3.11.2 added a per-row account lookup inside the posting transaction, so each request held a HikariCP connection for about two seconds. The pool (max 20 per pod) sat at active=20 with 140+ threads waiting, while postgres-ledger CPU stayed at 35%.

## What we tried
- Restarting ledger-svc pods: three minutes of relief, then latency came back.
- Raising the pool was discussed but not done.
- Rolled back ledger-svc to 3.11.1: p99 recovered within four minutes.

## Discriminator
db_pool_pending above zero with active pinned at the maximum while pg_cpu_pct stays normal means pool exhaustion in the application, not a slow query in the database.

## Action items
| Action | Owner | Due |
|---|---|---|
| Load test for ledger-svc changes that touch the posting transaction | Ananya Iyer | 2026-07-28 |
| Canary rollout for ledger-svc (one pod, 15 minutes) | Farhan Qureshi | 2026-08-11 |

## Lessons
Look at the pool and at Postgres together. Pool pinned plus a healthy database: roll back the change that made transactions longer. Restarts only reset the clock.
