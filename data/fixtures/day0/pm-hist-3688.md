---
id: pm-hist-3688
kind: postmortem
title: "INC-3688: postgres-ledger disk full; restart extended the outage"
author: Marcus Oyelaran
date: 2026-02-26T11:00:00+05:30
services: [postgres-ledger, ledger-svc]
symptom: write_failures
format: md
---
# INC-3688: postgres-ledger disk full; restart extended the outage

**Date:** Thu 26 Feb 2026 · **Severity:** SEV-1 · **Author:** Marcus Oyelaran · **Status:** final

## Summary
At 03:12 IST the postgres-ledger data volume reached 100%. Every ledger write failed with `No space left on device`; reads kept working. At 03:24 I restarted Postgres, hoping it would release space. It did not: Postgres could not finish crash recovery on a full disk and stayed down until 04:05. Writes were restored at 04:19 after we deleted rotated logs and grew the EBS volume. The restart turned a 25-minute outage into a 67-minute one.

## Impact
- 67 minutes without ledger writes; checkout failed for most payment attempts from 03:12 to 04:19.
- 41 of those minutes are attributable to the restart.

## Root cause
`log_min_duration_statement = 0` was left enabled after a debugging session on 23 Feb. Postgres logged every statement and filled the volume in three days.

## Trigger
Disk usage crossing 100%. We had no alert below 95%.

## Resolution
Deleted rotated logs, expanded the volume from 500 GB to 750 GB online, reset `log_min_duration_statement` to 250 ms.

## What went wrong
- **Restarting Postgres on a full disk.** Crash recovery needs to write WAL. With no free space it cannot finish, and the database stays down. This added 41 minutes.
- Disk alert threshold too high to act on.

## Where we got lucky
- 3 AM traffic.

## Action items
| Action | Owner | Due |
|---|---|---|
| Disk alert at 85% and 95% on postgres-ledger | Rohan Mehta | 2026-03-05 |
| Runbook: never restart Postgres on a full disk; check logs, WAL and replication slots | Marcus Oyelaran | 2026-03-02 |
| Guardrail: log_min_duration_statement changes need DBA review | Rohan Mehta | 2026-03-12 |

## Lessons
Never restart Postgres on a full disk. Free space first (logs, WAL held by replication slots, bloat), or grow the volume online.
