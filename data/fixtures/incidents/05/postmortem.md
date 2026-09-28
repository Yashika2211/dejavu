---
id: pm-INC-4165
kind: postmortem
title: "INC-4165: ledger-svc pool exhaustion again, from the batched tier re-land"
author: Ananya Iyer
date: 2026-08-25T10:00:00+05:30
incident_id: INC-4165
services: [ledger-svc, checkout-api]
symptom: latency_p99
format: md
---
# INC-4165: ledger-svc pool exhaustion again, from the batched tier re-land

**Date:** Mon 24 Aug 2026 · **Severity:** SEV-2 · **On call:** Tomás Ortega · **Author:** Ananya Iyer (Core Ledger)

## Summary
A recurrence of INC-4127. ledger-svc 3.15.1 (deployed 19:28 IST, chg-0044b2, PR #2220) re-landed the account tier enrichment with batched lookups, but the batch call still ran inside the `@Transactional` posting block and took up to 2 s under evening load. HikariCP pinned at 20 active per pod with over 100 threads waiting. Tomás recognised the pattern from INC-4127 and rolled back to 3.15.0 at 19:49; checkout recovered by 19:59.

## Impact
- 27 minutes during the evening peak.
- 16,120 failed payments, about ₹2.98 crore of payment volume at risk.

## Root cause
Same failure mode as INC-4127: remote calls inside the posting transaction hold database connections until the pool is exhausted. Batching reduced the number of calls, not the time the connection is held.

## Timeline (IST)
- 19:28 ledger-svc 3.15.0 -> 3.15.1
- 19:32 pool saturated, checkout p99 climbing
- 19:42 CheckoutLatencyP99High (p99 7,744 ms)
- 19:49 rollback to 3.15.0, no restart attempted
- 19:59 recovered

## What went well
- Straight to the rollback: 7 minutes from page to action, thanks to INC-4127's write-up.

## What went wrong
- My re-land did not follow INC-4127's action item: the lookup had to move out of the transaction, not just be batched.
- No canary; the canary action item from INC-4127 was due on 28 Aug.

## Action items
| Action | Owner | Due |
|---|---|---|
| Resolve account tiers before opening the posting transaction | Ananya Iyer | 2026-08-28 |
| Lint rule: no outbound HTTP clients inside `@Transactional` methods | Farhan Qureshi | 2026-09-04 |
| Canary rollout for ledger-svc (carried over) | Farhan Qureshi | 2026-08-28 |

## Lessons
Any change that makes the posting transaction longer, especially a remote call inside it, will exhaust the pool at peak. The fix is a rollback, not a restart.
