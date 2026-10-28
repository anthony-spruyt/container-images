"""Tests for the character spans the sliding-window scanner reports for the windows it flagged.

The service asks Jev about exactly these slices of the scanned text, so each span must cover the text of its window.
Run from llm-tool-guard/app so the app modules import: python -m pytest ../tests
"""

import math
from types import SimpleNamespace

import pytest
import torch
from tokenizers import Tokenizer, models, pre_tokenizers, processors
from transformers import PreTrainedTokenizerFast

import scanner_types
from scanner_types import PromptInjectionScanner

MARKER = "TRIGGER"
LABELS = {0: "SAFE", 1: "INJECTION"}
MAX_LENGTH = 12
OVERLAP = 3
WINDOW_WORDS = MAX_LENGTH - 2
STEP = WINDOW_WORDS - OVERLAP


def word_tokenizer() -> PreTrainedTokenizerFast:
    """Build an offline whitespace word-level fast tokenizer that wraps input in [CLS] ... [SEP]."""
    vocab = {tok: i for i, tok in enumerate(["[PAD]", "[UNK]", "[CLS]", "[SEP]", MARKER])}
    vocab.update({f"w{i}": len(vocab) + i for i in range(500)})
    backend = Tokenizer(models.WordLevel(vocab, unk_token="[UNK]"))
    backend.pre_tokenizer = pre_tokenizers.WhitespaceSplit()
    backend.post_processor = processors.TemplateProcessing(
        single="[CLS] $A [SEP]", special_tokens=[("[CLS]", vocab["[CLS]"]), ("[SEP]", vocab["[SEP]"])]
    )
    return PreTrainedTokenizerFast(
        tokenizer_object=backend, pad_token="[PAD]", unk_token="[UNK]", cls_token="[CLS]", sep_token="[SEP]"
    )


class MarkerPipe:
    """Pipeline stub over a real tokenizer: a window holding MARKER scores 0.95, any other window 0.05."""

    def __init__(self, tokenizer):
        """Wrap tokenizer."""
        self.tokenizer = tokenizer
        self.model = SimpleNamespace(
            config=SimpleNamespace(label2id={v: k for k, v in LABELS.items()}, id2label=LABELS)
        )
        self._marker_id = tokenizer.backend_tokenizer.token_to_id(MARKER)

    def __call__(self, text: str) -> list:
        """Score text as one input, the way the pipeline does for the full and sentence match types."""
        row = self.tokenizer(text)["input_ids"]
        return [self.postprocess(self.forward({"input_ids": torch.tensor([row])}), top_k=None)]

    def forward(self, model_inputs: dict) -> dict:
        """Score each row of a padded batch."""
        rows = model_inputs["input_ids"].tolist()
        high, low = [0.0, math.log(19)], [math.log(19), 0.0]
        return {"logits": torch.tensor([high if self._marker_id in row else low for row in rows])}

    def postprocess(self, model_outputs: dict, top_k=1) -> list:
        """Softmax the first row of logits into per-label scores."""
        assert top_k is None
        scores = torch.softmax(model_outputs["logits"][0], -1).tolist()
        return [{"label": LABELS[i], "score": s} for i, s in enumerate(scores)]


@pytest.fixture(autouse=True)
def pipes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Build every scanner over the offline tokenizer and MarkerPipe."""
    tokenizer = word_tokenizer()
    monkeypatch.setattr(scanner_types, "pipeline", lambda *_args, **_kwargs: MarkerPipe(tokenizer))


def words(n: int, marker_at: tuple[int, ...] = ()) -> str:
    return " ".join(MARKER if i in marker_at else f"w{i}" for i in range(n))


def scanner(**kwargs) -> PromptInjectionScanner:
    settings = {
        "match_type": "sliding_window",
        "model_max_length": MAX_LENGTH,
        "window_overlap": OVERLAP,
        "threshold": 0.9,
    }
    loaded = PromptInjectionScanner(**{**settings, **kwargs})
    loaded.load()
    return loaded


def marker_score() -> float:
    """Return the raw score MarkerPipe gives a window holding MARKER."""
    pipe = MarkerPipe(word_tokenizer())
    logits = pipe.forward({"input_ids": torch.tensor([[pipe._marker_id]])})
    return pipe.postprocess(logits, top_k=None)[1]["score"]


def window_text(text: str, first: int, last: int) -> str:
    """Return the words first..last (inclusive) of text, as the one-space-separated slice a window covers."""
    return " ".join(text.split(" ")[first : last + 1])


def test_a_flagged_window_is_reported_as_the_slice_of_text_it_covers():
    text = words(40, marker_at=(35,))

    result = scanner().scan(text)

    assert [text[start:end] for start, end in result.flagged_spans] == [
        window_text(text, 28, 37),
        window_text(text, 35, 39),
    ]


def test_every_window_holding_the_marker_is_reported_and_no_other():
    text = words(40, marker_at=(8,))

    result = scanner().scan(text)

    assert [text[start:end] for start, end in result.flagged_spans] == [
        window_text(text, 0, 9),
        window_text(text, 7, 16),
    ]
    assert not result.is_safe
    assert result.score == 0.95


def test_windows_far_apart_are_reported_in_text_order():
    text = words(60, marker_at=(2, 57))

    result = scanner().scan(text)

    covered = [text[start:end] for start, end in result.flagged_spans]
    assert covered[0].startswith("w0 ")
    assert covered[-1].endswith("w59")
    assert len(covered) == 3
    assert list(result.flagged_spans) == sorted(result.flagged_spans)


def test_a_window_scoring_exactly_the_threshold_is_flagged_and_one_just_below_it_is_not():
    text = words(10, marker_at=(3,))

    at = scanner(threshold=marker_score()).scan(text)
    above = scanner(threshold=math.nextafter(marker_score(), 1)).scan(text)

    assert (at.is_safe, len(at.flagged_spans)) == (False, 1)
    assert (above.is_safe, above.flagged_spans) == (True, ())


def test_a_clean_text_reports_no_spans():
    result = scanner().scan(words(40))

    assert result.is_safe
    assert result.flagged_spans == ()


def test_spans_do_not_depend_on_how_many_windows_are_scored_per_model_call():
    text = words(60, marker_at=(20, 45))

    assert scanner(window_batch_size=4).scan(text).flagged_spans == scanner().scan(text).flagged_spans


def test_a_text_over_max_windows_is_flagged_without_spans():
    result = scanner(max_windows=2).scan(words(40, marker_at=(8,)))

    assert not result.is_safe
    assert result.score == 1.0
    assert result.flagged_spans == ()


@pytest.mark.parametrize("match_type", ["full", "sentence"])
def test_the_other_match_types_report_no_spans(match_type):
    other = PromptInjectionScanner(match_type=match_type, threshold=0.9)
    other.load()

    result = other.scan(f"{MARKER} here")

    assert not result.is_safe
    assert result.flagged_spans == ()


def test_spans_count_characters_not_bytes():
    text = f"\U0001f600 é \U0001f600 {MARKER}"

    (start, end), *rest = scanner().scan(text).flagged_spans

    assert (start, end, rest) == (0, len(text), [])
    assert text[start:end] == text
