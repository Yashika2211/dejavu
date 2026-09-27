---
id: RB-checkout-latency
title: checkout-api latency (CheckoutLatencyP99High)
services: [checkout-api, edge-gateway, coredns]
keywords: [checkout, latency, p99, slow, timeout, alert, CheckoutLatencyP99High]
author: Marcus Oyelaran
last_edited: 2026-02-11
---
# checkout-api latency

Fires when checkout-api p99 on POST /v1/checkout stays above 2 s for 5 minutes. checkout-api is a fan-out: auth-svc, fraud-scorer, payments-svc (-> acquirerx/paynova) and ledger-svc. Latency here is almost always somebody else's latency.

1. **Check DNS first.** In January (INC-3517) checkout latency was CoreDNS timing out under load. Look at coredns latency_p99_ms and dns_lookup_errors before anything else.
2. Pull traces for checkout-api and see which downstream span dominates.
3. Check the change log for the last 6 hours: deploys, flag flips, Helm changes.
4. If one downstream is clearly slow, go to its runbook: RB-ledger-pool, RB-psp-degradation, RB-fraud-scorer-oom.
5. If nothing is obvious after 15 minutes, page the owning team of the slowest dependency.

Escalation: Payments on-call owns checkout-api.
