"""HTTP API: POST /v1/scan, health, readiness and Prometheus metrics."""

import asyncio
import hmac
import json
import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from typing import NoReturn

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


class _RequestError(Exception):
    def __init__(self, response: JSONResponse):
        self.response = response


def _error(status: int, detail: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail}, headers=headers)


def _parse(raw: bytes) -> tuple[list[dict], list[str]]:
    """Return the items to scan and the hashes to look up, holding nothing else of the body."""
    try:
        body = ScanRequest.model_validate(json.loads(raw))
    except ValidationError:
        raise _RequestError(_error(422, "body does not match the scan request schema")) from None
    except ValueError:
        raise _RequestError(_error(400, "body is not valid JSON")) from None
    return [item.model_dump() for item in body.new], body.known


async def _wait_for_disconnect(request: Request) -> None:
    message = await request.receive()
    while message["type"] != "http.disconnect":
        message = await request.receive()


class _Service:
    """Holds the guard once loaded, and serves the endpoints."""

    def __init__(self, settings: Settings, metrics: Metrics, load: Callable[[], Awaitable[ToolGuard]]):
        self._settings = settings
        self._metrics = metrics
        self._load = load
        self._token = f"Bearer {settings.auth_token}".encode() if settings.auth_token else None
        self.guard: ToolGuard | None = None
        self.failed = False
        self._active = 0

    async def start(self) -> None:
        try:
            self.guard = await self._load()
        except Exception:
            logger.exception("model load failed")
            self.failed = True
            return
        self._metrics.ready.set(1)
        logger.info("ready")

    @asynccontextmanager
    async def lifespan(self, _app: FastAPI):
        loading = asyncio.create_task(self.start())
        try:
            yield
        finally:
            loading.cancel()
            with suppress(asyncio.CancelledError):
                await loading
            if self.guard is not None:
                await self.guard.drain(self._settings.shutdown_drain_seconds)
                self.guard.close()

    def healthz(self):
        """Liveness: fails only when the model could not load."""
        if self.failed:
            return _error(503, "model load failed")
        return {"status": "ok"}

    def readyz(self):
        """Readiness: 503 until the model has loaded."""
        if self.guard is None:
            return _error(503, "not ready")
        return {"status": "ok"}

    def prometheus(self):
        """Prometheus metrics."""
        return Response(generate_latest(self._metrics.registry), media_type=CONTENT_TYPE_LATEST)

    async def scan(self, request: Request):
        """Return the hashes to flag and the known hashes without a verdict."""
        with self._metrics.request_seconds.time():
            try:
                guard = self._admit(request)
            except _RequestError as exc:
                return exc.response
            try:
                return await self._answer(guard, request)
            finally:
                self._active -= 1

    async def _answer(self, guard: ToolGuard, request: Request):
        try:
            check = asyncio.create_task(guard.check(*_parse(await self._read_body(request))))
        except _RequestError as exc:
            return exc.response
        gone = asyncio.create_task(_wait_for_disconnect(request))
        try:
            # Cancelling check drops only this request's wait; the scans it started are shielded and still get cached
            await asyncio.wait({check, gone}, return_when=asyncio.FIRST_COMPLETED)
            if not check.done():
                return _error(499, "client disconnected")
            flagged, unknown = check.result()
            return {"flagged": flagged, "unknown": unknown}
        finally:
            gone.cancel()
            check.cancel()

    def _admit(self, request: Request) -> ToolGuard:
        if self._token is not None:
            supplied = request.headers.get("authorization", "").encode()
            if not hmac.compare_digest(supplied, self._token):
                raise _RequestError(_error(401, "unauthorized", {"WWW-Authenticate": "Bearer"}))
        if self.guard is None:
            raise _RequestError(_error(503, "not ready"))
        if self._active >= self._settings.max_concurrent_requests:
            self._metrics.over_limit.labels("requests").inc()
            raise _RequestError(_error(503, "too many requests in flight"))
        self._active += 1
        return self.guard

    async def _read_body(self, request: Request) -> bytes:
        limit = self._settings.max_body_bytes
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            self._too_large(limit)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > limit:
                self._too_large(limit)
        return bytes(body)

    def _too_large(self, limit: int) -> NoReturn:
        self._metrics.over_limit.labels("body").inc()
        raise _RequestError(_error(413, f"body over {limit} bytes"))


def create_app(settings: Settings, metrics: Metrics, load: Callable[[], Awaitable[ToolGuard]]) -> FastAPI:
    """Build the app; load runs in the background at startup and returns the guard once the model is ready."""
    service = _Service(settings, metrics, load)
    app = FastAPI(lifespan=service.lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.get("/healthz")(service.healthz)
    app.get("/readyz")(service.readyz)
    app.get("/metrics")(service.prometheus)
    app.post("/v1/scan")(service.scan)
    return app
