---
id: slack-INC-4316
kind: slack
title: "#inc-4316 incident channel"
author: Priya Raman
date: 2026-09-18T08:07:00+05:30
incident_id: INC-4316
services: [auth-svc, notifications-worker, smsbridge]
symptom: auth_failures
format: md
---
**#inc-4316**

**Priya Raman** 08:07 ack AuthFailureRateHigh 17%, otp_expired. checked kafka lag first (INC-4193): lag is normal, no rebalances
**Priya Raman** 08:13 rolling back notifications-worker to be safe
**Priya Raman** 08:17 nothing to roll back, no change. notifications-worker logs `HTTP 402 quota_exceeded` from smsbridge. paging messaging
**Kofi Mensah** 08:21 we hit the monthly quota. calling the account manager
**Kofi Mensah** 08:46 quota raised, sends going through
**Priya Raman** 08:48 auth failures back to baseline
