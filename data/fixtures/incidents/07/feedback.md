---
id: fb-INC-4186
kind: feedback
title: "On-call feedback on INC-4186"
author: Tomás Ortega
date: 2026-08-27T12:45:00+05:30
incident_id: INC-4186
services: [postgres-ledger, ledger-svc]
symptom: latency_p99
format: md
---
Tomás Ortega (on-call) corrected the initial read of INC-4186: this was not connection pool exhaustion like INC-4127 and INC-4165. The root cause was a missing (account_id, created_at) index on ledger_entries after Flyway migration V88 (chg-f8a8a7), which turned statement lookups into sequential scans; postgres-ledger CPU was pinned at 94%. Raising the HikariCP pool made it worse and rolling back ledger-svc did nothing. Creating the index concurrently on postgres-ledger fixed it.
