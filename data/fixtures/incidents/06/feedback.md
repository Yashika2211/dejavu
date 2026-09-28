---
id: fb-INC-4178
kind: feedback
title: "On-call feedback on INC-4178"
author: Tomás Ortega
date: 2026-08-25T13:00:00+05:30
incident_id: INC-4178
services: [checkout-api, payments-svc]
symptom: error_rate_5xx
format: md
---
Tomás Ortega (on-call) confirmed: INC-4178 was a retry storm from the checkout-api flag `checkout.retry_policy` (standard -> aggressive, chg-99ad02), not a payments-svc capacity problem. Reverting the flag fixed it. Scaling payments-svc out had no effect and restarting it helped for a minute or two at most.
