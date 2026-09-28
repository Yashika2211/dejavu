---
id: pm-INC-4327
kind: postmortem
title: "INC-4327: ledger pool pressure from the synchronous audit trail (3.19.0)"
author: Ananya Iyer
date: 2026-09-22T11:00:00+05:30
incident_id: INC-4327
services: [ledger-svc, pgbouncer-ledger, checkout-api]
symptom: latency_p99
format: md
---
# INC-4327: ledger pool pressure from the synchronous audit trail

**Date:** Mon 21 Sep 2026 · **Severity:** SEV-2 · **On call:** Farhan Qureshi · **Author:** Ananya Iyer (Core Ledger)

## Summary
ledger-svc 3.19.0 (deployed 11:07 IST, chg-e3d988, PR #2305) moved `AuditTrailWriter.record()` inside the posting transaction, where it waits for the compliance-archive API before commit. Transactions got longer, PgBouncer's server pool filled and `pgbouncer_cl_waiting` climbed. Farhan checked PgBouncer first (the INC-4249 lesson), left HikariCP alone, and rolled back to 3.18.3 at 11:26; recovered by 11:36.

## Impact
- 25 minutes at the late-morning ramp. 9,481 failed payments, about ₹1.75 crore at risk.

## The pattern
This is the fourth ledger incident with one cause: a change that puts a remote call inside the posting transaction.
| Incident | Change | Fix |
|---|---|---|
| INC-4127 (17 Aug) | per-entry tier lookup | rollback |
| INC-4165 (24 Aug) | batched tier lookup, still in the transaction | rollback |
| INC-4249 (6 Sep, after PgBouncer) | FX rate lookup | PgBouncer default_pool_size, then rollback |
| INC-4327 (21 Sep) | synchronous audit trail | rollback |

## What went wrong
- PR #2305 touched `LedgerPostingService` and the transaction boundary. Nobody connected it to the three earlier incidents before it shipped; it went out without a canary.
- The lint rule from INC-4165/INC-4249 only matches client classes by name; `AuditTrailWriter` wraps its client.

## Action items
| Action | Owner | Due |
|---|---|---|
| Any change to LedgerPostingService or the transaction boundary: canary + load test + Core Ledger owner review | Ananya Iyer | 2026-09-25 |
| Make the audit trail asynchronous (outbox table) | Farhan Qureshi | 2026-10-02 |
| Transaction-duration SLO on ledger postings (p99 < 50 ms), alerting | Farhan Qureshi | 2026-09-30 |

## Lessons
Changes that lengthen the posting transaction are the highest-risk changes we ship. Review them against this history, canary them, and roll them back at the first sign of pgbouncer_cl_waiting.
