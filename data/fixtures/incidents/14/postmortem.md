---
id: pm-INC-4275
kind: postmortem
title: "INC-4275: cold valkey-cache after a failover, 12 hours after the Valkey migration"
author: Deepak Rao
date: 2026-09-11T15:00:00+05:30
incident_id: INC-4275
services: [valkey-cache, ledger-svc, postgres-ledger]
symptom: latency_p99
format: md
---
# INC-4275: cold valkey-cache after a failover

**Date:** Fri 11 Sep 2026 · **Severity:** SEV-3 · **On call:** Deepak Rao · **Author:** Deepak Rao (Platform)

## Summary
- 12 hours after the Redis -> Valkey migration (M2, 10 Sep).
- The new valkey-cache primary was OOM-killed at 01:30 IST: `maxmemory` was not carried over to the Valkey StatefulSet. Sentinel promoted a replica that was still loading; hit ratio fell to ~5%; postgres-ledger CPU 93%; ledger-svc p99 4.0 s.
- 01:47 followed RB-cache-failover and ran the warm-up against `redis-cache`. **redis-cache no longer exists** (deleted on 10 Sep). Lost two minutes.
- 01:49 same warm-up against `valkey-cache`. Recovered by 01:56.

## Impact
- 25 minutes overnight. 379 failed payments, about ₹7.0 lakh at risk.

## Action items
| Action | Owner | Due |
|---|---|---|
| Set maxmemory + allkeys-lru on valkey-cache | Sara Kim | 2026-09-11 (done) |
| Update RB-cache-failover: valkey-cli -h valkey-cache, not redis-cli -h redis-cache | Deepak Rao | 2026-09-14 |
| Grep all runbooks for redis-cache | Deepak Rao | 2026-09-14 |

## Lessons
- Since 10 Sep the cache is `valkey-cache`. Commands and targets that say `redis-cache` are dead.
- Cold cache after a failover: warm up + coalesce. Do not restart Postgres.
