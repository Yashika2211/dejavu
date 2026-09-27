---
id: pm-INC-4146
kind: postmortem
title: "INC-4146: login failures from an expired edge-gateway mTLS certificate"
author: Arjun Nair
date: 2026-08-21T12:00:00+05:30
incident_id: INC-4146
services: [edge-gateway, auth-svc]
symptom: auth_failures
format: md
---
# INC-4146: login failures from an expired edge-gateway mTLS certificate

**Date:** Thu 20 Aug 2026 · **Severity:** SEV-1 · **On call:** Priya Raman · **Author:** Arjun Nair (Identity)

## Summary
At 21:31 IST the `edge-gateway-mtls` client certificate that edge-gateway presents to auth-svc expired. Every login through the edge failed the TLS handshake (auth-svc: `x509: certificate has expired or is not yet valid`; Envoy: `SSLV3_ALERT_BAD_CERTIFICATE`). auth-svc saw less traffic rather than more errors. The certificate had not renewed because the Certificate still referenced the ClusterIssuer `kestrel-ca-issuer`, renamed a month ago. Renewing it at 21:50 restored logins by 21:59.

## Impact
- 28 minutes of failed logins at the evening peak (21:31-21:59).
- 12,829 failed payments, about ₹2.37 crore at risk.

## Timeline (IST)
- 21:31 certificate expires; edge 503s on /v1/auth/* jump to ~36%
- 21:37 AuthFailureRateHigh fires
- 21:43 Priya restarts auth-svc: no change (the certificate is the edge's, and a restart does not renew anything)
- 21:47 Arjun paged; finds the x509 errors and cert_days_remaining = 0 on edge-gateway
- 21:50 certificate renewed with cmctl, issuer reference fixed
- 21:59 logins recovered

## What went wrong
- cert-manager had logged `issuer.cert-manager.io "kestrel-ca-issuer" not found` for weeks. Nobody alerts on it, despite INC-3845 in May asking for exactly that.
- Restarting auth-svc was a guess.

## Action items
| Action | Owner | Due |
|---|---|---|
| Alert on cert_days_remaining < 14 for every mTLS certificate | Arjun Nair | 2026-08-24 |
| Alert on cert-manager renewal failures | Sara Kim | 2026-08-24 |
| Audit all Certificates for stale issuer references | Meera Pillai | 2026-08-27 |

## Lessons
If auth-svc traffic drops while the edge returns 503s, requests are not reaching auth-svc: check the mTLS certificate (cert_days_remaining) and cert-manager events before touching auth-svc.
