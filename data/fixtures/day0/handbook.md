---
id: handbook
kind: handbook
title: Kestrel Pay on-call handbook
author: Marcus Oyelaran
date: 2026-05-02T10:00:00+05:30
services: []
symptom: null
format: pdf
---
# Kestrel Pay on-call handbook

For whoever is on call. Written by Marcus Oyelaran, May 2026.

## The first ten minutes
1. Acknowledge the page. Open #inc-bridge and say you have it.
2. Read the alert, then the change log for the last six hours: deploys, flag flips, Helm changes. Most incidents follow a change.
3. Find which dependency is slow or failing before touching anything. checkout-api fans out to auth-svc, fraud-scorer, payments-svc and ledger-svc; its latency is usually someone else's.
4. Post a status update in #inc-bridge every 15 minutes, even if it is "still investigating".

## Rules
- Prefer reversible actions: roll back, revert the flag, fail over.
- Any action on postgres-ledger needs the DBA on call (Data Platform, Rohan Mehta's team). Actions on the cache or Kafka need Platform.
- Never restart Postgres on a full disk (INC-3688).
- If you are not making progress after 15 minutes, page the owning team. Nobody minds.

## Who owns what
- Payments (Priya Raman): checkout-api, payments-svc and the PSPs.
- Core Ledger (Ananya Iyer): ledger-svc.
- Identity (Arjun Nair): auth-svc, certificates for auth.
- Risk ML (Vikram Shetty): fraud-scorer and model releases.
- Messaging (Lena Fischer): notifications-worker, smsbridge.
- Platform (Sara Kim): edge-gateway, cache, Kafka, CoreDNS, nodes.
- Data Platform (Rohan Mehta): postgres-ledger.

## Postmortems
Every SEV-1 and SEV-2 gets a postmortem within three working days, in the Google SRE template. Every action item needs an owner and a due date.
