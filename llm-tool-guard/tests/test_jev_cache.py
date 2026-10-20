"""Tests for the Jev answer cache: key composition, stored forms, first-writer-wins and failure handling."""

import asyncio

import pytest

from cache import JevAnswer, JevCache, jev_namespace
from fakes import FakeValkey, digest, sample

TTL = 3600 * 24
BASE = {"model": "jev-1.13.0", "question": '{"type": "noul"}', "runtime": {"judge.py": "aaa"}}


def make_cache(valkey, metrics, *, ttl=TTL, namespace="jns"):
    return JevCache(valkey, namespace=namespace, ttl_seconds=ttl, metrics=metrics)


def key(hash_, namespace="jns"):
    return f"llm-tool-guard:jev:{namespace}:{hash_}"


def test_namespace_is_stable_for_the_same_settings():
    assert jev_namespace(**BASE) == jev_namespace(**dict(BASE))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model", "jev-1.14.0"),
        ("question", '{"type": "choice"}'),
        ("runtime", {"judge.py": "bbb"}),
    ],
)
def test_namespace_changes_with_the_model_the_question_and_the_client_source(field, value):
    assert jev_namespace(**{**BASE, field: value}) != jev_namespace(**BASE)


def test_an_answer_is_stored_as_the_raw_probability_for_the_full_ttl(metrics, valkey):
    cache = make_cache(valkey, metrics)

    winner = asyncio.run(cache.settle(digest("a"), 0.0312, permanent=True))

    assert winner == JevAnswer(0.0312)
    assert valkey.data == {key(digest("a")): "0.0312"}
    assert valkey.ttls == {key(digest("a")): TTL}


def test_it_is_written_only_if_absent_and_the_stored_value_is_read_back(metrics, valkey):
    cache = make_cache(valkey, metrics)

    asyncio.run(cache.settle(digest("a"), 0.5, permanent=True))

    assert valkey.set_calls == [(key(digest("a")), "0.5", TTL, True, True)]


def test_a_permanent_failure_is_stored_as_a_no_answer_marker_for_the_full_ttl(metrics, valkey):
    cache = make_cache(valkey, metrics)

    winner = asyncio.run(cache.settle(digest("a"), None, permanent=True))

    assert winner == JevAnswer(None)
    assert valkey.data == {key(digest("a")): "-"}
    assert valkey.ttls == {key(digest("a")): TTL}


def test_a_transient_failure_is_stored_for_an_hour(metrics, valkey):
    cache = make_cache(valkey, metrics)

    asyncio.run(cache.settle(digest("a"), None, permanent=False))

    assert valkey.ttls == {key(digest("a")): 3600}


def test_a_transient_failure_never_outlives_the_cache_ttl(metrics, valkey):
    cache = make_cache(valkey, metrics, ttl=60)

    asyncio.run(cache.settle(digest("a"), None, permanent=False))

    assert valkey.ttls == {key(digest("a")): 60}


def test_the_first_answer_stored_wins_over_a_later_one(metrics, valkey):
    cache = make_cache(valkey, metrics)
    hash_ = digest("a")

    first = asyncio.run(cache.settle(hash_, 0.97, permanent=True))
    second = asyncio.run(cache.settle(hash_, 0.01, permanent=True))

    assert first == second == JevAnswer(0.97)
    assert valkey.data == {key(hash_): "0.97"}


def test_a_stored_no_answer_marker_wins_over_a_later_answer(metrics, valkey):
    cache = make_cache(valkey, metrics)
    hash_ = digest("a")

    asyncio.run(cache.settle(hash_, None, permanent=False))
    winner = asyncio.run(cache.settle(hash_, 0.01, permanent=True))

    assert winner == JevAnswer(None)
    assert valkey.data == {key(hash_): "-"}


def test_a_stored_answer_wins_over_a_later_failure(metrics, valkey):
    cache = make_cache(valkey, metrics)
    hash_ = digest("a")

    asyncio.run(cache.settle(hash_, 0.4, permanent=True))

    assert asyncio.run(cache.settle(hash_, None, permanent=False)) == JevAnswer(0.4)


def test_an_unreadable_winner_counts_as_no_answer(metrics, valkey):
    valkey.data[key(digest("a"))] = "high"
    cache = make_cache(valkey, metrics)

    assert asyncio.run(cache.settle(digest("a"), 0.5, permanent=True)) == JevAnswer(None)


def test_get_many_returns_answers_and_markers_and_skips_misses(metrics, valkey):
    cache = make_cache(valkey, metrics)
    a, b, c = digest("a"), digest("b"), digest("c")
    asyncio.run(cache.settle(a, 0.25, permanent=True))
    asyncio.run(cache.settle(b, None, permanent=True))

    assert asyncio.run(cache.get_many([a, b, c])) == {a: JevAnswer(0.25), b: JevAnswer(None)}


def test_get_many_of_nothing_skips_valkey(metrics, valkey):
    assert asyncio.run(make_cache(valkey, metrics).get_many([])) == {}
    assert valkey.mget_calls == []


def test_answers_are_read_under_their_own_namespace(metrics, valkey):
    asyncio.run(make_cache(valkey, metrics, namespace="old").settle(digest("a"), 0.5, permanent=True))

    assert asyncio.run(make_cache(valkey, metrics, namespace="new").get_many([digest("a")])) == {}


def test_jev_keys_do_not_overlap_the_verdict_keys(metrics, valkey):
    asyncio.run(make_cache(valkey, metrics).settle(digest("a"), 0.5, permanent=True))
    valkey.data[f"llm-tool-guard:{'0123456789abcdef'}:{digest('a')}"] = "1:0.97"

    assert asyncio.run(make_cache(valkey, metrics).get_many([digest("a")])) == {digest("a"): JevAnswer(0.5)}


@pytest.mark.parametrize("value", ["", "high", "nan", "inf", "1.5", "-0.1", "0.5:1", "1:0.9", "--"])
def test_an_unexpected_stored_value_is_a_miss(metrics, valkey, value):
    valkey.data[key(digest("a"))] = value

    assert asyncio.run(make_cache(valkey, metrics).get_many([digest("a")])) == {}


def test_bytes_values_are_read(metrics, valkey):
    valkey.data[key(digest("a"))] = b"0.5"
    valkey.data[key(digest("b"))] = b"-"

    answers = asyncio.run(make_cache(valkey, metrics).get_many([digest("a"), digest("b")]))

    assert answers == {digest("a"): JevAnswer(0.5), digest("b"): JevAnswer(None)}


def test_the_probability_bounds_are_stored_and_read(metrics, valkey):
    cache = make_cache(valkey, metrics)
    asyncio.run(cache.settle(digest("zero"), 0.0, permanent=True))
    asyncio.run(cache.settle(digest("one"), 1.0, permanent=True))

    answers = asyncio.run(cache.get_many([digest("zero"), digest("one")]))

    assert answers == {digest("zero"): JevAnswer(0.0), digest("one"): JevAnswer(1.0)}


def test_valkey_errors_are_counted_and_the_local_answer_is_used(metrics):
    valkey = FakeValkey()
    cache = make_cache(valkey, metrics)
    valkey.down = True

    assert asyncio.run(cache.get_many([digest("a")])) == {}
    assert asyncio.run(cache.settle(digest("a"), 0.9, permanent=True)) == JevAnswer(0.9)
    assert asyncio.run(cache.settle(digest("b"), None, permanent=False)) == JevAnswer(None)
    assert sample(metrics, "llm_tool_guard_cache_errors_total", operation="get") == 1
    assert sample(metrics, "llm_tool_guard_cache_errors_total", operation="set") == 2
    assert sample(metrics, "llm_tool_guard_cache_up") == 0


def test_no_client_means_misses_and_the_local_answer(metrics):
    cache = make_cache(None, metrics)

    assert asyncio.run(cache.get_many([digest("a")])) == {}
    assert asyncio.run(cache.settle(digest("a"), 0.3, permanent=True)) == JevAnswer(0.3)
    assert sample(metrics, "llm_tool_guard_cache_errors_total", operation="get") == 0


def test_jev_lookups_do_not_count_as_verdict_cache_hits(metrics, valkey):
    cache = make_cache(valkey, metrics)
    asyncio.run(cache.settle(digest("a"), 0.3, permanent=True))

    asyncio.run(cache.get_many([digest("a"), digest("b")]))

    assert sample(metrics, "llm_tool_guard_cache_hits_total") == 0
    assert sample(metrics, "llm_tool_guard_cache_misses_total") == 0
