---
id: slack-INC-4230
kind: slack
title: "#inc-4230 incident channel"
author: Meera Pillai
date: 2026-09-04T02:16:00+05:30
incident_id: INC-4230
services: [ledger-svc, redis-cache, postgres-ledger]
symptom: latency_p99
format: md
---
**#inc-4230**

**Meera Pillai** 02:16 ack LedgerLatencyP99High 3.1s. pg cpu 93%
**Meera Pillai** 02:20 restarting ledger-svc
**Meera Pillai** 02:23 nothing. ledger logs: `balance cache miss ... loading from database` hundreds per minute
**Sara Kim** 02:24 redis-cache failed over at 02:08, the drain for kernel patching took the primary's node. new primary is nearly empty. same as INC-3951
**Sara Kim** 02:26 coalescing + warm-up running, rate limit on GET /balance for now
**Sara Kim** 02:33 hit ratio 90%, pg 35%, latency normal
