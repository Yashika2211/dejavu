---
id: slack-INC-4127
kind: slack
title: "#inc-4127 incident channel"
author: Priya Raman
date: 2026-08-17T03:09:00+05:30
incident_id: INC-4127
services: [ledger-svc, checkout-api]
symptom: latency_p99
format: md
---
**#inc-4127**

**Priya Raman** 03:09 ack. CheckoutLatencyP99High, p99 6.6s. looking
**Priya Raman** 03:12 ledger-svc p99 is huge. lots of `HikariPool-1 - Connection is not available` in ledger logs
**Priya Raman** 03:13 restarting ledger-svc pods to clear it
**Priya Raman** 03:18 it came back. same errors. waiting=140 again
**Farhan Qureshi** 03:19 here. 3.14.0 went out at 02:54, it does the tier lookup inside the transaction. pg cpu is fine so it's our pool, not the db
**Farhan Qureshi** 03:21 rolling back to 3.13.2
**Priya Raman** 03:31 p99 back to ~450ms. pool pending 0. resolving
**Farhan Qureshi** 03:32 thanks. I'll write it up, no more ledger deploys at 3am please 🙃
