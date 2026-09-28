---
id: slack-INC-4264
kind: slack
title: "#inc-4264 incident channel"
author: Deepak Rao
date: 2026-09-08T09:14:00+05:30
incident_id: INC-4264
services: [coredns, edge-gateway, checkout-api]
symptom: error_rate_5xx
format: md
---
**#inc-4264**

**Deepak Rao** 09:14 ack edge 5xx 11%. checkout-api errors `getaddrinfo EAI_AGAIN`
**Deepak Rao** 09:18 restarting checkout-api
**Deepak Rao** 09:21 no change, and payments-svc + ledger + auth all have lookup timeouts too. coredns p99 2.1s, cpu pinned
**Sara Kim** 09:23 autoscaler added 5 nodes at 09:00 for the batch fan-out. coredns is still 2 replicas. scale it
**Deepak Rao** 09:25 coredns -> 6
**Deepak Rao** 09:32 errors gone
**Sara Kim** 09:33 we really need NodeLocal DNSCache. taking it this sprint
