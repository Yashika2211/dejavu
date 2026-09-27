---
id: fb-INC-4133
kind: feedback
title: "On-call feedback on INC-4133"
author: Priya Raman
date: 2026-08-19T14:45:00+05:30
incident_id: INC-4133
services: [acquirerx, payments-svc]
symptom: latency_p99
format: md
---
Priya Raman (on-call) confirmed: the root cause of INC-4133 was acquirerx rate limiting (HTTP 429 `rate_limit_exceeded`), not a ledger or checkout problem; the ledger pool and postgres-ledger were healthy throughout. Failing over to paynova (psp.primary=paynova) fixed it; rolling back the unrelated checkout-api deploy did nothing. The acquirerx status page stayed green for about twenty minutes.

Marcus's INC-3517 from January looks like the same thing: checkout latency with payment failures at lunch, acquirerx 429s noted in the timeline, status page green. The DNS errors in that postmortem were probably noise, and the CoreDNS scale-up coincided with acquirerx recovering. Treat INC-3517's DNS conclusion as unreliable.
