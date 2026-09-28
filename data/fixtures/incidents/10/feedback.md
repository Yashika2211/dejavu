---
id: fb-INC-4213
kind: feedback
title: "On-call feedback on INC-4213"
author: Meera Pillai
date: 2026-09-01T23:00:00+05:30
incident_id: INC-4213
services: [nodes, auth-svc]
symptom: auth_failures
format: md
---
Meera Pillai (on-call) corrected the initial read of INC-4213: it was not an expired certificate like INC-4146. The root cause was clock skew on node ip-10-42-1-23 (chronyd dead, clock 49 s behind), so pods on that node rejected tokens as "used before issued"; only about a sixth of auth requests failed. Draining the node fixed it. Rotating the edge-gateway certificate did nothing and restarting auth-svc gave only brief partial relief.
