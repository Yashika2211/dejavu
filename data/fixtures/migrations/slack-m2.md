---
id: slack-m2
kind: announcement
title: "#eng-announce: redis-cache replaced by valkey-cache"
author: Sara Kim
date: 2026-09-10T14:50:00+05:30
services: [valkey-cache, redis-cache]
symptom: null
format: md
---
**#eng-announce**, Thu 10 Sep 2026

**Sara Kim** 14:50
Valkey migration done (RFC-015). All clients are on `valkey-cache`; `redis-cache` has been deleted. Hit ratio back to 95% after warm-up.

**Sara Kim** 14:51
Heads up for on-call: anything that says `redis-cli -h redis-cache` is dead. Use `valkey-cli -h valkey-cache`. RB-cache-failover still has the old commands; I'll fix it after the freeze.

**Deepak Rao** 14:55
👍 updating the dashboards now
