---
id: pm-INC-4205
kind: postmortem
title: "INC-4205: acquirerx rate limiting again; failover in twelve minutes"
author: Meera Pillai
date: 2026-09-01T11:00:00+05:30
incident_id: INC-4205
services: [payments-svc, acquirerx, checkout-api]
symptom: latency_p99
format: md
---
# INC-4205: acquirerx rate limiting again

**Date:** Mon 31 Aug 2026 · **Severity:** SEV-2 · **On call:** Meera Pillai · **Author:** Meera Pillai

## Summary
A recurrence of INC-4133. From 13:21 IST acquirerx rate-limited us (HTTP 429 `rate_limit_exceeded`); checkout-api p99 reached 4.4 s and payments failed. The acquirerx status page was green again. I found INC-4133's postmortem, confirmed psp_http_429_rate was above 30% on acquirerx while ledger and Postgres were healthy, and failed over to paynova at 13:42. Recovered by 13:48.

## Impact
- 27 minutes at lunch. 7,925 failed payments, about ₹1.47 crore at risk.

## Timeline (IST)
- 12:56 unrelated checkout-api deploy (copy change); left alone this time
- 13:21 acquirerx 429s start
- 13:30 CheckoutLatencyP99High (p99 4,391 ms)
- 13:36 psp_http_429_rate on acquirerx 30%+; payments-svc logs `acquirerx charge failed ... 429`
- 13:42 psp.primary=paynova, backoff on
- 13:43 status.acquirerx.com moves to "degraded performance"
- 13:48 recovered

## What went well
- INC-4133's write-up made this a twelve-minute diagnosis. The red-herring deploy was not touched.

## What went wrong
- Still manual. The automatic failover action item from INC-4133 is due 9 Sep.
- Second throttling event in twelve days; our rate limit with acquirerx has not been raised.

## Action items
| Action | Owner | Due |
|---|---|---|
| Automatic failover to paynova on sustained 429s (carried over) | Tomás Ortega | 2026-09-09 |
| Escalate the acquirerx rate limit with their account manager | Kabir Malhotra | 2026-09-04 |

## Lessons
Checkout latency plus payment failures with healthy internal services: check psp_http_429_rate before anything else. Status pages lag by about 20 minutes.
