---
id: fb-INC-4264
kind: feedback
title: "On-call feedback on INC-4264"
author: Deepak Rao
date: 2026-09-08T09:50:00+05:30
incident_id: INC-4264
services: [coredns]
symptom: error_rate_5xx
format: md
---
Deepak Rao (on-call) confirmed: INC-4264 was CoreDNS overload after the node group scaled from 6 to 11 nodes (chg-48b1fb): name-resolution timeouts in many services at once. Scaling CoreDNS out fixed it; restarting checkout-api did nothing.
