---
id: slack-m1
kind: announcement
title: "#eng-announce: ledger-svc now behind PgBouncer"
author: Rohan Mehta
date: 2026-09-03T14:40:00+05:30
services: [ledger-svc, pgbouncer-ledger, postgres-ledger]
symptom: null
format: md
---
**#eng-announce**, Thu 3 Sep 2026

**Rohan Mehta** 14:40
PgBouncer rollout for ledger-svc is done (RFC-014). ledger-svc talks to `pgbouncer-ledger` in transaction pooling mode; HikariCP is down to 10 per pod on purpose. Connection count on postgres-ledger went from ~60 to 24 at the same traffic. 🎉

**Rohan Mehta** 14:41
On-call folks: if ledger latency spikes, look at `pgbouncer_cl_waiting` on pgbouncer-ledger. Please don't bump the Hikari pool, it won't do anything now. Ping #data-platform for `default_pool_size` changes.

**Farhan Qureshi** 14:44
nice. RB-ledger-pool still says raise Hikari to 40, I'll update it this week

**Ananya Iyer** 14:46
🙏 thanks Rohan
