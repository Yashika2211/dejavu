"""Client-side rate limiting per model: requests per minute, tokens per minute, requests per day.

Groq enforces the same limits server-side; staying under them locally avoids burning retries on
429s. A server `retry-after` pauses the model's bucket for everyone. Clock and sleep are
injectable so tests run instantly.
"""

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

MINUTE = 60.0
DAY = 86_400.0


@dataclass(frozen=True)
class Limits:
    rpm: int
    tpm: int
    rpd: int


class RateLimiter:
    """Sliding-window limiter for one model."""

    def __init__(
        self,
        limits: Limits,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.limits = limits
        self._clock = clock
        self._sleep = sleep
        self._minute: deque[tuple[float, int]] = deque()
        self._day: deque[float] = deque()
        self._paused_until = 0.0
        self._lock = asyncio.Lock()

    def _prune(self, now: float) -> None:
        while self._minute and now - self._minute[0][0] >= MINUTE:
            self._minute.popleft()
        while self._day and now - self._day[0] >= DAY:
            self._day.popleft()

    def _wait_for(self, now: float, tokens: int) -> float:
        waits = [self._paused_until - now]
        if len(self._minute) >= self.limits.rpm:
            waits.append(self._minute[0][0] + MINUTE - now)
        used = sum(t for _, t in self._minute)
        if self._minute and used + tokens > self.limits.tpm:
            # wait until enough of the oldest requests fall out of the window
            excess = used + tokens - self.limits.tpm
            for at, t in self._minute:
                excess -= t
                if excess <= 0:
                    waits.append(at + MINUTE - now)
                    break
        if len(self._day) >= self.limits.rpd:
            waits.append(self._day[0] + DAY - now)
        return max(waits)

    async def acquire(self, tokens: int) -> float:
        """Block until a request of `tokens` fits; returns the seconds spent waiting."""
        waited = 0.0
        async with self._lock:
            while True:
                now = self._clock()
                self._prune(now)
                wait = self._wait_for(now, tokens)
                if wait <= 0:
                    self._minute.append((now, tokens))
                    self._day.append(now)
                    return waited
                await self._sleep(wait)
                waited += wait

    def pause(self, seconds: float) -> None:
        """Honour a server `retry-after`: nobody calls this model until it has passed."""
        self._paused_until = max(self._paused_until, self._clock() + seconds)


class RateLimiters:
    """One limiter per model, created on first use."""

    def __init__(self, limits: Limits, **kwargs: object) -> None:
        self._limits = limits
        self._kwargs = kwargs
        self._by_model: dict[str, RateLimiter] = {}

    def for_model(self, model: str) -> RateLimiter:
        if model not in self._by_model:
            self._by_model[model] = RateLimiter(self._limits, **self._kwargs)  # type: ignore[arg-type]
        return self._by_model[model]
