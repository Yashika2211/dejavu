---
id: slack-INC-4213
kind: slack
title: "#inc-4213 incident channel"
author: Meera Pillai
date: 2026-09-01T22:12:00+05:30
incident_id: INC-4213
services: [auth-svc, edge-gateway, nodes]
symptom: auth_failures
format: md
---
**#inc-4213**

**Meera Pillai** 22:12 ack AuthFailureRateHigh 20%. same alert as INC-4146 last week, checking certs
**Meera Pillai** 22:17 rotated the edge-gateway cert just in case
**Meera Pillai** 22:23 no change. auth-svc logs say `token used before issued`
**Meera Pillai** 22:26 restarting auth-svc
**Meera Pillai** 22:30 better for a few min then back. paging platform
**Deepak Rao** 22:33 node_clock_offset_ms on ip-10-42-1-23 is -49400. chronyd is dead on that node since 19:20. draining it
**Deepak Rao** 22:45 drained, pods rescheduled, failures back to baseline
**Meera Pillai** 22:46 thanks, ~1/6 failing should have told me it wasn't the cert
