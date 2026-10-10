"""Tests for the HTTP API: scan contract, auth, limits, health and metrics."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from api import create_app
from cache import VerdictCache
from config import Settings
from fakes import INJECTION, FakeScanner, FakeValkey, digest, sample
from guard import ToolGuard


def make_guard(metrics, valkey=None, scanner=None, **settings_env) -> ToolGuard:
    settings = Settings.from_env(settings_env)
    cache = VerdictCache(valkey, namespace="ns", ttl_seconds=60, metrics=metrics)
    return ToolGuard(
        scanner or FakeScanner(),
        cache,
        metrics,
        max_text_bytes=settings.max_text_bytes,
        max_pending_scans=settings.max_pending_scans,
        scan_workers=settings.scan_workers,
    )


def client_for(metrics, guard=None, load=None, **env) -> TestClient:
    settings = Settings.from_env(env)
    guard = guard or make_guard(metrics, FakeValkey())

    async def ready():
        await asyncio.sleep(0)
        return guard

    return TestClient(create_app(settings, metrics, load or ready))


@pytest.fixture(name="client")
def fixture_client(metrics):
    with client_for(metrics) as client:
        yield client


def body(new=(), known=()) -> dict:
    return {"new": [{"hash": digest(t), "text": t} for t in new], "known": list(known)}


def test_scan_returns_flagged_and_unknown(client):
    response = client.post("/v1/scan", json=body(["clean", f"{INJECTION} me"], [digest("never seen")]))

    assert response.status_code == 200
    assert response.json() == {"flagged": [digest(f"{INJECTION} me")], "unknown": [digest("never seen")]}


def test_known_lookup_after_scan_uses_the_cache(client):
    client.post("/v1/scan", json=body([f"{INJECTION} me", "clean"]))

    response = client.post("/v1/scan", json=body(known=[digest(f"{INJECTION} me"), digest("clean")]))

    assert response.json() == {"flagged": [digest(f"{INJECTION} me")], "unknown": []}


@pytest.mark.parametrize("payload", [{}, {"new": []}, {"known": []}, {"new": [], "known": [], "extra": 1}])
def test_missing_lists_default_to_empty(client, payload):
    response = client.post("/v1/scan", json=payload)

    assert response.status_code == 200
    assert response.json() == {"flagged": [], "unknown": []}


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"new": "x"},
        {"new": [{"hash": "sha256:00"}]},
        {"new": [{"text": "x"}]},
        {"new": [{"hash": 1, "text": "x"}]},
        {"new": [{"hash": "sha256:00", "text": 5}]},
        {"known": [1]},
        {"known": "sha256:00"},
    ],
)
def test_invalid_shape_is_rejected(client, payload):
    assert client.post("/v1/scan", json=payload).status_code == 422


def test_invalid_json_is_rejected(client):
    response = client.post("/v1/scan", content=b"{not json", headers={"Content-Type": "application/json"})

    assert response.status_code == 400


def test_lone_surrogates_in_json_hash_like_the_middleware(client):
    text = "half \ud83d pair"
    raw = json.dumps({"new": [{"hash": digest(text), "text": text}], "known": []})

    response = client.post("/v1/scan", content=raw.encode(), headers={"Content-Type": "application/json"})

    assert response.json() == {"flagged": [], "unknown": []}


def test_forged_hash_is_flagged(client):
    victim = digest(f"{INJECTION} hidden")

    response = client.post("/v1/scan", json={"new": [{"hash": victim, "text": "benign"}]})

    assert response.json()["flagged"] == [victim]


def test_body_over_the_limit_is_rejected(metrics):
    with client_for(metrics, MAX_BODY_BYTES="200") as client:
        response = client.post("/v1/scan", json=body(["x" * 300]))

    assert response.status_code == 413
    assert sample(metrics, "llm_tool_guard_over_limit_total", limit="body") == 1


def test_streamed_body_over_the_limit_is_rejected(metrics):
    def chunks():
        yield b'{"new": [{"hash": "sha256:00", "text": "'
        yield b"x" * 300
        yield b'"}]}'

    with client_for(metrics, MAX_BODY_BYTES="200") as client:
        response = client.post("/v1/scan", content=chunks(), headers={"Content-Type": "application/json"})

    assert response.status_code == 413


def test_text_over_the_item_limit_is_flagged(metrics):
    with client_for(metrics, guard=make_guard(metrics, FakeValkey(), MAX_TEXT_BYTES="10")) as client:
        response = client.post("/v1/scan", json=body(["x" * 11, "short"]))

    assert response.json() == {"flagged": [digest("x" * 11)], "unknown": []}


def test_auth_not_required_without_a_token(client):
    assert client.post("/v1/scan", json=body()).status_code == 200


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "secret-token"}, {"Authorization": "Basic secret-token"}],
)
def test_auth_rejects_missing_or_wrong_token(metrics, headers):
    with client_for(metrics, AUTH_TOKEN="secret-token") as client:
        response = client.post("/v1/scan", json=body(), headers=headers)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_auth_accepts_the_token(metrics):
    with client_for(metrics, AUTH_TOKEN="secret-token") as client:
        response = client.post("/v1/scan", json=body(), headers={"Authorization": "Bearer secret-token"})

    assert response.status_code == 200


def test_auth_is_checked_before_the_body_is_read(metrics):
    with client_for(metrics, AUTH_TOKEN="secret-token", MAX_BODY_BYTES="10") as client:
        response = client.post("/v1/scan", json=body(["x" * 100]))

    assert response.status_code == 401


def test_health_endpoints_do_not_need_auth(metrics):
    with client_for(metrics, AUTH_TOKEN="secret-token") as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/readyz").status_code == 200
        assert client.get("/metrics").status_code == 200


def test_not_ready_until_the_model_loads(metrics):
    loaded = asyncio.Event()
    guard = make_guard(metrics)

    async def load():
        await loaded.wait()
        return guard

    with client_for(metrics, load=load) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/readyz").status_code == 503
        assert client.post("/v1/scan", json=body(["x"])).status_code == 503
        client.portal.call(loaded.set)
        for _ in range(100):
            if client.get("/readyz").status_code == 200:
                break
            client.portal.call(asyncio.sleep, 0.01)
        assert client.get("/readyz").status_code == 200
        assert client.post("/v1/scan", json=body(["x"])).status_code == 200


def test_failed_model_load_fails_liveness(metrics):
    async def load():
        await asyncio.sleep(0)
        raise RuntimeError("model missing from cache")

    with client_for(metrics, load=load) as client:
        for _ in range(100):
            if client.get("/healthz").status_code != 200:
                break
            client.portal.call(asyncio.sleep, 0.01)
        assert client.get("/healthz").status_code == 503
        assert client.get("/readyz").status_code == 503


def test_metrics_endpoint_exposes_the_service_metrics(client):
    client.post("/v1/scan", json=body([f"{INJECTION} me"], [digest("unseen")]))

    text = client.get("/metrics").text

    for name in (
        "llm_tool_guard_scans_total",
        "llm_tool_guard_flagged_total",
        "llm_tool_guard_cache_hits_total",
        "llm_tool_guard_cache_misses_total",
        "llm_tool_guard_cache_errors_total",
        "llm_tool_guard_cache_up",
        "llm_tool_guard_scan_duration_seconds",
        "llm_tool_guard_request_duration_seconds",
        "llm_tool_guard_pending_scans",
        "llm_tool_guard_over_limit_total",
        "llm_tool_guard_ready",
    ):
        assert name in text


def test_ready_gauge(metrics):
    with client_for(metrics):
        assert sample(metrics, "llm_tool_guard_ready") == 1


def test_request_latency_is_observed(metrics, client):
    client.post("/v1/scan", json=body(["x"]))

    assert sample(metrics, "llm_tool_guard_request_duration_seconds_count") == 1
