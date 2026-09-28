---
id: slack-INC-4307
kind: slack
title: "#inc-4307 incident channel"
author: Priya Raman
date: 2026-09-15T11:52:00+05:30
incident_id: INC-4307
services: [payments-svc, checkout-api]
symptom: latency_p99
format: md
---
**#inc-4307**

**Priya Raman** 11:52 ack checkout p99 4.8s. acquirerx 429s normal, ledger pool normal. payments-svc p99 is the slow part
**Priya Raman** 11:56 restarting payments-svc
**Priya Raman** 12:01 no change. scaling to 8
**Priya Raman** 12:06 a bit better. cpu_throttle_ratio is 0.58?? cpu flat at exactly 2.0 cores across 4 pods
**Deepak Rao** 12:08 oh no. I cut the cpu limit to 500m at 11:40 for FINOPS-232. reverting
**Deepak Rao** 12:10 reverted to 2000m
**Priya Raman** 12:18 back to normal
