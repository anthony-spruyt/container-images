"""Tests for building the Jev second check from settings: what it is wired to and what its cache namespace covers."""

import asyncio
import json

import httpx2
import pytest

import judge as judge_module
from config import Settings
from fakes import FakeValkey, digest
from second_check import build_second_check

HASH = digest("flagged text")
ENFORCE = {"JEV_MODE": "enforce", "JEV_API_URL": "https://jev.test", "JEV_API_KEY": "jev-test-key"}


def jev_keys(valkey: FakeValkey) -> list[str]:
    return [key for key in valkey.data if key.startswith("llm-tool-guard:jev:")]


def namespace_of(settings_env: dict, metrics) -> str:
    """Build the second check on a fresh Valkey, ask once, and return the namespace its answer was stored under."""
    valkey = FakeValkey()
    second = build_second_check(Settings.from_env(settings_env), valkey, metrics, transport=answering(0.5))
    asyncio.run(second.ask(HASH, "text"))
    (key,) = jev_keys(valkey)
    return key.split(":")[2]


def answering(p: float, requests: list | None = None) -> httpx2.MockTransport:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if requests is not None:
            requests.append(request)
        model = json.loads(request.content)["model"]
        body = {"model": model, "answers": {judge_module.QUESTION_ID: {"type": "noul", "noul": p}}}
        return httpx2.Response(200, json=body)

    return httpx2.MockTransport(handler)


def test_nothing_is_built_while_the_mode_is_off(metrics):
    assert build_second_check(Settings.from_env({}), FakeValkey(), metrics) is None


def test_enforce_builds_a_second_check_that_asks_the_configured_service_with_the_key(metrics):
    requests: list[httpx2.Request] = []
    valkey = FakeValkey()
    env = {**ENFORCE, "JEV_API_URL": "https://jev.test/jev/", "JEV_MODEL": "jev-9"}
    second = build_second_check(Settings.from_env(env), valkey, metrics, transport=answering(0.25, requests))

    answer = asyncio.run(second.ask(HASH, "flagged text"))

    (request,) = requests
    assert answer.p == 0.25
    assert str(request.url) == "https://jev.test/jev/v1/systemone"
    assert request.headers["authorization"] == "Bearer jev-test-key"
    assert json.loads(request.content)["model"] == "jev-9"
    assert len(jev_keys(valkey)) == 1


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
    second = build_second_check(
        Settings.from_env({**ENFORCE, "JEV_API_URL": api_url}),
        FakeValkey(),
        metrics,
        transport=answering(0.5, requests),
    )

    asyncio.run(second.ask(HASH, "flagged text"))

    assert [str(request.url) for request in requests] == [posted_to]


def test_a_redirect_to_another_host_is_not_followed_and_ends_the_ask_as_a_transient_failure(metrics):
    requests: list[httpx2.Request] = []

    def redirect(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(302, headers={"location": "https://elsewhere.test/v1/systemone"})

    valkey = FakeValkey()
    second = build_second_check(Settings.from_env(ENFORCE), valkey, metrics, transport=httpx2.MockTransport(redirect))

    answer = asyncio.run(second.ask(HASH, "flagged text"))

    assert answer.p is None
    assert [str(request.url) for request in requests] == ["https://jev.test/v1/systemone"]
    assert list(valkey.ttls.values()) == [3600]


def test_the_configured_thresholds_and_size_limit_apply(metrics):
    env = {**ENFORCE, "JEV_BLOCK_AT": "0.6", "JEV_CLEAR_BELOW": "0.2", "JEV_MAX_TEXT_BYTES": "8"}
    requests: list[httpx2.Request] = []
    valkey = FakeValkey()
    second = build_second_check(Settings.from_env(env), valkey, metrics, transport=answering(0.5, requests))

    assert [second.classify(p) for p in (0.1, 0.2, 0.59, 0.6)] == ["cleared", "middle", "middle", "blocked"]
    assert asyncio.run(second.ask(HASH, "123456789")).p is None
    assert requests == []
    assert valkey.data == {}


def test_the_answer_cache_ttl_is_the_verdict_cache_ttl(metrics):
    valkey = FakeValkey()
    second = build_second_check(
        Settings.from_env({**ENFORCE, "CACHE_TTL_SECONDS": "1234"}), valkey, metrics, transport=answering(0.5)
    )

    asyncio.run(second.ask(HASH, "text"))

    assert list(valkey.ttls.values()) == [1234]


def test_the_namespace_is_stable_and_follows_the_model(metrics):
    first = namespace_of(ENFORCE, metrics)
    again = namespace_of(ENFORCE, metrics)

    assert first == again
    assert namespace_of({**ENFORCE, "JEV_MODEL": "jev-9"}, metrics) != first


@pytest.mark.parametrize(
    "setting", [{"JEV_BLOCK_AT": "0.5"}, {"JEV_CLEAR_BELOW": "0.01"}, {"JEV_TIMEOUT_SECONDS": "3"}]
)
def test_retuning_the_thresholds_or_the_timeout_keeps_the_namespace(metrics, setting):
    assert namespace_of({**ENFORCE, **setting}, metrics) == namespace_of(ENFORCE, metrics)


def test_the_namespace_follows_the_client_source(metrics, tmp_path, monkeypatch):
    original = namespace_of(ENFORCE, metrics)
    (tmp_path / "judge.py").write_text("# another client\n")
    monkeypatch.setattr(judge_module, "__file__", str(tmp_path / "judge.py"))

    assert namespace_of(ENFORCE, metrics) != original


def test_the_namespace_follows_the_question(metrics, monkeypatch):
    original = namespace_of(ENFORCE, metrics)
    monkeypatch.setattr(judge_module, "QUESTION", {**judge_module.QUESTION, "instructions": "Another question?"})

    assert namespace_of(ENFORCE, metrics) != original
