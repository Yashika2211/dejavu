---
id: slack-INC-4146
kind: slack
title: "#inc-4146 incident channel"
author: Priya Raman
date: 2026-08-20T21:39:00+05:30
incident_id: INC-4146
services: [edge-gateway, auth-svc]
symptom: auth_failures
format: md
---
**#inc-4146**

**Priya Raman** 21:39 ack AuthFailureRateHigh, 36% of /v1/auth failing at the edge
**Priya Raman** 21:43 restarting auth-svc
**Priya Raman** 21:46 no change. paging identity
**Arjun Nair** 21:48 auth-svc is logging `x509: certificate has expired or is not yet valid` on TLS handshakes from the edge. cert_days_remaining on edge-gateway = 0
**Arjun Nair** 21:49 cert-manager can't renew, still points at kestrel-ca-issuer which we renamed. fixing the issuer ref + cmctl renew
**Arjun Nair** 21:59 new cert is live, logins recovering
**Priya Raman** 22:01 confirmed, error rate back to baseline 🙏
