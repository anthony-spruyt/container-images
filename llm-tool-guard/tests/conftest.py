"""Fixtures shared by the llm-tool-guard tests.

Run from llm-tool-guard/app so the app modules import: python -m pytest ../tests
"""

from collections.abc import Callable

import pytest
from prometheus_client import CollectorRegistry
from redis.exceptions import ConnectionError as ValkeyConnectionError

from fakes import FakeValkey, closed_transport_error
from metrics import Metrics


@pytest.fixture(name="metrics")
def fixture_metrics() -> Metrics:
    """Metrics on a private registry."""
    return Metrics(CollectorRegistry())


@pytest.fixture(name="valkey")
def fixture_valkey() -> FakeValkey:
    """An empty fake Valkey."""
    return FakeValkey()


@pytest.fixture(name="cache_error", params=[ValkeyConnectionError, closed_transport_error], ids=["refused", "closed"])
def fixture_cache_error(request) -> Callable[[], Exception]:
    """Make a failure of the Valkey client: a refused connection, or a write to an already closed transport."""
    return request.param
