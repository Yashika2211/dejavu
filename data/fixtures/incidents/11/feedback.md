---
id: fb-INC-4230
kind: feedback
title: "On-call feedback on INC-4230"
author: Meera Pillai
date: 2026-09-04T02:50:00+05:30
incident_id: INC-4230
services: [redis-cache, ledger-svc]
symptom: latency_p99
format: md
---
Meera Pillai (on-call) confirmed: INC-4230 was a cache stampede after a redis-cache Sentinel failover to a cold replica (+switch-master at 02:08), not a database problem; postgres-ledger was overloaded by cache misses. Warming the cache with request coalescing fixed it. Restarting ledger-svc did nothing.
