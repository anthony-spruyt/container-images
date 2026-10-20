"""Fakes shared by the llm-tool-guard tests."""

import asyncio
import hashlib
import threading
from collections.abc import Callable

from redis.exceptions import ConnectionError as ValkeyConnectionError

from metrics import Metrics

INJECTION = "INJECT"
FLAGGED_SCORE = 0.97312
CLEAN_SCORE = 0.01234
FLAGGED_VALUE = f"1:{FLAGGED_SCORE}"
CLEAN_VALUE = f"0:{CLEAN_SCORE}"


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
        self.set_calls: list[tuple] = []

    def _check(self):
        if self.down:
            raise ValkeyConnectionError("connection refused")

    async def mget(self, keys):
        """Return the stored value or None for each key."""
        await asyncio.sleep(0)
        self._check()
        self.mget_calls.append(list(keys))
        return [self.data.get(k) for k in keys]

    async def set(self, key, value, ex=None, nx=False, get=False):
        """Store value with its TTL; with nx an existing key is kept, and with get the previous value is returned."""
        await asyncio.sleep(0)
        self._check()
        self.set_calls.append((key, value, ex, nx, get))
        previous = self.data.get(key)
        if nx and previous is not None:
            return previous if get else None
        self.data[key] = value
        self.ttls[key] = ex
        return previous if get else True


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
        self.verdict: Callable[[str], tuple[bool, float]] | None = None
        if not gated:
            self.gate.set()

    def release(self):
        """Let held scans finish."""
        self.gate.set()

    def __call__(self, text: str) -> tuple[bool, float]:
        """Return (flagged, score); flagged when text looks like an injection."""
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
            if self.verdict is not None:
                return self.verdict(text)
            flagged = INJECTION in text
            return flagged, FLAGGED_SCORE if flagged else CLEAN_SCORE
        finally:
            with self._lock:
                self.active -= 1


class FakeJudge:
    """Stand-in for the Jev client: answers per text from a table, records calls and can hold them on a gate."""

    def __init__(self, default: float | Exception = 0.5, *, gated: bool = False):
        """default answers every text not in answers; an Exception is raised instead of returned."""
        self.default = default
        self.answers: dict[str, float | Exception] = {}
        self.calls: list[str] = []
        self.started = asyncio.Event()
        self.gate = asyncio.Event()
        self.closed = False
        if not gated:
            self.gate.set()

    def release(self):
        """Let held asks finish."""
        self.gate.set()

    async def ask(self, text: str) -> float:
        """Return the scripted probability for text, or raise the scripted error."""
        self.calls.append(text)
        self.started.set()
        await self.gate.wait()
        answer = self.answers.get(text, self.default)
        if isinstance(answer, Exception):
            raise answer
        return answer

    async def aclose(self):
        """Record the close."""
        self.closed = True


def sample(metrics: Metrics, name: str, **labels) -> float:
    """Read one metric sample, 0.0 when it has not been recorded."""
    value = metrics.registry.get_sample_value(name, labels)
    return 0.0 if value is None else value
