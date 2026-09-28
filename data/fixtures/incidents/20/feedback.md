---
id: fb-INC-4320
kind: feedback
title: "On-call feedback on INC-4320"
author: Priya Raman
date: 2026-09-19T20:55:00+05:30
incident_id: INC-4320
services: [checkout-api, payments-svc]
symptom: error_rate_5xx
format: md
---
Priya Raman (on-call) confirmed: INC-4320 was a recurrence of the retry storm in INC-4178, caused by the checkout.retry_policy flag being set to aggressive for all traffic (chg-6394ce). Reverting the flag fixed it within five minutes; nothing else was needed.
