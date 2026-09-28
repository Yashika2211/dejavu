---
id: pm-INC-4178
kind: postmortem
title: "INC-4178: payments-svc 503s from a retry storm (checkout.retry_policy flag)"
author: Tomás Ortega
date: 2026-08-26T11:00:00+05:30
incident_id: INC-4178
services: [checkout-api, payments-svc]
symptom: error_rate_5xx
format: md
---
# INC-4178: payments-svc 503s from a retry storm

**Date:** Tue 25 Aug 2026 · **Severity:** SEV-2 · **On call:** Tomás Ortega · **Author:** Tomás Ortega

## Summary
12:10 IST: `checkout.retry_policy` flipped standard -> aggressive for EXP-352 (maxAttempts 2 -> 6, backoff 400 ms -> 50 ms). No deploy. payments-svc RPS went to about 4x while edge traffic was flat; payments-svc shed load with 503s (22% at the alert) and the retries fed themselves. Reverting the flag at 12:40 ended it by 12:45.

## Impact
- 32 minutes, lunch peak. 13,036 failed payments, about ₹2.41 crore at risk.

## Timeline (IST)
- 12:10 flag flipped (chg-99ad02)
- 12:13 payments-svc 503s start
- 12:20 PaymentsErrorRateHigh
- 12:26 scaled payments-svc 4 -> 8: no effect
- 12:32 restarted payments-svc: a minute or two of relief
- 12:40 reverted the flag
- 12:45 recovered

## What went wrong
- Scaled and restarted before reading the change log. The flag flip was the only change.
- RFC-011 (March) warned about exactly this and asked for a small rollout percentage. The flag went to 100%.

## Action items
| Action | Owner | Due |
|---|---|---|
| retry_policy changes require Payments review and a 5% rollout | Tomás Ortega | 2026-09-01 |
| Alert when payments-svc RPS / edge RPS > 2 | Priya Raman | 2026-09-04 |

## Lessons
payments-svc RPS up several times with flat user traffic = retry amplification. Check flags. Scaling payments-svc just absorbs more retries.
