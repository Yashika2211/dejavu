---
id: slack-INC-4150
kind: slack
title: "#inc-4150 incident channel"
author: Priya Raman
date: 2026-08-22T10:17:00+05:30
incident_id: INC-4150
services: [fraud-scorer, checkout-api]
symptom: latency_p99
format: md
---
**#inc-4150**

**Priya Raman** 10:17 ack checkout p99 3.2s. checkout-api logs: `fraud-scorer timeout, falling back to manual review`
**Priya Raman** 10:19 fraud-scorer pods getting OOMKilled, exit 137. restarting them
**Priya Raman** 10:31 back to OOMing. scaling to 6 to buy time
**Ishita Bose** 10:38 looking. v47 went out at 09:33 and the feature cache is unbounded in that build. rolling back to v46
**Priya Raman** 10:52 memory flat, no restarts for 10 min, p99 normal
**Ishita Bose** 10:53 sorry all. soak test is going in this week
