---
id: fb-INC-4343
kind: feedback
title: "On-call feedback on INC-4343"
author: Farhan Qureshi
date: 2026-09-23T05:35:00+05:30
incident_id: INC-4343
services: [postgres-ledger]
symptom: write_failures
format: md
---
Farhan Qureshi (on-call) confirmed: INC-4343 was postgres-ledger running out of disk because an inactive logical replication slot (debezium_ledger) retained WAL. Dropping the stale slot and growing the volume (DBA-approved) fixed it. Restarting ledger-svc did nothing, and Postgres was deliberately not restarted: on a full disk that extends the outage (INC-3688).
