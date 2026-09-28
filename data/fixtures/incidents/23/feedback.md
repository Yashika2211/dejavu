---
id: fb-INC-4356
kind: feedback
title: "On-call feedback on INC-4356"
author: Farhan Qureshi
date: 2026-09-24T23:10:00+05:30
incident_id: INC-4356
services: [nodes, auth-svc]
symptom: auth_failures
format: md
---
Farhan Qureshi (on-call) confirmed: INC-4356 was clock skew on node ip-10-42-2-14 (51 s behind, chronyd dead), a recurrence of INC-4213. Draining the node fixed it; no certificate or auth-svc changes were needed.
