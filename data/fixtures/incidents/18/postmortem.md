---
id: pm-INC-4311
kind: postmortem
title: "INC-4311: missing ledger_entries index again (V95); pool left alone"
author: Neha Kulkarni
date: 2026-09-17T11:00:00+05:30
incident_id: INC-4311
services: [postgres-ledger, ledger-svc, checkout-api]
symptom: latency_p99
format: md
---
# INC-4311: missing ledger_entries index again (V95)

**Date:** Wed 16 Sep 2026 · **Severity:** SEV-2 · **On call:** Priya Raman · **Author:** Neha Kulkarni (Data Platform)

## Summary
ledger-svc 3.18.1 (deployed 12:22 IST, PR #2288) added the Oct-Dec partitions for `ledger_entries`; Flyway V95 applied at 12:24 (chg-73b58d). It was generated from the same partition template as V88 in INC-4186 and again created only `(id)` and `(created_at)` indexes. Statement lookups became sequential scans and postgres-ledger CPU pinned at 94%. Priya recognised INC-4186 from `Seq Scan on ledger_entries` in the slow-query log and pinned pg CPU, **did not touch the pool**, and asked for the index. `CREATE INDEX CONCURRENTLY` from 12:42; recovered at 13:01.

## Impact
- 33 minutes at lunch. 11,497 failed payments, about ₹2.13 crore at risk.
- Compare INC-4186: 58 minutes and ₹5.42 crore, largely because the pool was raised first.

## Root cause
The partition-migration template omits the composite `(account_id, created_at)` index. INC-4186's review checklist was ticked for V95 without running EXPLAIN.

## Action items
| Action | Owner | Due |
|---|---|---|
| Fix the partition template to copy every index from the parent | Neha Kulkarni | 2026-09-18 |
| CI check: EXPLAIN the top 10 ledger queries against a migrated copy; fail on Seq Scan | Rohan Mehta | 2026-09-25 |

## Lessons
Same alert as pool exhaustion, but pg CPU pinned and seq scans in the slow log: the fix is the index (or reverting the migration), never a bigger pool. Twice now.
