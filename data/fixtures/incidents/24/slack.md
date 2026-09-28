---
id: slack-INC-4361
kind: slack
title: "#inc-4361 incident channel"
author: Farhan Qureshi
date: 2026-09-26T15:12:00+05:30
incident_id: INC-4361
services: [edge-gateway, checkout-api, nodes]
symptom: error_rate_5xx
format: md
---
**#inc-4361**

**Farhan Qureshi** 15:12 ack edge 5xx 23%. lots of services erroring. coredns looks fine this time
**Farhan Qureshi** 15:19 restarting checkout-api
**Farhan Qureshi** 15:22 nothing. errors are connect timeouts to 10.42.2.x / 10.42.4.x. paging platform
**Sara Kim** 15:25 those are the ap-south-1b subnets. kubelets there can't reach the api server either. evacuating 1b
**Sara Kim** 15:28 cordoned + draining ip-10-42-2-14 and ip-10-42-4-9
**Sara Kim** 15:38 everything rescheduled into 1a/1c, errors gone
**Sara Kim** 15:45 AWS health dashboard now admits it: network issue in one AZ
