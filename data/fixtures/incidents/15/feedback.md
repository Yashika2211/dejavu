---
id: fb-INC-4293
kind: feedback
title: "On-call feedback on INC-4293"
author: Deepak Rao
date: 2026-09-12T17:00:00+05:30
incident_id: INC-4293
services: [fraud-scorer]
symptom: latency_p99
format: md
---
Deepak Rao (on-call) confirmed: INC-4293 was a recurrence of INC-4150, a fraud-scorer memory leak from model v52 (unbounded feature cache) causing an OOM restart loop. Rolling the model back to v51 fixed it without any restarts or scaling.
