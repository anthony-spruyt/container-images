"""Tests that the scanner image carries no OpenVINO telemetry.

Importing openvino runs the OpenVINO converter package, which sends a usage event through openvino-telemetry when that
package is installed. The scanner makes no outside calls, so the package stays out of the environment.
Run from llm-tool-guard/app so the app modules import: python -m pytest ../tests
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROBE = """
import json, sys
import openvino as ov
from openvino import opset13 as ops

x = ops.parameter(ov.PartialShape([1]), ov.Type.f32, name="x")
ov.Core().compile_model(ov.Model([ops.relu(x)], [x], "tiny"), "CPU")
print(json.dumps({"telemetry_loaded": "openvino_telemetry" in sys.modules}))
"""


@pytest.fixture(name="probe")
def fixture_probe(tmp_path: Path) -> dict:
    """Import openvino and compile a model in a fresh interpreter with an empty home directory and no CI variable."""
    env = {"HOME": str(tmp_path), "PATH": os.environ["PATH"]}
    run = subprocess.run([sys.executable, "-I", "-c", PROBE], env=env, capture_output=True, text=True, check=True)
    return json.loads(run.stdout.splitlines()[-1])


def test_the_telemetry_package_is_not_installed():
    assert importlib.util.find_spec("openvino_telemetry") is None


def test_importing_openvino_and_compiling_a_model_loads_no_telemetry(probe: dict):
    assert probe["telemetry_loaded"] is False


@pytest.mark.usefixtures("probe")
def test_importing_openvino_and_compiling_a_model_leaves_no_telemetry_state_in_the_home_directory(tmp_path: Path):
    assert not (tmp_path / "intel").exists()
