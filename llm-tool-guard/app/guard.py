"""Answers scan requests: verifies each hash, serves cached verdicts and scans the rest once."""

import asyncio
import hashlib
import logging
import re
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import NamedTuple

from cache import JevAnswer, Verdict, VerdictCache
from metrics import Metrics
from second_check import SecondCheck

logger = logging.getLogger(__name__)

_HASH = re.compile(r"sha256:[0-9a-f]{64}")


def _encode(text: str) -> bytes:
    return text.encode("utf-8", "surrogatepass")


def _digest(encoded: bytes) -> str:
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def content_hash(text: str) -> str:
    """Hash text the way the LiteLLM middleware does."""
    return _digest(_encode(text))


class ScanStoppedError(Exception):
    """Raised by a scan that ended early because the service is shutting down."""


_ModelVerdicts = tuple[list[str], list[str], dict[str, float]]


class Judged(NamedTuple):
    """A check with Jev's second opinion: blocked is a subset of flagged, cleared is not in flagged."""

    flagged: list[str]
    unknown: list[str]
    scores: dict[str, float]
    blocked: list[str]
    cleared: list[str]
    jev_scores: dict[str, float]


class ToolGuard:
    """Scan service; each text is scanned at most once at a time, and a scan outlives the request that started it."""

    def __init__(  # noqa: PLR0913 - keyword-only limits
        self,
        scan: Callable[[str], tuple[bool, float]],
        cache: VerdictCache,
        metrics: Metrics,
        *,
        max_text_bytes: int,
        max_pending_scans: int,
        scan_workers: int,
        stop_scans: Callable[[], None] | None = None,
        second_check: SecondCheck | None = None,
    ):
        """scan is a blocking function returning (flagged, score) for a text; it runs on scan_workers threads.

        stop_scans makes running scans raise ScanStoppedError at their next safe point; close() calls it.
        second_check, when set, gives Jev's opinion on texts the model flagged to check_with_jev; asks in flight take
        pending slots like scans.
        """
        self._scan = scan
        self._stop_scans = stop_scans
        self._cache = cache
        self._metrics = metrics
        self._max_text_bytes = max_text_bytes
        self._max_pending = max_pending_scans
        self._executor = ThreadPoolExecutor(max_workers=scan_workers, thread_name_prefix="scan")
        self._second = second_check
        self._inflight: dict[str, asyncio.Task[Verdict | None]] = {}
        self._jev_inflight: dict[str, asyncio.Task[JevAnswer]] = {}

    async def check(self, new: Sequence[dict], known: Sequence[str]) -> _ModelVerdicts:
        """Return (flagged, unknown, scores): hashes to mark, known hashes without a verdict, and model scores.

        scores covers the hashes the model flagged; a flagged hash without one failed a scan, a limit or a hash check.
        """
        checking = self._check(new, known, second_opinion=False)
        del new
        result = await checking
        return result.flagged, result.unknown, result.scores

    async def check_with_jev(self, new: Sequence[dict], known: Sequence[str]) -> Judged:
        """Like check, with Jev's answer for the hashes the model flagged: blocked, cleared and jev_scores.

        A cleared hash is dropped from flagged; one Jev did not answer, or answered in between, stays flagged.
        """
        checking = self._check(new, known, second_opinion=True)
        del new
        return await checking

    async def _check(self, new: Sequence[dict], known: Sequence[str], *, second_opinion: bool) -> Judged:
        second_opinion = second_opinion and self._second is not None
        texts, flagged = self._verify(new)
        order = [*(item["hash"] for item in new), *known]
        del new
        unknown = [h for h in dict.fromkeys(known) if h not in texts and h not in flagged]
        lookups = [h for h in unknown if _HASH.fullmatch(h)]
        verdicts: dict[str, Verdict | None] = dict(
            await self._cache.get_many([*texts, *(h for h in lookups if h not in self._inflight)])
        )
        waits = {h: self._inflight[h] for h in lookups if h not in verdicts and h in self._inflight}
        waits.update(self._schedule({h: t for h, t in texts.items() if h not in verdicts}, flagged))
        held = {h: t for h, t in texts.items() if h not in verdicts or verdicts[h].flagged} if second_opinion else {}
        del texts
        scores = await self._settle(verdicts, waits, flagged)
        held = {h: t for h, t in held.items() if h in scores}
        answers = await self._second_opinions(list(scores), held) if second_opinion else {}
        blocked, cleared = self._apply_thresholds(answers)
        for hash_, reason in flagged.items():
            if hash_ not in cleared:
                self._metrics.flagged.labels(reason).inc()
        ordered = list(dict.fromkeys(order))
        return Judged(
            [h for h in ordered if h in flagged and h not in cleared],
            [h for h in unknown if h not in verdicts],
            scores,
            [h for h in ordered if h in blocked],
            [h for h in ordered if h in cleared],
            {h: a.p for h in ordered if (a := answers.get(h)) is not None and a.p is not None},
        )

    async def _settle(
        self,
        verdicts: dict[str, Verdict | None],
        waits: dict[str, asyncio.Task[Verdict | None]],
        flagged: dict[str, str],
    ) -> dict[str, float]:
        """Wait for the scans into verdicts, flag what the model flagged or failed to scan; return the model scores."""
        if waits:
            results = await asyncio.gather(*(asyncio.shield(t) for t in waits.values()))
            verdicts.update(zip(waits, results, strict=True))
        for hash_, verdict in verdicts.items():
            if verdict is None or verdict.flagged:
                flagged.setdefault(hash_, "error" if verdict is None else "verdict")
        return {h: v.score for h, v in verdicts.items() if v is not None and v.flagged and flagged[h] == "verdict"}

    async def _second_opinions(self, candidates: list[str], held: dict[str, str]) -> dict[str, JevAnswer]:
        """Return the stored answer or no-answer of each candidate Jev has one for; held is emptied as texts are used.

        Joins an ask already in flight, reads the cache, then asks about the rest that have a text and a free slot.
        """
        if self._second is None or not candidates:
            return {}
        waits = {h: self._jev_inflight[h] for h in candidates if h in self._jev_inflight}
        answers = await self._second.lookup([h for h in candidates if h not in waits])
        for hash_ in candidates:
            if hash_ in answers or hash_ in waits or hash_ not in held:
                continue
            task = self._jev_inflight.get(hash_) or self._start_jev(self._second, hash_, held.pop(hash_))
            if task is None:
                self._metrics.jev_requests.labels("skipped").inc()
            else:
                waits[hash_] = task
        held.clear()
        if waits:
            await asyncio.wait(waits.values())
            answers.update({h: t.result() for h, t in waits.items() if not t.cancelled()})
        return answers

    def _apply_thresholds(self, answers: dict[str, JevAnswer]) -> tuple[set[str], set[str]]:
        """Return the hashes whose answer blocks and the ones it clears."""
        blocked, cleared = set(), set()
        if self._second is None:
            return blocked, cleared
        for hash_, answer in answers.items():
            if answer.p is None:
                continue
            outcome = self._second.classify(answer.p)
            if outcome == "blocked":
                blocked.add(hash_)
            elif outcome == "cleared":
                cleared.add(hash_)
        return blocked, cleared

    def _schedule(self, texts: dict[str, str], flagged: dict[str, str]) -> dict[str, asyncio.Task[Verdict | None]]:
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

    def _pending(self) -> int:
        return len(self._inflight) + len(self._jev_inflight)

    def _start(self, hash_: str, text: str) -> asyncio.Task[Verdict | None] | None:
        if self._pending() >= self._max_pending:
            return None
        task = asyncio.get_running_loop().create_task(self._scan_and_store(hash_, text))
        self._inflight[hash_] = task
        task.add_done_callback(lambda _: self._finished(self._inflight, hash_))
        self._metrics.pending_scans.set(self._pending())
        return task

    def _start_jev(self, second: SecondCheck, hash_: str, text: str) -> asyncio.Task[JevAnswer] | None:
        if self._pending() >= self._max_pending:
            return None
        task = asyncio.get_running_loop().create_task(second.ask(hash_, text))
        self._jev_inflight[hash_] = task
        task.add_done_callback(lambda _: self._finished(self._jev_inflight, hash_))
        self._metrics.pending_scans.set(self._pending())
        return task

    def _finished(self, inflight: dict, hash_: str) -> None:
        inflight.pop(hash_, None)
        self._metrics.pending_scans.set(self._pending())

    async def _scan_and_store(self, hash_: str, text: str) -> Verdict | None:
        loop = asyncio.get_running_loop()
        start = time.perf_counter()
        try:
            verdict = await loop.run_in_executor(self._executor, self._timed, text)
        except ScanStoppedError:
            self._metrics.scans.labels("stopped").inc()
            return None
        except TimeoutError:
            self._metrics.scans.labels("timeout").inc()
            logger.warning("scan of %s over its time budget", hash_[:23])
            return None
        except Exception:
            self._metrics.scans.labels("error").inc()
            logger.exception("scan of %s failed", hash_[:23])
            return None
        self._metrics.scans.labels("flagged" if verdict.flagged else "clean").inc()
        logger.info(
            "scanned %s: flagged=%s score=%.4f bytes=%d seconds=%.3f",
            hash_[:23],
            verdict.flagged,
            verdict.score,
            len(_encode(text)),
            time.perf_counter() - start,
        )
        await self._cache.put(hash_, verdict)
        return verdict

    def _timed(self, text: str) -> Verdict:
        with self._metrics.scan_seconds.time():
            return Verdict(*self._scan(text))

    async def drain(self, max_wait: float | None = None) -> None:
        """Wait for scans and Jev asks in flight to finish and be cached, for at most max_wait seconds."""
        deadline = None if max_wait is None else time.monotonic() + max_wait
        while self._pending():
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                return
            await asyncio.wait([*self._inflight.values(), *self._jev_inflight.values()], timeout=remaining)

    def close(self) -> None:
        """Stop the scan threads and cancel Jev asks in flight; the running scans end at their next safe point."""
        if self._stop_scans is not None:
            self._stop_scans()
        self._executor.shutdown(wait=False, cancel_futures=True)
        for task in self._jev_inflight.values():
            task.cancel()

    async def aclose(self) -> None:
        """Release the Jev client; call after close()."""
        if self._second is not None:
            await self._second.aclose()
