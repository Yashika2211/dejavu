---
id: slack-INC-4193
kind: slack
title: "#inc-4193 incident channel"
author: Tomás Ortega
date: 2026-08-29T20:07:00+05:30
incident_id: INC-4193
services: [auth-svc, notifications-worker]
symptom: auth_failures
format: md
---
**#inc-4193**

**Tomás Ortega** 20:07 ack AuthFailureRateHigh 15%. auth-svc says otp_expired
**Tomás Ortega** 20:12 restarting auth-svc
**Tomás Ortega** 20:17 no change. notifications-worker lag is 12k and climbing. runbook says scale out consumers, going to 8
**Tomás Ortega** 20:26 lag is growing faster now?? paging messaging
**Lena Fischer** 20:29 stop scaling, every new pod triggers a rebalance. logs say poll timeout expired -> LeaveGroup. 2.9.2 renders templates with S3 fetches per message. rolling back
**Lena Fischer** 20:32 rolled back to 2.9.1, scaling back to 4
**Lena Fischer** 20:42 group stable, lag draining, otp failures gone
