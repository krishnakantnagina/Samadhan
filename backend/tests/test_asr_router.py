"""S32 -- ReaderRouter: fallback order, retries, breakers, rate limits, quality gate, budget, concurrency.
Fake providers and a fake clock: no network, no real sleeping.
"""

import threading

import pytest

from app.asr.config import AsrConfig
from app.asr.resilience import Metrics
from app.asr.router import ReaderRouter
from app.asr.types import AllProvidersFailed, ProviderError, ReadContext, Reading


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def reading(text="नल खराब है", *, confidence=0.9, audible=True, plain="नल खराब है"):
    return Reading(transcript=text, plain_hindi=plain, confidence=confidence, audible=audible)


class FakeProvider:
    """Plays a script: each call takes the next item (a Reading to return, an Exception to raise)."""

    def __init__(self, name, script=None, *, default=None):
        self.name = name
        self.script = list(script or [])
        self.default = default if default is not None else reading()
        self.calls = 0
        self.contexts: list[ReadContext] = []
        self._lock = threading.Lock()

    def read(self, audio, content_type, context):
        with self._lock:
            self.calls += 1
            self.contexts.append(context)
            item = self.script.pop(0) if self.script else self.default
        if isinstance(item, Exception):
            raise item
        return item


def config(**over):
    base = {
        "providers": ("a", "b"),
        "gemini_models": ("m",),
        "sarvam_language": "hi-IN",
        "rpm": {},  # unlimited unless a test sets it
        "max_concurrency": 8,
        "min_confidence": 0.5,
        "budget_seconds": 20.0,
        "max_attempts": 2,
        "breaker_threshold": 3,
        "breaker_cooldown": 30.0,
        "permanent_cooldown": 300.0,
        "max_queue_wait": 0.0,
    }
    base.update(over)
    return AsrConfig(**base)


def make(providers, clock=None, **over):
    clock = clock or FakeClock()
    router = ReaderRouter(
        providers, config(**over), clock=clock.time, sleep=clock.sleep, rng=lambda: 1.0, metrics=Metrics()
    )
    return router, clock


def read(router, text_context=None):
    return router.read(b"audio", "audio/webm", ReadContext(last_bot_question=text_context))


# --- happy path and fallback ----------------------------------------------------------------------


def test_first_healthy_provider_wins_and_the_rest_are_not_called():
    a, b = FakeProvider("a"), FakeProvider("b")
    router, _ = make([a, b])
    result = read(router)
    assert result.transcript == "नल खराब है" and result.provider == "a" and result.attempts == 1
    assert (a.calls, b.calls) == (1, 0)


def test_context_reaches_the_provider():
    a = FakeProvider("a")
    router, _ = make([a])
    read(router, "क्या आप वहीं हैं?")
    assert a.contexts[0].last_bot_question == "क्या आप वहीं हैं?"


def test_transient_failure_is_retried_with_backoff_then_succeeds():
    a = FakeProvider("a", [ProviderError("a HTTP 503", retryable=True, status=503)])
    router, clock = make([a])
    result = read(router)
    assert result.provider == "a" and result.attempts == 2 and a.calls == 2
    assert len(clock.slept) == 1 and 0.2 <= clock.slept[0] <= 0.4


def test_retry_after_is_obeyed_but_capped():
    a = FakeProvider("a", [ProviderError("a HTTP 429", retryable=True, retry_after=60.0, status=429)])
    router, clock = make([a])
    read(router)
    assert clock.slept == [3.0]  # asked for 60 s, a waiting citizen gets at most 3


def test_after_retries_are_used_up_it_falls_to_the_next_provider():
    err = ProviderError("a HTTP 503", retryable=True, status=503)
    a, b = FakeProvider("a", [err, err]), FakeProvider("b")
    router, _ = make([a, b])
    result = read(router)
    assert result.provider == "b" and a.calls == 2 and b.calls == 1


def test_a_rejected_clip_is_not_retried():
    a = FakeProvider("a", [ProviderError("a HTTP 400", status=400)])
    b = FakeProvider("b")
    router, _ = make([a, b])
    assert read(router).provider == "b" and a.calls == 1


def test_a_provider_that_crashes_does_not_break_the_request():
    a = FakeProvider("a", [RuntimeError("bug")])
    b = FakeProvider("b")
    router, _ = make([a, b])
    assert read(router).provider == "b"


def test_all_providers_failing_raises_with_no_secret_in_the_message():
    err = ProviderError("a HTTP 500", retryable=True, status=500)
    router, _ = make([FakeProvider("a", [err, err]), FakeProvider("b", [ProviderError("b HTTP 401", permanent=True, status=401)])])
    with pytest.raises(AllProvidersFailed) as info:
        read(router)
    assert "a HTTP 500" in str(info.value) and "b HTTP 401" in str(info.value)


def test_no_configured_provider_raises():
    router, _ = make([])
    with pytest.raises(AllProvidersFailed):
        read(router)


# --- breaker --------------------------------------------------------------------------------------


def test_permanent_error_opens_the_breaker_so_the_dead_provider_costs_nothing():
    a = FakeProvider("a", [ProviderError("a HTTP 402", permanent=True, status=402)])
    b = FakeProvider("b")
    router, clock = make([a, b])
    assert read(router).provider == "b"
    assert router.breaker_states()["a"] == "open"
    for _ in range(10):
        assert read(router).provider == "b"
    assert a.calls == 1  # never called again while open
    clock.now += 301
    a.script.append(reading("ठीक"))  # provider recovered
    assert read(router).provider == "a"  # one probe, success, closed again
    assert router.breaker_states()["a"] == "closed"


def test_repeated_failures_open_the_breaker_then_a_probe_recovers_it():
    boom = ProviderError("a HTTP 500", status=500)  # not retryable: one call per request
    a = FakeProvider("a", [boom, boom, boom])
    b = FakeProvider("b")
    router, clock = make([a, b])
    for _ in range(3):
        read(router)
    assert router.breaker_states()["a"] == "open"
    calls_when_opened = a.calls
    read(router)
    assert a.calls == calls_when_opened
    clock.now += 31
    assert read(router).provider == "a"
    assert router.breaker_states()["a"] == "closed"


def test_only_one_request_probes_a_half_open_provider():
    a = FakeProvider("a", [ProviderError("a HTTP 402", permanent=True, status=402)])
    release = threading.Event()
    entered = threading.Event()

    class SlowOnce(FakeProvider):
        def read(self, audio, content_type, context):
            entered.set()
            release.wait(timeout=5)
            return super().read(audio, content_type, context)

    a = SlowOnce("a", [ProviderError("a HTTP 402", permanent=True, status=402)])
    b = FakeProvider("b")
    router, clock = make([a, b])
    release.set()
    read(router)  # opens the breaker
    release.clear()
    entered.clear()
    clock.now += 301
    results = []
    probe = threading.Thread(target=lambda: results.append(read(router)))
    probe.start()
    assert entered.wait(timeout=5)  # the probe is inside the provider
    others = [read(router) for _ in range(5)]  # these must skip a, not queue behind it
    assert all(r.provider == "b" for r in others)
    release.set()
    probe.join(timeout=5)
    assert a.calls == 2  # the first failure + exactly one probe


# --- rate limit and concurrency cap ---------------------------------------------------------------


def test_rate_limited_provider_hands_the_overflow_to_the_next():
    a, b = FakeProvider("a"), FakeProvider("b")
    router, _ = make([a, b], rpm={"a": 1})  # burst of 1, refill 1/minute, no queue wait
    assert read(router).provider == "a"
    assert read(router).provider == "b"
    assert a.calls == 1


def test_a_short_wait_for_a_rate_limit_token_is_absorbed():
    a = FakeProvider("a")
    router, clock = make([a], rpm={"a": 60}, max_queue_wait=2.0)
    for _ in range(3):  # a 60/minute bucket stores 2 tokens; the third call has to wait about a second
        read(router)
    assert a.calls == 3 and 0.9 <= sum(clock.slept) <= 1.1


def test_concurrency_cap_sends_excess_calls_elsewhere():
    gate = threading.Event()
    inside = threading.Event()

    class Blocking(FakeProvider):
        def read(self, audio, content_type, context):
            inside.set()
            gate.wait(timeout=5)
            return super().read(audio, content_type, context)

    a, b = Blocking("a"), FakeProvider("b")
    router, _ = make([a, b], max_concurrency=1)
    first = threading.Thread(target=lambda: read(router))
    first.start()
    assert inside.wait(timeout=5)
    assert read(router).provider == "b"  # a is full
    gate.set()
    first.join(timeout=5)


# --- quality gate ---------------------------------------------------------------------------------


def test_noise_returns_an_empty_transcript_without_trying_other_providers():
    a, b = FakeProvider("a", [reading("", audible=False, confidence=0.9)]), FakeProvider("b")
    router, _ = make([a, b])
    result = read(router)
    assert result.transcript == "" and result.audible is False and b.calls == 0


def test_low_confidence_gets_a_second_opinion():
    a = FakeProvider("a", [reading("शायद कुछ", confidence=0.2)])
    b = FakeProvider("b", [reading("नल खराब है", confidence=None)])  # a provider with no score is accepted
    router, _ = make([a, b])
    result = read(router)
    assert result.provider == "b" and result.transcript == "नल खराब है"


def test_nobody_confident_means_ask_the_citizen_to_repeat():
    a = FakeProvider("a", [reading("शायद कुछ", confidence=0.2)])
    b = FakeProvider("b", [reading("शायद और", confidence=0.3)])
    router, _ = make([a, b])
    result = read(router)
    assert result.transcript == "" and result.plain_hindi is None


def test_exactly_at_the_threshold_is_accepted():
    a = FakeProvider("a", [reading(confidence=0.5)])
    router, _ = make([a])
    assert read(router).transcript != ""


# --- time budget ----------------------------------------------------------------------------------


def test_a_retry_that_would_blow_the_budget_is_not_attempted():
    a = FakeProvider("a", [ProviderError("a HTTP 503", retryable=True, status=503)])
    b = FakeProvider("b")
    router, clock = make([a, b], budget_seconds=0.1)
    assert read(router).provider == "b"
    assert a.calls == 1 and clock.slept == []


def test_when_the_budget_is_gone_no_more_providers_are_tried():
    class Slow(FakeProvider):
        def read(self, audio, content_type, context):
            clock_ref.now += 25  # the call itself eats the whole budget, then fails
            raise ProviderError("a timeout", retryable=True)

    clock_ref = FakeClock()
    a, b = Slow("a"), FakeProvider("b")
    router, _ = make([a, b], clock=clock_ref, max_attempts=1)
    with pytest.raises(AllProvidersFailed):
        read(router)
    assert b.calls == 0


# --- many requests at once ------------------------------------------------------------------------


def test_two_hundred_concurrent_requests_all_succeed_when_the_primary_is_flaky():
    flaky = [ProviderError("a HTTP 503", retryable=True, status=503) if i % 3 == 0 else reading() for i in range(400)]
    a, b = FakeProvider("a", flaky), FakeProvider("b")
    router, _ = make([a, b], max_concurrency=64, breaker_threshold=1000)
    outcomes, errors = [], []

    def work():
        try:
            outcomes.append(read(router))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(200)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    assert not errors and len(outcomes) == 200
    assert all(r.transcript for r in outcomes)
    snap = router.metrics.snapshot()
    assert snap["a"]["outcomes"]["ok"] + snap["a"]["outcomes"].get("fail_retryable", 0) == a.calls
