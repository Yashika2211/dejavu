---
id: RB-kafka-consumer-lag
title: notifications-worker consumer lag
services: [notifications-worker, kafka]
keywords: [kafka, lag, consumer, notifications, otp, sms, delay, backlog]
author: Marcus Oyelaran
last_edited: 2026-01-19
---
# notifications-worker consumer lag

OTPs go through Kafka (topic otp-requests, 12 partitions, consumer group notifications) to smsbridge. Lag means OTPs arrive late and step-up auth starts failing.

1. Check kafka_consumer_lag on notifications-worker.
2. Scale out notifications-worker to catch up the backlog (up to 12 pods, one per partition).
3. If smsbridge is erroring, check status.smsbridge.in and page Messaging.
