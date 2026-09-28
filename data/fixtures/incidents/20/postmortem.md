---
id: pm-INC-4320
kind: postmortem
title: "INC-4320: retry storm again; checkout.retry_policy flipped to 100%"
author: Priya Raman
date: 2026-09-20T12:00:00+05:30
incident_id: INC-4320
services: [checkout-api, payments-svc]
symptom: error_rate_5xx
format: md
---
# INC-4320: retry storm again

**Date:** Sat 19 Sep 2026 · **Severity:** SEV-2 · **On call:** Priya Raman · **Author:** Priya Raman

## Summary
A recurrence of INC-4178. At 20:20 IST `checkout.retry_policy` was set to `aggressive` for EXP-338 (chg-6394ce). The plan was 5% of traffic, as INC-4178's action item requires, but the flag UI applied it to 100%. payments-svc RPS went to about 4x with flat edge traffic and it shed load with 503s (21%). I recognised INC-4178 from the RPS ratio and reverted the flag at 20:35; recovered by 20:40.

## Impact
- 17 minutes at the Saturday evening peak. 6,962 failed payments, about ₹1.29 crore at risk.

## What went well
- Five minutes from page to fix. No scaling or restarts this time.

## What went wrong
- The 5% rollout rule from INC-4178 is a convention, not something the flag service enforces.
- The alert on payments-svc RPS / edge RPS (INC-4178 action item) was not live yet.

## Action items
| Action | Owner | Due |
|---|---|---|
| Flag service: `checkout.retry_policy` changes limited to 10% without a second approver | Tomás Ortega | 2026-09-25 |
| Ship the payments-svc / edge RPS ratio alert | Priya Raman | 2026-09-22 |

## Lessons
payments-svc 5xx with its RPS several times the edge's: look for a retry_policy flag change and revert it first.
