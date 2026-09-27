---
id: RB-fraud-scorer-oom
title: fraud-scorer memory and restarts
services: [fraud-scorer, checkout-api]
keywords: [fraud, scorer, memory, oom, oomkilled, restarts, model, timeout, manual, review]
author: Marcus Oyelaran
last_edited: 2026-04-02
---
# fraud-scorer memory and restarts

When fraud-scorer is slow, checkout-api waits 1.5 s and then sends the payment to manual review, so checkout latency and the manual-review queue both grow.

1. Check restarts and mem_bytes on fraud-scorer; look for OOMKilled events.
2. Restart the pods to clear memory if you need breathing room.
3. If memory climbs again after a restart, it is almost always a new model artifact. Check the change log for a model release and roll back the model version.
4. Page Risk ML (Vikram Shetty).
