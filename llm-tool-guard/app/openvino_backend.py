"""Scores token windows on the OpenVINO classifier that the llm-tool-guard-model image carries."""

import hashlib
import logging
import os
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import openvino as ov
from huggingface_hub import try_to_load_from_cache
from transformers import AutoConfig, AutoTokenizer

logger = logging.getLogger(__name__)

_IR_FILE = "openvino_model.xml"
_INPUTS = ("input_ids", "attention_mask")


def compile_options(device: str) -> dict[str, str]:
    """Return the compile properties for device: the LATENCY hint, with f16 on a GPU and f32 anywhere else."""
    precision = "f16" if device.split(".")[0] == "GPU" else "f32"
    return {"PERFORMANCE_HINT": "LATENCY", "INFERENCE_PRECISION_HINT": precision}


def ir_digest(xml: Path) -> str:
    """Return a digest of the model file and the weights beside it."""
    combined = hashlib.sha256()
    for path in (xml, xml.with_suffix(".bin")):
        with path.open("rb") as stream:
            combined.update(hashlib.file_digest(stream, "sha256").digest())
    return combined.hexdigest()


def _softmax(logits: np.ndarray) -> np.ndarray:
    exponents = np.exp(logits - logits.max())
    return exponents / exponents.sum()


class OpenVinoPipeline:
    """The part of a transformers text-classification pipeline the scanner uses, over a compiled OpenVINO model."""

    def __init__(self, tokenizer: Any, config: Any, request: Any, *, max_length: int, fingerprint: Mapping[str, str]):
        """Wrap an inference request of the model; fingerprint names what shapes its scores."""
        self.tokenizer = tokenizer
        self.model = SimpleNamespace(config=config)
        self.fingerprint = dict(fingerprint)
        self._request = request
        self._max_length = max_length
        self._lock = threading.Lock()

    def forward(self, batch: Mapping[str, Any]) -> dict[str, np.ndarray]:
        """Return the logits of a batch of one window; OpenVINO scores padded rows as NaN, which raises."""
        inputs = {name: np.asarray(batch[name], dtype=np.int64) for name in _INPUTS}
        with self._lock:
            logits = np.array(self._request.infer(inputs)[0], dtype=np.float32)
        if not np.isfinite(logits).all():
            raise ValueError("the model returned logits that are not finite")
        return {"logits": logits}

    def postprocess(self, outputs: Mapping[str, np.ndarray]) -> list[dict[str, Any]]:
        """Return the score of every label for the first row of logits."""
        scores = _softmax(np.asarray(outputs["logits"][0], dtype=np.float32))
        return [{"label": self.model.config.id2label[i], "score": score.item()} for i, score in enumerate(scores)]

    def __call__(self, text: str) -> list[dict[str, Any]]:
        """Return the score of every label for text cut to max_length tokens."""
        encoded = self.tokenizer(text, truncation=True, max_length=self._max_length, return_tensors="np")
        return self.postprocess(self.forward(encoded))


def load_pipeline(
    model: str,
    device: str,
    *,
    max_length: int,
    locate: Callable[[str, str], Any] = try_to_load_from_cache,
    environ: Mapping[str, str] = os.environ,
) -> OpenVinoPipeline:
    """Compile the cached model on device; a device OpenVINO does not list fails the load, with no fallback."""
    path = locate(model, _IR_FILE)
    if not isinstance(path, str):
        raise FileNotFoundError(
            f"{_IR_FILE} of {model} is not in the Hugging Face cache; mount the llm-tool-guard-model image there"
        )
    xml = Path(path)
    options = compile_options(device)
    logger.info("compiling %s on %s in %s", xml.name, device, options["INFERENCE_PRECISION_HINT"])
    compiled = ov.Core().compile_model(str(xml), device, options)
    return OpenVinoPipeline(
        AutoTokenizer.from_pretrained(str(xml.parent)),
        AutoConfig.from_pretrained(str(xml.parent)),
        compiled.create_infer_request(),
        max_length=max_length,
        fingerprint={
            "device": device,
            "precision": options["INFERENCE_PRECISION_HINT"],
            "ir": ir_digest(xml),
            "gpu_runtime": environ.get("INTEL_GPU_RUNTIME", ""),
        },
    )
