---
id: pm-INC-4193
kind: postmortem
title: "INC-4193: OTP failures from a notifications-worker rebalance storm"
author: Lena Fischer
date: 2026-08-31T10:00:00+05:30
incident_id: INC-4193
services: [notifications-worker, kafka, auth-svc]
symptom: auth_failures
format: md
---
# INC-4193: OTP failures from a notifications-worker rebalance storm

**Date:** Sat 29 Aug 2026 · **Severity:** SEV-2 · **On call:** Tomás Ortega · **Author:** Lena Fischer (Messaging)

## Summary
notifications-worker 2.9.2 (deployed 19:51 IST, chg-42c765, PR #982) moved OTP rendering to TemplateEngine v2, which loads brand assets from S3 for every message. A 500-record batch now took longer than `max.poll.interval.ms` (5 minutes), so consumers were kicked out of the group, the group rebalanced over and over, and lag climbed past 20,000. OTPs arrived after they expired, so users failed step-up authentication: it paged as AuthFailureRateHigh on auth-svc. Rolling back at 20:32 fixed it by 20:42.

## Impact
- 45 minutes at the evening peak; UPI payments needing OTP failed.
- 10,604 failed payments, about ₹1.96 crore at risk.

## Timeline (IST)
- 19:51 notifications-worker 2.9.1 -> 2.9.2
- 19:57 `sending LeaveGroup request ... consumer poll timeout has expired` in notifications-worker logs; kafka_rebalances 2-5/min
- 20:05 AuthFailureRateHigh (15.1%), all `otp verification failed: otp_expired`
- 20:12 auth-svc restarted: no effect (auth-svc was only reporting expired OTPs)
- 20:20 scaled notifications-worker 4 -> 8 per RB-kafka-consumer-lag: **more rebalances, lag grew faster**
- 20:28 Lena paged
- 20:32 rolled back to 2.9.1
- 20:42 group stable, lag draining, auth failures back to baseline

## What went wrong
- It looked like an auth problem and was treated as one for 15 minutes.
- RB-kafka-consumer-lag says to scale out consumers. RFC-012 says the opposite for rebalance storms; every new member triggers another rebalance. The runbook is wrong for this case.

## Action items
| Action | Owner | Due |
|---|---|---|
| Fix RB-kafka-consumer-lag: rebalance storm => roll back or raise max.poll.interval.ms, never scale out | Lena Fischer | 2026-09-04 |
| Cache brand assets in memory in TemplateEngine v2 | Kofi Mensah | 2026-09-02 |
| Alert on kafka_rebalances > 1/min for 5 minutes | Lena Fischer | 2026-09-04 |

## Lessons
OTP failures surface as auth failures. Check notifications-worker lag and rebalances first. If lag climbs together with rebalances after a deploy, roll back; scaling consumers makes it worse.
