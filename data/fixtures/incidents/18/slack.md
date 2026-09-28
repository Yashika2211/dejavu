---
id: slack-INC-4311
kind: slack
title: "#inc-4311 incident channel"
author: Priya Raman
date: 2026-09-16T12:37:00+05:30
incident_id: INC-4311
services: [postgres-ledger, ledger-svc]
symptom: latency_p99
format: md
---
**#inc-4311**

**Priya Raman** 12:37 ack checkout p99 6s. ledger pool is full BUT pg cpu is 94% and the slow log is all `Seq Scan on ledger_entries`. this is INC-4186 not INC-4127. not touching the pool
**Priya Raman** 12:38 V95 migration ran at 12:24. paging DBA for the index
**Neha Kulkarni** 12:41 confirmed, (account_id, created_at) missing again. creating it concurrently
**Neha Kulkarni** 13:01 index done, cpu 31%, recovered
**Rohan Mehta** 13:03 nice call on the pool Priya
