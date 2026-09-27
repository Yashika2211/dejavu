---
id: pm-INC-4133
kind: postmortem
title: "INC-4133: checkout latency and payment failures from acquirerx rate limiting"
author: Priya Raman
date: 2026-08-20T11:00:00+05:30
incident_id: INC-4133
services: [payments-svc, acquirerx, checkout-api]
symptom: latency_p99
format: md
---
# INC-4133: checkout latency and payment failures from acquirerx rate limiting

**Date:** Wed 19 Aug 2026 · **Severity:** SEV-2 · **On call:** Priya Raman · **Author:** Priya Raman

## Summary
From 13:51 to 14:28 IST acquirerx rate-limited our merchant account (HTTP 429, `rate_limit_exceeded`, `retry_after_s: 2`). payments-svc retried with backoff, so checkout-api p99 rose to 5.4 s and a large share of payments failed. Every internal service was healthy. We failed routing over to paynova at 14:22 and it recovered by 14:28.

## Impact
- 37 minutes during the lunch peak.
- 9,016 failed payments, about ₹1.67 crore of payment volume at risk.

## Root cause
External: acquirerx throttling. The acquirerx status page said "All Systems Operational" until about 14:13, twenty minutes after it started.

## Timeline (IST)
- 13:29 unrelated checkout-api deploy (UPI screen copy change)
- 13:51 acquirerx 429 rate climbs to ~30%
- 14:03 CheckoutLatencyP99High fires (p99 5,382 ms)
- 14:09 status.acquirerx.com: all operational
- 14:12 I rolled back the checkout-api copy-change deploy; no change (6 minutes lost)
- 14:18 found `acquirerx charge failed ... 429 rate_limit_exceeded` in payments-svc logs
- 14:22 failed over to paynova (psp.primary=paynova), backoff on
- 14:28 recovered

## What went well
- Failover took two minutes once we decided.

## What went wrong
- I rolled back the most recent deploy just because it was the most recent. It was a copy change.
- I trusted the status page.
- I also checked DNS first because RB-checkout-latency says to. DNS was fine.

## Action items
| Action | Owner | Due |
|---|---|---|
| Alert on psp_http_429_rate > 5% for acquirerx | Tomás Ortega | 2026-08-26 |
| Automatic failover to paynova when 429s exceed 20% for 3 minutes | Tomás Ortega | 2026-09-09 |
| Raise our acquirerx rate limit with the account manager | Kabir Malhotra | 2026-08-28 |

## Lessons
Check psp_http_429_rate and payments-svc logs before rolling anything back. The acquirerx status page lags reality by 15-30 minutes.
