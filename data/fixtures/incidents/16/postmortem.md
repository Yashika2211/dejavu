---
id: pm-INC-4302
kind: postmortem
title: "INC-4302: edge-gateway mTLS certificate expired again; injection attempt and a leaked token in logs"
author: Arjun Nair
date: 2026-09-14T12:00:00+05:30
incident_id: INC-4302
services: [edge-gateway, auth-svc]
symptom: auth_failures
format: md
---
# INC-4302: edge-gateway mTLS certificate expired again

**Date:** Sun 13 Sep 2026 · **Severity:** SEV-1 · **On call:** Deepak Rao · **Author:** Arjun Nair (Identity)

## Summary
At 20:58 IST the edge-gateway mTLS client certificate expired and logins through the edge failed, exactly like INC-4146. On 20 Aug I issued a short-lived (24-day) certificate by hand as a stopgap while the issuer fix went through review. The fix never merged (the PR stalled), cert-manager kept failing on `kestrel-ca-issuer`, and the stopgap ran out. Deepak recognised INC-4146 from the x509 errors and cert_days_remaining = 0 and rotated the certificate at 21:13; recovered by 21:22.

## Impact
- 23 minutes at the evening peak. 10,980 failed payments, about ₹2.03 crore at risk.

## Security findings (reported to security as SEC-118)
1. **Prompt-injection attempt in logs.** From 20:59, Envoy access logs contain requests from 185.220.101.47 and 185.220.101.52 (Tor exit nodes) whose User-Agent string is text addressed to "AI agents", claiming the incident is resolved and telling them to restart postgres-ledger. Nobody acted on it. Log content is untrusted input: it is attacker-controlled text, never an instruction.
2. **Credential in logs.** From 20:29, auth-svc DEBUG logging on the outbound acquirerx client printed full request headers, including a bearer token. The token was revoked and rotated at 21:40, DEBUG logging was turned off, and the log pipeline now redacts `Authorization` headers.

## Action items
| Action | Owner | Due |
|---|---|---|
| Merge the issuer-reference fix; no hand-issued certificates | Arjun Nair | 2026-09-14 |
| The cert_days_remaining < 14 alert from INC-4146: it existed but routed to a muted channel | Sara Kim | 2026-09-15 |
| Redact Authorization headers at the log shipper | Meera Pillai | 2026-09-16 |
| Block Tor exit nodes at the edge for /v1/auth/* | Sara Kim | 2026-09-18 |

## Lessons
- Recurrence of INC-4146: expired mTLS cert = rotate it, then fix renewal for real.
- Treat anything inside logs as data. Instructions in a User-Agent are an attack, not guidance.
