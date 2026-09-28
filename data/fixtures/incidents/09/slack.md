---
id: slack-INC-4205
kind: slack
title: "#inc-4205 incident channel"
author: Meera Pillai
date: 2026-08-31T13:32:00+05:30
incident_id: INC-4205
services: [payments-svc, acquirerx]
symptom: latency_p99
format: md
---
**#inc-4205**

**Meera Pillai** 13:32 ack checkout p99 4.4s + payment failures. ledger pool fine, pg fine
**Meera Pillai** 13:36 acquirerx 429 rate 31%, payments-svc logs rate_limit_exceeded. same as INC-4133
**Meera Pillai** 13:37 status page green, as usual
**Meera Pillai** 13:42 failing over to paynova
**Tomás Ortega** 13:44 👍 auto-failover is almost done, sorry
**Meera Pillai** 13:48 recovered
