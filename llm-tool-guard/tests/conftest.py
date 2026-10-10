"""Fixtures shared by the llm-tool-guard tests.

Run from llm-tool-guard/app so the app modules import: python -m pytest ../tests
"""

import pytest
from prometheus_client import CollectorRegistry

from fakes import FakeValkey
from metrics import Metrics


@pytest.fixture(name="metrics")
def fixture_metrics() -> Metrics:
    """Metrics on a private registry."""
    return Metrics(CollectorRegistry())


@pytest.fixture(name="valkey")
def fixture_valkey() -> FakeValkey:
    """An empty fake Valkey."""
    return FakeValkey()
