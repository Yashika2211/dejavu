---
id: slack-INC-4275
kind: slack
title: "#inc-4275 incident channel"
author: Deepak Rao
date: 2026-09-11T01:42:00+05:30
incident_id: INC-4275
services: [valkey-cache, ledger-svc]
symptom: latency_p99
format: md
---
**#inc-4275**

**Deepak Rao** 01:42 ack ledger p99 4s. pg cpu 93%, cache hit ratio 0.05
**Deepak Rao** 01:45 +switch-master in the sentinel logs. following RB-cache-failover
**Deepak Rao** 01:47 warm-up against redis-cache -> "no such target". right. it's valkey-cache since yesterday
**Deepak Rao** 01:49 warm-up against valkey-cache
**Deepak Rao** 01:56 hit ratio 92%, latency normal. old primary got OOM killed, maxmemory isn't set on the valkey sts
**Sara Kim** 07:40 ugh, missed that in the migration. fixing today
