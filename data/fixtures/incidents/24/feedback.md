---
id: fb-INC-4361
kind: feedback
title: "On-call feedback on INC-4361"
author: Farhan Qureshi
date: 2026-09-26T15:55:00+05:30
incident_id: INC-4361
services: [nodes]
symptom: error_rate_5xx
format: md
---
Farhan Qureshi (on-call) confirmed: INC-4361 was new, a network partition of availability zone ap-south-1b (AWS-side), not a DNS problem like INC-4264. Cordoning and draining the ap-south-1b nodes fixed it; restarting checkout-api did nothing.
