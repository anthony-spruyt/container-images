"""Tests for generate.py helpers."""

import shutil
from pathlib import Path

import pytest
import yaml

import generate
from generate import flavor_dir_error, resolve_linters, unique_by_package

FACTORY_DIR = Path(__file__).parent


def test_generate_files_composes_languages_into_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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

    assert [linter["package"] for linter in unique_by_package(linters)] == ["ruff", "pylint"]


def test_flavor_fragment_sees_fields_derived_from_upstream_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """extra_dockerfile can use base_flavor and upstream_tag, as it could before composition."""
    factory = tmp_path / "factory"
    shutil.copytree(FACTORY_DIR / "templates", factory / "templates")
    (factory / "base.yaml").write_text(yaml.safe_dump({"linters": []}))
    (factory / "languages").mkdir()
    flavor_dir = tmp_path / "megalinter-x"
    flavor_dir.mkdir()
    (flavor_dir / "flavor.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "x",
                "upstream_image": "ghcr.io/oxsecurity/megalinter-go:v10.1.0@sha256:abc",
                "extra_dockerfile": ("LABEL base={{ flavor.base_flavor }} tag={{ flavor.upstream_tag }}\n"),
            }
        )
    )
    monkeypatch.setattr(generate, "get_megalinter_linters", lambda: {"linters": {}, "base_flavor_linters": {}})

    generate.generate_files(flavor_dir, factory)

    assert "LABEL base=go tag=v10.1.0\n" in (flavor_dir / "Dockerfile").read_text()


def test_resolve_linters_describes_base_and_custom_linters() -> None:
    """Base linters get test info; custom linters get the install fields for their type."""
    megalinter_data = {
        "linters": {
            "BASE_ONE": {"version_command": "one --version"},
            "BIN_LINT": {
                "type": "docker_binary",
                "version": "1.2",
                "version_command": "bin -v",
                "binary_path": "/src",
                "target_path": "/dst",
                "source_image": "org/bin",
                "apk_packages": ["libc"],
            },
            "NPM_LINT": {"type": "npm", "package": "lint-a", "version": "3"},
            "NPM_MULTI": {"type": "npm", "package": "a", "npm_packages": ["a", "b"]},
            "PIP_LINT": {"type": "pip", "package": "ruff", "version": "0.1", "description": "d"},
            "SCRIPT_LINT": {"type": "script", "dockerfile": ["RUN x"]},
            "APK_LINT": {"type": "apk", "apk_packages": ["tool"]},
        },
        "base_flavor_linters": {"go": ["BASE_ONE", "BASE_NO_INFO", "PIP_LINT"]},
    }
    flavor = {
        "base_flavor": "go",
        "custom_linters": ["BIN_LINT", "NPM_LINT", "NPM_MULTI", "PIP_LINT", "SCRIPT_LINT", "APK_LINT"],
    }

    all_linters, base, custom = resolve_linters(flavor, megalinter_data)

    assert all_linters == [
        "BASE_ONE",
        "BASE_NO_INFO",
        "PIP_LINT",
        "BIN_LINT",
        "NPM_LINT",
        "NPM_MULTI",
        "SCRIPT_LINT",
        "APK_LINT",
    ]
    assert base[1] == {"linter_key": "BASE_NO_INFO", "name": "info", "version_command": "info --version"}
    assert base[0]["name"] == "one"
    by_key = {linter["linter_key"]: linter for linter in custom}
    assert by_key["BIN_LINT"] == {
        "linter_key": "BIN_LINT",
        "name": "bin",
        "type": "docker_binary",
        "version": "1.2",
        "version_command": "bin -v",
        "description": "",
        "binary_path": "/src",
        "target_path": "/dst",
        "source_image": "org/bin",
        "digest": "",
        "image": "org/bin:1.2",
        "apk_packages": ["libc"],
    }
    assert by_key["NPM_LINT"]["npm_packages"] == ["lint-a"]
    assert by_key["NPM_MULTI"]["npm_packages"] == ["a", "b"]
    assert by_key["PIP_LINT"]["package"] == "ruff"
    assert by_key["PIP_LINT"]["description"] == "d"
    assert "npm_packages" not in by_key["PIP_LINT"]
    assert by_key["SCRIPT_LINT"]["dockerfile"] == ["RUN x"]
    assert by_key["SCRIPT_LINT"]["apk_packages"] == []
    assert by_key["APK_LINT"]["name"] == "lint"
    assert "package" not in by_key["APK_LINT"]


def test_resolve_linters_defaults_to_ci_light() -> None:
    """A flavor without base_flavor takes the ci_light base list."""
    data = {"linters": {}, "base_flavor_linters": {"ci_light": ["A_B"]}}

    assert resolve_linters({}, data)[0] == ["A_B"]


def test_resolve_linters_docker_binary_without_version_has_no_image() -> None:
    """The image reference needs both a source image and a version."""
    data = {"linters": {"BIN_LINT": {"type": "docker_binary", "source_image": "org/bin"}}, "base_flavor_linters": {}}

    custom = resolve_linters({"custom_linters": ["BIN_LINT"]}, data)[2]

    assert "image" not in custom[0]


def test_resolve_linters_rejects_an_unknown_custom_linter() -> None:
    """A custom linter MegaLinter does not know would silently drop out of the image."""
    with pytest.raises(ValueError, match="MISSING_LINT not found"):
        resolve_linters({"custom_linters": ["MISSING_LINT"]}, {"linters": {}, "base_flavor_linters": {}})


def test_flavor_dir_error_rejects_a_missing_directory(tmp_path: Path) -> None:
    """A path that is not a directory cannot hold a flavor."""
    assert flavor_dir_error(tmp_path / "absent") == f"{tmp_path / 'absent'} is not a directory"


def test_flavor_dir_error_rejects_a_directory_without_flavor_yaml(tmp_path: Path) -> None:
    """A flavor directory needs a flavor.yaml."""
    assert flavor_dir_error(tmp_path) == f"{tmp_path / 'flavor.yaml'} not found"


def test_flavor_dir_error_accepts_a_flavor_directory(tmp_path: Path) -> None:
    """A directory with flavor.yaml passes."""
    (tmp_path / "flavor.yaml").write_text("name: x\n")
    assert flavor_dir_error(tmp_path) is None


def test_main_fails_without_flavor_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    """main reports the flavor directory problem and exits non-zero."""
    monkeypatch.setattr("sys.argv", ["generate.py", str(tmp_path)])
    assert generate.main() == 1
    assert "flavor.yaml not found" in capsys.readouterr().err
