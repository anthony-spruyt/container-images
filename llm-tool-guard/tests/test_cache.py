"""Tests for the Valkey verdict cache: key composition, TTL and failure handling."""

import asyncio
import hashlib
from importlib.metadata import PackageNotFoundError

import pytest

from cache import VerdictCache, cache_namespace, runtime_fingerprint
from fakes import FakeValkey, digest, sample

BASE = {
    "model": "Horizon-Labs/prompt-injection-guard-base",
    "revision": "abc123",
    "injection_label": "INJECTION",
    "threshold": 0.9,
    "window_tokens": 2048,
    "window_overlap": 512,
    "max_windows": 200,
    "runtime": {
        "scanner_types.py": "aaa",
        "classifier.py": "bbb",
        "transformers": "5.18.0",
        "tokenizers": "0.23.3",
        "torch": "2.13.0",
    },
}


def test_namespace_is_stable_for_the_same_settings():
    assert cache_namespace(**BASE) == cache_namespace(**dict(BASE))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model", "other/model"),
        ("revision", "def456"),
        ("injection_label", "LABEL_1"),
        ("threshold", 0.91),
        ("window_tokens", 8192),
        ("window_overlap", 256),
        ("max_windows", 201),
        ("runtime", {**BASE["runtime"], "scanner_types.py": "ccc"}),
        ("runtime", {**BASE["runtime"], "classifier.py": "ccc"}),
        ("runtime", {**BASE["runtime"], "transformers": "5.19.0"}),
        ("runtime", {**BASE["runtime"], "tokenizers": "0.24.0"}),
        ("runtime", {**BASE["runtime"], "torch": "2.14.0"}),
    ],
)
def test_namespace_changes_with_every_verdict_setting(field, value):
    assert cache_namespace(**{**BASE, field: value}) != cache_namespace(**BASE)


def versions(**installed):
    def lookup(name):
        if name not in installed:
            raise PackageNotFoundError(name)
        return installed[name]

    return lookup


def write_sources(directory, **contents):
    paths = []
    for name, text in contents.items():
        path = directory / f"{name}.py"
        path.write_text(text)
        paths.append(path)
    return paths


def test_runtime_fingerprint_holds_the_source_digests_and_library_versions(tmp_path):
    sources = write_sources(tmp_path, scanner_types="SCANNER = 1\n", classifier="CLASSIFIER = 1\n")

    fingerprint = runtime_fingerprint(
        sources, version=versions(transformers="5.18.0", tokenizers="0.23.3", torch="2.13.0")
    )

    assert fingerprint == {
        "scanner_types.py": hashlib.sha256(b"SCANNER = 1\n").hexdigest(),
        "classifier.py": hashlib.sha256(b"CLASSIFIER = 1\n").hexdigest(),
        "transformers": "5.18.0",
        "tokenizers": "0.23.3",
        "torch": "2.13.0",
    }


@pytest.mark.parametrize("changed", ["scanner_types", "classifier"])
def test_changing_a_runtime_source_changes_the_namespace(tmp_path, changed):
    sources = write_sources(tmp_path, scanner_types="SCANNER = 1\n", classifier="CLASSIFIER = 1\n")
    lookup = versions(transformers="1", tokenizers="1", torch="1")

    def namespace() -> str:
        return cache_namespace(**{**BASE, "runtime": runtime_fingerprint(sources, version=lookup)})

    before = namespace()
    (tmp_path / f"{changed}.py").write_text("CHANGED = 2\n")

    assert namespace() != before


def test_runtime_fingerprint_names_a_missing_library(tmp_path):
    sources = write_sources(tmp_path, scanner_types="")

    lookup = versions(transformers="1", tokenizers="1")

    with pytest.raises(PackageNotFoundError, match="torch"):
        runtime_fingerprint(sources, version=lookup)


def test_keys_carry_the_namespace_and_hash(metrics, valkey):
    cache = VerdictCache(valkey, namespace="n1", ttl_seconds=60, metrics=metrics)
    hash_ = digest("x")

    asyncio.run(cache.put(hash_, flagged=True))

    assert valkey.data == {f"llm-tool-guard:n1:{hash_}": "1"}
    assert valkey.ttls == {f"llm-tool-guard:n1:{hash_}": 60}


def test_verdicts_from_another_namespace_are_not_read(metrics, valkey):
    old = VerdictCache(valkey, namespace="old", ttl_seconds=60, metrics=metrics)
    new = VerdictCache(valkey, namespace="new", ttl_seconds=60, metrics=metrics)
    hash_ = digest("x")
    asyncio.run(old.put(hash_, flagged=False))

    assert asyncio.run(new.get_many([hash_])) == {}


def test_get_many_returns_stored_verdicts_only(metrics, valkey):
    cache = VerdictCache(valkey, namespace="n", ttl_seconds=60, metrics=metrics)
    a, b, c = digest("a"), digest("b"), digest("c")
    asyncio.run(cache.put(a, flagged=True))
    asyncio.run(cache.put(b, flagged=False))

    assert asyncio.run(cache.get_many([a, b, c])) == {a: True, b: False}
    assert sample(metrics, "llm_tool_guard_cache_hits_total") == 2
    assert sample(metrics, "llm_tool_guard_cache_misses_total") == 1


def test_get_many_of_nothing_skips_valkey(metrics, valkey):
    cache = VerdictCache(valkey, namespace="n", ttl_seconds=60, metrics=metrics)

    assert asyncio.run(cache.get_many([])) == {}
    assert valkey.mget_calls == []


def test_unexpected_stored_value_is_a_miss(metrics, valkey):
    cache = VerdictCache(valkey, namespace="n", ttl_seconds=60, metrics=metrics)
    hash_ = digest("a")
    valkey.data[f"llm-tool-guard:n:{hash_}"] = "maybe"

    assert asyncio.run(cache.get_many([hash_])) == {}


def test_bytes_values_are_read(metrics, valkey):
    cache = VerdictCache(valkey, namespace="n", ttl_seconds=60, metrics=metrics)
    hash_ = digest("a")
    valkey.data[f"llm-tool-guard:n:{hash_}"] = b"1"

    assert asyncio.run(cache.get_many([hash_])) == {hash_: True}


def test_errors_count_and_mark_the_cache_down_until_it_answers(metrics):
    valkey = FakeValkey()
    cache = VerdictCache(valkey, namespace="n", ttl_seconds=60, metrics=metrics)
    hash_ = digest("a")
    valkey.down = True

    assert asyncio.run(cache.get_many([hash_])) == {}
    asyncio.run(cache.put(hash_, flagged=False))
    assert sample(metrics, "llm_tool_guard_cache_errors_total", operation="get") == 1
    assert sample(metrics, "llm_tool_guard_cache_errors_total", operation="set") == 1
    assert sample(metrics, "llm_tool_guard_cache_up") == 0

    valkey.down = False
    asyncio.run(cache.get_many([hash_]))
    assert sample(metrics, "llm_tool_guard_cache_up") == 1


def test_timeouts_count_as_errors(metrics):
    class SlowValkey(FakeValkey):
        async def mget(self, keys):
            await asyncio.sleep(0)
            raise TimeoutError

    cache = VerdictCache(SlowValkey(), namespace="n", ttl_seconds=60, metrics=metrics)

    assert asyncio.run(cache.get_many([digest("a")])) == {}
    assert sample(metrics, "llm_tool_guard_cache_errors_total", operation="get") == 1


def test_no_client_means_every_lookup_misses_without_errors(metrics):
    cache = VerdictCache(None, namespace="n", ttl_seconds=60, metrics=metrics)

    assert asyncio.run(cache.get_many([digest("a")])) == {}
    asyncio.run(cache.put(digest("a"), flagged=True))
    assert sample(metrics, "llm_tool_guard_cache_errors_total", operation="get") == 0
    assert sample(metrics, "llm_tool_guard_cache_up") == 0
