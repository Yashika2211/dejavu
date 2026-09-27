---
id: pm-INC-4150
kind: postmortem
title: "INC-4150: fraud-scorer OOM loop after model v47"
author: Ishita Bose
date: 2026-08-24T10:30:00+05:30
incident_id: INC-4150
services: [fraud-scorer, checkout-api]
symptom: latency_p99
format: md
---
# INC-4150: fraud-scorer OOM loop after model v47

**Date:** Sat 22 Aug 2026 · **Severity:** SEV-3 · **On call:** Priya Raman · **Author:** Ishita Bose (Risk ML)

## Summary
Model v47 (released 09:33 IST, chg-92e8a5) replaced the bounded LRU feature cache with an in-process dict keyed by merchant and hour. fraud-scorer memory climbed to the 2Gi limit roughly every 11 minutes and the pods were OOM-killed (exit code 137). While pods restarted, checkout-api waited out its 1.5 s fraud timeout and sent payments to manual review; checkout p99 reached 3.2 s. Rolling the model back to v46 at 10:42 fixed it by 10:52.

## Impact
- 43 minutes of elevated checkout latency and a growing manual review queue.
- 776 failed payments (mostly abandonment), about ₹14.4 lakh at risk.

## Timeline (IST)
- 09:33 model v46 -> v47
- 10:09 first OOMKilled events
- 10:15 CheckoutLatencyP99High fires (p99 3,226 ms)
- 10:20 restart fraud-scorer: fine for ~10 minutes, then OOMs resume
- 10:33 scaled 3 -> 6 pods: delayed the next OOM, did not stop it
- 10:42 rolled back to v46
- 10:52 memory flat, restarts stop

## What went wrong
- We repeated INC-3790's playbook in the wrong order: restart, scale, and only then roll back.
- The memory soak test promised after INC-3790 never shipped.

## Action items
| Action | Owner | Due |
|---|---|---|
| Memory soak test (2 h at peak replay) gating model releases | Ishita Bose | 2026-09-04 |
| Canary model artifacts on one pod for 30 minutes | Vikram Shetty | 2026-09-01 |

## Lessons
OOMKilled with a sawtooth memory graph right after a model release: roll back the model first. Restarts and scale-outs only buy minutes.
