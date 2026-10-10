"""Tests against the app served by a real uvicorn, where a client can give up on a request."""

import asyncio
import http.client
import json
import threading
import time
from collections.abc import Callable, Iterator

import pytest
import uvicorn

from api import create_app
from cache import VerdictCache
from config import Settings
from fakes import INJECTION, FakeScanner, FakeValkey, digest
from guard import ToolGuard
from metrics import Metrics


def wait_until(predicate: Callable[[], bool], what: str, seconds: float = 5) -> None:
    deadline = time.monotonic() + seconds
    while not predicate():
        if time.monotonic() > deadline:
            raise TimeoutError(f"{what} not reached within {seconds}s")
        time.sleep(0.02)


class Served:
    """The app on a loopback port, served from a background thread."""

    def __init__(self, metrics: Metrics, settings: Settings):
        """Build the app around a gate-controlled scanner and an in-memory Valkey."""
        self.scanner = FakeScanner()
        self.valkey = FakeValkey()
        cache = VerdictCache(self.valkey, namespace="ns", ttl_seconds=60, metrics=metrics)
        guard = ToolGuard(
            self.scanner,
            cache,
            metrics,
            max_text_bytes=settings.max_text_bytes,
            max_pending_scans=settings.max_pending_scans,
            scan_workers=settings.scan_workers,
        )
        app = create_app(settings, metrics, lambda: asyncio.sleep(0, guard))
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run)
        self.port = 0

    def start(self) -> None:
        """Serve and wait until the app reports ready."""
        self.thread.start()
        wait_until(lambda: self.server.started, "server start")
        self.port = self.server.servers[0].sockets[0].getsockname()[1]
        wait_until(lambda: self.request("GET", "/readyz")[0] == 200, "readiness")

    def stop(self) -> None:
        """Shut the server down."""
        self.scanner.release()
        self.server.should_exit = True
        self.thread.join(timeout=15)

    def request(self, method: str, path: str, payload: dict | None = None, timeout: float = 5) -> tuple[int, dict]:
        """Send one request and return the status and JSON body."""
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        try:
            connection.request(method, path, body=None if payload is None else json.dumps(payload))
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def scan(self, new=(), known=(), timeout: float = 5) -> tuple[int, dict]:
        """POST /v1/scan."""
        payload = {"new": [{"hash": digest(t), "text": t} for t in new], "known": list(known)}
        return self.request("POST", "/v1/scan", payload, timeout)

    def cached(self, text: str) -> bool:
        """Whether a verdict for text has been stored."""
        return any(key.endswith(digest(text)) for key in self.valkey.data)


@pytest.fixture(name="served")
def fixture_served(metrics) -> Iterator[Served]:
    served = Served(metrics, Settings.from_env({"MAX_CONCURRENT_REQUESTS": "1"}))
    served.start()
    try:
        yield served
    finally:
        served.stop()


def test_a_client_that_gives_up_frees_the_request_slot_and_its_scan_still_lands_in_the_cache(served):
    cached, abandoned = f"{INJECTION} cached", f"{INJECTION} abandoned"
    served.scan([cached])
    served.scanner.gate.clear()
    served.scanner.started.clear()

    with pytest.raises(TimeoutError):
        served.scan([abandoned], timeout=0.3)
    assert served.scanner.started.wait(timeout=5)
    answers = []

    def lookup_admitted() -> bool:
        answers[:] = [served.scan(known=[digest(cached)])]
        return answers[0][0] == 200

    wait_until(lookup_admitted, "a cache lookup admitted after the client gave up")
    served.scanner.release()
    wait_until(lambda: served.cached(abandoned), "the abandoned scan cached")

    assert answers == [(200, {"flagged": [digest(cached)], "unknown": []})]
    assert served.scan(known=[digest(abandoned)]) == (200, {"flagged": [digest(abandoned)], "unknown": []})
