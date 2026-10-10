"""Fakes shared by the llm-tool-guard tests."""

import asyncio
import hashlib
import threading

from redis.exceptions import ConnectionError as ValkeyConnectionError

from metrics import Metrics

INJECTION = "INJECT"


def digest(text: str) -> str:
    """Hash text the way the LiteLLM middleware does."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


class FakeValkey:
    """In-memory stand-in for the async Valkey client; set down=True to make every call fail."""

    def __init__(self):
        """Start empty and up."""
        self.data: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.down = False
        self.mget_calls: list[list[str]] = []

    def _check(self):
        if self.down:
            raise ValkeyConnectionError("connection refused")

    async def mget(self, keys):
        """Return the stored value or None for each key."""
        await asyncio.sleep(0)
        self._check()
        self.mget_calls.append(list(keys))
        return [self.data.get(k) for k in keys]

    async def set(self, key, value, ex=None):
        """Store value with its TTL."""
        await asyncio.sleep(0)
        self._check()
        self.data[key] = value
        self.ttls[key] = ex
        return True


class FakeScanner:
    """Synchronous scan function: flags text containing INJECTION, records calls, and can hold scans on a gate."""

    def __init__(self, *, gated: bool = False, error: Exception | None = None):
        """Gated scans wait for release(); error makes every scan raise it."""
        self.calls: list[str] = []
        self.started = threading.Event()
        self.gate = threading.Event()
        self.active = 0
        self.peak = 0
        self._lock = threading.Lock()
        self._error = error
        if not gated:
            self.gate.set()

    def release(self):
        """Let held scans finish."""
        self.gate.set()

    def __call__(self, text: str) -> bool:
        """Return True when text looks like an injection."""
        with self._lock:
            self.calls.append(text)
            self.active += 1
            self.peak = max(self.peak, self.active)
        self.started.set()
        try:
            if not self.gate.wait(timeout=10):
                raise TimeoutError("scan gate never released")
            if self._error is not None:
                raise self._error
            return INJECTION in text
        finally:
            with self._lock:
                self.active -= 1


def sample(metrics: Metrics, name: str, **labels) -> float:
    """Read one metric sample, 0.0 when it has not been recorded."""
    value = metrics.registry.get_sample_value(name, labels)
    return 0.0 if value is None else value
