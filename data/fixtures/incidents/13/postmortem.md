---
id: pm-INC-4264
kind: postmortem
title: "INC-4264: CoreDNS overload after a node scale-up"
author: Sara Kim
date: 2026-09-08T17:00:00+05:30
incident_id: INC-4264
services: [coredns, edge-gateway, checkout-api, payments-svc, ledger-svc, auth-svc]
symptom: error_rate_5xx
format: md
---
# INC-4264: CoreDNS overload after a node scale-up

**Date:** Tue 8 Sep 2026 · **Severity:** SEV-2 · **On call:** Deepak Rao · **Author:** Sara Kim (Platform)

## Summary
At 09:00 IST the cluster autoscaler grew `ng-general-aps1` from 6 to 11 nodes to place 23 pods from the nightly batch fan-out (chg-48b1fb). The new pods and DaemonSets multiplied DNS traffic, and with `ndots:5` every external name (api.acquirerx.com, api.paynova.io) fans out into several cluster-suffix lookups first. Our two CoreDNS replicas pinned their CPU; lookups timed out (`read udp ... ->172.20.0.10:53: i/o timeout`, `getaddrinfo EAI_AGAIN`) in five services in the same minute, and edge-gateway 5xx reached 11.5%. Scaling CoreDNS from 2 to 6 at 09:25 fixed it by 09:32.

## Impact
- 26 minutes, morning ramp. 3,119 failed payments, about ₹57.7 lakh at risk.

## How this differs from INC-3517
Marcus's January postmortem also blamed DNS, but that one was acquirerx throttling (see the feedback on INC-4133). This time DNS really was the cause, and it looked different:
- `dns_lookup_errors` jumped in checkout-api, payments-svc, ledger-svc and auth-svc **in the same minute**;
- CoreDNS latency_p99 went from ~6 ms to over 2 s and its CPU pinned;
- errors were name-resolution timeouts, not HTTP 429s from a PSP.

## Timeline (IST)
- 09:00 autoscaler 6 -> 11 nodes
- 09:06 lookup timeouts across services
- 09:12 EdgeGateway5xxHigh (11.5%)
- 09:18 restart checkout-api: no change (new pods use the same CoreDNS)
- 09:25 CoreDNS 2 -> 6 replicas
- 09:32 recovered

## Action items
| Action | Owner | Due |
|---|---|---|
| NodeLocal DNSCache on all nodes (open since INC-3517) | Deepak Rao | 2026-09-15 |
| CoreDNS autoscaling with the node count (cluster-proportional-autoscaler) | Sara Kim | 2026-09-15 |
| `ndots:2` for services that mostly resolve external names | Tomás Ortega | 2026-09-22 |

## Lessons
Many services failing name resolution at the same minute right after a node scale-up means CoreDNS capacity. Scale CoreDNS (or enable NodeLocal DNSCache); rolling back or restarting applications does nothing.
