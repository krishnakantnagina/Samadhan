"""Shared test setup.

The rate limiter (app/ratelimit.py) is OFF in the test suite: every test shares one fake client address, so the per-minute limits would make unrelated
tests fail at random. tests/test_ratelimit.py turns it on for itself.
"""

import pytest

from app import ratelimit


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_DISABLED", "1")
    ratelimit.reset()
    yield
    ratelimit.reset()
