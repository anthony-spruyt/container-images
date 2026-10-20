"""Jev as a second check on texts the model flagged: asks, stores the raw answer and applies the thresholds."""

import json
import logging
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx2

import judge as judge_module
from cache import JevAnswer, JevCache, jev_namespace, runtime_fingerprint
from config import Settings
from judge import JevError, Judge
from metrics import Metrics

logger = logging.getLogger(__name__)

Outcome = Literal["blocked", "cleared", "middle"]


class Judging(Protocol):
    """What SecondCheck needs from the Jev client."""

    async def ask(self, text: str) -> float:
        """Return the probability that text holds an embedded instruction, or raise JevError."""

    async def aclose(self) -> None:
        """Release the client."""


class SecondCheck:
    """Asks Jev about one text at a time and stores what it said; the first answer stored for a hash is the one used."""

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

    def classify(self, p: float) -> Outcome:
        """Return blocked at or above block_at, cleared below clear_below, else middle."""
        if p >= self._block_at:
            return "blocked"
        return "cleared" if p < self._clear_below else "middle"

    async def lookup(self, hashes: list[str]) -> dict[str, JevAnswer]:
        """Return the stored answer or no-answer marker of each hash that has one."""
        return await self._cache.get_many(hashes)

    async def ask(self, hash_: str, text: str) -> JevAnswer:
        """Ask Jev about text, store the outcome and return what is stored.

        A request Jev refuses is stored as no-answer for the full TTL, any other failure for an hour. A text over the
        size limit is not asked and nothing is stored, so raising the limit takes effect at once. A cancelled ask
        stores nothing.
        """
        if len(text.encode("utf-8", "surrogatepass")) > self._max_text_bytes:
            self._metrics.jev_requests.labels("skipped").inc()
            return JevAnswer(None)
        try:
            with self._metrics.jev_seconds.time():
                p = await self._judge.ask(text)
        except JevError as exc:
            logger.warning("jev gave no answer for %s: %s", hash_[:23], exc)
            return await self._failed(hash_, permanent=exc.permanent)
        except Exception:
            logger.exception("jev failed for %s", hash_[:23])
            return await self._failed(hash_, permanent=False)
        self._metrics.jev_requests.labels(self.classify(p)).inc()
        logger.info("jev scored %s: p=%.4f", hash_[:23], p)
        return await self._cache.settle(hash_, p, permanent=True)

    async def aclose(self) -> None:
        """Close the Jev client."""
        await self._judge.aclose()

    async def _failed(self, hash_: str, *, permanent: bool) -> JevAnswer:
        self._metrics.jev_requests.labels("error").inc()
        return await self._cache.settle(hash_, None, permanent=permanent)


def build_second_check(
    settings: Settings, valkey: Any, metrics: Metrics, *, transport: httpx2.AsyncBaseTransport | None = None
) -> SecondCheck | None:
    """Return the second check the settings ask for, or None while JEV_MODE is off; valkey may be None.

    transport replaces the network connection to the Jev API, for tests.
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
