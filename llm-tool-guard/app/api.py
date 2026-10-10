"""HTTP API: POST /v1/scan, health, readiness and Prometheus metrics."""

import asyncio
import hmac
import json
import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, ConfigDict, ValidationError

from config import Settings
from guard import ToolGuard
from metrics import Metrics

logger = logging.getLogger(__name__)


class NewItem(BaseModel):
    """A tool result sent with its text."""

    model_config = ConfigDict(strict=True, extra="ignore")

    hash: str
    text: str


class ScanRequest(BaseModel):
    """Body of POST /v1/scan."""

    model_config = ConfigDict(strict=True, extra="ignore")

    new: list[NewItem] = []
    known: list[str] = []


class _BodyTooLargeError(Exception):
    pass


class _State:
    def __init__(self):
        self.guard: ToolGuard | None = None
        self.failed = False


def _error(status: int, detail: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail}, headers=headers)


async def _read_body(request: Request, limit: int) -> bytes:
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise _BodyTooLargeError
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            raise _BodyTooLargeError
    return bytes(body)


def create_app(settings: Settings, metrics: Metrics, load: Callable[[], Awaitable[ToolGuard]]) -> FastAPI:
    """Build the app; load runs in the background at startup and returns the guard once the model is ready."""
    state = _State()
    token = f"Bearer {settings.auth_token}".encode() if settings.auth_token else None

    async def start():
        try:
            state.guard = await load()
        except Exception:
            logger.exception("model load failed")
            state.failed = True
            return
        metrics.ready.set(1)
        logger.info("ready")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        loading = asyncio.create_task(start())
        try:
            yield
        finally:
            loading.cancel()
            with suppress(asyncio.CancelledError):
                await loading
            if state.guard is not None:
                state.guard.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/healthz")
    def healthz():
        """Liveness: fails only when the model could not load."""
        if state.failed:
            return _error(503, "model load failed")
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz():
        """Readiness: 503 until the model has loaded."""
        if state.guard is None:
            return _error(503, "not ready")
        return {"status": "ok"}

    @app.get("/metrics")
    def prometheus():
        """Prometheus metrics."""
        return Response(generate_latest(metrics.registry), media_type=CONTENT_TYPE_LATEST)

    @app.post("/v1/scan")
    async def scan(request: Request):
        """Return the hashes to flag and the known hashes without a verdict."""
        with metrics.request_seconds.time():
            if token is not None:
                supplied = request.headers.get("authorization", "").encode()
                if not hmac.compare_digest(supplied, token):
                    return _error(401, "unauthorized", {"WWW-Authenticate": "Bearer"})
            guard = state.guard
            if guard is None:
                return _error(503, "not ready")
            try:
                raw = await _read_body(request, settings.max_body_bytes)
            except _BodyTooLargeError:
                metrics.over_limit.labels("body").inc()
                return _error(413, f"body over {settings.max_body_bytes} bytes")
            try:
                body = ScanRequest.model_validate(json.loads(raw))
            except ValidationError:
                return _error(422, "body does not match the scan request schema")
            except ValueError:
                return _error(400, "body is not valid JSON")
            flagged, unknown = await guard.check([item.model_dump() for item in body.new], body.known)
            return {"flagged": flagged, "unknown": unknown}

    return app
