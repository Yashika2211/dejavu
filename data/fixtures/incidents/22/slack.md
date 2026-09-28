---
id: slack-INC-4343
kind: slack
title: "#inc-4343 incident channel"
author: Farhan Qureshi
date: 2026-09-23T04:53:00+05:30
incident_id: INC-4343
services: [postgres-ledger, ledger-svc]
symptom: write_failures
format: md
---
**#inc-4343**

**Farhan Qureshi** 04:53 ack LedgerWriteErrorsHigh 36%. POST /entries failing, GET /balance fine
**Farhan Qureshi** 04:56 restarting ledger-svc
**Farhan Qureshi** 04:59 no change. postgres logs: `No space left on device`, disk 100%. NOT restarting postgres (INC-3688). paging DBA
**Rohan Mehta** 05:04 debezium_ledger slot is inactive and holding ~410GB of WAL. the CDC connector died in July. dropping the slot + growing the volume
**Rohan Mehta** 05:19 disk 58%, writes ok
**Farhan Qureshi** 05:20 thanks Rohan 🙏
