---
id: fb-INC-4146
kind: feedback
title: "On-call feedback on INC-4146"
author: Priya Raman
date: 2026-08-20T22:15:00+05:30
incident_id: INC-4146
services: [edge-gateway, auth-svc]
symptom: auth_failures
format: md
---
Priya Raman (on-call) confirmed: INC-4146 was an expired mTLS client certificate on edge-gateway (edge-gateway-mtls), which cert-manager failed to renew because of a stale issuer reference. It was not an auth-svc code problem: restarting auth-svc did nothing. Rotating the certificate fixed it. Tell-tales: cert_days_remaining = 0, `x509: certificate has expired` in auth-svc logs, auth-svc traffic dropping while the edge returns 503s, and nearly all login requests failing rather than a fraction.
