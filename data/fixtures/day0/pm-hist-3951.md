---
id: pm-hist-3951
kind: postmortem
title: "INC-3951: ledger latency after a redis-cache failover (cold cache)"
author: Marcus Oyelaran
date: 2026-07-29T12:00:00+05:30
services: [redis-cache, ledger-svc, postgres-ledger]
symptom: latency_p99
format: md
---
# INC-3951: ledger latency after a redis-cache failover (cold cache)

**Date:** Wed 29 Jul 2026 · **Severity:** SEV-2 · **Author:** Marcus Oyelaran · **Status:** final

## Summary
At 01:52 IST Sentinel failed redis-cache over to a replica that was mid full-resync. The new primary came up almost empty, cache_hit_ratio fell to 3%, every balance lookup hit postgres-ledger, and Postgres CPU went to 95%. ledger-svc p99 reached 3.8 s. Enabling request coalescing and warming the balance cache restored it in 20 minutes.

## What we did
- Confirmed the failover: `redis-cli -h redis-cache -p 26379 SENTINEL get-master-addr-by-name kestrel-cache` and `+switch-master` in the Sentinel log.
- Warmed the cache: `kubectl -n prod exec deploy/ledger-svc -- curl -XPOST localhost:8081/admin/cache/warm`.
- Turned on the temporary rate limit on GET /balance while it warmed.
- Rohan asked us not to restart Postgres; it would have dropped every connection and warmed nothing.

## Action items
| Action | Owner | Due |
|---|---|---|
| Block failover to replicas that are still syncing (min-replicas-to-write) | Sara Kim | 2026-08-12 |
| Make request coalescing the default for balance lookups | Farhan Qureshi | 2026-08-19 |

## Lessons
After a cache failover, check cache_hit_ratio before blaming the database. Warm the cache and coalesce requests; adding indexes or restarting Postgres does not help.
