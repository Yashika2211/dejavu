---
id: pm-INC-4307
kind: postmortem
title: "INC-4307: payments-svc CPU throttling after a limits change"
author: Tomás Ortega
date: 2026-09-15T18:00:00+05:30
incident_id: INC-4307
services: [payments-svc, checkout-api]
symptom: latency_p99
format: md
---
# INC-4307: payments-svc CPU throttling after a limits change

**Date:** Tue 15 Sep 2026 · **Severity:** SEV-2 · **On call:** Priya Raman · **Author:** Tomás Ortega (Payments)

## Summary
11:40 IST: Helm values change for payments-svc, `resources.limits.cpu` 2000m -> 500m per pod (FINOPS-232, chg-10fd11). At lunch load the pods hit their CFS quota; `cpu_throttle_ratio` went above 0.5 and CPU sat flat at the new limit. Charge handling slowed, checkout p99 4.8 s. Restart: no change (same limits). Scale 4 -> 8: partial relief. Reverting the limit at 12:10 fixed it by 12:18.

## Impact
- 36 minutes. 4,681 failed payments, about ₹86.6 lakh at risk.

## Why it took 20 minutes
Throttling does not log anything. The signal is in metrics only: cpu_throttle_ratio and CPU pinned at exactly the limit. The PSP was healthy and the ledger was healthy, which ruled out the usual suspects but did not point anywhere.

## Action items
| Action | Owner | Due |
|---|---|---|
| Alert on cpu_throttle_ratio > 0.25 for 5 minutes | Deepak Rao | 2026-09-18 |
| Limits changes on payment-path services need the owning team's approval | Kabir Malhotra | 2026-09-18 |
| Load test before right-sizing limits | Deepak Rao | 2026-09-25 |

## Lessons
Slow service, no errors in logs, CPU flat at a round number: check cpu_throttle_ratio and recent Helm changes. Revert the limit; restarts keep the same limit and scaling out only dilutes it.
