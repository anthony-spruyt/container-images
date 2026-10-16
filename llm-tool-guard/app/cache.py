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

    def _failed(self, operation: str, exc: Exception) -> None:
        self._metrics.cache_errors.labels(operation).inc()
        self._metrics.cache_up.set(0)
        logger.warning("verdict cache %s failed: %s", operation, type(exc).__name__)

    async def get_many(self, hashes: Iterable[str]) -> dict[str, Verdict]:
        """Return the cached verdict for each hash that has one."""
        hashes = list(hashes)
        if not hashes or self._client is None:
            self._metrics.cache_misses.inc(len(hashes))
            return {}
        try:
            values = await self._client.mget([self._key(h) for h in hashes])
        except (RedisError, OSError) as exc:
            self._failed("get", exc)
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
            self._failed("set", exc)
            return
        self._metrics.cache_up.set(1)
