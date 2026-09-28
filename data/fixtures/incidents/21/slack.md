---
id: slack-INC-4327
kind: slack
title: "#inc-4327 incident channel"
author: Farhan Qureshi
date: 2026-09-21T11:22:00+05:30
incident_id: INC-4327
services: [ledger-svc, pgbouncer-ledger]
symptom: latency_p99
format: md
---
**#inc-4327**

**Farhan Qureshi** 11:22 ack checkout p99 7.1s. pgbouncer_cl_waiting 130 and climbing, query_wait_timeout in pgbouncer logs. not touching hikari
**Farhan Qureshi** 11:24 3.19.0 went out 11:07, sync audit trail inside the posting tx. rolling back
**Ananya Iyer** 11:25 yes please, sorry
**Farhan Qureshi** 11:36 recovered, cl_waiting 0
**Ananya Iyer** 11:40 fourth time with the same shape. I'm adding a mandatory review for anything touching the posting transaction
