---
id: fb-INC-4311
kind: feedback
title: "On-call feedback on INC-4311"
author: Priya Raman
date: 2026-09-16T13:15:00+05:30
incident_id: INC-4311
services: [postgres-ledger]
symptom: latency_p99
format: md
---
Priya Raman (on-call) confirmed: INC-4311 was a missing (account_id, created_at) index on ledger_entries after Flyway migration V95 (chg-73b58d), a recurrence of INC-4186, not pool exhaustion. Creating the index concurrently on postgres-ledger fixed it. The pool was deliberately left alone: raising it made INC-4186 worse.
