---
id: fb-INC-4205
kind: feedback
title: "On-call feedback on INC-4205"
author: Meera Pillai
date: 2026-08-31T14:00:00+05:30
incident_id: INC-4205
services: [acquirerx, payments-svc]
symptom: latency_p99
format: md
---
Meera Pillai (on-call) confirmed: INC-4205 was acquirerx rate limiting (HTTP 429), a recurrence of INC-4133. Failing over to paynova fixed it. The checkout-api deploy at 12:56 was unrelated and was correctly left alone.
