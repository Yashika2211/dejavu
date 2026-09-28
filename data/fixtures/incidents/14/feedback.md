---
id: fb-INC-4275
kind: feedback
title: "On-call feedback on INC-4275"
author: Deepak Rao
date: 2026-09-11T02:10:00+05:30
incident_id: INC-4275
services: [valkey-cache, ledger-svc]
symptom: latency_p99
format: md
---
Deepak Rao (on-call) confirmed: INC-4275 was a cache stampede after a valkey-cache failover to a cold replica, the same failure mode as INC-4230 but on the new Valkey cluster. Warming valkey-cache fixed it. Actions that target redis-cache fail: it was removed in the 10 Sep migration, and RB-cache-failover still uses the old host.
