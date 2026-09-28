---
id: slack-INC-4293
kind: slack
title: "#inc-4293 incident channel"
author: Deepak Rao
date: 2026-09-12T16:27:00+05:30
incident_id: INC-4293
services: [fraud-scorer, checkout-api]
symptom: latency_p99
format: md
---
**#inc-4293**

**Deepak Rao** 16:27 ack checkout p99 3.9s, fraud-scorer OOMKilled exit 137. model v52 went out at 15:43. same as INC-4150, rolling the model back
**Deepak Rao** 16:31 rolled back to v51
**Deepak Rao** 16:41 memory flat, no restarts, p99 normal
**Vikram Shetty** 16:50 v52 was cut from an old branch without the cache fix. on it
