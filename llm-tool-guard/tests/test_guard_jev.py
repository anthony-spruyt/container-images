"""Tests for the Jev second check in the scan service: which windows go to Jev, what answers mean, what is stored."""

import asyncio
import gc
import weakref

import pytest

from cache import JevCache, VerdictCache
from fakes import FLAGGED_SCORE, INJECTION, FakeJudge, FakeScanner, FakeValkey, digest, flagged_value, sample
from guard import Judged, ToolGuard
from judge import JevError
from metrics import Metrics
from second_check import SecondCheck

TTL = 3600 * 24
BLOCK_AT = 0.9
CLEAR_BELOW = 0.08
JEV_BYTES = 512
JEV_WINDOWS = 3
REQUESTS = "llm_tool_guard_jev_requests_total"


def make_guard(  # noqa: PLR0913 - test builder with keyword-only knobs
    judge: FakeJudge | None,
    metrics: Metrics,
    valkey: FakeValkey | None,
    *,
    scanner: FakeScanner | None = None,
    max_pending_scans: int = 16,
    block_at: float = BLOCK_AT,
    clear_below: float = CLEAR_BELOW,
    max_windows: int = JEV_WINDOWS,
) -> ToolGuard:
    cache = VerdictCache(valkey, namespace="ns", ttl_seconds=TTL, metrics=metrics)
    second = None
    if judge is not None:
        jev_cache = JevCache(valkey, namespace="jns", ttl_seconds=TTL, metrics=metrics)
        second = SecondCheck(
            judge,
            jev_cache,
            metrics,
            block_at=block_at,
            clear_below=clear_below,
            max_text_bytes=JEV_BYTES,
            max_windows=max_windows,
        )
    return ToolGuard(
        scanner or FakeScanner(),
        cache,
        metrics,
        max_text_bytes=1024,
        max_pending_scans=max_pending_scans,
        scan_workers=1,
        second_check=second,
    )


def item(text: str) -> dict:
    return {"hash": digest(text), "text": text}


def bad(name: str = "a") -> dict:
    return item(f"{INJECTION} {name}")


def multi(*pieces: str, flagged: tuple[int, ...]) -> tuple[dict, tuple[tuple[int, int], ...]]:
    """Return an item whose text is the pieces on separate lines, and the spans of the pieces at the flagged indexes."""
    spans, at = [], 0
    for piece in pieces:
        spans.append((at, at + len(piece)))
        at += len(piece) + 1
    return item("\n".join(pieces)), tuple(spans[i] for i in flagged)


def flagging(spans: tuple[tuple[int, int], ...], **kwargs) -> FakeScanner:
    """Return a scanner that flags every text, with the model's flagged windows at spans."""
    scanner = FakeScanner(**kwargs)
    scanner.verdict = lambda _text: (True, FLAGGED_SCORE, spans)
    return scanner


def spans_value(spans: tuple[tuple[int, int], ...]) -> str:
    """Return the verdict-cache value of a flagged text whose flagged windows are at spans."""
    return f"1:{FLAGGED_SCORE}:" + ",".join(f"{start}-{end}" for start, end in spans)


def horizon_key(hash_: str) -> str:
    return f"llm-tool-guard:ns:{hash_}"


def jev_key(hash_: str) -> str:
    return f"llm-tool-guard:jev:jns:{hash_}"


def judged(guard: ToolGuard, new=(), known=()) -> Judged:
    return asyncio.run(guard.check(list(new), list(known)))


async def wait_for(predicate):
    for _ in range(500):
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise TimeoutError("condition not met within 5s")


def test_a_confident_answer_blocks_the_flagged_text(metrics, valkey):
    judge = FakeJudge(0.97)
    guard = make_guard(judge, metrics, valkey)
    text = bad()

    result = judged(guard, [text])

    h = text["hash"]
    assert result == Judged([h], [], {h: FLAGGED_SCORE}, [h], [], {h: 0.97})
    assert judge.calls == [text["text"]]
    assert sample(metrics, REQUESTS, outcome="blocked") == 1
    assert sample(metrics, "llm_tool_guard_flagged_total", reason="verdict") == 1


def test_a_low_answer_clears_the_flagged_text(metrics, valkey):
    guard = make_guard(FakeJudge(0.02), metrics, valkey)
    text = bad()

    result = judged(guard, [text])

    h = text["hash"]
    assert result == Judged([], [], {h: FLAGGED_SCORE}, [], [h], {h: 0.02})
    assert sample(metrics, REQUESTS, outcome="cleared") == 1
    assert sample(metrics, "llm_tool_guard_flagged_total", reason="verdict") == 0


def test_an_answer_in_between_leaves_the_text_flagged(metrics, valkey):
    guard = make_guard(FakeJudge(0.5), metrics, valkey)
    text = bad()

    result = judged(guard, [text])

    h = text["hash"]
    assert result == Judged([h], [], {h: FLAGGED_SCORE}, [], [], {h: 0.5})
    assert sample(metrics, REQUESTS, outcome="middle") == 1
    assert sample(metrics, "llm_tool_guard_flagged_total", reason="verdict") == 1


@pytest.mark.parametrize(
    ("p", "blocked", "cleared"),
    [
        (BLOCK_AT, True, False),
        (0.8999, False, False),
        (CLEAR_BELOW, False, False),
        (0.0799, False, True),
        (0.0, False, True),
        (1.0, True, False),
    ],
)
def test_thresholds_block_at_or_above_and_clear_strictly_below(metrics, valkey, p, blocked, cleared):
    result = judged(make_guard(FakeJudge(p), metrics, valkey), [bad()])

    assert (bool(result.blocked), bool(result.cleared)) == (blocked, cleared)


def test_each_text_gets_its_own_answer_and_the_lists_follow_request_order(metrics, valkey):
    judge = FakeJudge(0.5)
    first, second, third = bad("one"), bad("two"), bad("three")
    judge.answers = {first["text"]: 0.99, second["text"]: 0.01}
    guard = make_guard(judge, metrics, valkey)

    result = judged(guard, [third, second, first])

    assert result.flagged == [third["hash"], first["hash"]]
    assert result.blocked == [first["hash"]]
    assert result.cleared == [second["hash"]]
    assert result.jev_scores == {third["hash"]: 0.5, second["hash"]: 0.01, first["hash"]: 0.99}
    assert set(result.scores) == {first["hash"], second["hash"], third["hash"]}


def test_without_a_second_check_every_flag_stays_flagged_and_the_new_fields_are_empty(metrics, valkey):
    guard = make_guard(None, metrics, valkey)
    text = bad()

    result = judged(guard, [text])

    h = text["hash"]
    assert result == Judged([h], [], {h: FLAGGED_SCORE}, [], [], {})


def test_a_clean_text_never_goes_to_jev(metrics, valkey):
    judge = FakeJudge()
    guard = make_guard(judge, metrics, valkey)

    result = judged(guard, [item("fine")])

    assert result == Judged([], [], {}, [], [], {})
    assert judge.calls == []


def test_flags_that_are_not_model_verdicts_never_go_to_jev(metrics, valkey):
    judge = FakeJudge(0.0)
    scanner = FakeScanner(error=RuntimeError("boom"))
    guard = make_guard(judge, metrics, valkey, scanner=scanner)
    forged = {"hash": digest("other"), "text": "benign"}
    too_big = item("x" * 2000)

    result = judged(guard, [forged, too_big, item("scan fails")])

    assert len(result.flagged) == 3
    assert (result.blocked, result.cleared, result.jev_scores) == ([], [], {})
    assert judge.calls == []


def test_the_horizon_cache_is_untouched_and_the_answer_is_stored_as_the_raw_probability(metrics, valkey):
    guard = make_guard(FakeJudge(0.5), metrics, valkey)
    text = bad()

    judged(guard, [text])

    h = text["hash"]
    assert valkey.data == {horizon_key(h): flagged_value(text["text"]), jev_key(h): "0.5"}
    assert valkey.ttls[jev_key(h)] == TTL


def test_a_stored_answer_is_served_without_asking_again_and_thresholds_apply_when_read(metrics, valkey):
    text = bad()
    judged(make_guard(FakeJudge(0.5), metrics, valkey), [text])
    judge = FakeJudge(0.0)
    stricter = make_guard(judge, metrics, valkey, block_at=0.4)

    by_text = judged(stricter, [text])
    by_hash = judged(stricter, known=[text["hash"]])

    h = text["hash"]
    expected = Judged([h], [], {h: FLAGGED_SCORE}, [h], [], {h: 0.5})
    assert by_text == expected
    assert by_hash == expected
    assert judge.calls == []


def test_a_known_hash_the_model_flagged_without_a_stored_answer_stays_flagged(metrics, valkey):
    judge = FakeJudge(0.0)
    guard = make_guard(judge, metrics, valkey)
    h = digest("old")
    valkey.data[horizon_key(h)] = flagged_value("old")

    result = judged(guard, known=[h])

    assert result == Judged([h], [], {h: FLAGGED_SCORE}, [], [], {})
    assert judge.calls == []


def test_a_flagged_text_the_model_cached_is_sent_to_jev_when_it_arrives_as_new(metrics, valkey):
    judge = FakeJudge(0.01)
    scanner = FakeScanner()
    guard = make_guard(judge, metrics, valkey, scanner=scanner)
    text = bad()
    valkey.data[horizon_key(text["hash"])] = flagged_value(text["text"])

    result = judged(guard, [text])

    assert result.cleared == [text["hash"]]
    assert scanner.calls == []
    assert judge.calls == [text["text"]]


def test_text_over_the_jev_limit_is_flagged_unasked_and_stored_as_no_answer_so_it_is_not_tried_again(metrics, valkey):
    judge = FakeJudge(0.0)
    guard = make_guard(judge, metrics, valkey)
    text = item(f"{INJECTION} " + "x" * JEV_BYTES)

    result = judged(guard, [text])
    again = judged(guard, [text])

    h = text["hash"]
    assert result == again == Judged([h], [], {h: FLAGGED_SCORE}, [], [], {})
    assert judge.calls == []
    assert valkey.data[jev_key(h)] == "-"
    assert valkey.ttls[jev_key(h)] == TTL
    assert sample(metrics, REQUESTS, outcome="skipped") == 1


def test_text_exactly_at_the_jev_limit_is_asked(metrics, valkey):
    judge = FakeJudge(0.5)
    text = item(f"{INJECTION} ".ljust(JEV_BYTES, "x"))

    judged(make_guard(judge, metrics, valkey), [text])

    assert judge.calls == [text["text"]]


def test_the_limit_counts_bytes_not_characters(metrics, valkey):
    judge = FakeJudge(0.5)
    text = item(f"{INJECTION} " + "é" * (JEV_BYTES // 2))

    judged(make_guard(judge, metrics, valkey), [text])

    assert judge.calls == []


@pytest.mark.parametrize(("permanent", "ttl"), [(True, TTL), (False, 3600)])
def test_an_error_is_flagged_and_stored_as_a_marker_for_the_ttl_its_kind_calls_for(metrics, valkey, permanent, ttl):
    judge = FakeJudge(JevError("no", permanent=permanent))
    guard = make_guard(judge, metrics, valkey)
    text = bad()

    result = judged(guard, [text])

    h = text["hash"]
    assert result == Judged([h], [], {h: FLAGGED_SCORE}, [], [], {})
    assert valkey.data[jev_key(h)] == "-"
    assert valkey.ttls[jev_key(h)] == ttl
    assert sample(metrics, REQUESTS, outcome="error") == 1


def test_an_unexpected_failure_is_flagged_and_stored_as_a_short_marker(metrics, valkey):
    guard = make_guard(FakeJudge(RuntimeError("bug")), metrics, valkey)
    text = bad()

    result = judged(guard, [text])

    assert result.flagged == [text["hash"]]
    assert valkey.ttls[jev_key(text["hash"])] == 3600
    assert sample(metrics, REQUESTS, outcome="error") == 1


def test_a_marker_is_served_as_flagged_without_asking_again(metrics, valkey):
    judge = FakeJudge(0.0)
    guard = make_guard(judge, metrics, valkey)
    text = bad()
    valkey.data[jev_key(text["hash"])] = "-"

    result = judged(guard, [text])

    assert result.flagged == [text["hash"]]
    assert judge.calls == []


def test_an_error_marker_is_not_cleared_by_a_later_answer_from_another_replica(metrics, valkey):
    text = bad()
    judged(make_guard(FakeJudge(JevError("down")), metrics, valkey), [text])
    other = FakeJudge(0.0)

    result = judged(make_guard(other, metrics, valkey), [text])

    assert result.cleared == []
    assert other.calls == []


def test_concurrent_requests_for_one_text_ask_jev_once(metrics, valkey):
    judge = FakeJudge(0.97, gated=True)
    guard = make_guard(judge, metrics, valkey)
    text = bad()

    async def run():
        first = asyncio.create_task(guard.check([text], []))
        await wait_for(judge.started.is_set)
        second = asyncio.create_task(guard.check([text], []))
        third = asyncio.create_task(guard.check([], [text["hash"]]))
        await asyncio.sleep(0.05)
        judge.release()
        return await asyncio.gather(first, second, third)

    results = asyncio.run(run())

    assert len(judge.calls) == 1
    assert all(r.blocked == [text["hash"]] for r in results)


def test_the_same_text_twice_in_one_request_is_asked_once(metrics, valkey):
    judge = FakeJudge(0.5)
    text = bad()

    result = judged(make_guard(judge, metrics, valkey), [text, text])

    assert judge.calls == [text["text"]]
    assert result.flagged == [text["hash"]]


def test_two_replicas_asking_at_once_serve_the_first_answer_stored(metrics, valkey):
    judge_a, judge_b = FakeJudge(0.99, gated=True), FakeJudge(0.01, gated=True)
    guard_a, guard_b = make_guard(judge_a, metrics, valkey), make_guard(judge_b, metrics, valkey)
    text = bad()

    async def run():
        first = asyncio.create_task(guard_a.check([text], []))
        second = asyncio.create_task(guard_b.check([text], []))
        await wait_for(lambda: judge_a.started.is_set() and judge_b.started.is_set())
        judge_a.release()
        won = await first
        judge_b.release()
        return won, await second

    first, second = asyncio.run(run())

    h = text["hash"]
    assert first.blocked == second.blocked == [h]
    assert second.jev_scores == {h: 0.99}
    assert valkey.data[jev_key(h)] == "0.99"
    assert sample(metrics, REQUESTS, outcome="cleared") == 1


def test_a_marker_stored_by_another_replica_wins_over_a_late_answer(metrics, valkey):
    judge_a, judge_b = FakeJudge(JevError("down"), gated=True), FakeJudge(0.01, gated=True)
    guard_a, guard_b = make_guard(judge_a, metrics, valkey), make_guard(judge_b, metrics, valkey)
    text = bad()

    async def run():
        first = asyncio.create_task(guard_a.check([text], []))
        second = asyncio.create_task(guard_b.check([text], []))
        await wait_for(lambda: judge_a.started.is_set() and judge_b.started.is_set())
        judge_a.release()
        await first
        judge_b.release()
        return await second

    result = asyncio.run(run())

    assert result.cleared == []
    assert result.flagged == [text["hash"]]


def test_a_known_hash_waits_for_the_jev_answer_in_flight(metrics, valkey):
    judge = FakeJudge(0.01, gated=True)
    guard = make_guard(judge, metrics, valkey)
    text = bad()

    async def run():
        request = asyncio.create_task(guard.check([text], []))
        await wait_for(judge.started.is_set)
        lookup = asyncio.create_task(guard.check([], [text["hash"]]))
        await asyncio.sleep(0.05)
        waiting = not lookup.done()
        judge.release()
        await request
        return waiting, await lookup

    waiting, result = asyncio.run(run())

    assert waiting
    assert result.cleared == [text["hash"]]


def test_the_ask_finishes_and_is_stored_after_the_request_is_cancelled(metrics, valkey):
    judge = FakeJudge(0.97, gated=True)
    guard = make_guard(judge, metrics, valkey)
    text = bad()

    async def run():
        request = asyncio.create_task(guard.check([text], []))
        await wait_for(judge.started.is_set)
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
        judge.release()
        await wait_for(lambda: jev_key(text["hash"]) in valkey.data)

    asyncio.run(run())

    assert valkey.data[jev_key(text["hash"])] == "0.97"


async def cancel_mid_scan(guard: ToolGuard, scanner: FakeScanner, text: dict) -> None:
    """Start a request, drop it while its scan runs, then let the scan finish and the guard settle."""
    request = asyncio.create_task(guard.check([text], []))
    await wait_for(scanner.started.is_set)
    request.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request
    scanner.release()
    await guard.drain(5)


@pytest.mark.parametrize("max_pending_scans", [1, 16])
def test_the_ask_follows_the_scan_and_is_stored_after_the_request_is_cancelled_mid_scan(
    metrics, valkey, max_pending_scans
):
    judge = FakeJudge(0.97)
    scanner = FakeScanner(gated=True)
    guard = make_guard(judge, metrics, valkey, scanner=scanner, max_pending_scans=max_pending_scans)
    text = bad()

    asyncio.run(cancel_mid_scan(guard, scanner, text))
    later = judged(guard, known=[text["hash"]])

    h = text["hash"]
    assert valkey.data[jev_key(h)] == "0.97"
    assert judge.calls == [text["text"]]
    assert later == Judged([h], [], {h: FLAGGED_SCORE}, [h], [], {h: 0.97})


def test_the_ask_after_a_cancelled_request_is_skipped_when_an_answer_is_already_stored(metrics, valkey):
    judge = FakeJudge(0.0)
    scanner = FakeScanner(gated=True)
    guard = make_guard(judge, metrics, valkey, scanner=scanner)
    text = bad()
    valkey.data[jev_key(text["hash"])] = "0.5"

    asyncio.run(cancel_mid_scan(guard, scanner, text))

    assert judge.calls == []
    assert valkey.data[jev_key(text["hash"])] == "0.5"


def test_a_clean_scan_is_not_followed_by_an_ask_after_a_cancelled_request(metrics, valkey):
    judge = FakeJudge(0.97)
    scanner = FakeScanner(gated=True)
    guard = make_guard(judge, metrics, valkey, scanner=scanner)

    asyncio.run(cancel_mid_scan(guard, scanner, item("fine")))

    assert judge.calls == []


def test_close_cancels_asks_in_flight_and_stores_nothing(metrics, valkey):
    judge = FakeJudge(0.97, gated=True)
    guard = make_guard(judge, metrics, valkey)
    text = bad()

    async def run():
        request = asyncio.create_task(guard.check([text], []))
        await wait_for(judge.started.is_set)
        guard.close()
        return await request

    result = asyncio.run(run())

    h = text["hash"]
    assert result == Judged([h], [], {h: FLAGGED_SCORE}, [], [], {})
    assert jev_key(h) not in valkey.data
    assert sample(metrics, REQUESTS, outcome="error") == 0


def test_drain_waits_for_asks_in_flight(metrics, valkey):
    judge = FakeJudge(0.97, gated=True)
    guard = make_guard(judge, metrics, valkey)
    text = bad()

    async def run():
        request = asyncio.create_task(guard.check([text], []))
        await wait_for(judge.started.is_set)
        draining = asyncio.create_task(guard.drain(5))
        await asyncio.sleep(0.05)
        waiting = not draining.done()
        judge.release()
        await draining
        await request
        return waiting

    assert asyncio.run(run()) is True
    assert valkey.data[jev_key(text["hash"])] == "0.97"


def test_drain_gives_up_on_a_slow_ask_without_cancelling_it(metrics, valkey):
    judge = FakeJudge(0.97, gated=True)
    guard = make_guard(judge, metrics, valkey)

    async def run():
        request = asyncio.create_task(guard.check([bad()], []))
        await wait_for(judge.started.is_set)
        started = asyncio.get_running_loop().time()
        await guard.drain(0.05)
        elapsed = asyncio.get_running_loop().time() - started
        judge.release()
        await request
        return elapsed

    assert asyncio.run(run()) < 2


def test_asks_in_flight_use_pending_slots_and_a_text_beyond_the_limit_is_flagged_unasked(metrics, valkey):
    judge = FakeJudge(0.97, gated=True)
    guard = make_guard(judge, metrics, valkey, max_pending_scans=1)
    first, second = bad("one"), bad("two")
    for text in (first, second):
        valkey.data[horizon_key(text["hash"])] = flagged_value(text["text"])

    async def run():
        request = asyncio.create_task(guard.check([first, second], []))
        await wait_for(judge.started.is_set)
        gauge = sample(metrics, "llm_tool_guard_pending_scans")
        judge.release()
        return gauge, await request

    gauge, result = asyncio.run(run())

    assert gauge == 1
    assert result.blocked == [first["hash"]]
    assert result.flagged == [first["hash"], second["hash"]]
    assert judge.calls == [first["text"]]
    assert jev_key(second["hash"]) not in valkey.data
    assert sample(metrics, REQUESTS, outcome="skipped") == 1
    assert sample(metrics, "llm_tool_guard_pending_scans") == 0


@pytest.mark.parametrize("p", [0.01, 0.99])
def test_valkey_down_still_asks_jev_but_an_answer_that_cannot_be_stored_leaves_the_text_flagged(metrics, valkey, p):
    valkey.down = True
    judge = FakeJudge(p)
    guard = make_guard(judge, metrics, valkey)
    text = bad()

    result = judged(guard, [text])

    h = text["hash"]
    assert result == Judged([h], [], {h: FLAGGED_SCORE}, [], [], {})
    assert judge.calls == [text["text"]]


def test_without_valkey_jev_is_asked_each_time(metrics):
    judge = FakeJudge(0.01)
    guard = make_guard(judge, metrics, None)
    text = bad()

    first = judged(guard, [text])
    second = judged(guard, [text])

    assert first.cleared == second.cleared == [text["hash"]]
    assert judge.calls == [text["text"]] * 2


def test_the_ask_is_timed(metrics, valkey):
    judged(make_guard(FakeJudge(0.5), metrics, valkey), [bad()])

    assert sample(metrics, "llm_tool_guard_jev_duration_seconds_count") == 1


class Text(str):
    """A str that can be weakly referenced."""


def test_texts_that_need_no_second_look_are_released_while_others_scan(metrics, valkey):
    scanner = FakeScanner(gated=True)
    guard = make_guard(FakeJudge(0.5), metrics, valkey, scanner=scanner)
    refs = []

    def items():
        cached = Text("already known clean")
        refs.append(weakref.ref(cached))
        valkey.data[horizon_key(digest(cached))] = "0:0.01"
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


def test_aclose_closes_the_judge(metrics, valkey):
    judge = FakeJudge()
    guard = make_guard(judge, metrics, valkey)

    asyncio.run(guard.aclose())

    assert judge.closed is True


def test_aclose_without_a_second_check_does_nothing(metrics, valkey):
    asyncio.run(make_guard(None, metrics, valkey).aclose())


ONE, TWO, THREE = "first trigger", "second trigger", "third trigger"
ERROR = JevError("no answer", permanent=False)


def test_only_the_flagged_windows_are_sent_each_as_its_own_slice_of_the_text(metrics, valkey):
    text, spans = multi("calm intro", ONE, "calm middle", TWO, "calm end", flagged=(1, 3))
    judge = FakeJudge(0.5)

    result = judged(make_guard(judge, metrics, valkey, scanner=flagging(spans)), [text])

    assert judge.calls == [ONE, TWO]
    assert result.flagged == [text["hash"]]
    assert sample(metrics, REQUESTS, outcome="middle") == 2


def test_overlapping_flagged_windows_are_each_sent_whole(metrics, valkey):
    text = item("abcdefghij")
    judge = FakeJudge(0.5)

    judged(make_guard(judge, metrics, valkey, scanner=flagging(((0, 6), (4, 10)))), [text])

    assert judge.calls == ["abcdef", "efghij"]


def test_a_text_over_the_jev_limit_with_one_small_flagged_window_sends_only_that_window(metrics, valkey):
    text, spans = multi("x" * 600, ONE, "y" * 100, flagged=(1,))
    judge = FakeJudge(0.97)

    result = judged(make_guard(judge, metrics, valkey, scanner=flagging(spans)), [text])

    assert len(text["text"].encode()) > JEV_BYTES
    assert judge.calls == [ONE]
    assert result.blocked == [text["hash"]]
    assert sample(metrics, REQUESTS, outcome="skipped") == 0


@pytest.mark.parametrize(("p", "blocked"), [(0.97, True), (0.01, False)])
def test_a_flagged_window_over_the_jev_limit_is_not_sent_counts_as_unanswered_and_is_not_asked_again(
    metrics, valkey, p, blocked
):
    text, spans = multi(ONE, "z" * (JEV_BYTES + 1), flagged=(0, 1))
    judge = FakeJudge(p)
    h = text["hash"]

    guard = make_guard(judge, metrics, valkey, scanner=flagging(spans))

    result = judged(guard, [text])
    again = judged(guard, [text])

    assert judge.calls == [ONE]
    assert result.flagged == again.flagged == [h]
    assert (result.blocked, result.cleared) == (again.blocked, again.cleared) == ([h] if blocked else [], [])
    assert valkey.data[jev_key(h)] == f"{p}+"
    assert valkey.ttls[jev_key(h)] == TTL
    assert sample(metrics, REQUESTS, outcome="skipped") == 1


@pytest.mark.parametrize(
    ("answers", "outcome"),
    [
        ([0.97, 0.01], "blocked"),
        ([0.01, 0.97], "blocked"),
        ([BLOCK_AT, 0.0], "blocked"),
        ([0.97, ERROR], "blocked"),
        ([ERROR, 0.97], "blocked"),
        ([0.01, 0.02], "cleared"),
        ([0.0799, 0.0], "cleared"),
        ([0.01, 0.5], "flagged"),
        ([0.5, 0.5], "flagged"),
        ([CLEAR_BELOW, 0.0], "flagged"),
        ([0.01, ERROR], "flagged"),
        ([ERROR, 0.01], "flagged"),
        ([ERROR, ERROR], "flagged"),
    ],
)
def test_a_text_is_blocked_when_any_window_blocks_cleared_only_when_every_window_clears_else_flagged(
    metrics, valkey, answers, outcome
):
    text, spans = multi(ONE, "calm", TWO, flagged=(0, 2))
    judge = FakeJudge()
    judge.answers = dict(zip([ONE, TWO], answers, strict=True))
    h = text["hash"]

    result = judged(make_guard(judge, metrics, valkey, scanner=flagging(spans)), [text])

    assert judge.calls == [ONE, TWO]
    assert result.blocked == ([h] if outcome == "blocked" else [])
    assert result.cleared == ([h] if outcome == "cleared" else [])
    assert result.flagged == ([] if outcome == "cleared" else [h])


def test_the_jev_score_and_the_stored_answer_of_a_text_are_the_highest_probability_of_its_windows(metrics, valkey):
    text, spans = multi(ONE, TWO, THREE, flagged=(0, 1, 2))
    judge = FakeJudge()
    judge.answers = {ONE: 0.3, TWO: 0.6, THREE: 0.1}
    h = text["hash"]

    result = judged(make_guard(judge, metrics, valkey, scanner=flagging(spans)), [text])

    assert result.jev_scores == {h: 0.6}
    assert valkey.data[jev_key(h)] == "0.6"
    assert valkey.ttls[jev_key(h)] == TTL
    assert sample(metrics, REQUESTS, outcome="middle") == 3


@pytest.mark.parametrize(("permanent", "ttl"), [(True, TTL), (False, 3600)])
def test_a_window_without_an_answer_makes_the_stored_answer_partial_for_the_ttl_its_failure_calls_for(
    metrics, valkey, permanent, ttl
):
    text, spans = multi(ONE, TWO, flagged=(0, 1))
    judge = FakeJudge()
    judge.answers = {ONE: 0.4, TWO: JevError("no", permanent=permanent)}
    h = text["hash"]

    result = judged(make_guard(judge, metrics, valkey, scanner=flagging(spans)), [text])

    assert result.jev_scores == {h: 0.4}
    assert valkey.data[jev_key(h)] == "0.4+"
    assert valkey.ttls[jev_key(h)] == ttl
    assert sample(metrics, REQUESTS, outcome="error") == 1


@pytest.mark.parametrize(("stored", "blocked"), [("0.01+", False), ("0.95+", True), ("0.5+", False)])
def test_a_partial_answer_never_clears_even_under_thresholds_that_would_but_can_still_block(
    metrics, valkey, stored, blocked
):
    text = bad()
    h = text["hash"]
    valkey.data[jev_key(h)] = stored
    judge = FakeJudge(0.0)

    result = judged(make_guard(judge, metrics, valkey, clear_below=0.6), [text])

    assert result.flagged == [h]
    assert (result.blocked, result.cleared) == ([h] if blocked else [], [])
    assert judge.calls == []


def test_a_text_the_model_flagged_with_no_window_to_ask_about_stays_flagged_unasked(metrics, valkey):
    text = bad()
    h = text["hash"]
    judge = FakeJudge(0.0)
    scanner = FakeScanner()
    scanner.verdict = lambda _text: (True, 1.0, ())

    result = judged(make_guard(judge, metrics, valkey, scanner=scanner), [text])

    assert result == Judged([h], [], {h: 1.0}, [], [], {})
    assert judge.calls == []
    assert jev_key(h) not in valkey.data
    assert sample(metrics, REQUESTS, outcome="skipped") == 0


@pytest.mark.parametrize(("windows", "asked"), [(1, True), (2, True), (3, False), (5, False)])
def test_a_text_flagged_in_more_windows_than_the_cap_is_not_asked_and_stays_flagged(metrics, valkey, windows, asked):
    text, spans = multi(*(f"{n} trigger" for n in range(windows)), flagged=tuple(range(windows)))
    judge = FakeJudge(0.0)
    h = text["hash"]

    result = judged(make_guard(judge, metrics, valkey, scanner=flagging(spans), max_windows=2), [text])

    assert len(judge.calls) == (windows if asked else 0)
    assert result.cleared == ([h] if asked else [])
    assert result.flagged == ([] if asked else [h])
    assert (jev_key(h) in valkey.data) is asked
    assert sample(metrics, REQUESTS, outcome="skipped") == 0


def test_a_cached_flag_in_more_windows_than_the_cap_is_not_asked_about(metrics, valkey):
    text, spans = multi(*(f"{n} trigger" for n in range(4)), flagged=(0, 1, 2, 3))
    h = text["hash"]
    valkey.data[horizon_key(h)] = spans_value(spans)
    judge = FakeJudge(0.0)

    result = judged(make_guard(judge, metrics, valkey), [text])

    assert result == Judged([h], [], {h: FLAGGED_SCORE}, [], [], {})
    assert judge.calls == []
    assert jev_key(h) not in valkey.data


def test_a_flagged_verdict_cached_without_spans_is_not_asked_about(metrics, valkey):
    text = bad()
    h = text["hash"]
    valkey.data[horizon_key(h)] = "1:1.0"
    judge = FakeJudge(0.0)

    result = judged(make_guard(judge, metrics, valkey), [text])

    assert result == Judged([h], [], {h: 1.0}, [], [], {})
    assert judge.calls == []
    assert jev_key(h) not in valkey.data


def test_a_flagged_text_cached_without_a_jev_answer_is_asked_about_its_stored_windows_and_not_rescanned(
    metrics, valkey
):
    text, spans = multi("calm intro", ONE, "calm middle", TWO, flagged=(1, 3))
    h = text["hash"]
    judged(make_guard(None, metrics, valkey, scanner=flagging(spans)), [text])
    scanner = FakeScanner()
    judge = FakeJudge(0.01)

    result = judged(make_guard(judge, metrics, valkey, scanner=scanner), [text])

    assert valkey.data[horizon_key(h)] == f"1:{FLAGGED_SCORE}:11-24,37-51"
    assert scanner.calls == []
    assert judge.calls == [ONE, TWO]
    assert result.cleared == [h]


def test_the_windows_of_a_text_are_asked_at_once(metrics, valkey):
    text, spans = multi(ONE, TWO, THREE, flagged=(0, 1, 2))
    judge = FakeJudge(0.01, gated=True)
    guard = make_guard(judge, metrics, valkey, scanner=flagging(spans))

    async def run():
        request = asyncio.create_task(guard.check([text], []))
        await wait_for(lambda: len(judge.calls) == 3)
        judge.release()
        return await request

    assert asyncio.run(run()).cleared == [text["hash"]]
    assert sorted(judge.calls) == sorted([ONE, TWO, THREE])


def test_a_text_takes_a_pending_slot_for_each_of_its_windows_at_once(metrics, valkey):
    text, spans = multi(ONE, TWO, THREE, flagged=(0, 1, 2))
    judge = FakeJudge(0.01, gated=True)
    guard = make_guard(judge, metrics, valkey, scanner=flagging(spans), max_pending_scans=3)

    async def run():
        request = asyncio.create_task(guard.check([text], []))
        await wait_for(lambda: len(judge.calls) == 3)
        gauge = sample(metrics, "llm_tool_guard_pending_scans")
        judge.release()
        return gauge, await request

    gauge, result = asyncio.run(run())

    assert gauge == 3
    assert result.cleared == [text["hash"]]
    assert sample(metrics, "llm_tool_guard_pending_scans") == 0


def test_a_text_whose_windows_do_not_all_find_a_slot_is_not_asked_and_nothing_is_stored(metrics, valkey):
    text, spans = multi(ONE, TWO, THREE, flagged=(0, 1, 2))
    judge = FakeJudge(0.97)
    guard = make_guard(judge, metrics, valkey, scanner=flagging(spans), max_pending_scans=2)
    h = text["hash"]

    result = judged(guard, [text])

    assert result == Judged([h], [], {h: FLAGGED_SCORE}, [], [], {})
    assert judge.calls == []
    assert jev_key(h) not in valkey.data
    assert sample(metrics, REQUESTS, outcome="skipped") == 3
    assert sample(metrics, "llm_tool_guard_pending_scans") == 0


def test_a_text_that_cannot_have_a_slot_for_every_window_leaves_the_free_slots_to_other_texts(metrics, valkey):
    first, first_spans = multi(ONE, TWO, flagged=(0, 1))
    second, second_spans = multi("alpha trigger", "beta trigger", flagged=(0, 1))
    for text, spans in ((first, first_spans), (second, second_spans)):
        valkey.data[horizon_key(text["hash"])] = spans_value(spans)
    judge = FakeJudge(0.97, gated=True)
    guard = make_guard(judge, metrics, valkey, max_pending_scans=3)
    third = bad("third")
    valkey.data[horizon_key(third["hash"])] = flagged_value(third["text"])

    async def run():
        request = asyncio.create_task(guard.check([first, second, third], []))
        await wait_for(lambda: len(judge.calls) == 3)
        await asyncio.sleep(0.05)
        judge.release()
        return await request

    result = asyncio.run(run())

    assert sorted(judge.calls) == sorted([ONE, TWO, third["text"]])
    assert result.blocked == [first["hash"], third["hash"]]
    assert result.flagged == [first["hash"], second["hash"], third["hash"]]
    assert jev_key(second["hash"]) not in valkey.data
    assert sample(metrics, REQUESTS, outcome="skipped") == 2


def test_after_a_cancelled_request_a_text_flagged_with_no_window_to_ask_about_is_not_asked_or_stored(metrics, valkey):
    text = bad()
    h = text["hash"]
    scanner = FakeScanner(gated=True)
    scanner.verdict = lambda _text: (True, 1.0, ())
    judge = FakeJudge(0.0)
    guard = make_guard(judge, metrics, valkey, scanner=scanner)

    asyncio.run(cancel_mid_scan(guard, scanner, text))
    later = judged(guard, known=[h])

    assert judge.calls == []
    assert jev_key(h) not in valkey.data
    assert later == Judged([h], [], {h: 1.0}, [], [], {})


def test_after_a_cancelled_request_a_text_flagged_in_more_windows_than_the_cap_is_not_asked_or_stored(metrics, valkey):
    text, spans = multi(*(f"{n} trigger" for n in range(JEV_WINDOWS + 1)), flagged=tuple(range(JEV_WINDOWS + 1)))
    scanner = flagging(spans, gated=True)
    judge = FakeJudge(0.0)
    guard = make_guard(judge, metrics, valkey, scanner=scanner)

    asyncio.run(cancel_mid_scan(guard, scanner, text))

    assert judge.calls == []
    assert jev_key(text["hash"]) not in valkey.data


def test_replicas_asking_about_the_windows_of_one_text_serve_the_first_answer_stored(metrics, valkey):
    text, spans = multi(ONE, TWO, flagged=(0, 1))
    judge_a, judge_b = FakeJudge(gated=True), FakeJudge(0.02, gated=True)
    judge_a.answers = {ONE: 0.99, TWO: 0.01}
    guard_a = make_guard(judge_a, metrics, valkey, scanner=flagging(spans))
    guard_b = make_guard(judge_b, metrics, valkey, scanner=flagging(spans))
    h = text["hash"]

    async def run():
        first = asyncio.create_task(guard_a.check([text], []))
        second = asyncio.create_task(guard_b.check([text], []))
        await wait_for(lambda: len(judge_a.calls) == 2 and len(judge_b.calls) == 2)
        judge_a.release()
        won = await first
        judge_b.release()
        return won, await second

    first, second = asyncio.run(run())

    assert first.blocked == second.blocked == [h]
    assert second.jev_scores == {h: 0.99}
    assert valkey.data[jev_key(h)] == "0.99"


def test_after_a_cancelled_request_the_flagged_windows_are_asked_once_the_scan_ends(metrics, valkey):
    text, spans = multi("calm", ONE, TWO, flagged=(1, 2))
    scanner = flagging(spans, gated=True)
    judge = FakeJudge(0.97)
    guard = make_guard(judge, metrics, valkey, scanner=scanner)

    asyncio.run(cancel_mid_scan(guard, scanner, text))

    assert judge.calls == [ONE, TWO]
    assert valkey.data[jev_key(text["hash"])] == "0.97"
