"""Tests for the Jev second check: asking per window, settling a text's windows and what the cache namespace covers."""

import asyncio
import json

import httpx2
import pytest

import judge as judge_module
from cache import JevAnswer
from config import Settings
from fakes import FakeValkey, digest, sample
from second_check import Asked, SecondCheck, build_second_check

HASH = digest("flagged text")
SCAN = "0123456789abcdef"
NO_ANSWER_FOR_GOOD = Asked(None, permanent=True)
ENFORCE = {"JEV_MODE": "enforce", "JEV_API_URL": "https://jev.test", "JEV_API_KEY": "jev-test-key"}
DAY = 3600 * 24


def jev_keys(valkey: FakeValkey) -> list[str]:
    return [key for key in valkey.data if key.startswith("llm-tool-guard:jev:")]


def answering(p: float, requests: list | None = None) -> httpx2.MockTransport:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if requests is not None:
            requests.append(request)
        model = json.loads(request.content)["model"]
        body = {"model": model, "answers": {judge_module.QUESTION_ID: {"type": "noul", "noul": p}}}
        return httpx2.Response(200, json=body)

    return httpx2.MockTransport(handler)


def build(metrics, *, valkey=None, transport=None, scan=SCAN, **overrides) -> SecondCheck:
    settings = Settings.from_env({**ENFORCE, "CACHE_TTL_SECONDS": str(DAY), **overrides})
    second = build_second_check(
        settings, FakeValkey() if valkey is None else valkey, metrics, scan_namespace=scan, transport=transport
    )
    assert second is not None
    return second


def settle(second: SecondCheck, *windows: Asked) -> JevAnswer:
    return asyncio.run(second.settle(HASH, list(windows)))


def namespace_of(metrics, **kwargs) -> str:
    """Build the second check on a fresh Valkey, answer one window and return the namespace it was stored under."""
    valkey = FakeValkey()
    second = build(metrics, valkey=valkey, transport=answering(0.5), **kwargs)
    settle(second, asyncio.run(second.ask_window(HASH, 0, "text")))
    (key,) = jev_keys(valkey)
    return key.split(":")[2]


def test_nothing_is_built_while_the_mode_is_off(metrics):
    assert build_second_check(Settings.from_env({}), FakeValkey(), metrics, scan_namespace=SCAN) is None


def test_enforce_builds_a_second_check_that_asks_the_configured_service_with_the_key(metrics):
    requests: list[httpx2.Request] = []
    settings = {"JEV_API_URL": "https://jev.test/jev/", "JEV_MODEL": "jev-9"}
    second = build(metrics, transport=answering(0.25, requests), **settings)

    asked = asyncio.run(second.ask_window(HASH, 0, "flagged text"))

    (request,) = requests
    assert asked == Asked(0.25)
    assert str(request.url) == "https://jev.test/jev/v1/systemone"
    assert request.headers["authorization"] == "Bearer jev-test-key"
    assert json.loads(request.content)["model"] == "jev-9"


@pytest.mark.parametrize(
    ("api_url", "posted_to"),
    [
        ("https://jev.test", "https://jev.test/v1/systemone"),
        ("https://jev.test/", "https://jev.test/v1/systemone"),
        ("https://jev.test/jev", "https://jev.test/jev/v1/systemone"),
        ("https://jev.test/jev/", "https://jev.test/jev/v1/systemone"),
        ("http://jev.svc:4000/a/b/", "http://jev.svc:4000/a/b/v1/systemone"),
    ],
)
def test_the_question_is_posted_to_the_api_url_with_or_without_a_trailing_slash_or_path_prefix(
    metrics, api_url, posted_to
):
    requests: list[httpx2.Request] = []
    second = build(metrics, transport=answering(0.5, requests), JEV_API_URL=api_url)

    asyncio.run(second.ask_window(HASH, 0, "flagged text"))

    assert [str(request.url) for request in requests] == [posted_to]


def test_a_redirect_to_another_host_is_not_followed_and_ends_the_ask_as_a_transient_failure(metrics):
    requests: list[httpx2.Request] = []

    def redirect(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(302, headers={"location": "https://elsewhere.test/v1/systemone"})

    valkey = FakeValkey()
    second = build(metrics, valkey=valkey, transport=httpx2.MockTransport(redirect))

    asked = asyncio.run(second.ask_window(HASH, 0, "flagged text"))
    answer = settle(second, asked)

    assert asked == Asked(None)
    assert answer == JevAnswer(None)
    assert [str(request.url) for request in requests] == ["https://jev.test/v1/systemone"]
    assert list(valkey.ttls.values()) == [3600]


def test_the_configured_thresholds_apply(metrics):
    second = build(metrics, JEV_BLOCK_AT="0.6", JEV_CLEAR_BELOW="0.2")

    assert [second.classify(p) for p in (0.1, 0.2, 0.59, 0.6)] == ["cleared", "middle", "middle", "blocked"]


def test_an_answer_with_a_window_missing_is_never_cleared_but_can_still_block(metrics):
    second = build(metrics, JEV_BLOCK_AT="0.6", JEV_CLEAR_BELOW="0.2")

    assert [second.classify(p, partial=True) for p in (0.1, 0.4, 0.6)] == ["middle", "middle", "blocked"]


def test_a_window_over_the_size_limit_is_not_asked_and_counts_as_an_answer_that_asking_again_would_not_change(metrics):
    requests: list[httpx2.Request] = []
    second = build(metrics, transport=answering(0.5, requests), JEV_MAX_TEXT_BYTES="8")

    asked = asyncio.run(second.ask_window(HASH, 0, "123456789"))

    assert asked == NO_ANSWER_FOR_GOOD
    assert requests == []
    assert sample(metrics, "llm_tool_guard_jev_requests_total", outcome="skipped") == 1


def test_the_size_limit_counts_bytes_of_one_window(metrics):
    requests: list[httpx2.Request] = []
    second = build(metrics, transport=answering(0.5, requests), JEV_MAX_TEXT_BYTES="8")

    asked = [asyncio.run(second.ask_window(HASH, i, text)) for i, text in enumerate(["12345678", "ééééé"])]

    assert asked == [Asked(0.5), NO_ANSWER_FOR_GOOD]
    assert len(requests) == 1


def test_a_window_without_text_is_not_asked(metrics):
    requests: list[httpx2.Request] = []
    second = build(metrics, transport=answering(0.5, requests))

    assert asyncio.run(second.ask_window(HASH, 0, "")) == NO_ANSWER_FOR_GOOD
    assert requests == []


def test_each_window_asked_is_counted_by_what_it_scored(metrics):
    second = build(metrics, transport=answering(0.5), JEV_BLOCK_AT="0.4")

    asyncio.run(second.ask_window(HASH, 0, "one"))
    asyncio.run(second.ask_window(HASH, 1, "two"))

    assert sample(metrics, "llm_tool_guard_jev_requests_total", outcome="blocked") == 2


def test_the_answer_cache_ttl_is_the_verdict_cache_ttl(metrics):
    valkey = FakeValkey()
    second = build(metrics, valkey=valkey, transport=answering(0.5), CACHE_TTL_SECONDS="1234")

    settle(second, asyncio.run(second.ask_window(HASH, 0, "text")))

    assert list(valkey.ttls.values()) == [1234]


def test_a_text_is_stored_with_the_highest_probability_of_its_windows(metrics):
    valkey = FakeValkey()
    second = build(metrics, valkey=valkey)

    answer = settle(second, Asked(0.3), Asked(0.97), Asked(0.05))

    assert answer == JevAnswer(0.97)
    assert list(valkey.data.values()) == ["0.97"]
    assert list(valkey.ttls.values()) == [DAY]


@pytest.mark.parametrize(("permanent", "ttl"), [(True, DAY), (False, 3600)])
def test_a_text_with_a_window_that_failed_is_stored_partial_for_as_long_as_the_failure_would_repeat(
    metrics, permanent, ttl
):
    valkey = FakeValkey()
    second = build(metrics, valkey=valkey)

    answer = settle(second, Asked(0.4), Asked(None, permanent=permanent))

    assert answer == JevAnswer(0.4, partial=True)
    assert list(valkey.data.values()) == ["0.4+"]
    assert list(valkey.ttls.values()) == [ttl]


def test_a_text_every_window_of_which_failed_is_stored_as_no_answer(metrics):
    valkey = FakeValkey()
    second = build(metrics, valkey=valkey)

    answer = settle(second, Asked(None, permanent=True), Asked(None))

    assert answer == JevAnswer(None)
    assert list(valkey.data.values()) == ["-"]
    assert list(valkey.ttls.values()) == [3600]


def test_a_text_with_a_window_that_was_not_asked_is_stored_partial_for_the_full_ttl_so_it_is_not_asked_again(metrics):
    valkey = FakeValkey()
    second = build(metrics, valkey=valkey)

    answer = settle(second, Asked(0.4), NO_ANSWER_FOR_GOOD)

    assert answer == JevAnswer(0.4, partial=True)
    assert list(valkey.data.values()) == ["0.4+"]
    assert list(valkey.ttls.values()) == [DAY]


def test_a_text_with_only_windows_that_were_not_asked_is_stored_as_no_answer_for_the_full_ttl(metrics):
    valkey = FakeValkey()
    second = build(metrics, valkey=valkey)

    assert settle(second, NO_ANSWER_FOR_GOOD, NO_ANSWER_FOR_GOOD) == JevAnswer(None)
    assert list(valkey.data.values()) == ["-"]
    assert list(valkey.ttls.values()) == [DAY]


def test_a_text_with_no_window_asked_has_no_answer_and_is_not_stored(metrics):
    valkey = FakeValkey()
    second = build(metrics, valkey=valkey)

    assert settle(second) == JevAnswer(None)
    assert valkey.data == {}


def test_the_first_answer_stored_for_a_text_is_the_one_every_replica_uses(metrics):
    valkey = FakeValkey()
    other = build(metrics, valkey=valkey)
    mine = build(metrics, valkey=valkey)
    settle(other, Asked(0.02), Asked(0.01))

    assert settle(mine, Asked(0.97)) == JevAnswer(0.02)


def test_the_namespace_is_stable_and_follows_the_model(metrics):
    first = namespace_of(metrics)
    again = namespace_of(metrics)

    assert first == again
    assert namespace_of(metrics, JEV_MODEL="jev-9") != first


def test_the_namespace_follows_the_scan_namespace_because_that_decides_which_windows_are_asked(metrics):
    assert namespace_of(metrics, scan="fedcba9876543210") != namespace_of(metrics)


@pytest.mark.parametrize("setting", [{"JEV_MAX_TEXT_BYTES": "1024"}, {"JEV_MAX_WINDOWS": "4"}])
def test_the_namespace_follows_the_size_and_window_limits_because_they_decide_what_is_asked(metrics, setting):
    assert namespace_of(metrics, **setting) != namespace_of(metrics)


@pytest.mark.parametrize(
    "setting", [{"JEV_BLOCK_AT": "0.5"}, {"JEV_CLEAR_BELOW": "0.01"}, {"JEV_TIMEOUT_SECONDS": "3"}]
)
def test_retuning_the_thresholds_or_the_timeout_keeps_the_namespace(metrics, setting):
    assert namespace_of(metrics, **setting) == namespace_of(metrics)


def test_the_namespace_follows_the_client_source(metrics, tmp_path, monkeypatch):
    original = namespace_of(metrics)
    (tmp_path / "judge.py").write_text("# another client\n")
    monkeypatch.setattr(judge_module, "__file__", str(tmp_path / "judge.py"))

    assert namespace_of(metrics) != original


def test_the_namespace_follows_the_question(metrics, monkeypatch):
    original = namespace_of(metrics)
    monkeypatch.setattr(judge_module, "QUESTION", {**judge_module.QUESTION, "instructions": "Another question?"})

    assert namespace_of(metrics) != original
