---
id: RB-postgres-disk
title: postgres-ledger disk usage
services: [postgres-ledger]
keywords: [postgres, disk, full, space, wal, storage, volume, write, failures]
author: Marcus Oyelaran
last_edited: 2026-02-27
---
# postgres-ledger disk usage

1. disk_used_pct on postgres-ledger. Above 90% is urgent, 100% means writes are failing (`No space left on device`).
2. Find what is using the space: table bloat, logs, or WAL. Check for inactive replication slots holding WAL (`SELECT slot_name, active, restart_lsn FROM pg_replication_slots`).
3. **Never restart Postgres on a full disk.** In February a restart during a disk-full event put the database into crash recovery and added about 40 minutes of outage.
4. Expanding the EBS volume is safe online. Involve the DBA on call (Data Platform, Rohan Mehta) for anything that touches slots or data files.
