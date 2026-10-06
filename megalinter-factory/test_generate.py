"""Tests for generate.py helpers."""

import shutil
from pathlib import Path

import pytest
import yaml

import generate
from generate import unique_by_package

FACTORY_DIR = Path(__file__).parent


def test_generate_files_composes_languages_into_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A flavor listing a language gets its linters, Dockerfile fragment and test checks."""
    factory = tmp_path / "factory"
    shutil.copytree(FACTORY_DIR / "templates", factory / "templates")
    (factory / "base.yaml").write_text(yaml.safe_dump({"linters": ["BASE_LINT"]}))
    (factory / "languages").mkdir()
    (factory / "languages" / "go.yaml").write_text(
        yaml.safe_dump(
            {
                "linters": ["GO_LINT"],
                "extra_dockerfile": "ENV GOTOOLCHAIN=local\n",
                "extra_test_linters": [{"name": "go", "version_command": "go version"}],
            }
        )
    )
    flavor_dir = tmp_path / "megalinter-go"
    flavor_dir.mkdir()
    (flavor_dir / "flavor.yaml").write_text(
        yaml.safe_dump({"name": "go", "upstream_image": "img:1", "languages": ["go"]})
    )
    script = {"type": "script", "version_command": "x --version", "dockerfile": []}
    monkeypatch.setattr(
        generate,
        "get_megalinter_linters",
        lambda: {
            "linters": {"BASE_LINT": script, "GO_LINT": script},
            "base_flavor_linters": {},
        },
    )

    generate.generate_files(flavor_dir, factory)

    dockerfile = (flavor_dir / "Dockerfile").read_text()
    assert "# - BASE_LINT, GO_LINT\n" in dockerfile
    assert "ENV GOTOOLCHAIN=local\n" in dockerfile
    assert 'check_linter "go" "go version"' in (flavor_dir / "test.sh").read_text()


def test_unique_by_package_drops_linters_sharing_a_package() -> None:
    """Linters backed by one package, like ruff and ruff-format, install it once."""
    linters = [
        {"name": "ruff", "package": "ruff"},
        {"name": "pylint", "package": "pylint"},
        {"name": "ruff", "package": "ruff"},
    ]

    assert [l["package"] for l in unique_by_package(linters)] == ["ruff", "pylint"]
