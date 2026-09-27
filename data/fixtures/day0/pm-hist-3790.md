---
id: pm-hist-3790
kind: postmortem
title: "INC-3790: fraud-scorer OOM loop after model v31"
author: Marcus Oyelaran
date: 2026-04-08T20:00:00+05:30
services: [fraud-scorer, checkout-api]
symptom: latency_p99
format: md
---
# INC-3790: fraud-scorer OOM loop after model v31

**Date:** Wed 8 Apr 2026 · **Severity:** SEV-2 · **Author:** Marcus Oyelaran · **Status:** final

## Summary
fraud-scorer pods were OOM-killed every 10-12 minutes after model v31 went out at 15:40. While pods restarted, checkout-api waited out its 1.5 s fraud timeout and pushed payments into manual review. Checkout p99 reached 3.1 s. Rolling the model back to v30 at 17:02 fixed it.

## Impact
- 1 h 20 min of elevated checkout latency; manual review queue grew by about 2,400 payments.

## Root cause
Model v31 added a per-merchant feature that was cached in an unbounded in-process dict. Memory grew until the container hit its 2Gi limit (exit code 137).

## What we tried
- Restarting fraud-scorer: fine for about ten minutes, then the OOMs resumed.
- Scaling out 3 -> 6: bought time, doubled cost, did not fix anything.
- Rolling back the model: fixed it.

## Action items
| Action | Owner | Due |
|---|---|---|
| Canary new model artifacts on one pod for 30 minutes | Vikram Shetty | 2026-04-22 |
| Memory soak test in CI for model releases | Ishita Bose | 2026-05-06 |

## Lessons
If memory climbs again after a restart, it is the artifact. Roll back the model; restarts and scaling only buy time.
