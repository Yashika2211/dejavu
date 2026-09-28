---
id: slack-INC-4249
kind: slack
title: "#inc-4249 incident channel"
author: Meera Pillai
date: 2026-09-06T18:57:00+05:30
incident_id: INC-4249
services: [ledger-svc, pgbouncer-ledger]
symptom: latency_p99
format: md
---
**#inc-4249**

**Meera Pillai** 18:57 ack checkout p99 6.6s. ledger pool pinned at 10/10, pending ~25
**Meera Pillai** 19:01 RB-ledger-pool says raise hikari, bumping 10 -> 20
**Meera Pillai** 19:07 no change at all
**Meera Pillai** 19:09 restarting ledger-svc
**Meera Pillai** 19:13 back again after 3 min. paging core ledger
**Farhan Qureshi** 19:15 we're behind pgbouncer since thursday, hikari doesn't matter now. pgbouncer_cl_waiting is 120+, logs full of query_wait_timeout. @Rohan ok to raise default_pool_size to 40?
**Rohan Mehta** 19:16 yes go
**Farhan Qureshi** 19:24 recovered. rolling back 3.16.3 too, the fx lookup is inside the transaction
**Farhan Qureshi** 19:25 and yes I owe everyone a runbook update
