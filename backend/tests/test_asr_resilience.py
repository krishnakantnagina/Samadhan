"""S32 -- rate limiter, circuit breaker, bulkhead and metrics, on a fake clock (no real waiting)."""

import threading

from app.asr.resilience import Bulkhead, CircuitBreaker, Metrics, TokenBucket


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


# --- TokenBucket ----------------------------------------------------------------------------------


def test_bucket_none_or_zero_rate_is_unlimited():
    for rate in (None, 0):
        bucket = TokenBucket(rate)
        assert all(bucket.acquire() for _ in range(1000))


def test_bucket_refuses_when_empty_and_no_wait_allowed():
    clock = FakeClock()
    bucket = TokenBucket(60, burst=1, clock=clock.time, sleep=clock.sleep)  # 1 per second
    assert bucket.acquire() is True
    assert bucket.acquire(max_wait=0) is False


def test_bucket_waits_for_a_token_within_max_wait():
    clock = FakeClock()
    bucket = TokenBucket(60, burst=1, clock=clock.time, sleep=clock.sleep)
    assert bucket.acquire() is True
    assert bucket.acquire(max_wait=2.0) is True
    assert 0.9 <= sum(clock.slept) <= 1.1  # waited about one second, then got the token


def test_bucket_gives_up_when_the_wait_would_be_too_long():
    clock = FakeClock()
    bucket = TokenBucket(6, burst=1, clock=clock.time, sleep=clock.sleep)  # 1 per 10 seconds
    assert bucket.acquire() is True
    assert bucket.acquire(max_wait=2.0) is False
    assert clock.slept == []  # did not waste the wait


def test_bucket_refills_over_time_but_not_beyond_burst():
    clock = FakeClock()
    bucket = TokenBucket(60, burst=2, clock=clock.time, sleep=clock.sleep)
    assert bucket.acquire() and bucket.acquire()
    clock.now += 3600
    assert bucket.acquire() and bucket.acquire()
    assert bucket.acquire(max_wait=0) is False  # only 2 stored, not 3600


def test_bucket_never_hands_out_more_than_the_quota_across_threads():
    bucket = TokenBucket(60, burst=10)  # real clock: 10 stored, ~1/second refill
    granted = []

    def grab():
        granted.append(bucket.acquire(max_wait=0))

    threads = [threading.Thread(target=grab) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert 10 <= granted.count(True) <= 11  # the burst (+ at most one refilled while the threads ran)


# --- CircuitBreaker -------------------------------------------------------------------------------


def make_breaker(clock, threshold=3, cooldown=30.0):
    return CircuitBreaker(failure_threshold=threshold, cooldown_seconds=cooldown, clock=clock.time)


def test_breaker_opens_after_threshold_consecutive_failures():
    clock = FakeClock()
    b = make_breaker(clock)
    for _ in range(2):
        b.record_failure()
    assert b.state == "closed" and b.allow()
    b.record_failure()
    assert b.state == "open" and not b.allow() and b.is_open()


def test_a_success_resets_the_failure_count():
    clock = FakeClock()
    b = make_breaker(clock)
    b.record_failure()
    b.record_failure()
    b.record_success()
    b.record_failure()
    b.record_failure()
    assert b.state == "closed"


def test_breaker_lets_exactly_one_probe_through_after_cooldown():
    clock = FakeClock()
    b = make_breaker(clock)
    for _ in range(3):
        b.record_failure()
    clock.now += 31
    assert b.is_open() is False  # cooled down: a probe may go
    assert b.allow() is True  # the probe
    assert b.state == "half_open"
    assert b.allow() is False and b.is_open() is True  # everyone else still skips
    b.record_success()
    assert b.state == "closed" and b.allow()


def test_failed_probe_reopens_for_a_full_cooldown():
    clock = FakeClock()
    b = make_breaker(clock)
    for _ in range(3):
        b.record_failure()
    clock.now += 31
    assert b.allow()
    b.record_failure()
    assert b.state == "open" and not b.allow()
    clock.now += 31
    assert b.allow()


def test_cooldown_override_opens_at_once_and_for_longer():
    clock = FakeClock()
    b = make_breaker(clock)
    b.record_failure(cooldown=300)
    assert b.state == "open"
    clock.now += 100
    assert not b.allow()
    clock.now += 250
    assert b.allow()


def test_release_probe_frees_the_slot():
    clock = FakeClock()
    b = make_breaker(clock)
    for _ in range(3):
        b.record_failure()
    clock.now += 31
    assert b.allow()
    b.release_probe()
    assert b.allow()


# --- Bulkhead and Metrics -------------------------------------------------------------------------


def test_bulkhead_caps_concurrency():
    bulkhead = Bulkhead(2)
    assert bulkhead.acquire() and bulkhead.acquire()
    assert bulkhead.acquire() is False
    bulkhead.release()
    assert bulkhead.acquire() is True


def test_metrics_counts_and_latency_percentiles():
    m = Metrics()
    for ms in range(1, 101):
        m.observe_latency("gemini", ms)
    m.count("gemini", "ok")
    m.count("gemini", "ok")
    m.count("sarvam", "fail_permanent")
    snap = m.snapshot()
    assert snap["gemini"]["outcomes"] == {"ok": 2}
    assert snap["gemini"]["latency_ms_p50"] == 51
    assert snap["gemini"]["latency_ms_p95"] == 96
    assert snap["sarvam"]["outcomes"] == {"fail_permanent": 1}
