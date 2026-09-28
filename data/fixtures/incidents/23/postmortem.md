---
id: pm-INC-4356
kind: postmortem
title: "INC-4356: clock skew on ip-10-42-2-14 broke JWT validation"
author: Meera Pillai
date: 2026-09-25T12:00:00+05:30
incident_id: INC-4356
services: [nodes, auth-svc]
symptom: auth_failures
format: md
---
# INC-4356: clock skew on ip-10-42-2-14 broke JWT validation

**Date:** Thu 24 Sep 2026 · **Severity:** SEV-2 · **On call:** Farhan Qureshi · **Author:** Meera Pillai

## Summary
A recurrence of INC-4213 on a different node. chronyd had died on `ip-10-42-2-14` (ap-south-1b) and a live migration at 22:30 IST left its clock **51 s behind**. Pods there rejected tokens as `token used before issued`; about a sixth of auth requests failed (20.3% at the alert). Farhan checked node_clock_offset_ms first, as INC-4213 taught us, and drained the node at 22:48; recovered by 22:58.

## Impact
- 27 minutes at night. 3,537 failed payments, about ₹65.4 lakh at risk.
- INC-4213: 41 minutes and ₹1.04 crore, with a certificate rotation and a restart on the way.

## Why it happened again
The chronyd restart-on-failure fix from INC-4213 went into the node AMI, so only new nodes have it. ip-10-42-2-14 predates the fix. The clock-offset alert from INC-4213 did fire at 22:33, into the non-paging #platform-alerts channel.

## Action items
| Action | Owner | Due |
|---|---|---|
| Roll every node to the fixed AMI | Deepak Rao | 2026-09-29 |
| Make the clock-offset alert page | Sara Kim | 2026-09-25 |

## Lessons
Partial auth failures with `token used before issued`: check node_clock_offset_ms and drain the skewed node. Certificates and auth-svc restarts are the wrong direction.
