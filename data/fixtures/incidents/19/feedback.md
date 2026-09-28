---
id: fb-INC-4316
kind: feedback
title: "On-call feedback on INC-4316"
author: Priya Raman
date: 2026-09-18T09:00:00+05:30
incident_id: INC-4316
services: [smsbridge, notifications-worker]
symptom: auth_failures
format: md
---
Priya Raman (on-call) confirmed: INC-4316 was new, not a repeat of the Kafka rebalance storm in INC-4193. smsbridge rejected every OTP send because our monthly SMS quota was exhausted (HTTP 402 quota_exceeded), while consumer lag stayed normal. No change on our side could fix it; it was resolved when smsbridge raised the quota after Messaging escalated. Rolling back notifications-worker did nothing.
