import pytest

from dejavu.llm.ratelimit import Limits, RateLimiter


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture
def fake() -> FakeTime:
    return FakeTime()


async def test_requests_per_minute(fake: FakeTime) -> None:
    limiter = RateLimiter(Limits(rpm=2, tpm=10_000, rpd=100), clock=fake.clock, sleep=fake.sleep)
    assert await limiter.acquire(10) == 0
    assert await limiter.acquire(10) == 0
    waited = await limiter.acquire(10)
    assert waited == pytest.approx(60)


async def test_tokens_per_minute(fake: FakeTime) -> None:
    limiter = RateLimiter(Limits(rpm=100, tpm=1_000, rpd=100), clock=fake.clock, sleep=fake.sleep)
    await limiter.acquire(600)
    fake.now = 20
    await limiter.acquire(300)
    waited = await limiter.acquire(300)  # 1,200 > 1,000: wait for the first request to expire
    assert fake.now == pytest.approx(60)
    assert waited == pytest.approx(40)


async def test_a_single_request_bigger_than_tpm_still_goes_through_alone(fake: FakeTime) -> None:
    limiter = RateLimiter(Limits(rpm=100, tpm=1_000, rpd=100), clock=fake.clock, sleep=fake.sleep)
    assert await limiter.acquire(5_000) == 0


async def test_requests_per_day(fake: FakeTime) -> None:
    limiter = RateLimiter(Limits(rpm=100, tpm=100_000, rpd=2), clock=fake.clock, sleep=fake.sleep)
    await limiter.acquire(1)
    await limiter.acquire(1)
    assert await limiter.acquire(1) == pytest.approx(86_400)


async def test_retry_after_pauses_the_model(fake: FakeTime) -> None:
    limiter = RateLimiter(Limits(rpm=100, tpm=100_000, rpd=100), clock=fake.clock, sleep=fake.sleep)
    limiter.pause(7.5)
    assert await limiter.acquire(1) == pytest.approx(7.5)
