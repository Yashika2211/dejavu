---
id: fb-INC-4165
kind: feedback
title: "On-call feedback on INC-4165"
author: Tomás Ortega
date: 2026-08-24T20:15:00+05:30
incident_id: INC-4165
services: [ledger-svc]
symptom: latency_p99
format: md
---
Tomás Ortega (on-call) confirmed: INC-4165 was a recurrence of INC-4127, ledger-svc connection pool exhaustion caused by the 3.15.1 deploy (chg-0044b2), whose batched tier lookup still runs inside the posting transaction. Rolling back ledger-svc fixed it; no restart was needed or tried.
