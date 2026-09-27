---
id: RB-cache-failover
title: redis-cache failover and cold cache
services: [redis-cache, ledger-svc, postgres-ledger]
keywords: [redis, cache, sentinel, failover, switch-master, cold, stampede, hit, ratio, miss]
author: Marcus Oyelaran
last_edited: 2026-06-22
---
# redis-cache failover and cold cache

After a Sentinel failover the new primary can come up cold. Every cache miss falls through to postgres-ledger and the database melts.

1. Confirm the failover:
   `redis-cli -h redis-cache -p 26379 SENTINEL get-master-addr-by-name kestrel-cache`
   and look for `+switch-master` in the redis-cache logs.
2. Check cache_hit_ratio on redis-cache and pg_cpu_pct on postgres-ledger.
3. Enable request coalescing and warm the balance cache:
   `kubectl -n prod exec deploy/ledger-svc -- curl -XPOST localhost:8081/admin/cache/warm`
   Turn on the temporary rate limit on GET /balance if Postgres stays above 90%.
4. **Do not restart postgres-ledger.** It will not warm the cache and it drops every connection.
5. Adding indexes does not help; the queries are fine, there are just too many of them.
