---
id: pm-INC-4249
kind: postmortem
title: "INC-4249: ledger pool pressure after the PgBouncer migration; the old runbook fix no longer works"
author: Farhan Qureshi
date: 2026-09-07T11:00:00+05:30
incident_id: INC-4249
services: [ledger-svc, pgbouncer-ledger, postgres-ledger, checkout-api]
symptom: latency_p99
format: md
---
# INC-4249: ledger pool pressure after the PgBouncer migration

**Date:** Sun 6 Sep 2026 · **Severity:** SEV-2 · **On call:** Meera Pillai · **Author:** Farhan Qureshi (Core Ledger)

## Summary
ledger-svc 3.16.3 (deployed 18:41 IST, chg-604c0e, PR #2258) calls `FxRateClient.rateFor()` for each foreign-currency entry inside the `@Transactional` posting block. Same failure mode as INC-4127 and INC-4165, but **three days after the PgBouncer migration (M1, 3 Sep)** it no longer looks the same or has the same fix. Server connections are now held by PgBouncer (`default_pool_size=20`), so clients queued there: `pgbouncer_cl_waiting` climbed past 120 and PgBouncer logged `query_wait_timeout`. Following RB-ledger-pool, the HikariCP pool was raised (10 -> 20 per pod) at 19:01: **no effect**. A restart gave three minutes. At 19:17 I raised PgBouncer's `default_pool_size` 20 -> 40 and checkout recovered by 19:24; we rolled back 3.16.3 right after.

## Impact
- 39 minutes at the Sunday evening peak. 11,775 failed payments, about ₹2.18 crore at risk.

## What changed with M1
| | Before 3 Sep | Since 3 Sep (PgBouncer, transaction pooling) |
|---|---|---|
| Where the queue shows up | db_pool_pending on ledger-svc | pgbouncer_cl_waiting on pgbouncer-ledger (+ `query_wait_timeout`) |
| Raise HikariCP maximum-pool-size | partial relief | **does nothing**: Hikari is not the bottleneck |
| The knob | Hikari pool size | PgBouncer `default_pool_size` / `max_db_connections` (Data Platform) |
| The real fix | roll back the change | roll back the change (and tune PgBouncer if needed) |

## Timeline (IST)
- 18:41 ledger-svc 3.16.2 -> 3.16.3
- 18:45 pgbouncer_cl_waiting climbing; `query_wait_timeout` in PgBouncer logs
- 18:55 CheckoutLatencyP99High (p99 6,621 ms)
- 19:01 HikariCP 10 -> 20 per RB-ledger-pool: no effect
- 19:09 restart ledger-svc: three minutes of relief
- 19:17 default_pool_size 20 -> 40 (approved by Rohan)
- 19:24 recovered; 3.16.3 rolled back afterwards

## What went wrong
- RB-ledger-pool is stale. It predates M1 and still says to raise the HikariCP pool. Rohan asked for it to be updated on 3 Sep; I didn't.
- Another remote call inside the posting transaction shipped despite the lint rule from INC-4165 (it only catches HTTP clients named `*HttpClient`).

## Action items
| Action | Owner | Due |
|---|---|---|
| Rewrite RB-ledger-pool for PgBouncer | Farhan Qureshi | 2026-09-09 |
| Extend the lint rule to every outbound client | Farhan Qureshi | 2026-09-11 |
| Alert on pgbouncer_cl_waiting > 20 for 3 minutes | Rohan Mehta | 2026-09-09 |

## Lessons
Since 3 Sep, look at `pgbouncer_cl_waiting` first. Raising the HikariCP pool is a no-op now; tune PgBouncer `default_pool_size` and roll back whatever lengthened the transaction.
