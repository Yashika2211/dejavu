---
id: pm-INC-4361
kind: postmortem
title: "INC-4361: ap-south-1b lost cross-AZ connectivity"
author: Sara Kim
date: 2026-09-26T21:00:00+05:30
incident_id: INC-4361
services: [nodes, edge-gateway, checkout-api, payments-svc, auth-svc, ledger-svc]
symptom: error_rate_5xx
format: md
---
# INC-4361: ap-south-1b lost cross-AZ connectivity

**Date:** Sat 26 Sep 2026 · **Severity:** SEV-1 · **On call:** Farhan Qureshi · **Author:** Sara Kim (Platform)

## Summary
From 15:03 IST our two ap-south-1b nodes (ip-10-42-2-14, ip-10-42-4-9) lost connectivity to the other zones: a transit gateway attachment in 1b was flapping on AWS's side. Calls between 1b and 1a/1c timed out at the TCP layer (`dial tcp 10.42.4.x:8080: connect: connection timed out`, `connect ETIMEDOUT`), roughly a third of requests failed, and edge 5xx reached 22.9%. Kubelets in 1b could not reach the API server. A checkout-api restart at 15:19 did nothing. At 15:28 I cordoned and drained both 1b nodes; workloads rescheduled into 1a and 1c and errors stopped by 15:38. The AWS Health Dashboard posted about "increased network latency in a single AZ in ap-south-1" at 15:44.

## Impact
- 35 minutes on a Saturday afternoon. 7,508 failed payments, about ₹1.39 crore at risk.

## How it differed from the DNS incident (INC-4264)
Both showed many services failing at once. Here DNS was healthy (CoreDNS p99 normal, no lookup errors); the errors were connect timeouts, all to addresses in 10.42.2.0/24 and 10.42.4.0/24, the ap-south-1b subnets.

## Action items
| Action | Owner | Due |
|---|---|---|
| Runbook: evacuate an AZ (cordon + drain, shift edge weights) | Sara Kim | 2026-10-02 |
| Topology spread constraints so every service survives losing one AZ | Deepak Rao | 2026-10-09 |
| Zone-aware routing at the edge | Sara Kim | 2026-10-16 |

## Lessons
Many services failing with connect timeouts to one zone's subnets: evacuate the zone, don't restart applications. Status pages, AWS's included, trail reality.
