from governed_mcp.gateway.policy import RateLimit
from governed_mcp.gateway.ratelimit import RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


LIMIT = RateLimit(requests_per_minute=60, burst=3)


def test_burst_then_deny_with_retry_after() -> None:
    clock = FakeClock()
    rl = RateLimiter(clock=clock)
    assert [rl.check("a", LIMIT).allowed for _ in range(3)] == [True, True, True]
    denied = rl.check("a", LIMIT)
    assert not denied.allowed
    assert denied.retry_after_s == 1.0


def test_refills_at_the_configured_rate() -> None:
    clock = FakeClock()
    rl = RateLimiter(clock=clock)
    for _ in range(3):
        rl.check("a", LIMIT)
    clock.now += 1.0
    assert rl.check("a", LIMIT).allowed
    assert not rl.check("a", LIMIT).allowed
    clock.now += 3600
    assert [rl.check("a", LIMIT).allowed for _ in range(4)] == [True, True, True, False]


def test_clients_have_separate_buckets() -> None:
    rl = RateLimiter(clock=FakeClock())
    for _ in range(3):
        rl.check("a", LIMIT)
    assert not rl.check("a", LIMIT).allowed
    assert rl.check("b", LIMIT).allowed


def test_memory_is_bounded() -> None:
    rl = RateLimiter(clock=FakeClock(), max_clients=2)
    for key in ("a", "b", "c"):
        rl.check(key, LIMIT)
    assert len(rl._buckets) == 2
    assert "a" not in rl._buckets
