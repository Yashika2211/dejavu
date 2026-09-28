---
id: fb-INC-4193
kind: feedback
title: "On-call feedback on INC-4193"
author: Tomás Ortega
date: 2026-08-29T21:00:00+05:30
incident_id: INC-4193
services: [notifications-worker, auth-svc]
symptom: auth_failures
format: md
---
Tomás Ortega (on-call) corrected the initial read of INC-4193: it was not an auth-svc or certificate problem. The root cause was a Kafka consumer rebalance storm in notifications-worker after the 2.9.2 deploy (chg-42c765), whose slow template rendering exceeded max.poll.interval.ms; delayed OTPs expired and failed step-up auth. Rolling back notifications-worker fixed it. Restarting auth-svc did nothing, and scaling out notifications-worker made it worse (more rebalances).
