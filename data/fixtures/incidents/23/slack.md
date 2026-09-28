---
id: slack-INC-4356
kind: slack
title: "#inc-4356 incident channel"
author: Farhan Qureshi
date: 2026-09-24T22:42:00+05:30
incident_id: INC-4356
services: [auth-svc, nodes]
symptom: auth_failures
format: md
---
**#inc-4356**

**Farhan Qureshi** 22:42 ack AuthFailureRateHigh 20%, `token used before issued`. checking node clocks per INC-4213
**Farhan Qureshi** 22:45 ip-10-42-2-14 is -51s. draining it
**Farhan Qureshi** 22:58 drained, failures back to baseline
**Deepak Rao** 23:05 that node is on the old AMI without the chronyd fix. rolling the rest this week
