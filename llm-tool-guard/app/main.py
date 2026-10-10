"""Entry point: loads the PromptInjection model and serves the scan API."""

import asyncio
import logging
import os
from pathlib import Path

import uvicorn
from prometheus_client import CollectorRegistry
from redis.asyncio import Redis

import scanner_types
from api import create_app
from cache import VerdictCache, cache_namespace, runtime_fingerprint
from classifier import Classifier
from config import Settings
from guard import ToolGuard
from metrics import Metrics
from scanner_types import PromptInjectionScanner

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)


def build(settings: Settings, metrics: Metrics):
    """Return the background loader that builds the guard once the model is ready."""

    async def load() -> ToolGuard:
        classifier = Classifier(
            PromptInjectionScanner(
                model=settings.model,
                injection_label=settings.injection_label,
                threshold=settings.threshold,
                match_type="sliding_window",
                model_max_length=settings.window_tokens,
                window_overlap=settings.window_overlap,
                window_batch_size=settings.window_batch_size,
                max_windows=settings.max_windows,
            ),
            settings.model,
            time_budget_seconds=settings.scan_timeout_seconds,
        )
        await asyncio.to_thread(classifier.load)
        client = None
        if settings.valkey_url:
            client = Redis.from_url(
                settings.valkey_url,
                username=settings.valkey_username or None,
                password=settings.valkey_password or None,
                socket_timeout=settings.valkey_timeout_seconds,
                socket_connect_timeout=settings.valkey_timeout_seconds,
            )
        namespace = cache_namespace(
            model=settings.model,
            revision=classifier.revision,
            injection_label=settings.injection_label,
            threshold=settings.threshold,
            window_tokens=settings.window_tokens,
            window_overlap=settings.window_overlap,
            max_windows=settings.max_windows,
            runtime=runtime_fingerprint(Path(scanner_types.__file__)),
        )
        logging.getLogger(__name__).info(
            "cache namespace %s (model revision %s, valkey %s)",
            namespace,
            classifier.revision or "unknown",
            "on" if client is not None else "off",
        )
        cache = VerdictCache(client, namespace=namespace, ttl_seconds=settings.cache_ttl_seconds, metrics=metrics)
        return ToolGuard(
            classifier,
            cache,
            metrics,
            max_text_bytes=settings.max_text_bytes,
            max_pending_scans=settings.max_pending_scans,
            scan_workers=settings.scan_workers,
        )

    return load


def main() -> None:
    """Serve until stopped."""
    settings = Settings.from_env(os.environ)
    logging.getLogger(__name__).info("settings %s", settings)
    metrics = Metrics(CollectorRegistry())
    app = create_app(settings, metrics, build(settings, metrics))
    uvicorn.run(app, host=settings.listen_host, port=settings.listen_port)


if __name__ == "__main__":
    main()
