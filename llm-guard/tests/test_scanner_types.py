"""Tests for the PromptInjection scanner's match types.

Run from llm-guard/app so the app modules import: python -m pytest ../tests
"""

from itertools import pairwise
from types import SimpleNamespace

import pytest

import scanner_types
from scanner_types import PromptInjectionScanner

MARKER = "TRIGGER"
SPECIAL_TOKENS = 2


class FakeTokenizer:
    """Whitespace tokenizer that reports character offsets like a fast tokenizer."""

    @staticmethod
    def num_special_tokens_to_add(pair: bool = False) -> int:
        """Report a CLS/SEP pair, as a BERT-style tokenizer would."""
        return 0 if pair else SPECIAL_TOKENS

    def __call__(self, text: str, add_special_tokens: bool = True, return_offsets_mapping: bool = False) -> dict:
        """Tokenize on whitespace; offsets point into the original text."""
        offsets = []
        start = None
        for i, ch in enumerate(text):
            if ch.isspace():
                if start is not None:
                    offsets.append((start, i))
                    start = None
            elif start is None:
                start = i
        if start is not None:
            offsets.append((start, len(text)))
        enc = {"input_ids": list(range(len(offsets)))}
        if return_offsets_mapping:
            enc["offset_mapping"] = offsets
        return enc


class FakePipe:
    """Text-classification pipeline stub: scores 0.9 if MARKER is in the text, else 0.1."""

    def __init__(self):
        """Record every text the scanner asks to classify."""
        self.calls: list[str] = []
        self.tokenizer = FakeTokenizer()
        self.model = SimpleNamespace(config=SimpleNamespace(label2id={"SAFE": 0, "INJECTION": 1}))

    def __call__(self, text: str) -> list:
        """Return pipeline output in the top_k=None shape."""
        self.calls.append(text)
        score = 0.9 if MARKER in text else 0.1
        return [[{"label": "INJECTION", "score": score}, {"label": "SAFE", "score": 1 - score}]]


@pytest.fixture(name="pipe")
def fixture_pipe(monkeypatch: pytest.MonkeyPatch) -> FakePipe:
    """Replace transformers.pipeline with a FakePipe factory."""
    fake = FakePipe()
    monkeypatch.setattr(scanner_types, "pipeline", lambda *_args, **_kwargs: fake)
    return fake


def words(n: int, marker_at: int | None = None) -> str:
    """Build n space-separated tokens, optionally with MARKER at one position."""
    return " ".join(MARKER if i == marker_at else f"w{i}" for i in range(n))


def loaded(**kwargs) -> PromptInjectionScanner:
    """Build and load a scanner against the patched pipeline."""
    scanner = PromptInjectionScanner(**kwargs)
    scanner.load()
    return scanner


def test_full_scores_whole_text_in_one_call(pipe: FakePipe):
    text = words(50, marker_at=49)
    result = loaded(match_type="full", model_max_length=12).scan(text)
    assert pipe.calls == [text]
    assert not result.is_safe


def test_sentence_scores_each_sentence(pipe: FakePipe):
    result = loaded(match_type="sentence").scan("First one. Second TRIGGER here! Third?")
    assert pipe.calls == ["First one.", "Second TRIGGER here!", "Third?"]
    assert result.score == 0.9


def test_sliding_window_short_text_is_one_window(pipe: FakePipe):
    text = words(10)
    result = loaded(match_type="sliding_window", model_max_length=12, window_overlap=2).scan(text)
    assert pipe.calls == [text]
    assert result.is_safe


def test_sliding_window_windows_fit_model_and_overlap(pipe: FakePipe):
    span = 12 - SPECIAL_TOKENS
    loaded(match_type="sliding_window", model_max_length=12, window_overlap=3).scan(words(30))
    windows = [call.split() for call in pipe.calls]
    assert all(len(w) <= span for w in windows)
    for prev, nxt in pairwise(windows):
        assert prev[-3:] == nxt[:3]
    assert windows[0][0] == "w0"
    assert windows[-1][-1] == "w29"


def test_sliding_window_covers_every_token(pipe: FakePipe):
    loaded(match_type="sliding_window", model_max_length=12, window_overlap=3).scan(words(30))
    seen = {tok for call in pipe.calls for tok in call.split()}
    assert seen == set(words(30).split())


def test_sliding_window_takes_max_score_across_windows(pipe: FakePipe):
    result = loaded(match_type="sliding_window", model_max_length=12, window_overlap=3).scan(words(40, marker_at=39))
    assert len(pipe.calls) > 1
    assert MARKER not in pipe.calls[0]
    assert result.score == 0.9
    assert not result.is_safe


def test_sliding_window_preserves_original_text_between_tokens(pipe: FakePipe):
    text = "a  b\tc\nd e f g h i j k l m n"
    loaded(match_type="sliding_window", model_max_length=6, window_overlap=1).scan(text)
    assert pipe.calls[0] == "a  b\tc\nd"


def test_sliding_window_default_overlap_is_a_quarter_of_the_span(pipe: FakePipe):
    span = 18 - SPECIAL_TOKENS
    loaded(match_type="sliding_window", model_max_length=18).scan(words(40))
    first, second = (call.split() for call in pipe.calls[:2])
    assert first[-(span // 4) :] == second[: span // 4]
    assert first[-(span // 4) - 1] != second[0]


@pytest.mark.parametrize("overlap", [-1, 10, 11])
def test_sliding_window_rejects_overlap_outside_span(pipe: FakePipe, overlap: int):
    scanner = PromptInjectionScanner(match_type="sliding_window", model_max_length=12, window_overlap=overlap)
    with pytest.raises(ValueError, match="window_overlap"):
        scanner.load()
    assert pipe.calls == []
