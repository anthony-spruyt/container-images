"""Answers scan requests: verifies each hash, serves cached verdicts and scans the rest once."""

import asyncio
import hashlib
import logging
import re
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor

from cache import VerdictCache
from metrics import Metrics

logger = logging.getLogger(__name__)

_HASH = re.compile(r"sha256:[0-9a-f]{64}")


def _encode(text: str) -> bytes:
    return text.encode("utf-8", "surrogatepass")


def _digest(encoded: bytes) -> str:
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def content_hash(text: str) -> str:
    """Hash text the way the LiteLLM middleware does."""
    return _digest(_encode(text))


class ToolGuard:
    """Scan service; each text is scanned at most once at a time, and a scan outlives the request that started it."""

    def __init__(  # noqa: PLR0913 - keyword-only limits
        self,
        scan: Callable[[str], bool],
        cache: VerdictCache,
        metrics: Metrics,
        *,
        max_text_bytes: int,
        max_pending_scans: int,
        scan_workers: int,
    ):
        """scan is a blocking function returning True when text is flagged; it runs on scan_workers threads."""
        self._scan = scan
        self._cache = cache
        self._metrics = metrics
        self._max_text_bytes = max_text_bytes
        self._max_pending = max_pending_scans
        self._executor = ThreadPoolExecutor(max_workers=scan_workers, thread_name_prefix="scan")
        self._inflight: dict[str, asyncio.Task[bool | None]] = {}

    async def check(self, new: Sequence[dict], known: Sequence[str]) -> tuple[list[str], list[str]]:
        """Return (flagged, unknown): hashes to mark, and known hashes without a verdict."""
        texts, flagged = self._verify(new)
        unknown = [h for h in dict.fromkeys(known) if h not in texts and h not in flagged]
        lookups = [h for h in unknown if _HASH.fullmatch(h)]
        verdicts: dict[str, bool | None] = dict(
            await self._cache.get_many([*texts, *(h for h in lookups if h not in self._inflight)])
        )
        waits = {h: self._inflight[h] for h in lookups if h not in verdicts and h in self._inflight}
        waits.update(self._schedule({h: t for h, t in texts.items() if h not in verdicts}, flagged))
        if waits:
            results = await asyncio.gather(*(asyncio.shield(t) for t in waits.values()))
            verdicts.update(zip(waits, results, strict=True))
        for hash_, verdict in verdicts.items():
            if verdict is not False:
                flagged.setdefault(hash_, "error" if verdict is None else "verdict")
        for reason in flagged.values():
            self._metrics.flagged.labels(reason).inc()
        order = [*(item["hash"] for item in new), *known]
        return list(dict.fromkeys(h for h in order if h in flagged)), [h for h in unknown if h not in verdicts]

    def _schedule(self, texts: dict[str, str], flagged: dict[str, str]) -> dict[str, asyncio.Task[bool | None]]:
        """Join or start a scan per text; texts beyond the pending limit are flagged instead."""
        tasks = {}
        for hash_, text in texts.items():
            task = self._inflight.get(hash_) or self._start(hash_, text)
            if task is None:
                flagged[hash_] = "over_limit"
                self._metrics.over_limit.labels("queue").inc()
            else:
                tasks[hash_] = task
        return tasks

    def _verify(self, new: Sequence[dict]) -> tuple[dict[str, str], dict[str, str]]:
        """Split items into texts to look up or scan, and hashes flagged without a scan (by reason)."""
        texts: dict[str, str] = {}
        flagged: dict[str, str] = {}
        for item in new:
            hash_, text = item["hash"], item["text"]
            if hash_ in flagged:
                continue
            encoded = _encode(text)
            if hash_ != _digest(encoded):
                flagged[hash_] = "hash_mismatch"
                texts.pop(hash_, None)
            elif len(encoded) > self._max_text_bytes:
                flagged[hash_] = "over_limit"
                self._metrics.over_limit.labels("text_bytes").inc()
            else:
                texts.setdefault(hash_, text)
        return texts, flagged

    def _start(self, hash_: str, text: str) -> asyncio.Task[bool | None] | None:
        if len(self._inflight) >= self._max_pending:
            return None
        task = asyncio.get_running_loop().create_task(self._scan_and_store(hash_, text))
        self._inflight[hash_] = task
        task.add_done_callback(lambda _: self._finished(hash_))
        self._metrics.pending_scans.set(len(self._inflight))
        return task

    def _finished(self, hash_: str) -> None:
        self._inflight.pop(hash_, None)
        self._metrics.pending_scans.set(len(self._inflight))

    async def _scan_and_store(self, hash_: str, text: str) -> bool | None:
        loop = asyncio.get_running_loop()
        start = time.perf_counter()
        try:
            flagged = await loop.run_in_executor(self._executor, self._timed, text)
        except Exception:
            self._metrics.scans.labels("error").inc()
            logger.exception("scan of %s failed", hash_[:23])
            return None
        self._metrics.scans.labels("flagged" if flagged else "clean").inc()
        logger.info(
            "scanned %s: flagged=%s bytes=%d seconds=%.3f",
            hash_[:23],
            flagged,
            len(_encode(text)),
            time.perf_counter() - start,
        )
        await self._cache.put(hash_, flagged=flagged)
        return flagged

    def _timed(self, text: str) -> bool:
        with self._metrics.scan_seconds.time():
            return self._scan(text)

    async def drain(self) -> None:
        """Wait for every scan in flight to finish and be cached."""
        while self._inflight:
            await asyncio.gather(*self._inflight.values(), return_exceptions=True)

    def close(self) -> None:
        """Stop the scan threads without waiting for queued scans."""
        self._executor.shutdown(wait=False, cancel_futures=True)
