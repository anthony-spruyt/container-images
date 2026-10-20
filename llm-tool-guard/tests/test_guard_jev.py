"""Tests for the Jev second check in the scan service: which texts go to Jev, what each answer means, what is stored."""

import asyncio
import gc
import weakref

import pytest

from cache import JevCache, VerdictCache
from fakes import FLAGGED_SCORE, FLAGGED_VALUE, INJECTION, FakeJudge, FakeScanner, FakeValkey, digest, sample
from guard import Judged, ToolGuard
from judge import JevError
from metrics import Metrics
from second_check import SecondCheck

TTL = 3600 * 24
BLOCK_AT = 0.9
CLEAR_BELOW = 0.08
JEV_BYTES = 512
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
) -> ToolGuard:
    cache = VerdictCache(valkey, namespace="ns", ttl_seconds=TTL, metrics=metrics)
    second = None
    if judge is not None:
        jev_cache = JevCache(valkey, namespace="jns", ttl_seconds=TTL, metrics=metrics)
        second = SecondCheck(
            judge, jev_cache, metrics, block_at=block_at, clear_below=clear_below, max_text_bytes=JEV_BYTES
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


def horizon_key(hash_: str) -> str:
    return f"llm-tool-guard:ns:{hash_}"


def jev_key(hash_: str) -> str:
    return f"llm-tool-guard:jev:jns:{hash_}"


def judged(guard: ToolGuard, new=(), known=()) -> Judged:
    return asyncio.run(guard.check_with_jev(list(new), list(known)))


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


def test_check_without_the_opt_in_never_asks_jev_and_flags_as_before(metrics, valkey):
    judge = FakeJudge(0.99)
    guard = make_guard(judge, metrics, valkey)
    text = bad()

    flagged, unknown, scores = asyncio.run(guard.check([text], []))

    assert (flagged, unknown, scores) == ([text["hash"]], [], {text["hash"]: FLAGGED_SCORE})
    assert judge.calls == []
    assert [k for k in valkey.data if "jev" in k] == []


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
    assert valkey.data == {horizon_key(h): FLAGGED_VALUE, jev_key(h): "0.5"}
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
    valkey.data[horizon_key(h)] = FLAGGED_VALUE

    result = judged(guard, known=[h])

    assert result == Judged([h], [], {h: FLAGGED_SCORE}, [], [], {})
    assert judge.calls == []


def test_a_flagged_text_the_model_cached_is_sent_to_jev_when_it_arrives_as_new(metrics, valkey):
    judge = FakeJudge(0.01)
    scanner = FakeScanner()
    guard = make_guard(judge, metrics, valkey, scanner=scanner)
    text = bad()
    valkey.data[horizon_key(text["hash"])] = FLAGGED_VALUE

    result = judged(guard, [text])

    assert result.cleared == [text["hash"]]
    assert scanner.calls == []
    assert judge.calls == [text["text"]]


def test_text_over_the_jev_limit_is_flagged_unasked_and_the_marker_is_stored_for_the_full_ttl(metrics, valkey):
    judge = FakeJudge(0.0)
    guard = make_guard(judge, metrics, valkey)
    text = item(f"{INJECTION} " + "x" * JEV_BYTES)

    result = judged(guard, [text])

    h = text["hash"]
    assert result == Judged([h], [], {h: FLAGGED_SCORE}, [], [], {})
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
        first = asyncio.create_task(guard.check_with_jev([text], []))
        await wait_for(judge.started.is_set)
        second = asyncio.create_task(guard.check_with_jev([text], []))
        third = asyncio.create_task(guard.check_with_jev([], [text["hash"]]))
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
        first = asyncio.create_task(guard_a.check_with_jev([text], []))
        second = asyncio.create_task(guard_b.check_with_jev([text], []))
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
        first = asyncio.create_task(guard_a.check_with_jev([text], []))
        second = asyncio.create_task(guard_b.check_with_jev([text], []))
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
        request = asyncio.create_task(guard.check_with_jev([text], []))
        await wait_for(judge.started.is_set)
        lookup = asyncio.create_task(guard.check_with_jev([], [text["hash"]]))
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
        request = asyncio.create_task(guard.check_with_jev([text], []))
        await wait_for(judge.started.is_set)
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
        judge.release()
        await wait_for(lambda: jev_key(text["hash"]) in valkey.data)

    asyncio.run(run())

    assert valkey.data[jev_key(text["hash"])] == "0.97"


def test_close_cancels_asks_in_flight_and_stores_nothing(metrics, valkey):
    judge = FakeJudge(0.97, gated=True)
    guard = make_guard(judge, metrics, valkey)
    text = bad()

    async def run():
        request = asyncio.create_task(guard.check_with_jev([text], []))
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
        request = asyncio.create_task(guard.check_with_jev([text], []))
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
        request = asyncio.create_task(guard.check_with_jev([bad()], []))
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
        valkey.data[horizon_key(text["hash"])] = FLAGGED_VALUE

    async def run():
        request = asyncio.create_task(guard.check_with_jev([first, second], []))
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


def test_valkey_down_still_asks_jev_and_uses_the_answer_for_this_request(metrics, valkey):
    valkey.down = True
    guard = make_guard(FakeJudge(0.01), metrics, valkey)
    text = bad()

    result = judged(guard, [text])

    assert result.cleared == [text["hash"]]


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
        request = asyncio.create_task(guard.check_with_jev(items(), []))
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
