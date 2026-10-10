"""Tests for the adapter between the service and the PromptInjection scanner."""

import threading
import time
from types import SimpleNamespace

import pytest

from classifier import Classifier

MODEL = "org/model"
SNAPSHOT = "/hf/hub/models--org--model/snapshots/0123abc/config.json"


class StubScanner:
    """Records scanned text and answers with a fixed verdict."""

    def __init__(self, is_safe: bool):
        """Build a scanner with a fixed verdict."""
        self.is_safe = is_safe
        self.texts: list[str] = []
        self.loaded = False

    def load(self):
        """Pretend to load the model."""
        self.loaded = True

    def scan(self, text: str):
        """Return the fixed verdict."""
        self.texts.append(text)
        return SimpleNamespace(is_safe=self.is_safe, score=0.0)


def locate(found):
    calls = []

    def lookup(model: str, filename: str):
        calls.append((model, filename))
        return found

    return lookup, calls


def test_flagged_when_the_scanner_finds_it_unsafe():
    assert Classifier(StubScanner(is_safe=False), MODEL)("x") is True
    assert Classifier(StubScanner(is_safe=True), MODEL)("x") is False


def test_lone_surrogates_are_replaced_before_tokenizing():
    scanner = StubScanner(is_safe=True)

    Classifier(scanner, MODEL)("a \ud800 b")

    assert scanner.texts == ["a � b"]


def test_load_loads_the_scanner_and_reads_the_cached_snapshot_revision():
    scanner = StubScanner(is_safe=True)
    lookup, calls = locate(SNAPSHOT)
    classifier = Classifier(scanner, MODEL, locate=lookup)

    classifier.load()

    assert scanner.loaded
    assert calls == [(MODEL, "config.json")]
    assert classifier.revision == "0123abc"


def test_revision_is_empty_when_the_model_is_not_in_the_hub_cache():
    lookup, _ = locate(None)
    classifier = Classifier(StubScanner(is_safe=True), MODEL, locate=lookup)

    classifier.load()

    assert classifier.revision == ""


def test_revision_is_empty_for_a_cached_non_existence_marker():
    lookup, _ = locate(object())
    classifier = Classifier(StubScanner(is_safe=True), MODEL, locate=lookup)

    classifier.load()

    assert classifier.revision == ""


class WindowedScanner:
    """Scores one window per forward call, taking `seconds` each, like the sliding-window scanner."""

    def __init__(self, windows: int, seconds: float):
        """Build a scanner whose scan makes `windows` forward calls."""
        self.windows = windows
        self.seconds = seconds
        self.forwards = 0
        self._pipe = SimpleNamespace(forward=self._forward)

    def load(self):
        """Pretend to load the model."""

    def _forward(self, batch):
        self.forwards += 1
        time.sleep(self.seconds)
        return batch

    def scan(self, text: str):
        """Run every window through the pipeline."""
        for _ in range(self.windows):
            self._pipe.forward(text)
        return SimpleNamespace(is_safe=True, score=0.0)


def loaded(scanner, **kwargs) -> Classifier:
    classifier = Classifier(scanner, MODEL, locate=locate(None)[0], **kwargs)
    classifier.load()
    return classifier


def test_scan_over_its_time_budget_stops_between_windows():
    scanner = WindowedScanner(windows=50, seconds=0.02)
    classifier = loaded(scanner, time_budget_seconds=0.1)

    with pytest.raises(TimeoutError, match=r"0\.1s"):
        classifier("x")

    assert 2 <= scanner.forwards < 50


def test_scan_within_its_time_budget_is_unaffected():
    scanner = WindowedScanner(windows=3, seconds=0)

    assert loaded(scanner, time_budget_seconds=5)("x") is False
    assert scanner.forwards == 3


def test_each_scan_gets_a_fresh_time_budget():
    classifier = loaded(WindowedScanner(windows=3, seconds=0.05), time_budget_seconds=0.25)

    assert classifier("x") is False
    assert classifier("y") is False


def test_without_a_time_budget_scans_run_to_the_end():
    scanner = WindowedScanner(windows=5, seconds=0.01)

    assert loaded(scanner)("x") is False
    assert scanner.forwards == 5


def test_time_budgets_are_per_thread():
    classifier = loaded(WindowedScanner(windows=3, seconds=0.05), time_budget_seconds=0.25)
    outcomes = []

    def run():
        try:
            outcomes.append(classifier("x"))
        except TimeoutError:
            outcomes.append("timeout")

    threads = [threading.Thread(target=run) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert outcomes == [False, False, False]
