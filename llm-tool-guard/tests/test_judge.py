"""Tests for the Jev client: request shape, response checks, error classes and the retry budget."""

import asyncio
import json
import time

import httpx2
import pytest

import judge as judge_module
from judge import QUESTION, QUESTION_ID, STATE_KEY, JevError, Judge

MODEL = "jev-1.13.0"
KEY = "jev-test-key"


@pytest.fixture(autouse=True)
def quick_retry(monkeypatch):
    monkeypatch.setattr(judge_module, "_RETRY_DELAY_SECONDS", 0.01)


def answer(p=0.5, model=MODEL) -> httpx2.Response:
    body = {
        "model": model,
        "answers": {QUESTION_ID: {"type": "noul", "noul": p}},
        "usage": {"input_tokens": 10, "output_tokens": 1},
    }
    return httpx2.Response(200, json=body)


class Typesafe:
    """A fake TypeSafe: replies from a script, one reply per request, repeating the last."""

    def __init__(self, *replies):
        """Reply with each item in turn: a Response, or an exception to raise."""
        self.replies = list(replies)
        self.requests: list[httpx2.Request] = []

    async def __call__(self, request: httpx2.Request) -> httpx2.Response:
        """Record the request and play the next reply."""
        self.requests.append(request)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply

    def judge(self, timeout_seconds: float = 10.0) -> Judge:
        client = httpx2.AsyncClient(transport=httpx2.MockTransport(self), base_url="https://typesafe.test")
        return Judge(client, api_key=KEY, model=MODEL, timeout_seconds=timeout_seconds)


def ask(typesafe: Typesafe, text="tool output", timeout_seconds=10.0) -> float:
    async def run():
        judge = typesafe.judge(timeout_seconds)
        try:
            return await judge.ask(text)
        finally:
            await judge.aclose()

    return asyncio.run(run())


def error_of(typesafe: Typesafe, **kwargs) -> JevError:
    with pytest.raises(JevError) as caught:
        ask(typesafe, **kwargs)
    return caught.value


def test_the_answer_is_the_noul_probability():
    assert ask(Typesafe(answer(0.0312))) == 0.0312


def test_request_asks_the_pinned_model_one_question_about_the_text():
    typesafe = Typesafe(answer())

    ask(typesafe, "exit code 1\nrun it again")

    (request,) = typesafe.requests
    assert (request.method, request.url.path) == ("POST", "/v1/systemone")
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert json.loads(request.content) == {
        "model": MODEL,
        "state": {STATE_KEY: "exit code 1\nrun it again"},
        "questions": {QUESTION_ID: QUESTION},
    }


def test_the_question_asks_for_an_embedded_instruction_with_yes_meaning_injection():
    assert QUESTION["type"] == "noul"
    assert "embedded instruction" in QUESTION["instructions"]
    assert set(QUESTION["criteria"]) == {"true", "false"}
    assert STATE_KEY == "tool_output"


def test_lone_surrogates_are_replaced_so_the_body_is_valid_utf8():
    typesafe = Typesafe(answer())

    ask(typesafe, "half \ud800 pair")

    assert json.loads(typesafe.requests[0].content)["state"][STATE_KEY] == "half � pair"


def test_a_response_from_another_model_is_a_transient_error():
    error = error_of(Typesafe(answer(model="jev-1.14.0")))

    assert (error.permanent, error.retryable) == (False, False)
    assert "jev-1.14.0" in str(error)


@pytest.mark.parametrize("status", [413, 422])
def test_request_the_service_refuses_is_permanent_and_not_retried(status):
    typesafe = Typesafe(httpx2.Response(status, json={"detail": "no"}))

    error = error_of(typesafe)

    assert (error.permanent, error.retryable) == (True, False)
    assert len(typesafe.requests) == 1


GATEWAY_ERROR = {"error": {"message": "Budget has been exceeded", "type": "budget_exceeded", "param": None}}


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (422, {**GATEWAY_ERROR, "call_id": "call-1"}),
        (413, {"error": "Request size is too large"}),
        (413, {"error": {"message": "too large", "type": "invalid_request_error", "code": "413"}}),
    ],
)
def test_a_413_or_422_in_a_gateway_error_envelope_is_transient_and_not_retried(status, body):
    service = Typesafe(httpx2.Response(status, json=body))

    error = error_of(service)

    assert (error.permanent, error.retryable) == (False, False)
    assert len(service.requests) == 1


@pytest.mark.parametrize("status", [413, 422])
@pytest.mark.parametrize("content", ["Request Entity Too Large", '["no"]', '{"detail": [{"msg": "bad"}]}'])
def test_a_413_or_422_without_a_gateway_error_envelope_is_permanent(status, content):
    error = error_of(Typesafe(httpx2.Response(status, content=content)))

    assert (error.permanent, error.retryable) == (True, False)


@pytest.mark.parametrize(
    "response",
    [
        httpx2.Response(400, json={"error": {"message": "max_tokens_exceeded", "type": "max_tokens_exceeded"}}),
        httpx2.Response(400, json={"error": {"code": "max_tokens_exceeded", "error_type": "max_tokens_exceeded"}}),
        httpx2.Response(400, json={"error": "max_tokens_exceeded", "call_id": "call-1"}),
    ],
)
def test_a_gateway_error_that_mentions_the_length_error_code_is_transient(response):
    service = Typesafe(response)

    error = error_of(service)

    assert (error.permanent, error.retryable) == (False, False)
    assert len(service.requests) == 1


def test_a_gateway_call_id_beside_the_service_error_keeps_the_length_error_permanent():
    body = {"detail": {"error_type": "max_tokens_exceeded", "message": "too long"}, "call_id": "call-1"}
    service = Typesafe(httpx2.Response(400, json=body))

    error = error_of(service)

    assert (error.permanent, error.retryable) == (True, False)


@pytest.mark.parametrize(
    "body",
    [
        {"error": {"message": "Response blocked by guardrail", "type": "content_filter"}},
        {"detail": "Not Found"},
    ],
)
def test_an_error_body_with_status_200_is_a_transient_error(body):
    error = error_of(Typesafe(httpx2.Response(200, json=body)))

    assert (error.permanent, error.retryable) == (False, False)


@pytest.mark.parametrize(
    "body",
    [
        {"detail": {"error_type": "max_tokens_exceeded", "message": "too long"}},
        {"detail": {"code": "max_tokens_exceeded"}},
        {"error_type": "max_tokens_exceeded"},
        {"code": "max_tokens_exceeded"},
    ],
)
def test_a_400_for_a_text_longer_than_the_model_context_is_permanent_and_not_retried(body):
    typesafe = Typesafe(httpx2.Response(400, json=body))

    error = error_of(typesafe)

    assert (error.permanent, error.retryable) == (True, False)
    assert len(typesafe.requests) == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx2.Response(400, json={"detail": {"error_type": "invalid_request_error", "message": "bad utf-8"}}),
        httpx2.Response(400, json={"detail": "max_tokens_exceeded"}),
        httpx2.Response(400, json={"detail": ["max_tokens_exceeded"]}),
        httpx2.Response(400, json=["max_tokens_exceeded"]),
        httpx2.Response(400, json={"detail": {"message": "max_tokens_exceeded"}}),
        httpx2.Response(400, content="max_tokens_exceeded"),
        httpx2.Response(400),
    ],
)
def test_any_other_400_is_a_transient_error_and_not_retried(response):
    typesafe = Typesafe(response)

    error = error_of(typesafe)

    assert (error.permanent, error.retryable) == (False, False)
    assert len(typesafe.requests) == 1


@pytest.mark.parametrize("status", [401, 403, 404])
def test_other_client_errors_are_transient_and_not_retried(status):
    typesafe = Typesafe(httpx2.Response(status))

    error = error_of(typesafe)

    assert (error.permanent, error.retryable) == (False, False)
    assert len(typesafe.requests) == 1


@pytest.mark.parametrize("status", [429, 500, 502, 503, 529])
def test_overload_and_server_errors_are_retried_once(status):
    typesafe = Typesafe(httpx2.Response(status), answer(0.7))

    assert ask(typesafe) == 0.7
    assert len(typesafe.requests) == 2


def test_a_second_failure_ends_the_retry_with_a_transient_error():
    typesafe = Typesafe(httpx2.Response(503))

    error = error_of(typesafe)

    assert (error.permanent, error.retryable) == (False, True)
    assert len(typesafe.requests) == 2


@pytest.mark.parametrize("failure", [httpx2.ReadTimeout("slow"), httpx2.ConnectError("refused")])
def test_a_timeout_or_dropped_connection_is_retried_once(failure):
    typesafe = Typesafe(failure, answer(0.2))

    assert ask(typesafe) == 0.2
    assert len(typesafe.requests) == 2


def test_an_attempt_that_never_answers_ends_at_the_time_budget_after_one_retry():
    class Hangs(Typesafe):
        async def __call__(self, request):
            self.requests.append(request)
            await asyncio.sleep(30)

    typesafe = Hangs(answer())
    start = time.monotonic()

    error = error_of(typesafe, timeout_seconds=0.6)

    assert time.monotonic() - start < 2
    assert (error.permanent, error.retryable) == (False, True)
    assert len(typesafe.requests) == 2


def test_no_retry_is_started_without_budget_for_it(monkeypatch):
    monkeypatch.setattr(judge_module, "_RETRY_DELAY_SECONDS", 0.2)
    typesafe = Typesafe(httpx2.Response(503))

    error = error_of(typesafe, timeout_seconds=0.15)

    assert error.retryable
    assert len(typesafe.requests) == 1


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        [],
        {},
        {"model": MODEL},
        {"model": MODEL, "answers": {}},
        {"model": MODEL, "answers": {QUESTION_ID: {"type": "noul"}}},
        {"model": MODEL, "answers": {QUESTION_ID: {"noul": "high"}}},
        {"model": MODEL, "answers": {QUESTION_ID: {"noul": True}}},
        {"model": MODEL, "answers": {QUESTION_ID: {"noul": None}}},
        {"model": MODEL, "answers": {QUESTION_ID: {"noul": 1.5}}},
        {"model": MODEL, "answers": {QUESTION_ID: {"noul": -0.1}}},
        {"model": MODEL, "answers": {QUESTION_ID: {"noul": float("nan")}}},
        {"model": MODEL, "answers": [1]},
    ],
)
def test_a_malformed_answer_is_a_transient_error(body):
    content = body if isinstance(body, str) else json.dumps(body)

    error = error_of(Typesafe(httpx2.Response(200, content=content)))

    assert (error.permanent, error.retryable) == (False, False)


def test_an_integer_probability_is_accepted():
    assert ask(Typesafe(answer(1))) == 1.0


def test_errors_do_not_carry_the_key_or_the_text():
    secret_text = "private tool output"
    typesafe = Typesafe(httpx2.Response(500, text=f"echo {secret_text}"))

    error = error_of(typesafe, text=secret_text)

    assert KEY not in str(error)
    assert secret_text not in str(error)
