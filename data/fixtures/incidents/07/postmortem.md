---
id: pm-INC-4186
kind: postmortem
title: "INC-4186: missing index on ledger_entries after the V88 migration; raising the pool made it worse"
author: Rohan Mehta
date: 2026-08-28T15:00:00+05:30
incident_id: INC-4186
services: [postgres-ledger, ledger-svc, checkout-api]
symptom: latency_p99
format: md
---
# INC-4186: missing index on ledger_entries after the V88 migration

**Date:** Thu 27 Aug 2026 · **Severity:** SEV-1 · **On call:** Tomás Ortega · **Author:** Rohan Mehta (Data Platform)

## Summary
ledger-svc 3.15.1 (deployed 11:25 IST, PR #2230) shipped Flyway migration V88__repartition_ledger_entries, applied at 11:27 (chg-f8a8a7). It recreated `ledger_entries` as a range-partitioned table with indexes on `(id)` and `(created_at)` only. The `(account_id, created_at)` index was gone, so every statement lookup became a sequential scan over 18 million rows. postgres-ledger CPU pinned at 94%, slow queries went from ~1/min to 300+/min, and the ledger pool filled as a side effect. The alert was the same CheckoutLatencyP99High as INC-4127, and it was treated like pool exhaustion: raising the HikariCP pool to 40 made it worse. Creating the index concurrently at 12:10 fixed it by 12:29.

## Impact
- 58 minutes, including the lunch ramp. The longest ledger incident this quarter.
- 29,304 failed payments, about ₹5.42 crore at risk.

## Timeline (IST)
- 11:25 ledger-svc 3.15.0 -> 3.15.1; 11:27 V88 applied
- 11:31 pg CPU climbing, seq scans in the slow-query log
- 11:42 CheckoutLatencyP99High (p99 5,749 ms)
- 11:47 pool raised to 40 per RB-ledger-pool: **more concurrent scans, Postgres worse**
- 11:57 ledger-svc rolled back: no change, because an app rollback does not revert an applied migration
- 12:05 Rohan paged; slow-query log shows `Seq Scan on ledger_entries_2026q3 ... Filter: (account_id = $1)`
- 12:10 `CREATE INDEX CONCURRENTLY` on (account_id, created_at), about 15 minutes
- 12:29 recovered

## What went wrong
- **Same alert, different disease.** The pool was full because Postgres was slow, not the other way round. pg_cpu_pct at 94% was the tell; in INC-4127 it was normal.
- RB-ledger-pool's "raise the pool" advice is dangerous when the database is the bottleneck.
- Migrations are not reviewed for index coverage.

## Action items
| Action | Owner | Due |
|---|---|---|
| Migration review checklist: every index on the old table exists on the new one; EXPLAIN the top 10 queries | Rohan Mehta | 2026-09-03 |
| Add "check pg_cpu_pct before touching the pool" to RB-ledger-pool | Farhan Qureshi | 2026-09-01 |
| Alert on pg_slow_queries_per_min > 50 | Neha Kulkarni | 2026-09-03 |

## Lessons
Pool full + Postgres CPU pinned + seq scans = a query-plan problem. Never raise the pool then: more connections run more scans at once. Fix the index (DBA approval) or revert the migration; rolling back the application does not undo a migration.
