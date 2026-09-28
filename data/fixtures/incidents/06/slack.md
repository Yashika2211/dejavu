---
id: slack-INC-4178
kind: slack
title: "#inc-4178 incident channel"
author: Tomás Ortega
date: 2026-08-25T12:22:00+05:30
incident_id: INC-4178
services: [checkout-api, payments-svc]
symptom: error_rate_5xx
format: md
---
**#inc-4178**

**Tomás Ortega** 12:22 ack. payments-svc 22% 503s, `request rejected: server overloaded`
**Tomás Ortega** 12:26 scaling payments-svc to 8
**Tomás Ortega** 12:31 no change. restarting
**Priya Raman** 12:37 checkout logs are full of `retrying payments-svc call` attempt 5/6. I flipped checkout.retry_policy to aggressive at 12:10 for EXP-352, could that be it?
**Tomás Ortega** 12:38 payments rps is 4x, edge rps flat. yes. reverting the flag
**Tomás Ortega** 12:45 recovered
**Priya Raman** 12:46 sorry!! didn't know about RFC-011
