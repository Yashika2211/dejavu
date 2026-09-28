---
id: pm-INC-4316
kind: postmortem
title: "INC-4316: OTP failures because the smsbridge monthly quota ran out"
author: Kofi Mensah
date: 2026-09-18T17:00:00+05:30
incident_id: INC-4316
services: [smsbridge, notifications-worker, auth-svc]
symptom: auth_failures
format: md
---
# INC-4316: OTP failures because the smsbridge monthly quota ran out

**Date:** Fri 18 Sep 2026 · **Severity:** SEV-2 · **On call:** Priya Raman · **Author:** Kofi Mensah (Messaging)

## Summary
At 07:55 IST our smsbridge account hit its monthly SMS quota. Every send came back `HTTP 402 quota_exceeded`, OTPs were dead-lettered, and UPI step-up authentication failed (AuthFailureRateHigh, 17%). notifications-worker consumed messages normally; this was not lag or a rebalance storm. The smsbridge status page stayed green because the problem was specific to our account. Priya rolled back notifications-worker at 08:13 (nothing recent to roll back, no change) and paged Messaging at 08:19. I reached the smsbridge account manager, who raised the quota at 08:46.

## Impact
- 49 minutes during the morning ramp. 2,137 failed payments, about ₹39.5 lakh at risk.

## Root cause
OTP volume is up about 40% month on month since UPI step-up went to 100%, and nobody tracked our quota against it.

## How to tell it apart from INC-4193
- kafka_consumer_lag normal, no rebalances.
- notifications-worker logs `smsbridge send failed: HTTP 402 {"error":"quota_exceeded"...}`.
- smsbridge error_rate_4xx at 100%.

## Action items
| Action | Owner | Due |
|---|---|---|
| Alert at 80% of the monthly smsbridge quota | Kofi Mensah | 2026-09-22 |
| Raise the contracted quota by 60% | Lena Fischer | 2026-09-30 |
| RFC: secondary SMS provider with automatic failover | Lena Fischer | 2026-10-09 |

## Lessons
When a vendor rejects us for account reasons there is nothing to fix on our side: identify it quickly and escalate to the owning team and the vendor.
