---
id: fb-INC-4249
kind: feedback
title: "On-call feedback on INC-4249"
author: Meera Pillai
date: 2026-09-06T19:40:00+05:30
incident_id: INC-4249
services: [ledger-svc, pgbouncer-ledger]
symptom: latency_p99
format: md
---
Meera Pillai (on-call) confirmed: INC-4249 was ledger-svc connection pool exhaustion caused by the 3.16.3 deploy (chg-604c0e), but since the PgBouncer migration on 3 Sep the queue is in PgBouncer (pgbouncer_cl_waiting, query_wait_timeout), not in HikariCP. Raising the HikariCP pool had no effect; restarting ledger-svc gave three minutes of relief. Raising PgBouncer default_pool_size fixed it, and the deploy was rolled back afterwards. RB-ledger-pool's advice to raise the HikariCP pool is out of date.
