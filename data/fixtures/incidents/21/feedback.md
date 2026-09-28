---
id: fb-INC-4327
kind: feedback
title: "On-call feedback on INC-4327"
author: Farhan Qureshi
date: 2026-09-21T11:50:00+05:30
incident_id: INC-4327
services: [ledger-svc, pgbouncer-ledger]
symptom: latency_p99
format: md
---
Farhan Qureshi (on-call) confirmed: INC-4327 was ledger-svc connection pool exhaustion caused by the 3.19.0 deploy (chg-e3d988), which put a synchronous audit-trail call inside the posting transaction. Behind PgBouncer the queue showed up as pgbouncer_cl_waiting. Rolling back ledger-svc fixed it; HikariCP was deliberately left alone.
