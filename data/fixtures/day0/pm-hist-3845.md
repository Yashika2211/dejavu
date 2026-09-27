---
id: pm-hist-3845
kind: postmortem
title: "INC-3845: OTP delays after the Kafka client certificate expired"
author: Marcus Oyelaran
date: 2026-05-19T23:10:00+05:30
services: [notifications-worker, kafka, auth-svc]
symptom: auth_failures
format: md
---
# INC-3845: OTP delays after the Kafka client certificate expired

**Date:** Tue 19 May 2026 · **Severity:** SEV-2 · **Author:** Marcus Oyelaran · **Status:** final

## Summary
notifications-worker's mTLS client certificate for Kafka expired at 21:00 IST. Consumers could not reconnect after a routine broker restart, OTPs stopped flowing, and UPI step-up authentication failed for 38 minutes. Renewing the certificate with cert-manager fixed it.

## Impact
- AuthFailureRateHigh on auth-svc (OTP verification failures), about 14% of auth traffic for 38 minutes.

## Root cause
cert-manager could not renew because the Certificate still referenced an Issuer we had deleted during the April cleanup. It had been failing quietly for three weeks.

## Detection
We first looked at auth-svc and restarted it, which did nothing. The Kafka client logs said `SSL handshake failed ... certificate expired`.

## Action items
| Action | Owner | Due |
|---|---|---|
| Alert when any certificate has less than 14 days left (cert_days_remaining) | Sara Kim | 2026-05-26 |
| Alert on cert-manager renewal failures | Deepak Rao | 2026-05-26 |

## Lessons
Auth failures are not always auth-svc's fault. When certificates are involved, check `cert_days_remaining` and cert-manager events first; renewal failures are silent until the day of expiry.
