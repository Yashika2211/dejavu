---
id: pm-INC-4343
kind: postmortem
title: "INC-4343: postgres-ledger disk full from WAL held by a stale replication slot"
author: Rohan Mehta
date: 2026-09-23T15:00:00+05:30
incident_id: INC-4343
services: [postgres-ledger, ledger-svc, checkout-api]
symptom: write_failures
format: md
---
# INC-4343: postgres-ledger disk full from WAL held by a stale replication slot

**Date:** Wed 23 Sep 2026 · **Severity:** SEV-1 · **On call:** Farhan Qureshi · **Author:** Rohan Mehta (Data Platform)

## Summary
At 04:44 IST the postgres-ledger volume reached 100% and every ledger write failed (`could not extend file ... No space left on device`; a few `PANIC: could not write to file "pg_wal/xlogtemp..."`). Reads kept working. The space was WAL retained by `debezium_ledger`, a logical replication slot left behind when we decommissioned the CDC connector in July; with nobody consuming it, Postgres kept every WAL segment for two months. Farhan restarted ledger-svc (no effect) and paged me. **Nobody restarted Postgres** (INC-3688: a restart on a full disk adds ~40 minutes of crash recovery). At 05:07 I dropped the inactive slot and grew the volume; writes were back by 05:19.

## Impact
- 35 minutes of failed ledger writes overnight; checkout failed for most payments in that window.
- 3,338 failed payments, about ₹61.8 lakh at risk.

## Timeline (IST)
- 19 Sep the 85% disk warning fired; acknowledged, not investigated
- 04:44 disk 100%, writes fail
- 04:51 LedgerWriteErrorsHigh (36.3%)
- 04:56 restart ledger-svc: no change
- 05:00 DBA paged; `pg_replication_slots` shows `debezium_ledger` active = false holding ~410 GB of WAL
- 05:07 slot dropped, volume 750 GB -> 1 TB online
- 05:19 writes recovered

## Action items
| Action | Owner | Due |
|---|---|---|
| Alert on any inactive replication slot retaining > 10 GB of WAL | Rohan Mehta | 2026-09-25 |
| Decommissioning checklist: drop replication slots | Neha Kulkarni | 2026-09-30 |
| 85% disk warning pages the DBA during business hours | Rohan Mehta | 2026-09-25 |

## Lessons
Writes failing, reads fine, disk at 100%: look at WAL and replication slots first. Drop stale slots and grow the volume online. Never restart Postgres on a full disk.
