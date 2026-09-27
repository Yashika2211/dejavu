---
id: RB-auth-failures
title: authentication failures (AuthFailureRateHigh)
services: [auth-svc, edge-gateway]
keywords: [auth, login, token, jwt, 401, certificate, cert, x509, mtls, otp, AuthFailureRateHigh]
author: Marcus Oyelaran
last_edited: 2026-05-07
---
# Authentication failures

1. Where do requests fail? edge-gateway error_rate_5xx and auth-svc rps/error_rate_4xx. If auth-svc rps drops while the edge returns 503s, requests are not reaching auth-svc: suspect mTLS between edge-gateway and auth-svc.
2. Certificates: check cert_days_remaining on edge-gateway and auth-svc, and cert-manager events. Renew with cert-manager (`cmctl renew`).
3. JWT errors in auth-svc logs: `token is expired`, `token used before issued` (clock problems), unknown `kid` (key rotation).
4. OTP step-up failures usually mean OTPs are arriving late; look at notifications-worker and smsbridge.
5. Restarting auth-svc rarely helps; find the cause first.
