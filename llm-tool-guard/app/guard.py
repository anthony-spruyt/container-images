"""Answers scan requests: verifies each hash, serves cached verdicts, scans the rest once and asks Jev about flags."""

import asyncio
import hashlib
import logging
import re
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import NamedTuple

from cache import JevAnswer, Span, Verdict, VerdictCache
from metrics import Metrics
from second_check import SKIPPED, Asked, SecondCheck

logger = logging.getLogger(__name__)

_HASH = re.compile(r"sha256:[0-9a-f]{64}")


def _encode(text: str) -> bytes:
    return text.encode("utf-8", "surrogatepass")


def _digest(encoded: bytes) -> str:
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def content_hash(text: str) -> str:
    """Hash text the way the LiteLLM middleware does."""
    return _digest(_encode(text))


def _slices(text: str, spans: Sequence[Span]) -> list[str]:
    """Return the part of text each span covers; the spans index characters of the text the model scanned."""
    return [text[start:end] for start, end in spans]


class ScanStoppedError(Exception):
    """Raised by a scan that ended early because the service is shutting down."""


class Judged(NamedTuple):
    """The answer to a check: blocked is a subset of flagged, cleared is not in flagged.

    scores holds the model score of each hash it flagged; a flagged hash without one failed a scan, a limit or a hash
    check. jev_scores holds, per hash, the highest probability Jev gave across the windows it was asked about.
    """

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
        scan: Callable[[str], tuple[bool, float, tuple[Span, ...]]],
        cache: VerdictCache,
        metrics: Metrics,
        *,
        max_text_bytes: int,
        max_pending_scans: int,
        scan_workers: int,
        stop_scans: Callable[[], None] | None = None,
        second_check: SecondCheck | None = None,
    ):
        """scan is a blocking function returning (flagged, score, spans) for a text; it runs on scan_workers threads.

        spans are the character spans of the windows the model flagged. stop_scans makes running scans raise
        ScanStoppedError at their next safe point; close() calls it. second_check, when set, gives Jev's opinion on
        the flagged windows of every text the model flagged; each window asked takes a pending slot like a scan.
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
        self._jev_asks = 0

    async def check(self, new: Sequence[dict], known: Sequence[str]) -> Judged:
        """Return the hashes to mark (flagged), the known hashes without a verdict (unknown) and the rest of Judged.

        While a second check is set, Jev is asked about each window the model flagged in a flagged text. Its answer for
        the text blocks it when any window answered blocks, clears it only when every window asked clears, and
        otherwise leaves it flagged, as it does a window with no answer, no slot or over the size limit. A cleared hash
        is dropped from flagged. If the caller goes away while a scan runs, the scan is followed by its Jev asks, so
        later turns find the answer.
        """
        checking = self._check(new, known)
        del new
        return await checking

    async def _check(self, new: Sequence[dict], known: Sequence[str]) -> Judged:
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
        held = {h: t for h, t in texts.items() if h not in verdicts or verdicts[h].flagged} if self._second else {}
        del texts
        modelled = await self._settle(verdicts, waits, flagged, held)
        held = {h: t for h, t in held.items() if h in modelled}
        answers = await self._second_opinions(modelled, held)
        blocked, cleared = self._apply_thresholds(answers)
        for hash_, reason in flagged.items():
            if hash_ not in cleared:
                self._metrics.flagged.labels(reason).inc()
        ordered = list(dict.fromkeys(order))
        return Judged(
            [h for h in ordered if h in flagged and h not in cleared],
            [h for h in unknown if h not in verdicts],
            {h: v.score for h, v in modelled.items()},
            [h for h in ordered if h in blocked],
            [h for h in ordered if h in cleared],
            {h: a.p for h in ordered if (a := answers.get(h)) is not None and a.p is not None},
        )

    async def _settle(
        self,
        verdicts: dict[str, Verdict | None],
        waits: dict[str, asyncio.Task[Verdict | None]],
        flagged: dict[str, str],
        held: dict[str, str],
    ) -> dict[str, Verdict]:
        """Wait for the scans into verdicts, flag what the model flagged or failed to scan; return the model's flags.

        If the request is cancelled meanwhile, each scan it waits on asks Jev about its text (from held) when it ends.
        """
        if waits:
            try:
                results = await asyncio.gather(*(asyncio.shield(t) for t in waits.values()))
            except asyncio.CancelledError:
                self._ask_when_scans_end(waits, held)
                raise
            verdicts.update(zip(waits, results, strict=True))
        for hash_, verdict in verdicts.items():
            if verdict is None or verdict.flagged:
                flagged.setdefault(hash_, "error" if verdict is None else "verdict")
        return {h: v for h, v in verdicts.items() if v is not None and v.flagged and flagged[h] == "verdict"}

    async def _second_opinions(self, modelled: dict[str, Verdict], held: dict[str, str]) -> dict[str, JevAnswer]:
        """Return the stored answer or no-answer of each flagged hash Jev has one for; held is emptied as used.

        Joins asks already in flight, reads the cache, then asks about the flagged windows of the rest that have a
        text. A flagged text without windows (the model flagged it for its length) is not asked about.
        """
        if self._second is None or not modelled:
            return {}
        waits = {h: self._jev_inflight[h] for h in modelled if h in self._jev_inflight}
        answers = await self._second.lookup([h for h in modelled if h not in waits])
        for hash_, verdict in modelled.items():
            if hash_ in answers or hash_ in waits or hash_ not in held or not verdict.spans:
                continue
            pieces = _slices(held.pop(hash_), verdict.spans)
            waits[hash_] = self._jev_inflight.get(hash_) or self._start_jev(self._second, hash_, pieces)
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
            outcome = self._second.classify(answer.p, partial=answer.partial)
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
        return len(self._inflight) + self._jev_asks

    def _start(self, hash_: str, text: str) -> asyncio.Task[Verdict | None] | None:
        if self._pending() >= self._max_pending:
            return None
        task = asyncio.get_running_loop().create_task(self._scan_and_store(hash_, text))
        self._inflight[hash_] = task
        task.add_done_callback(lambda _: self._finished(self._inflight, hash_))
        self._metrics.pending_scans.set(self._pending())
        return task

    def _ask_when_scans_end(self, waits: dict[str, asyncio.Task[Verdict | None]], held: dict[str, str]) -> None:
        for hash_, task in waits.items():
            if hash_ in held:
                task.add_done_callback(partial(self._ask_if_flagged, hash_, held[hash_]))

    def _ask_if_flagged(self, hash_: str, text: str, scan: asyncio.Task[Verdict | None]) -> None:
        if self._second is None or scan.cancelled() or scan.exception() is not None:
            return
        verdict = scan.result()
        if verdict is not None and verdict.flagged and verdict.spans and hash_ not in self._jev_inflight:
            self._start_jev(self._second, hash_, _slices(text, verdict.spans), recheck=True)

    def _start_jev(
        self, second: SecondCheck, hash_: str, pieces: list[str], *, recheck: bool = False
    ) -> asyncio.Task[JevAnswer]:
        task = asyncio.get_running_loop().create_task(self._ask_windows(second, hash_, pieces, recheck=recheck))
        self._jev_inflight[hash_] = task
        task.add_done_callback(lambda _: self._finished(self._jev_inflight, hash_))
        return task

    async def _ask_windows(self, second: SecondCheck, hash_: str, pieces: list[str], *, recheck: bool) -> JevAnswer:
        """Ask Jev about every window of a text at once and return the answer stored for the text.

        With recheck, a stored answer is returned instead of asking.
        """
        if recheck:
            stored = await second.lookup([hash_])
            if hash_ in stored:
                return stored[hash_]
        asked = await asyncio.gather(*(self._ask_window(second, hash_, i, piece) for i, piece in enumerate(pieces)))
        return await second.settle(hash_, asked)

    async def _ask_window(self, second: SecondCheck, hash_: str, index: int, text: str) -> Asked:
        """Ask about one window while holding a pending slot; a window with no free slot is skipped."""
        if self._pending() >= self._max_pending:
            self._metrics.jev_requests.labels("skipped").inc()
            return SKIPPED
        self._jev_asks += 1
        self._metrics.pending_scans.set(self._pending())
        try:
            return await second.ask_window(hash_, index, text)
        finally:
            self._jev_asks -= 1
            self._metrics.pending_scans.set(self._pending())

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
        while self._inflight or self._jev_inflight:
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
