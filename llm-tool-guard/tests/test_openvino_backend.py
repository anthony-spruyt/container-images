"""Tests for the OpenVINO pipeline that scores windows on the compiled model.

A tiny model stands in for the classifier: its logits are [number of attended tokens, sum of attended token ids].
Run from llm-tool-guard/app so the app modules import: python -m pytest ../tests
"""

import asyncio
import json
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import numpy as np
import openvino as ov
import pytest
from openvino import opset13 as ops

import openvino_backend
import scanner_types
from cache import VerdictCache
from classifier import Classifier
from fakes import digest, sample, word_tokenizer
from guard import ToolGuard
from openvino_backend import OpenVinoPipeline, compile_options, ir_digest, load_pipeline
from scanner_types import PromptInjectionScanner

MODEL = "org/model"
LABELS = {"0": "SAFE", "1": "INJECTION"}
DRIVER = "compute-runtime-1.2.3"


def write_ir(directory, *, bias: float = 0.0) -> None:
    """Save a model whose logits are [attended tokens, sum of attended ids + bias]."""
    ids = ops.parameter(ov.PartialShape([-1, -1]), ov.Type.i64, name="input_ids")
    mask = ops.parameter(ov.PartialShape([-1, -1]), ov.Type.i64, name="attention_mask")
    ids_f, mask_f = ops.convert(ids, "f32"), ops.convert(mask, "f32")
    axis = ops.constant(np.array([1], dtype=np.int64))
    attended = ops.reduce_sum(mask_f, axis, keep_dims=True)
    total = ops.add(ops.reduce_sum(ops.multiply(ids_f, mask_f), axis, keep_dims=True), ops.constant(bias, np.float32))
    logits = ops.concat([attended, total], 1)
    model = ov.Model([logits], [ids, mask], "tiny")
    ov.save_model(model, str(directory / "openvino_model.xml"), compress_to_fp16=False)


CONFIG = SimpleNamespace(id2label={0: "SAFE", 1: "INJECTION"})


class RecordingRequest:
    """Stands in for an inference request: records the shape of each input and answers with fixed logits."""

    def __init__(self, logits):
        """Answer every call with logits."""
        self._logits = np.array(logits, dtype=np.float32)
        self.shapes: list[tuple] = []

    def infer(self, inputs: dict) -> dict:
        """Record the shape of input_ids."""
        self.shapes.append(inputs["input_ids"].shape)
        return {0: self._logits}


class SequenceRequest:
    """Stands in for an inference request: answers each call with the next of the given logits, then the last again."""

    def __init__(self, *answers):
        """Answer the calls in the order of answers."""
        self._answers = answers
        self._calls = 0

    def infer(self, inputs: dict) -> dict:
        """Return the next logits."""
        answer = self._answers[min(self._calls, len(self._answers) - 1)]
        self._calls += 1
        return {0: np.array(answer, dtype=np.float32)}


class OverlapProbe:
    """Stands in for an inference request and records the most calls running at once."""

    def __init__(self):
        """Start idle."""
        self._lock = threading.Lock()
        self.running = 0
        self.most = 0

    def infer(self, inputs: dict) -> dict:
        """Take a moment, as a real inference does."""
        with self._lock:
            self.running += 1
            self.most = max(self.most, self.running)
        time.sleep(0.005)
        with self._lock:
            self.running -= 1
        return {0: np.zeros((1, 2), dtype=np.float32)}


@pytest.fixture(name="snapshot")
def fixture_snapshot(tmp_path):
    """A model snapshot directory: config, tokenizer and the tiny OpenVINO model."""
    (tmp_path / "config.json").write_text(
        json.dumps({"model_type": "bert", "id2label": LABELS, "label2id": {v: int(k) for k, v in LABELS.items()}})
    )
    word_tokenizer().save_pretrained(tmp_path)
    write_ir(tmp_path)
    return tmp_path


def locate_in(snapshot):
    def lookup(model: str, filename: str):
        assert model == MODEL
        path = snapshot / filename
        return str(path) if path.exists() else None

    return lookup


def load(snapshot, device="CPU", **kwargs):
    return load_pipeline(MODEL, device, max_length=kwargs.pop("max_length", 12), locate=locate_in(snapshot), **kwargs)


def test_forward_feeds_both_inputs_to_the_model_and_returns_its_logits(snapshot):
    pipe = load(snapshot)

    out = pipe.forward({"input_ids": np.array([[5, 6, 7]]), "attention_mask": np.array([[1, 1, 0]])})

    assert out["logits"].dtype == np.float32
    assert out["logits"].tolist() == [[2.0, 11.0]]


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_forward_raises_on_logits_that_are_not_finite(bad):
    pipe = OpenVinoPipeline(word_tokenizer(), CONFIG, RecordingRequest([[0.0, bad]]), max_length=8, fingerprint={})
    batch = {"input_ids": np.array([[1, 2]]), "attention_mask": np.array([[1, 1]])}

    with pytest.raises(ValueError, match="not finite"):
        pipe.forward(batch)


def test_a_non_finite_score_in_a_later_window_flags_the_text_as_an_error(monkeypatch, metrics, valkey):
    request = SequenceRequest([[0.0, -9.0]], [[np.nan, np.nan]], [[0.0, -9.0]])
    pipe = OpenVinoPipeline(word_tokenizer(), CONFIG, request, max_length=12, fingerprint={})
    monkeypatch.setattr(scanner_types, "load_pipeline", lambda *_args, **_kwargs: pipe)
    scanner = PromptInjectionScanner(
        match_type="sliding_window", model_max_length=12, window_overlap=3, threshold=0.9, max_windows=8
    )
    classifier = Classifier(scanner, MODEL, locate=lambda *_args: None)
    classifier.load()
    cache = VerdictCache(valkey, namespace="ns", ttl_seconds=60, metrics=metrics)
    guard = ToolGuard(classifier, cache, metrics, max_text_bytes=1024, max_pending_scans=4, scan_workers=1)
    text = " ".join(f"w{i}" for i in range(30))

    judged = asyncio.run(guard.check([{"hash": digest(text), "text": text}], []))

    assert judged.flagged == [digest(text)]
    assert judged.scores == {}
    assert sample(metrics, "llm_tool_guard_scans_total", verdict="error") == 1
    assert sample(metrics, "llm_tool_guard_flagged_total", reason="error") == 1


def test_postprocess_scores_every_label_with_a_softmax_of_the_first_row(snapshot):
    pipe = load(snapshot)

    scores = pipe.postprocess({"logits": np.array([[0.0, math.log(19)]], dtype=np.float32)})

    assert {s["label"]: s["score"] for s in scores} == {"SAFE": pytest.approx(0.05), "INJECTION": pytest.approx(0.95)}


def test_postprocess_does_not_overflow_on_large_logits(snapshot):
    pipe = load(snapshot)

    scores = pipe.postprocess({"logits": np.array([[0.0, 1e4]], dtype=np.float32)})

    assert {s["label"]: s["score"] for s in scores} == {"SAFE": 0.0, "INJECTION": 1.0}


def test_calling_the_pipeline_scores_one_text_cut_to_max_length():
    request = RecordingRequest(logits=[[0.0, math.log(19)]])
    pipe = OpenVinoPipeline(word_tokenizer(), CONFIG, request, max_length=8, fingerprint={})

    scores = pipe(" ".join(f"w{i}" for i in range(30)))

    assert request.shapes == [(1, 8)]
    assert {s["label"]: s["score"] for s in scores} == {"SAFE": pytest.approx(0.05), "INJECTION": pytest.approx(0.95)}


def test_the_pipeline_exposes_the_tokenizer_and_the_model_config(snapshot):
    pipe = load(snapshot)

    assert pipe.tokenizer.is_fast
    assert pipe.model.config.id2label == {0: "SAFE", 1: "INJECTION"}


@pytest.mark.parametrize(("device", "precision"), [("CPU", "f32"), ("GPU", "f16"), ("GPU.1", "f16")])
def test_gpu_devices_run_in_f16_and_everything_else_in_f32(device, precision):
    assert compile_options(device) == {"PERFORMANCE_HINT": "LATENCY", "INFERENCE_PRECISION_HINT": precision}


def test_the_model_is_compiled_on_the_named_device_in_the_precision_for_it(snapshot):
    pipe = load(snapshot, "CPU")

    assert pipe.fingerprint["device"] == "CPU"
    assert pipe.fingerprint["precision"] == "f32"


@pytest.mark.parametrize(("device", "precision"), [("CPU", "f32"), ("GPU", "f16")])
def test_the_latency_hint_and_the_precision_for_the_device_reach_compile_model(
    snapshot, monkeypatch, device, precision
):
    compiles = []
    real = ov.Core()

    class SpyCore:
        def compile_model(self, model, device_name, config=None):
            compiles.append((device_name, config))
            return real.compile_model(model, "CPU")

    monkeypatch.setattr(openvino_backend, "ov", SimpleNamespace(Core=SpyCore))

    load(snapshot, device)

    assert [name for name, _ in compiles] == [device]
    assert compiles[0][1]["PERFORMANCE_HINT"] == "LATENCY"
    assert compiles[0][1]["INFERENCE_PRECISION_HINT"] == precision


def test_a_missing_device_fails_the_load_instead_of_falling_back(snapshot):
    with pytest.raises(RuntimeError, match="NO_SUCH_DEVICE"):
        load(snapshot, "NO_SUCH_DEVICE")


def test_a_cache_without_the_converted_model_names_the_model_and_the_file(tmp_path):
    with pytest.raises(FileNotFoundError, match=f"openvino_model.xml.*{MODEL}"):
        load(tmp_path)


def test_the_fingerprint_holds_the_device_precision_driver_and_model_digest(snapshot):
    fingerprint = load(snapshot, environ={"INTEL_GPU_RUNTIME": DRIVER}).fingerprint

    assert set(fingerprint) == {"device", "precision", "ir", "gpu_runtime"}
    assert fingerprint["gpu_runtime"] == DRIVER
    assert len(fingerprint["ir"]) == 64


def test_the_model_digest_changes_with_the_model_file_and_its_weights(snapshot):
    xml = snapshot / "openvino_model.xml"
    before = ir_digest(xml)

    write_ir(snapshot, bias=1.0)
    changed = ir_digest(xml)
    with (snapshot / "openvino_model.bin").open("ab") as weights:
        weights.write(b"\x00")

    assert len({before, changed, ir_digest(xml)}) == 3


def test_scans_on_different_threads_never_share_the_inference_request_at_once():
    probe = OverlapProbe()
    pipe = OpenVinoPipeline(word_tokenizer(), CONFIG, probe, max_length=8, fingerprint={})
    batch = {"input_ids": np.array([[1, 2]]), "attention_mask": np.array([[1, 1]])}

    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda _: pipe.forward(batch), range(40)))

    assert probe.most == 1
