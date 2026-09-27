---
id: fb-INC-4150
kind: feedback
title: "On-call feedback on INC-4150"
author: Priya Raman
date: 2026-08-22T11:10:00+05:30
incident_id: INC-4150
services: [fraud-scorer]
symptom: latency_p99
format: md
---
Priya Raman (on-call) confirmed: INC-4150 was a memory leak in fraud-scorer from model v47 (unbounded feature cache), causing an OOMKilled restart loop. Rolling the model back to v46 fixed it. Restarting fraud-scorer and scaling out to six pods each only delayed the next OOM by about ten minutes.
