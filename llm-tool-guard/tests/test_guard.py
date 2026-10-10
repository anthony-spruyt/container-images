"""Tests for the scan service: hashing, verdict cache use, single-flight, limits and failure paths."""

import asyncio
import gc
import hashlib
import threading
import time
import weakref
from collections.abc import Callable

import pytest

from cache import VerdictCache
from fakes import INJECTION, FakeScanner, FakeValkey, digest, sample
from guard import ScanStoppedError, ToolGuard, content_hash
from metrics import Metrics

NAMESPACE = "ns"
TTL = 3600


def make_guard(  # noqa: PLR0913 - test builder with keyword-only knobs
    scanner: FakeScanner,
    metrics: Metrics,
    valkey: FakeValkey | None,
    *,
    max_text_bytes: int = 1024,
    max_pending_scans: int = 16,
    scan_workers: int = 1,
    stop_scans: Callable[[], None] | None = None,
) -> ToolGuard:
    cache = VerdictCache(valkey, namespace=NAMESPACE, ttl_seconds=TTL, metrics=metrics)
    return ToolGuard(
        scanner,
        cache,
        metrics,
        max_text_bytes=max_text_bytes,
        max_pending_scans=max_pending_scans,
        scan_workers=scan_workers,
        stop_scans=stop_scans,
    )


def item(text: str, hash_: str | None = None) -> dict:
    return {"hash": hash_ or digest(text), "text": text}


def cache_key(hash_: str) -> str:
    return f"llm-tool-guard:{NAMESPACE}:{hash_}"


async def wait_for(predicate):
    for _ in range(500):
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise TimeoutError("condition not met within 5s")


def test_content_hash_matches_middleware_format():
    text = "kubectl get pods\nNAME READY"
    assert content_hash(text) == "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def test_content_hash_encodes_lone_surrogates_like_the_middleware():
    text = "broken \ud800 pair"
    assert content_hash(text) == digest(text)


def test_clean_item_is_not_flagged_and_its_verdict_is_cached(metrics, valkey):
    scanner = FakeScanner()
    guard = make_guard(scanner, metrics, valkey)
    clean = item("NAME READY STATUS")

    flagged, unknown = asyncio.run(guard.check([clean], []))

    assert (flagged, unknown) == ([], [])
    assert valkey.data == {cache_key(clean["hash"]): "0"}
    assert valkey.ttls[cache_key(clean["hash"])] == TTL
    assert sample(metrics, "llm_tool_guard_scans_total", verdict="clean") == 1


def test_injection_item_is_flagged_and_cached(metrics, valkey):
    guard = make_guard(FakeScanner(), metrics, valkey)
    bad = item(f"log line {INJECTION} here")

    flagged, _ = asyncio.run(guard.check([bad], []))

    assert flagged == [bad["hash"]]
    assert valkey.data == {cache_key(bad["hash"]): "1"}
    assert sample(metrics, "llm_tool_guard_scans_total", verdict="flagged") == 1
    assert sample(metrics, "llm_tool_guard_flagged_total", reason="verdict") == 1


def test_new_item_with_cached_verdict_is_not_rescanned(metrics, valkey):
    scanner = FakeScanner()
    guard = make_guard(scanner, metrics, valkey)
    text = "plain output"
    valkey.data[cache_key(digest(text))] = "1"

    flagged, _ = asyncio.run(guard.check([item(text)], []))

    assert flagged == [digest(text)]
    assert scanner.calls == []
    assert sample(metrics, "llm_tool_guard_cache_hits_total") == 1


def test_known_hashes_are_answered_from_the_cache(metrics, valkey):
    scanner = FakeScanner()
    guard = make_guard(scanner, metrics, valkey)
    bad, clean, missing = digest("a"), digest("b"), digest("c")
    valkey.data[cache_key(bad)] = "1"
    valkey.data[cache_key(clean)] = "0"

    flagged, unknown = asyncio.run(guard.check([], [bad, clean, missing]))

    assert flagged == [bad]
    assert unknown == [missing]
    assert scanner.calls == []
    assert sample(metrics, "llm_tool_guard_cache_hits_total") == 2
    assert sample(metrics, "llm_tool_guard_cache_misses_total") == 1


@pytest.mark.parametrize(
    "known",
    [
        "sha256:" + "A" * 64,
        "sha256:" + "a" * 63,
        "md5:" + "a" * 64,
        "a" * 64,
        "sha256:" + "a" * 64 + "*",
    ],
)
def test_malformed_known_hash_is_unknown_without_a_lookup(metrics, valkey, known):
    guard = make_guard(FakeScanner(), metrics, valkey)
    valkey.data[cache_key(known)] = "0"

    flagged, unknown = asyncio.run(guard.check([], [known]))

    assert (flagged, unknown) == ([], [known])
    assert valkey.mget_calls == []


def test_known_hash_also_sent_as_new_is_scanned_not_unknown(metrics, valkey):
    guard = make_guard(FakeScanner(), metrics, valkey)
    clean = item("fine")

    flagged, unknown = asyncio.run(guard.check([clean], [clean["hash"]]))

    assert (flagged, unknown) == ([], [])


def test_hash_mismatch_is_flagged_and_nothing_is_cached(metrics, valkey):
    scanner = FakeScanner()
    guard = make_guard(scanner, metrics, valkey)
    victim = digest(f"{INJECTION} the agent")
    forged = {"hash": victim, "text": "harmless text"}

    flagged, unknown = asyncio.run(guard.check([forged], []))

    assert (flagged, unknown) == ([victim], [])
    assert valkey.data == {}
    assert scanner.calls == []
    assert sample(metrics, "llm_tool_guard_flagged_total", reason="hash_mismatch") == 1


def test_hash_mismatch_cannot_make_a_later_known_lookup_clean(metrics, valkey):
    guard = make_guard(FakeScanner(), metrics, valkey)
    victim = digest(f"{INJECTION} the agent")

    asyncio.run(guard.check([{"hash": victim, "text": "harmless text"}], []))
    flagged, unknown = asyncio.run(guard.check([], [victim]))

    assert (flagged, unknown) == ([], [victim])


def test_hash_mismatch_wins_over_a_matching_duplicate(metrics, valkey):
    guard = make_guard(FakeScanner(), metrics, valkey)
    clean = item("fine")

    flagged, _ = asyncio.run(guard.check([clean, {"hash": clean["hash"], "text": "other"}], []))

    assert flagged == [clean["hash"]]
    assert valkey.data == {}


def test_uppercase_hex_does_not_match(metrics, valkey):
    guard = make_guard(FakeScanner(), metrics, valkey)
    text = "fine"
    upper = "sha256:" + digest(text).removeprefix("sha256:").upper()

    flagged, _ = asyncio.run(guard.check([item(text, upper)], []))

    assert flagged == [upper]


def test_text_over_the_byte_limit_is_flagged_without_a_scan(metrics, valkey):
    scanner = FakeScanner()
    guard = make_guard(scanner, metrics, valkey, max_text_bytes=8)
    over = item("é" * 5)

    flagged, _ = asyncio.run(guard.check([over], []))

    assert flagged == [over["hash"]]
    assert scanner.calls == []
    assert valkey.data == {}
    assert sample(metrics, "llm_tool_guard_over_limit_total", limit="text_bytes") == 1
    assert sample(metrics, "llm_tool_guard_flagged_total", reason="over_limit") == 1


def test_text_at_the_byte_limit_is_scanned(metrics, valkey):
    scanner = FakeScanner()
    guard = make_guard(scanner, metrics, valkey, max_text_bytes=8)

    flagged, _ = asyncio.run(guard.check([item("é" * 4)], []))

    assert flagged == []
    assert scanner.calls == ["é" * 4]


def test_flagged_hashes_are_unique_and_in_request_order(metrics, valkey):
    guard = make_guard(FakeScanner(), metrics, valkey)
    first, second = item(f"{INJECTION} 1"), item(f"{INJECTION} 2")

    flagged, _ = asyncio.run(guard.check([second, first, second], [first["hash"]]))

    assert flagged == [second["hash"], first["hash"]]


def test_concurrent_requests_for_one_text_scan_it_once(metrics, valkey):
    scanner = FakeScanner(gated=True)
    guard = make_guard(scanner, metrics, valkey)
    bad = item(f"{INJECTION} once")

    async def run():
        first = asyncio.create_task(guard.check([bad], []))
        second = asyncio.create_task(guard.check([bad], []))
        await wait_for(scanner.started.is_set)
        await asyncio.sleep(0.05)
        scanner.release()
        return await first, await second

    first, second = asyncio.run(run())

    assert first == second == ([bad["hash"]], [])
    assert len(scanner.calls) == 1


def test_scan_finishes_and_is_cached_after_the_request_is_cancelled(metrics, valkey):
    scanner = FakeScanner(gated=True)
    guard = make_guard(scanner, metrics, valkey)
    bad = item(f"{INJECTION} slow")

    async def run():
        request = asyncio.create_task(guard.check([bad], []))
        await wait_for(scanner.started.is_set)
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
        scanner.release()
        await guard.drain()
        return await guard.check([], [bad["hash"]])

    assert asyncio.run(run()) == ([bad["hash"]], [])
    assert valkey.data == {cache_key(bad["hash"]): "1"}


def test_scan_finishes_after_a_client_timeout(metrics, valkey):
    scanner = FakeScanner(gated=True)
    guard = make_guard(scanner, metrics, valkey)
    clean = item("slow but fine")

    async def run():
        request = asyncio.wait_for(guard.check([clean], []), 0.05)
        with pytest.raises(TimeoutError):
            await request
        scanner.release()
        await guard.drain()

    asyncio.run(run())

    assert valkey.data == {cache_key(clean["hash"]): "0"}


def test_known_hash_waits_for_its_scan_in_flight(metrics, valkey):
    scanner = FakeScanner(gated=True)
    guard = make_guard(scanner, metrics, valkey)
    bad = item(f"{INJECTION} pending")

    async def run():
        scanning = asyncio.create_task(guard.check([bad], []))
        await wait_for(scanner.started.is_set)
        lookup = asyncio.create_task(guard.check([], [bad["hash"]]))
        await asyncio.sleep(0.05)
        scanner.release()
        await scanning
        return await lookup

    assert asyncio.run(run()) == ([bad["hash"]], [])
    assert len(scanner.calls) == 1


def test_items_beyond_the_pending_scan_limit_are_flagged(metrics, valkey):
    scanner = FakeScanner(gated=True)
    guard = make_guard(scanner, metrics, valkey, max_pending_scans=1)
    first, second = item("first"), item("second")

    async def run():
        held = asyncio.create_task(guard.check([first], []))
        await wait_for(scanner.started.is_set)
        rejected = await guard.check([second], [])
        scanner.release()
        return await held, rejected

    held, rejected = asyncio.run(run())

    assert held == ([], [])
    assert rejected == ([second["hash"]], [])
    assert cache_key(second["hash"]) not in valkey.data
    assert sample(metrics, "llm_tool_guard_over_limit_total", limit="queue") == 1


def test_pending_scans_gauge_tracks_the_queue(metrics, valkey):
    scanner = FakeScanner(gated=True)
    guard = make_guard(scanner, metrics, valkey)

    async def run():
        request = asyncio.create_task(guard.check([item("a"), item("b")], []))
        await wait_for(scanner.started.is_set)
        during = sample(metrics, "llm_tool_guard_pending_scans")
        scanner.release()
        await request
        return during

    assert asyncio.run(run()) == 2
    assert sample(metrics, "llm_tool_guard_pending_scans") == 0


def test_scans_run_at_most_scan_workers_at_a_time(metrics, valkey):
    scanner = FakeScanner(gated=True)
    guard = make_guard(scanner, metrics, valkey, scan_workers=2)

    async def run():
        request = asyncio.create_task(guard.check([item(str(i)) for i in range(5)], []))
        await wait_for(lambda: scanner.active == 2)
        await asyncio.sleep(0.05)
        scanner.release()
        return await request

    asyncio.run(run())

    assert scanner.peak == 2
    assert len(scanner.calls) == 5


def test_scan_error_is_flagged_and_not_cached(metrics, valkey):
    guard = make_guard(FakeScanner(error=RuntimeError("model failed")), metrics, valkey)
    clean = item("fine")

    flagged, _ = asyncio.run(guard.check([clean], []))

    assert flagged == [clean["hash"]]
    assert valkey.data == {}
    assert sample(metrics, "llm_tool_guard_scans_total", verdict="error") == 1
    assert sample(metrics, "llm_tool_guard_flagged_total", reason="error") == 1


def test_scan_over_its_time_budget_is_flagged_and_not_cached(metrics, valkey):
    guard = make_guard(FakeScanner(error=TimeoutError("scan over budget")), metrics, valkey)
    slow = item("slow")

    flagged, _ = asyncio.run(guard.check([slow], []))

    assert flagged == [slow["hash"]]
    assert valkey.data == {}
    assert sample(metrics, "llm_tool_guard_scans_total", verdict="timeout") == 1
    assert sample(metrics, "llm_tool_guard_scans_total", verdict="error") == 0
    assert sample(metrics, "llm_tool_guard_flagged_total", reason="error") == 1


def test_timed_out_scan_frees_its_slot_and_the_text_is_scanned_again_next_time(metrics, valkey):
    scanner = FakeScanner(error=TimeoutError("scan over budget"))
    guard = make_guard(scanner, metrics, valkey, max_pending_scans=1)
    slow = item("slow")

    asyncio.run(guard.check([slow], []))
    asyncio.run(guard.check([slow], []))

    assert len(scanner.calls) == 2
    assert sample(metrics, "llm_tool_guard_pending_scans") == 0


class Text(str):
    """A str that can be weakly referenced."""


def test_texts_not_waiting_on_a_scan_are_released_while_others_scan(metrics, valkey):
    scanner = FakeScanner(gated=True)
    guard = make_guard(scanner, metrics, valkey)
    refs = []

    def items():
        cached = Text("already known")
        refs.append(weakref.ref(cached))
        valkey.data[cache_key(digest(cached))] = "0"
        return [{"hash": digest(cached), "text": cached}, item("still scanning")]

    async def run():
        request = asyncio.create_task(guard.check(items(), []))
        await wait_for(scanner.started.is_set)
        gc.collect()
        alive = refs[0]() is not None
        scanner.release()
        await request
        return alive

    assert asyncio.run(run()) is False


def test_scan_latency_is_observed(metrics, valkey):
    guard = make_guard(FakeScanner(), metrics, valkey)

    asyncio.run(guard.check([item("fine")], []))

    assert sample(metrics, "llm_tool_guard_scan_duration_seconds_count") == 1


def test_valkey_down_still_scans_and_reports_known_as_unknown(metrics, valkey):
    scanner = FakeScanner()
    guard = make_guard(scanner, metrics, valkey)
    valkey.down = True
    bad = item(f"{INJECTION} x")

    flagged, unknown = asyncio.run(guard.check([bad], [digest("old")]))

    assert flagged == [bad["hash"]]
    assert unknown == [digest("old")]
    assert len(scanner.calls) == 1
    assert sample(metrics, "llm_tool_guard_cache_errors_total", operation="get") == 1
    assert sample(metrics, "llm_tool_guard_cache_errors_total", operation="set") == 1
    assert sample(metrics, "llm_tool_guard_cache_up") == 0


def test_without_valkey_items_are_scanned_and_known_is_unknown(metrics):
    scanner = FakeScanner()
    guard = make_guard(scanner, metrics, None)
    clean = item("fine")

    assert asyncio.run(guard.check([clean], [digest("old")])) == ([], [digest("old")])
    assert asyncio.run(guard.check([clean], [])) == ([], [])
    assert len(scanner.calls) == 2


def test_drain_returns_once_scans_finish_within_the_timeout(metrics, valkey):
    scanner = FakeScanner(gated=True)
    guard = make_guard(scanner, metrics, valkey)
    clean = item("slow but fine")

    async def run():
        asyncio.get_running_loop().call_later(0.05, scanner.release)
        request = asyncio.create_task(guard.check([clean], []))
        await wait_for(scanner.started.is_set)
        await guard.drain(max_wait=5)
        await request

    asyncio.run(run())

    assert valkey.data == {cache_key(clean["hash"]): "0"}


def test_drain_gives_up_after_the_timeout_without_cancelling_scans(metrics, valkey):
    scanner = FakeScanner(gated=True)
    guard = make_guard(scanner, metrics, valkey)
    clean = item("slow but fine")

    async def run():
        request = asyncio.create_task(guard.check([clean], []))
        await wait_for(scanner.started.is_set)
        start = time.monotonic()
        await guard.drain(max_wait=0.05)
        waited = time.monotonic() - start
        before = dict(valkey.data)
        scanner.release()
        await request
        return waited, before

    waited, before = asyncio.run(run())

    assert 0.05 <= waited < 5
    assert before == {}
    assert valkey.data == {cache_key(clean["hash"]): "0"}


def test_drain_with_nothing_in_flight_returns_at_once(metrics, valkey):
    guard = make_guard(FakeScanner(), metrics, valkey)

    asyncio.run(asyncio.wait_for(guard.drain(max_wait=0), 1))


class StoppableScanner(FakeScanner):
    """A scan that runs until stop() is called, then ends the way a stopped classifier does."""

    def __init__(self):
        """Build a scanner that has not been stopped."""
        super().__init__(gated=True)
        self.stopped = threading.Event()

    def stop(self):
        """Ask running scans to end."""
        self.stopped.set()

    def __call__(self, text: str) -> bool:
        """Run until stopped."""
        self.calls.append(text)
        self.started.set()
        if not self.stopped.wait(timeout=10):
            raise TimeoutError("scan never stopped")
        raise ScanStoppedError("stopped")


def test_close_stops_the_running_scan_and_its_verdict_is_not_cached(metrics, valkey):
    scanner = StoppableScanner()
    guard = make_guard(scanner, metrics, valkey, stop_scans=scanner.stop)
    slow = item("slow")

    async def run():
        request = asyncio.create_task(guard.check([slow], []))
        await wait_for(scanner.started.is_set)
        start = time.monotonic()
        guard.close()
        await guard.drain(max_wait=5)
        return time.monotonic() - start, await request

    waited, (flagged, _) = asyncio.run(run())

    assert waited < 2
    assert flagged == [slow["hash"]]
    assert valkey.data == {}
    assert sample(metrics, "llm_tool_guard_scans_total", verdict="stopped") == 1
    assert sample(metrics, "llm_tool_guard_scans_total", verdict="error") == 0
