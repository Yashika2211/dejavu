---
id: slack-INC-4186
kind: slack
title: "#inc-4186 incident channel"
author: Tomás Ortega
date: 2026-08-27T11:44:00+05:30
incident_id: INC-4186
services: [postgres-ledger, ledger-svc]
symptom: latency_p99
format: md
---
**#inc-4186**

**Tomás Ortega** 11:44 ack. checkout p99 5.7s, ledger pool full again. following RB-ledger-pool, raising hikari to 40
**Tomás Ortega** 11:53 worse. pg cpu 97%
**Tomás Ortega** 11:55 ledger deployed at 11:25, rolling back
**Tomás Ortega** 12:04 no change after rollback. paging DBA
**Rohan Mehta** 12:06 slow log is all `Seq Scan on ledger_entries_2026q3`. V88 recreated the table without the (account_id, created_at) index. rolling back the app doesn't undo flyway
**Rohan Mehta** 12:08 please put the pool back to 20, you're feeding it more scans
**Rohan Mehta** 12:10 creating the index concurrently, ~15 min
**Rohan Mehta** 12:29 index is in, cpu 30%, recovered
**Tomás Ortega** 12:30 thanks. lesson learned re: the pool
