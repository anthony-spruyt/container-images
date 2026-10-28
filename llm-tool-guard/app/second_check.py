"""Jev as a second check on the windows of a text the model flagged: asks per window, stores one answer per text."""

import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, NamedTuple, Protocol

import httpx2

import judge as judge_module
from cache import JevAnswer, JevCache, jev_namespace, runtime_fingerprint
from config import Settings
from judge import JevError, Judge
from metrics import Metrics

logger = logging.getLogger(__name__)

Outcome = Literal["blocked", "cleared", "middle"]


class Asked(NamedTuple):
    """What asking Jev about one window gave: its probability, or none, and whether asking again would repeat that."""

    p: float | None
    permanent: bool = False
    skipped: bool = False


SKIPPED = Asked(None, skipped=True)


class Judging(Protocol):
    """What SecondCheck needs from the Jev client."""

    async def ask(self, text: str) -> float:
        """Return the probability that text holds an embedded instruction, or raise JevError."""

    async def aclose(self) -> None:
        """Release the client."""


class SecondCheck:
    """Asks Jev about the flagged windows of a text and stores one answer per text; the first one stored is used."""

    def __init__(  # noqa: PLR0913 - keyword-only thresholds and limit
        self,
        judge: Judging,
        cache: JevCache,
        metrics: Metrics,
        *,
        block_at: float,
        clear_below: float,
        max_text_bytes: int,
    ):
        """block_at and clear_below are applied to every answer when it is read, so retuning them never asks again."""
        self._judge = judge
        self._cache = cache
        self._metrics = metrics
        self._block_at = block_at
        self._clear_below = clear_below
        self._max_text_bytes = max_text_bytes

    def classify(self, p: float, *, partial: bool = False) -> Outcome:
        """Return blocked at or above block_at, cleared below clear_below, else middle; never cleared when partial."""
        if p >= self._block_at:
            return "blocked"
        return "cleared" if p < self._clear_below and not partial else "middle"

    async def lookup(self, hashes: list[str]) -> dict[str, JevAnswer]:
        """Return the stored answer or no-answer marker of each hash that has one."""
        return await self._cache.get_many(hashes)

    async def ask_window(self, hash_: str, index: int, text: str) -> Asked:
        """Ask Jev about one window of the text with this hash; nothing is stored until settle.

        A window with no text or over the size limit is not asked. A cancelled ask returns nothing.
        """
        if not text or len(text.encode("utf-8", "surrogatepass")) > self._max_text_bytes:
            self._metrics.jev_requests.labels("skipped").inc()
            return SKIPPED
        try:
            with self._metrics.jev_seconds.time():
                p = await self._judge.ask(text)
        except JevError as exc:
            logger.warning("jev gave no answer for %s window %d: %s", hash_[:23], index, exc)
            self._metrics.jev_requests.labels("error").inc()
            return Asked(None, permanent=exc.permanent)
        except Exception:
            logger.exception("jev failed for %s window %d", hash_[:23], index)
            self._metrics.jev_requests.labels("error").inc()
            return Asked(None)
        self._metrics.jev_requests.labels(self.classify(p)).inc()
        logger.info("jev scored %s window %d: p=%.4f", hash_[:23], index, p)
        return Asked(p)

    async def settle(self, hash_: str, asked: Sequence[Asked]) -> JevAnswer:
        """Store the text's answer, its windows' highest probability, and return what is stored for the hash.

        The answer is partial when a window gave none. If a window was skipped nothing is stored, so raising the limit
        or a free slot takes effect at once; the answer returned is for this request only.
        """
        answered = [a.p for a in asked if a.p is not None]
        p = max(answered, default=None)
        partial = bool(answered) and len(answered) < len(asked)
        if any(a.skipped for a in asked):
            return JevAnswer(p, partial)
        permanent = all(a.permanent for a in asked if a.p is None)
        return await self._cache.settle(hash_, p, partial=partial, permanent=permanent)

    async def aclose(self) -> None:
        """Close the Jev client."""
        await self._judge.aclose()


def build_second_check(
    settings: Settings,
    valkey: Any,
    metrics: Metrics,
    *,
    scan_namespace: str,
    transport: httpx2.AsyncBaseTransport | None = None,
) -> SecondCheck | None:
    """Return the second check the settings ask for, or None while JEV_MODE is off; valkey may be None.

    scan_namespace is the verdict cache namespace: Jev answers are kept apart per namespace because it decides which
    windows are asked about. transport replaces the network connection to the Jev API, for tests.
    """
    if settings.jev_mode != "enforce":
        return None
    client = httpx2.AsyncClient(base_url=settings.jev_api_url, transport=transport)
    judge = Judge(
        client,
        api_key=settings.jev_api_key,
        model=settings.jev_model,
        timeout_seconds=settings.jev_timeout_seconds,
    )
    namespace = jev_namespace(
        model=settings.jev_model,
        question=json.dumps(judge_module.QUESTION, sort_keys=True),
        runtime=runtime_fingerprint([Path(judge_module.__file__)], libraries=()),
        scan_namespace=scan_namespace,
    )
    logger.info("jev namespace %s (model %s)", namespace, settings.jev_model)
    cache = JevCache(valkey, namespace=namespace, ttl_seconds=settings.cache_ttl_seconds, metrics=metrics)
    return SecondCheck(
        judge,
        cache,
        metrics,
        block_at=settings.jev_block_at,
        clear_below=settings.jev_clear_below,
        max_text_bytes=settings.jev_max_text_bytes,
    )
