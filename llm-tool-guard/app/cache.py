"""Verdict cache in Valkey, keyed by content hash under a namespace derived from the verdict settings."""

import hashlib
import importlib.metadata
import json
import logging
import math
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any, NamedTuple

from redis.exceptions import RedisError

from metrics import Metrics

logger = logging.getLogger(__name__)

_PREFIX = "llm-tool-guard"
_FLAGS = {"1": True, "0": False}
_NO_ANSWER = "-"
_TRANSIENT_TTL_SECONDS = 3600
_LIBRARIES = ("transformers", "tokenizers", "torch")


class Verdict(NamedTuple):
    """The model's decision on a text and the score behind it; flagged is stored, never derived from score."""

    flagged: bool
    score: float


def _encode(verdict: Verdict) -> str:
    return f"{'1' if verdict.flagged else '0'}:{verdict.score!r}"


def _decode(value: str | bytes | None) -> Verdict | None:
    """Parse a stored "<0|1>:<score>"; anything else, including a non-finite score, is a miss."""
    if value is None:
        return None
    flag, sep, raw = (value.decode() if isinstance(value, bytes) else value).partition(":")
    if not sep or flag not in _FLAGS:
        return None
    try:
        score = float(raw)
    except ValueError:
        return None
    return Verdict(_FLAGS[flag], score) if math.isfinite(score) else None


class JevAnswer(NamedTuple):
    """Jev's raw probability of an embedded instruction; None is a stored "no answer" (the text stays flagged)."""

    p: float | None


def _encode_answer(answer: JevAnswer) -> str:
    return _NO_ANSWER if answer.p is None else repr(answer.p)


def _decode_answer(value: str | bytes | None) -> JevAnswer | None:
    """Parse a stored probability or no-answer marker; anything else, including one outside [0, 1], is a miss."""
    if value is None:
        return None
    raw = value.decode() if isinstance(value, bytes) else value
    if raw == _NO_ANSWER:
        return JevAnswer(None)
    try:
        p = float(raw)
    except ValueError:
        return None
    return JevAnswer(p) if math.isfinite(p) and 0 <= p <= 1 else None


def runtime_fingerprint(
    sources: Iterable[Path],
    libraries: Iterable[str] = _LIBRARIES,
    *,
    version: Callable[[str], str] = importlib.metadata.version,
) -> dict[str, str]:
    """Return the digest of each source file and the installed library versions that shape a verdict."""
    fingerprint = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    fingerprint.update({name: version(name) for name in libraries})
    return fingerprint


def cache_namespace(  # noqa: PLR0913 - one argument per setting that changes a verdict
    *,
    model: str,
    revision: str,
    injection_label: str,
    threshold: float,
    window_tokens: int,
    window_overlap: int,
    max_windows: int,
    runtime: Mapping[str, str],
) -> str:
    """Return a short digest of every setting that can change a verdict, so changing one starts a fresh cache."""
    settings = {
        "model": model,
        "revision": revision,
        "injection_label": injection_label,
        "threshold": threshold,
        "window_tokens": window_tokens,
        "window_overlap": window_overlap,
        "max_windows": max_windows,
        "runtime": dict(runtime),
    }
    return hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:16]


def jev_namespace(*, model: str, question: str, runtime: Mapping[str, str]) -> str:
    """Return a short digest of what shapes Jev's answer: its model, its question and the client source."""
    settings = {"model": model, "question": question, "runtime": dict(runtime)}
    return hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:16]


def _failed(metrics: Metrics, operation: str, exc: Exception) -> None:
    metrics.cache_errors.labels(operation).inc()
    metrics.cache_up.set(0)
    logger.warning("cache %s failed: %s", operation, type(exc).__name__)


class VerdictCache:
    """Reads and writes verdicts; failures are counted and treated as misses so scanning carries on."""

    def __init__(self, client: Any, *, namespace: str, ttl_seconds: int, metrics: Metrics):
        """Wrap an async Valkey client; None disables the cache."""
        self._client = client
        self._namespace = namespace
        self._ttl = ttl_seconds
        self._metrics = metrics
        metrics.cache_up.set(0)

    def _key(self, hash_: str) -> str:
        return f"{_PREFIX}:{self._namespace}:{hash_}"

    async def get_many(self, hashes: Iterable[str]) -> dict[str, Verdict]:
        """Return the cached verdict for each hash that has one."""
        hashes = list(hashes)
        if not hashes or self._client is None:
            self._metrics.cache_misses.inc(len(hashes))
            return {}
        try:
            values = await self._client.mget([self._key(h) for h in hashes])
        except (RedisError, OSError) as exc:
            _failed(self._metrics, "get", exc)
            self._metrics.cache_misses.inc(len(hashes))
            return {}
        self._metrics.cache_up.set(1)
        verdicts = {}
        for hash_, value in zip(hashes, values, strict=True):
            verdict = _decode(value)
            if verdict is not None:
                verdicts[hash_] = verdict
        self._metrics.cache_hits.inc(len(verdicts))
        self._metrics.cache_misses.inc(len(hashes) - len(verdicts))
        return verdicts

    async def put(self, hash_: str, verdict: Verdict) -> None:
        """Store a verdict for ttl_seconds."""
        if self._client is None:
            return
        try:
            await self._client.set(self._key(hash_), _encode(verdict), ex=self._ttl)
        except (RedisError, OSError) as exc:
            _failed(self._metrics, "set", exc)
            return
        self._metrics.cache_up.set(1)


class JevCache:
    """Jev's answers by content hash; the first answer stored for a hash is the one every replica serves."""

    def __init__(self, client: Any, *, namespace: str, ttl_seconds: int, metrics: Metrics):
        """Wrap an async Valkey client; None disables the cache. Lookups are not counted as verdict cache hits."""
        self._client = client
        self._namespace = namespace
        self._ttl = ttl_seconds
        self._metrics = metrics

    def _key(self, hash_: str) -> str:
        return f"{_PREFIX}:jev:{self._namespace}:{hash_}"

    async def get_many(self, hashes: Iterable[str]) -> dict[str, JevAnswer]:
        """Return the stored answer or no-answer marker of each hash that has one."""
        hashes = list(hashes)
        if not hashes or self._client is None:
            return {}
        try:
            values = await self._client.mget([self._key(h) for h in hashes])
        except (RedisError, OSError) as exc:
            _failed(self._metrics, "get", exc)
            return {}
        self._metrics.cache_up.set(1)
        decoded = ((hash_, _decode_answer(value)) for hash_, value in zip(hashes, values, strict=True))
        return {hash_: answer for hash_, answer in decoded if answer is not None}

    async def settle(self, hash_: str, p: float | None, *, permanent: bool) -> JevAnswer:
        """Store p (None for no answer) unless the hash already has one, and return what is stored.

        An answer, and a no-answer that asking again would repeat, last the cache TTL; any other no-answer an hour.
        With a store configured but unreachable the result is no answer, so every turn sees the same verdict.
        """
        own = JevAnswer(p)
        if self._client is None:
            return own
        ttl = self._ttl if p is not None or permanent else min(_TRANSIENT_TTL_SECONDS, self._ttl)
        try:
            stored = await self._client.set(self._key(hash_), _encode_answer(own), ex=ttl, nx=True, get=True)
        except (RedisError, OSError) as exc:
            _failed(self._metrics, "set", exc)
            return JevAnswer(None)
        self._metrics.cache_up.set(1)
        return own if stored is None else _decode_answer(stored) or JevAnswer(None)
