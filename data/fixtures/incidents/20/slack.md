---
id: slack-INC-4320
kind: slack
title: "#inc-4320 incident channel"
author: Priya Raman
date: 2026-09-19T20:32:00+05:30
incident_id: INC-4320
services: [checkout-api, payments-svc]
symptom: error_rate_5xx
format: md
---
**#inc-4320**

**Priya Raman** 20:32 ack payments-svc 21% 503s. payments rps 4x, edge rps flat. this is INC-4178. checking flags
**Priya Raman** 20:34 checkout.retry_policy -> aggressive at 20:20. reverting
**Tomás Ortega** 20:35 argh, that was meant to be 5% for EXP-338, the UI applied it to everyone
**Priya Raman** 20:40 recovered
