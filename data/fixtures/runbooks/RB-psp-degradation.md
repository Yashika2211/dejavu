---
id: RB-psp-degradation
title: payment processor (PSP) degradation and failover
services: [payments-svc, acquirerx, paynova]
keywords: [psp, acquirerx, paynova, 429, rate, limit, throttling, failover, payments, failures, declines]
author: Marcus Oyelaran
last_edited: 2026-04-18
---
# PSP degradation and failover

acquirerx is primary for cards and UPI; paynova is secondary. Routing is the flag `psp.primary`.

1. query_metrics on acquirerx: psp_http_429_rate and psp_latency_p99_ms. Normal 429 rate is well under 1%.
2. Do not trust the status page. status.acquirerx.com usually says "All Systems Operational" for the first 15-30 minutes of an incident.
3. Normal declines (`insufficient_funds`, `do_not_honor`) are not an outage. Look for `rate_limit_exceeded` or 5xx.
4. To fail over: set `psp.primary=paynova` (flag service, takes a minute) and make sure payments-svc backoff is enabled. Fail back once acquirerx has been healthy for 30 minutes.
5. Rolling back payments-svc does nothing for a PSP-side problem.
6. Tell #payments-partners so someone chases the acquirerx account manager.
