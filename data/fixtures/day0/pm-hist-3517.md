---
id: pm-hist-3517
kind: postmortem
title: "INC-3517: checkout latency and payment failures during lunch peak"
author: Marcus Oyelaran
date: 2026-01-14T18:30:00+05:30
services: [checkout-api, payments-svc, coredns]
symptom: latency_p99
format: md
---
# INC-3517: checkout latency and payment failures during lunch peak

**Date:** Wed 14 Jan 2026 · **Severity:** SEV-2 · **Author:** Marcus Oyelaran · **Status:** final

## Summary
Between 12:29 and 13:21 IST checkout-api p99 latency rose to about 4.8 s and roughly 18% of payments failed. We traced it to CoreDNS saturation during the lunch peak: lookups from payments-svc were timing out. Scaling CoreDNS from 2 to 4 replicas restored normal latency.

## Impact
- 52 minutes of degraded checkout during the 12:00-14:00 peak.
- About 18% of payment attempts failed at the worst point; customers retried or abandoned.
- No data loss. Manual review queue unaffected.

## Root cause
CoreDNS (2 replicas) could not keep up with lunch-peak query volume. With ndots:5, every external lookup (api.acquirerx.com) fans out into several cluster-suffix queries. payments-svc logged `lookup ... i/o timeout` errors, and CoreDNS latency_p99 went from ~5 ms to ~40 ms.

## Trigger
Traffic growth. No deploys in the preceding 6 hours.

## Detection
CheckoutLatencyP99High paged at 12:34. The acquirerx status page was green throughout.

## Resolution
Scaled CoreDNS to 4 replicas at 13:05. Latency recovered by 13:21.

## Timeline (IST)
- 12:29 checkout p99 starts climbing
- 12:34 alert fires; Marcus on call
- 12:41 payments-svc shows some acquirerx 429s, within what we usually see at peak
- 12:48 a few dozen DNS lookup timeouts in payments-svc logs; CoreDNS latency up
- 13:05 CoreDNS scaled 2 -> 4
- 13:21 latency back to normal

## What went well
- Quick to find the DNS errors once we looked.

## What went wrong
- Nobody had CoreDNS on a dashboard.
- 30 minutes before we looked at DNS at all.

## Where we got lucky
- It was lunch, not the evening peak.

## Action items
| Action | Owner | Due |
|---|---|---|
| Put CoreDNS latency and errors on the main dashboard | Sara Kim | 2026-01-28 |
| Evaluate NodeLocal DNSCache | Deepak Rao | 2026-02-15 |
| Add "check DNS first" to the checkout latency runbook | Marcus Oyelaran | 2026-01-21 |

## Lessons
When checkout is slow and nothing was deployed, look at DNS early.
