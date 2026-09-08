"""The device-token revocation cache.

The middleware used to read the revocation flag from Mongo on every
device-token request, which the wall clock's ten-second poll turned into a
round-trip per poll forever. These pin the properties that make caching it
safe: it expires, and revoking drops the entry immediately.
"""

import time

import pytest

from beats.auth import device_access


@pytest.fixture(autouse=True)
def _clean():
    device_access.clear()
    yield
    device_access.clear()


class TestDeviceAccessCache:
    def test_unknown_device_is_a_miss(self):
        assert device_access.get("dev-1") is None

    def test_remembers_both_verdicts(self):
        device_access.remember("allowed", allowed=True)
        device_access.remember("denied", allowed=False)

        assert device_access.get("allowed") is True
        assert device_access.get("denied") is False

    def test_forget_makes_the_next_read_a_miss(self):
        """Revoking calls this, so a revoked device is refused on its next
        request rather than when the entry would have expired."""
        device_access.remember("dev-1", allowed=True)
        device_access.forget("dev-1")

        assert device_access.get("dev-1") is None

    def test_forget_is_safe_for_an_uncached_device(self):
        device_access.forget("never-seen")

    def test_entry_expires(self, monkeypatch):
        clock = [1000.0]
        monkeypatch.setattr(time, "monotonic", lambda: clock[0])

        device_access.remember("dev-1", allowed=True)
        clock[0] += device_access.TTL_SECONDS - 1
        assert device_access.get("dev-1") is True

        clock[0] += 2
        assert device_access.get("dev-1") is None

    def test_devices_are_independent(self):
        device_access.remember("a", allowed=True)
        device_access.remember("b", allowed=False)
        device_access.forget("a")

        assert device_access.get("a") is None
        assert device_access.get("b") is False
