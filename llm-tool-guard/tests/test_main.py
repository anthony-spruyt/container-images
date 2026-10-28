"""Tests for what the service wires together at startup.

Run from llm-tool-guard/app so the app modules import: python -m pytest ../tests
"""

from types import SimpleNamespace

import main


def test_the_runtime_fingerprint_covers_the_backend_source_the_libraries_and_the_loaded_model():
    scanner = SimpleNamespace(fingerprint=lambda: {"device": "GPU", "ir": "abc"})

    runtime = main.runtime_of(scanner)

    assert {"scanner_types.py", "classifier.py", "openvino_backend.py", "openvino"} <= runtime.keys()
    assert (runtime["device"], runtime["ir"]) == ("GPU", "abc")
