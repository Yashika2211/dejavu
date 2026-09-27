---
id: fb-INC-4127
kind: feedback
title: "On-call feedback on INC-4127"
author: Priya Raman
date: 2026-08-17T03:45:00+05:30
incident_id: INC-4127
services: [ledger-svc]
symptom: latency_p99
format: md
---
Priya Raman (on-call) confirmed the root cause of INC-4127: connection pool exhaustion in ledger-svc, triggered by the 3.14.0 deploy (chg-c3e375), which holds HikariCP connections inside the posting transaction. postgres-ledger was healthy throughout. Rolling back ledger-svc fixed it within minutes; restarting ledger-svc pods gave about three minutes of relief and then the pool saturated again.
