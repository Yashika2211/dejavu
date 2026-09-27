---
id: slack-INC-4133
kind: slack
title: "#inc-4133 incident channel"
author: Priya Raman
date: 2026-08-19T14:05:00+05:30
incident_id: INC-4133
services: [payments-svc, acquirerx, checkout-api]
symptom: latency_p99
format: md
---
**#inc-4133**

**Priya Raman** 14:05 ack, checkout p99 5.4s during lunch. runbook says check DNS first, coredns looks fine
**Priya Raman** 14:10 checkout-api deployed at 13:29, rolling that back
**Priya Raman** 14:18 no change after rollback. payments-svc logs full of `acquirerx charge failed` status 429 rate_limit_exceeded
**Tomás Ortega** 14:19 acquirerx status page?
**Priya Raman** 14:19 says all systems operational
**Tomás Ortega** 14:20 it always does for the first half hour. fail over to paynova, psp.primary=paynova
**Priya Raman** 14:22 done
**Priya Raman** 14:28 recovered. failures back to normal declines only
**Tomás Ortega** 14:31 fyi status page just went to "degraded performance" lol
