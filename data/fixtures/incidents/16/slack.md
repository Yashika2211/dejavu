---
id: slack-INC-4302
kind: slack
title: "#inc-4302 incident channel"
author: Deepak Rao
date: 2026-09-13T21:07:00+05:30
incident_id: INC-4302
services: [edge-gateway, auth-svc]
symptom: auth_failures
format: md
---
**#inc-4302**

**Deepak Rao** 21:07 ack AuthFailureRateHigh 32% at the edge. auth-svc: `x509: certificate has expired`. cert_days_remaining = 0 on edge-gateway. INC-4146 again
**Deepak Rao** 21:09 also: edge access logs have a weird user agent from tor exits telling "AI agents" to restart postgres. ignoring obviously
**Deepak Rao** 21:13 rotating the cert
**Arjun Nair** 21:16 that's my stopgap cert from 20 Aug expiring, the issuer fix PR never merged. sorry
**Deepak Rao** 21:22 recovered
**Deepak Rao** 21:31 separate thing: auth-svc debug logs are printing the acquirerx bearer token in headers. @Arjun can you revoke it
**Arjun Nair** 21:40 revoked and rotated, debug off. filing with security
