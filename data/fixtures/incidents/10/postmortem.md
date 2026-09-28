---
id: pm-INC-4213
kind: postmortem
title: "INC-4213: JWT validation failures from clock skew on one node"
author: Deepak Rao
date: 2026-09-02T15:00:00+05:30
incident_id: INC-4213
services: [auth-svc, nodes]
symptom: auth_failures
format: md
---
# INC-4213: JWT validation failures from clock skew on one node

**Date:** Tue 1 Sep 2026 · **Severity:** SEV-2 · **On call:** Meera Pillai · **Author:** Deepak Rao (Platform)

## Summary
- chronyd on node `ip-10-42-1-23` (ap-south-1a) was OOM-killed at 19:20 IST (`status=9/KILL`) and never restarted.
- At 22:03 a hypervisor live migration left that node's clock **49.4 s behind**. Without chrony nothing corrected it.
- Pods on that node rejected valid tokens: `token has invalid claims: token used before issued`. About one auth request in six failed (20% at the alert).
- 22:17 certificate rotation: no effect. 22:26 auth-svc restart: a few minutes of relief (some pods moved), then back.
- 22:35 drained the node; recovered by 22:45.

## Impact
- 41 minutes. 5,598 failed payments, about ₹1.04 crore at risk.

## Why it looked like INC-4146
Same alert name. Differences we should have seen in the first five minutes:
- INC-4146 failed ~100% of logins at the edge; this failed a fraction, and auth-svc traffic was normal.
- The error was `token used before issued`, not `x509: certificate has expired`.
- `node_clock_offset_ms` on one node was -49,400 ms; all others within a few ms.

## Action items
| Action | Owner | Due |
|---|---|---|
| Alert on abs(node_clock_offset_ms) > 1000 on any node | Deepak Rao | 2026-09-04 |
| systemd: restart chronyd on failure; exclude it from the OOM killer | Deepak Rao | 2026-09-08 |
| JWT validation leeway 5 s (from 0) | Arjun Nair | 2026-09-08 |

## Lessons
- Partial auth failures + `token used before issued` = clock. Check node_clock_offset_ms; drain the skewed node.
- Rotating certificates does not help clock problems.
