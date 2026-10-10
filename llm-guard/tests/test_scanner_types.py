"""Tests for the PromptInjection scanner's match types.

Run from llm-guard/app so the app modules import: python -m pytest ../tests

The Horizon tests download only the model's tokenizer files. They skip when the
Hub is unreachable unless LLM_GUARD_TESTS_REQUIRE_HUB is set, as test.sh does.
"""

import logging
import math
import os
import random
from itertools import pairwise
from types import SimpleNamespace

import pytest
import torch
from tokenizers import Tokenizer, models, pre_tokenizers, processors
from transformers import (
    AutoTokenizer,
    ModernBertConfig,
    ModernBertForSequenceClassification,
    PreTrainedTokenizerFast,
    pipeline,
)

import scanner_types
from scanner_types import PromptInjectionScanner

MARKER = "TRIGGER"
HORIZON = "Horizon-Labs/prompt-injection-guard-base"
LABELS = {0: "SAFE", 1: "INJECTION"}
SPECIAL_TOKENS = 2


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


class RecordingPipe:
    """
    Text-classification pipeline stub over a real tokenizer.

    Records every model input row as the model receives it, and scores 0.9 when
    the MARKER token is among the scored ids, else 0.1.
    """

    def __init__(self, tokenizer, max_length: int, max_position_embeddings: int | None = None):
        """Wrap tokenizer; max_length is the pipeline's truncation length."""
        self.tokenizer = tokenizer
        self.max_length = max_length
        label2id = {v: k for k, v in LABELS.items()}
        cfg = SimpleNamespace(label2id=label2id, id2label=LABELS)
        if max_position_embeddings is not None:
            cfg.max_position_embeddings = max_position_embeddings
        self.model = SimpleNamespace(config=cfg)
        self.texts: list[str] = []
        self.rows: list[list[int]] = []
        self.batch_sizes: list[int] = []
        self._marker_id = tokenizer.backend_tokenizer.token_to_id(MARKER)

    def _logits(self, ids: list[int]) -> list[float]:
        return [0.0, math.log(9)] if self._marker_id in ids else [math.log(9), 0.0]

    def __call__(self, text: str) -> list:
        """Score text the way the real pipeline does: truncated to max_length."""
        self.texts.append(text)
        self.rows.append(self.tokenizer(text)["input_ids"])
        ids = self.tokenizer(text, truncation=True, max_length=self.max_length)["input_ids"]
        return [self.postprocess({"logits": torch.tensor([self._logits(ids)])}, top_k=None)]

    def forward(self, model_inputs: dict) -> dict:
        """Score a padded batch of token-ID rows."""
        ids, masks = model_inputs["input_ids"].tolist(), model_inputs["attention_mask"].tolist()
        rows = [[i for i, keep in zip(row, mask, strict=True) if keep] for row, mask in zip(ids, masks, strict=True)]
        self.rows.extend(rows)
        self.batch_sizes.append(len(rows))
        return {"logits": torch.tensor([self._logits(row) for row in rows])}

    def postprocess(self, model_outputs: dict, top_k=1) -> list:
        """Softmax the first row of logits into per-label scores."""
        assert top_k is None
        scores = torch.softmax(model_outputs["logits"][0], -1).tolist()
        return [{"label": LABELS[i], "score": s} for i, s in enumerate(scores)]


class BrokenOverflowTokenizer:
    """Fast-tokenizer proxy whose overflow windows break the stride contract, as tokenizers 0.23.1-0.23.2 do."""

    def __init__(self, tokenizer, mode: str):
        """Wrap tokenizer; mode is "stops_at_max_length", "ignores_stride" or "drops_last_window"."""
        self._tokenizer = tokenizer
        self._mode = mode

    def __getattr__(self, name: str):
        """Delegate everything else to the wrapped tokenizer."""
        return getattr(self._tokenizer, name)

    def __call__(self, text: str, **kwargs):
        """Tokenize text, breaking the overflow windows when asked for them."""
        if not kwargs.get("return_overflowing_tokens"):
            return self._tokenizer(text, **kwargs)
        if self._mode == "stops_at_max_length":
            return self._tokenizer(" ".join(text.split()[: kwargs["max_length"]]), **kwargs)
        if self._mode == "ignores_stride":
            return self._tokenizer(text, **{**kwargs, "stride": 0})
        enc = self._tokenizer(text, **kwargs)
        for key in list(enc.keys()):
            enc[key] = enc[key][:-1]
        return enc


def use_pipe(monkeypatch: pytest.MonkeyPatch, tokenizer, max_position_embeddings: int | None = None) -> list:
    """Patch transformers.pipeline to build RecordingPipes over tokenizer; return the pipes it built."""
    built = []

    def factory(*_args, max_length: int, **_kwargs) -> RecordingPipe:
        built.append(RecordingPipe(tokenizer, max_length, max_position_embeddings))
        return built[-1]

    monkeypatch.setattr(scanner_types, "pipeline", factory)
    return built


@pytest.fixture(name="pipes")
def fixture_pipes(monkeypatch: pytest.MonkeyPatch) -> list:
    """Patch transformers.pipeline with the offline word tokenizer."""
    return use_pipe(monkeypatch, word_tokenizer())


@pytest.fixture(scope="session", name="horizon_tokenizer")
def fixture_horizon_tokenizer():
    """Load the real Horizon tokenizer (tokenizer files only, no weights)."""
    try:
        return AutoTokenizer.from_pretrained(HORIZON)
    except OSError as exc:
        if os.environ.get("LLM_GUARD_TESTS_REQUIRE_HUB"):
            raise
        pytest.skip(f"{HORIZON} tokenizer unavailable: {exc}")


@pytest.fixture(name="horizon_pipes")
def fixture_horizon_pipes(monkeypatch: pytest.MonkeyPatch, horizon_tokenizer) -> list:
    """Patch transformers.pipeline with the Horizon tokenizer."""
    return use_pipe(monkeypatch, horizon_tokenizer)


def words(n: int, marker_at: int | None = None) -> str:
    """Build n space-separated tokens, optionally with MARKER at one position."""
    return " ".join(MARKER if i == marker_at else f"w{i}" for i in range(n))


def loaded(**kwargs) -> PromptInjectionScanner:
    """Build and load a scanner against the patched pipeline."""
    scanner = PromptInjectionScanner(**kwargs)
    scanner.load()
    return scanner


def content(tokenizer, row: list[int]) -> list[int]:
    """Strip special tokens from a model input row."""
    special = set(tokenizer.all_special_ids)
    return [i for i in row if i not in special]


def assert_windows_cover(full: list[int], windows: list[list[int]]):
    """Assert each window is a contiguous slice of full, in order, with no gap between them and none at either end."""
    covered = 0
    for window in windows:
        starts = [s for s in range(max(0, covered - len(window)), covered + 1) if full[s : s + len(window)] == window]
        assert starts, f"window does not continue the input at token {covered}"
        covered = max(covered, starts[-1] + len(window))
    assert covered == len(full), f"windows end at token {covered} of {len(full)}"


def random_text(rng: random.Random) -> str:
    """Build text mixing scripts, punctuation, emoji, Unicode tag characters and irregular whitespace."""
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJ0123456789éüñßøçあいうえお漢字中文한국어Жизнь😀🚀"
    pieces = []
    for _ in range(rng.randint(0, 400)):
        word = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 14)))
        if rng.random() < 0.05:
            word += "".join(chr(0xE0000 + ord(c)) for c in "hidden")
        pieces.append(word + rng.choice([" ", " ", " ", "  ", "\n", "\t", ", ", ". ", "-", "/", ""]))
    return "".join(pieces)


def test_full_scores_whole_text_in_one_call(pipes: list):
    text = words(50, marker_at=5)
    result = loaded(match_type="full", model_max_length=12).scan(text)
    assert pipes[0].texts == [text]
    assert not result.is_safe


def test_sentence_scores_each_sentence(pipes: list):
    result = loaded(match_type="sentence").scan("First one. Second TRIGGER here! Third?")
    assert pipes[0].texts == ["First one.", "Second TRIGGER here!", "Third?"]
    assert result.score == 0.9


def test_sliding_window_short_text_is_one_window(pipes: list):
    result = loaded(match_type="sliding_window", model_max_length=12, window_overlap=2).scan(words(10))
    assert pipes[0].rows == [pipes[0].tokenizer(words(10))["input_ids"]]
    assert result.is_safe


def test_sliding_window_windows_fit_model_and_overlap(pipes: list):
    span = 12 - SPECIAL_TOKENS
    loaded(match_type="sliding_window", model_max_length=12, window_overlap=3).scan(words(30))
    tok = pipes[0].tokenizer
    windows = [tok.convert_ids_to_tokens(content(tok, row)) for row in pipes[0].rows]
    assert all(len(row) <= 12 for row in pipes[0].rows)
    assert all(len(w) <= span for w in windows)
    for prev, nxt in pairwise(windows):
        assert prev[-3:] == nxt[:3]
    assert windows[0][0] == "w0"
    assert windows[-1][-1] == "w29"


def test_sliding_window_covers_every_token(pipes: list):
    loaded(match_type="sliding_window", model_max_length=12, window_overlap=3).scan(words(30))
    tok = pipes[0].tokenizer
    full = tok(words(30), add_special_tokens=False)["input_ids"]
    assert_windows_cover(full, [content(tok, row) for row in pipes[0].rows])


def test_sliding_window_takes_max_score_across_windows(pipes: list):
    result = loaded(match_type="sliding_window", model_max_length=12, window_overlap=3).scan(words(40, marker_at=39))
    tok = pipes[0].tokenizer
    assert len(pipes[0].rows) > 1
    assert MARKER not in tok.convert_ids_to_tokens(pipes[0].rows[0])
    assert result.score == 0.9
    assert not result.is_safe


def test_sliding_window_default_overlap_is_a_quarter_of_the_span(pipes: list):
    span = 18 - SPECIAL_TOKENS
    loaded(match_type="sliding_window", model_max_length=18).scan(words(40))
    tok = pipes[0].tokenizer
    first, second = (content(tok, row) for row in pipes[0].rows[:2])
    assert first[-(span // 4) :] == second[: span // 4]
    assert first[-(span // 4) - 1] != second[0]


@pytest.mark.parametrize("overlap", [-1, 10, 11])
def test_sliding_window_rejects_overlap_outside_span(pipes: list, overlap: int):
    scanner = PromptInjectionScanner(match_type="sliding_window", model_max_length=12, window_overlap=overlap)
    with pytest.raises(ValueError, match="window_overlap"):
        scanner.load()
    assert not pipes or pipes[0].rows == []


@pytest.mark.parametrize(
    ("param", "value"),
    [
        ("window_overlap", 2.5),
        ("window_overlap", "3"),
        ("window_overlap", True),
        ("model_max_length", 12.0),
        ("model_max_length", "12"),
        ("model_max_length", SPECIAL_TOKENS),
        ("window_batch_size", 0),
        ("window_batch_size", 1.5),
        ("max_windows", 0),
        ("max_windows", "64"),
    ],
)
def test_sliding_window_rejects_bad_window_params_at_load(pipes: list, param: str, value):
    kwargs = {"match_type": "sliding_window", "model_max_length": 12, "window_overlap": 2, param: value}
    scanner = PromptInjectionScanner(**kwargs)
    with pytest.raises(ValueError, match=param):
        scanner.load()


def test_sliding_window_requires_fast_tokenizer(monkeypatch: pytest.MonkeyPatch):
    slow = SimpleNamespace(is_fast=False, num_special_tokens_to_add=lambda pair=False: SPECIAL_TOKENS)
    pipe = SimpleNamespace(tokenizer=slow, model=SimpleNamespace(config=SimpleNamespace(label2id={"INJECTION": 1})))
    monkeypatch.setattr(scanner_types, "pipeline", lambda *_args, **_kwargs: pipe)
    scanner = PromptInjectionScanner(match_type="sliding_window", model_max_length=12)
    with pytest.raises(ValueError, match="fast tokenizer"):
        scanner.load()


@pytest.mark.parametrize(
    ("mode", "overlap"),
    [
        ("stops_at_max_length", 0),
        ("stops_at_max_length", 3),
        ("stops_at_max_length", 9),
        ("ignores_stride", 3),
        ("ignores_stride", 9),
        ("drops_last_window", 0),
        ("drops_last_window", 3),
        ("drops_last_window", 9),
    ],
)
def test_sliding_window_load_rejects_tokenizer_with_broken_overflow_windows(
    monkeypatch: pytest.MonkeyPatch, mode: str, overlap: int
):
    use_pipe(monkeypatch, BrokenOverflowTokenizer(word_tokenizer(), mode))
    scanner = PromptInjectionScanner(match_type="sliding_window", model_max_length=12, window_overlap=overlap)
    with pytest.raises(RuntimeError, match="overflow windows"):
        scanner.load()


@pytest.mark.parametrize("overlap", [0, 1, 9])
def test_sliding_window_load_accepts_tokenizer_with_correct_overflow_windows(pipes: list, overlap: int):
    loaded(match_type="sliding_window", model_max_length=12, window_overlap=overlap)
    assert pipes[0].rows == []


@pytest.mark.parametrize("match_type", ["full", "sentence", "sliding_window"])
@pytest.mark.parametrize("limit_from", ["max_position_embeddings", "tokenizer"])
def test_load_rejects_model_max_length_over_the_model_limit(
    monkeypatch: pytest.MonkeyPatch, match_type: str, limit_from: str
):
    tok = word_tokenizer()
    if limit_from == "tokenizer":
        tok.model_max_length = 16
        use_pipe(monkeypatch, tok)
    else:
        use_pipe(monkeypatch, tok, max_position_embeddings=16)
    loaded(match_type=match_type, model_max_length=16)
    scanner = PromptInjectionScanner(match_type=match_type, model_max_length=17)
    with pytest.raises(ValueError, match="model_max_length 17 exceeds the model limit of 16"):
        scanner.load()


def test_sliding_window_over_max_windows_is_blocked(pipes: list, caplog: pytest.LogCaptureFixture):
    scanner = loaded(match_type="sliding_window", model_max_length=12, window_overlap=2, max_windows=12)
    with caplog.at_level(logging.WARNING, logger="scanner_types"):
        result = scanner.scan(words(100))
    assert pipes[0].rows == []
    assert not result.is_safe
    assert result.score == 1.0
    assert "max_windows" in result.reason
    assert any("13 windows" in r.getMessage() for r in caplog.records)


def test_sliding_window_at_max_windows_scores_every_window(pipes: list):
    result = loaded(match_type="sliding_window", model_max_length=12, window_overlap=2, max_windows=13).scan(
        words(100, marker_at=99)
    )
    assert len(pipes[0].rows) == 13
    assert result.score == 0.9


def test_sliding_window_scores_in_batches(pipes: list):
    loaded(match_type="sliding_window", model_max_length=12, window_overlap=2, window_batch_size=4).scan(words(100))
    assert pipes[0].batch_sizes == [4, 4, 4, 1]


@pytest.mark.parametrize("batch_size", [2, 5, 13])
def test_sliding_window_batched_scores_match_unbatched_on_a_real_model(
    monkeypatch: pytest.MonkeyPatch, batch_size: int
):
    tok = word_tokenizer()
    torch.manual_seed(0)
    model = ModernBertForSequenceClassification(
        ModernBertConfig(
            vocab_size=len(tok),
            hidden_size=32,
            intermediate_size=64,
            num_hidden_layers=2,
            num_attention_heads=2,
            pad_token_id=tok.pad_token_id,
            cls_token_id=tok.cls_token_id,
            sep_token_id=tok.sep_token_id,
            bos_token_id=tok.cls_token_id,
            eos_token_id=tok.sep_token_id,
            num_labels=2,
            id2label=LABELS,
            label2id={v: k for k, v in LABELS.items()},
        )
    ).eval()
    monkeypatch.setattr(
        scanner_types, "pipeline", lambda task, **kwargs: pipeline(task, **{**kwargs, "model": model, "tokenizer": tok})
    )
    text = " ".join(f"w{(i * 7) % 500}" for i in range(97))

    def score(size: int) -> float:
        scanner = loaded(match_type="sliding_window", model_max_length=12, window_overlap=2, window_batch_size=size)
        return scanner.scan(text).score

    assert score(batch_size) == pytest.approx(score(1), abs=1e-4)


def test_horizon_input_exactly_one_window(horizon_pipes: list, horizon_tokenizer):
    text = "Summarise the attached report and list the open action items for the team."
    full = horizon_tokenizer(text, add_special_tokens=False)["input_ids"]
    loaded(match_type="sliding_window", model_max_length=len(full) + SPECIAL_TOKENS, window_overlap=0).scan(text)
    assert horizon_pipes[0].rows == [horizon_tokenizer(text)["input_ids"]]


def test_horizon_input_one_token_over_one_window(horizon_pipes: list, horizon_tokenizer):
    text = "Summarise the attached report and list the open action items for the team."
    full = horizon_tokenizer(text, add_special_tokens=False)["input_ids"]
    max_length = len(full) + SPECIAL_TOKENS - 1
    loaded(match_type="sliding_window", model_max_length=max_length, window_overlap=0).scan(text)
    rows = horizon_pipes[0].rows
    assert len(rows) == 2
    assert all(len(row) <= max_length for row in rows)
    assert_windows_cover(full, [content(horizon_tokenizer, row) for row in rows])


def test_horizon_empty_input_is_one_window(horizon_pipes: list, horizon_tokenizer):
    result = loaded(match_type="sliding_window", model_max_length=16).scan("")
    assert horizon_pipes[0].rows == [horizon_tokenizer("")["input_ids"]]
    assert result.is_safe


def test_horizon_last_window_full_length_starting_mid_word(horizon_pipes: list, horizon_tokenizer):
    text = random_text(random.Random(7))
    full = horizon_tokenizer(text, add_special_tokens=False)["input_ids"]
    tokens = horizon_tokenizer.convert_ids_to_tokens(full)
    overlap = 3
    span = next(
        s for s in range(8, 64) if (len(full) - s) % (s - overlap) == 0 and not tokens[len(full) - s].startswith("▁")
    )
    max_length = span + SPECIAL_TOKENS
    scanner = loaded(
        match_type="sliding_window", model_max_length=max_length, window_overlap=overlap, max_windows=10_000
    )
    scanner.scan(text)
    rows = horizon_pipes[0].rows
    assert len(rows[-1]) == max_length
    assert content(horizon_tokenizer, rows[-1]) == full[-span:]
    assert all(len(row) <= max_length for row in rows)
    assert_windows_cover(full, [content(horizon_tokenizer, row) for row in rows])


@pytest.mark.parametrize("seed", range(40))
def test_horizon_overlap_zero_covers_every_token(horizon_pipes: list, horizon_tokenizer, seed: int):
    text = random_text(random.Random(seed))
    loaded(match_type="sliding_window", model_max_length=24, window_overlap=0, max_windows=10_000).scan(text)
    full = horizon_tokenizer(text, add_special_tokens=False)["input_ids"]
    assert all(len(row) <= 24 for row in horizon_pipes[0].rows)
    assert_windows_cover(full, [content(horizon_tokenizer, row) for row in horizon_pipes[0].rows])


def test_horizon_windows_cover_every_token_and_fit_the_model(monkeypatch: pytest.MonkeyPatch, horizon_tokenizer):
    rng = random.Random(1234)
    for _ in range(200):
        pipes = use_pipe(monkeypatch, horizon_tokenizer)
        text = random_text(rng)
        max_length = rng.randint(SPECIAL_TOKENS + 2, 80)
        overlap = rng.randint(0, max_length - SPECIAL_TOKENS - 1)
        loaded(
            match_type="sliding_window",
            model_max_length=max_length,
            window_overlap=overlap,
            window_batch_size=rng.randint(1, 9),
            max_windows=10_000,
        ).scan(text)
        full = horizon_tokenizer(text, add_special_tokens=False)["input_ids"]
        assert all(len(row) <= max_length for row in pipes[0].rows), (text, max_length, overlap)
        assert_windows_cover(full, [content(horizon_tokenizer, row) for row in pipes[0].rows])
