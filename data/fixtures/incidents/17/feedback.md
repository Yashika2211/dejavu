---
id: fb-INC-4307
kind: feedback
title: "On-call feedback on INC-4307"
author: Priya Raman
date: 2026-09-15T12:30:00+05:30
incident_id: INC-4307
services: [payments-svc]
symptom: latency_p99
format: md
---
Priya Raman (on-call) confirmed: INC-4307 was CPU throttling in payments-svc caused by the Helm change that cut its CPU limit from 2000m to 500m (chg-10fd11). Reverting the limit fixed it. Restarting payments-svc did nothing and scaling out gave only partial relief.
