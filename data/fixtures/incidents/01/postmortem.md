---
id: pm-INC-4127
kind: postmortem
title: "INC-4127: checkout p99 latency from ledger-svc connection pool exhaustion"
author: Farhan Qureshi
date: 2026-08-17T16:00:00+05:30
incident_id: INC-4127
services: [ledger-svc, checkout-api, postgres-ledger]
symptom: latency_p99
format: md
---
# INC-4127: checkout p99 latency from ledger-svc connection pool exhaustion

**Date:** Mon 17 Aug 2026 · **Severity:** SEV-2 · **On call:** Priya Raman · **Author:** Farhan Qureshi

## Summary
From 02:58 to 03:31 IST checkout-api p99 on POST /v1/checkout sat above 6 s. ledger-svc 3.14.0 (deployed 02:54, chg-c3e375) calls `AccountTierClient.fetchTier()` for every entry inside the `@Transactional` posting block, so each request held a HikariCP connection for seconds. The pool pinned at 20 active per pod with 100+ threads waiting; postgres-ledger CPU stayed normal. Rolling back to 3.13.3 fixed it.

## Impact
- 33 minutes of degraded checkout (02:58-03:31), low overnight traffic.
- 1,539 failed payments, about ₹28.5 lakh of payment volume at risk.

## Root cause
Connection pool exhaustion in ledger-svc caused by longer transactions in 3.14.0. The database was not the bottleneck.

## Detection
CheckoutLatencyP99High paged at 03:07 (p99 6,672 ms). Priya acknowledged at 03:09.

## Timeline (IST)
- 02:54 ledger-svc 3.13.3 -> 3.14.0 deployed
- 02:58 HikariCP `Connection is not available ... waiting=` warnings begin
- 03:07 alert fires
- 03:13 Priya restarts ledger-svc pods: three minutes of relief, then latency returns
- 03:21 Farhan joins and rolls back to 3.13.3 (6 minutes)
- 03:31 p99 back under 600 ms

## What went well
- The pool metrics made the diagnosis quick once someone looked at them.

## What went wrong
- The restart cost 8 minutes and only masked the problem.
- A change that lengthens transactions went out without a load test, at 02:54.

## Where we got lucky
- 3 AM traffic.

## Action items
| Action | Owner | Due |
|---|---|---|
| Move the tier lookup out of the transaction and batch it | Ananya Iyer | 2026-08-21 |
| Canary ledger-svc on one pod for 15 minutes before full rollout | Farhan Qureshi | 2026-08-28 |
| No non-emergency ledger deploys between 01:00 and 06:00 | Kabir Malhotra | 2026-08-19 |

## Lessons
db_pool_pending above zero with active pinned at the max and a healthy Postgres means the application is holding connections too long. Roll back the change; restarts only reset the clock. Same shape as Marcus's INC-3902 in July.
