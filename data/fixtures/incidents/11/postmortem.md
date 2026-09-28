---
id: pm-INC-4230
kind: postmortem
title: "INC-4230: cold redis-cache after a Sentinel failover during node maintenance"
author: Sara Kim
date: 2026-09-04T16:00:00+05:30
incident_id: INC-4230
services: [redis-cache, ledger-svc, postgres-ledger]
symptom: latency_p99
format: md
---
# INC-4230: cold redis-cache after a Sentinel failover

**Date:** Fri 4 Sep 2026 · **Severity:** SEV-3 · **On call:** Meera Pillai · **Author:** Sara Kim (Platform)

## Summary
At 02:08 IST the node hosting the redis-cache primary was drained for kernel patching. Sentinel failed over to `10.42.5.31`, a replica still in a full resync, so the new primary came up with almost no keys. cache_hit_ratio fell to about 5%, every balance lookup fell through to postgres-ledger (CPU 93%), and ledger-svc p99 reached 3.2 s. Restarting ledger-svc did nothing. Request coalescing plus a cache warm-up at 02:26 fixed it by 02:33. Same shape as Marcus's INC-3951 in July.

## Impact
- 24 minutes overnight. 452 failed payments, about ₹8.4 lakh at risk.

## Context
PgBouncer (M1) had gone live for ledger-svc 12 hours earlier. Postgres was the victim here, not the cause; PgBouncer behaved.

## Timeline (IST)
- 02:08 `+switch-master kestrel-cache 10.42.2.14 6379 10.42.5.31 6379`
- 02:09 hit ratio collapses; pg CPU climbs
- 02:14 LedgerLatencyP99High (3,150 ms)
- 02:20 restart ledger-svc: no change
- 02:26 coalescing on, warm-up via `/admin/cache/warm`, temporary rate limit on GET /balance
- 02:33 recovered

## Action items
| Action | Owner | Due |
|---|---|---|
| Do not drain the node running the cache primary; fail over deliberately first | Sara Kim | 2026-09-09 |
| Block promotion of replicas mid-resync (INC-3951's action item, still open) | Sara Kim | 2026-09-09 |

## Lessons
LedgerLatencyP99High with pg CPU high and cache_hit_ratio near zero: check Sentinel logs for `+switch-master` and warm the cache. Do not restart Postgres and do not add indexes; the queries are fine, there are just too many of them.
