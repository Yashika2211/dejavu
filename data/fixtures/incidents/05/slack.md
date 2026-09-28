---
id: slack-INC-4165
kind: slack
title: "#inc-4165 incident channel"
author: Tomás Ortega
date: 2026-08-24T19:44:00+05:30
incident_id: INC-4165
services: [ledger-svc, checkout-api]
symptom: latency_p99
format: md
---
**#inc-4165**

**Tomás Ortega** 19:44 ack. checkout p99 7.7s. ledger pool pinned, pending 110+. looks exactly like INC-4127
**Tomás Ortega** 19:45 ledger 3.15.1 went out 19:28. @Ananya ok to roll back?
**Ananya Iyer** 19:46 yes, that's the tier re-land. roll it back
**Tomás Ortega** 19:49 rolling back to 3.15.0
**Tomás Ortega** 19:59 recovered. pool pending 0
**Ananya Iyer** 20:02 my bad, the batch call is still inside the transaction. fixing properly this week
