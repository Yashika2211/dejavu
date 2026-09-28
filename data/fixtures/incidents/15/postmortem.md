---
id: pm-INC-4293
kind: postmortem
title: "INC-4293: fraud-scorer OOM loop after model v52"
author: Vikram Shetty
date: 2026-09-13T11:00:00+05:30
incident_id: INC-4293
services: [fraud-scorer, checkout-api]
symptom: latency_p99
format: md
---
# INC-4293: fraud-scorer OOM loop after model v52

**Date:** Sat 12 Sep 2026 · **Severity:** SEV-3 · **On call:** Deepak Rao · **Author:** Vikram Shetty (Risk ML)

## Summary
Model v52 (released 15:43 IST, chg-63c54c) was trained from a branch cut before the feature-cache fix from INC-4150 merged, so it shipped the same unbounded cache. OOMKilled restarts started at 16:15; checkout p99 reached 3.9 s from fraud timeouts. Deepak recognised INC-4150 and rolled the model back to v51 at 16:31; recovered by 16:41.

## Impact
- 26 minutes. 634 failed payments, about ₹11.7 lakh at risk.

## What went wrong
- The memory soak test from INC-4150 runs for 30 minutes; the leak takes about 35 minutes to hit the limit at Saturday traffic.

## Action items
| Action | Owner | Due |
|---|---|---|
| Soak test 2 hours at replayed peak traffic | Ishita Bose | 2026-09-18 |
| Model builds refuse branches without the cache fix | Vikram Shetty | 2026-09-16 |

## Lessons
OOMKilled right after a model release: roll back the model. Straight to the rollback worked: 6 minutes from page to fix.
