"""Tests for the adapter between the service and the PromptInjection scanner."""

from types import SimpleNamespace

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
