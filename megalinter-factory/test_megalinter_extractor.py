"""Tests for megalinter_extractor descriptor parsing."""

import json
import time
from pathlib import Path

import pytest

from megalinter_extractor import (
    extract_base_flavor_linters,
    extract_linter_info,
    has_download_install_run,
    parse_dockerfile_instructions,
    strip_npm_version,
)

SHARED_PRETTIER = """---
linter_name: prettier
install:
  dockerfile:
    - |-
      ARG NPM_PRETTIER_VERSION=3.9.6
  npm:
    - prettier@${NPM_PRETTIER_VERSION}
"""

SHARED_ESLINT = """---
linter_name: eslint
cli_version_arg_name: --version
"""

SHARED_BIOME = """---
linter_name: biome
descriptor_flavors:
  - javascript
install:
  dockerfile:
    - |-
      ARG NPM_BIOME_VERSION=2.5.13
  npm:
    - "@biomejs/biome@${NPM_BIOME_VERSION}"
"""

JAVASCRIPT_DESCRIPTOR = """---
descriptor_id: JAVASCRIPT
descriptor_flavors:
  - ci_light
linters:
  - extends: eslint
    linter_name: eslint
    name: JAVASCRIPT_ES
    install:
      dockerfile:
        - |-
          ARG NPM_ESLINT_VERSION=9.40.0
          ARG NPM_MICROSOFT_ESLINT_FORMATTER_SARIF_VERSION=3.1.0
      npm:
        - eslint@${NPM_ESLINT_VERSION}
        - "@microsoft/eslint-formatter-sarif@${NPM_MICROSOFT_ESLINT_FORMATTER_SARIF_VERSION}"
  - extends: prettier
    linter_name: prettier
  - extends: biome
    linter_name: biome
"""

TYPESCRIPT_DESCRIPTOR = """---
descriptor_id: TYPESCRIPT
descriptor_flavors:
  - ci_light
linters:
  - extends: prettier
    linter_name: prettier
"""

PYTHON_DESCRIPTOR = """---
descriptor_id: PYTHON
linters:
  - linter_name: ruff
    name: PYTHON_RUFF
    install:
      dockerfile:
        - |-
          ARG PIP_RUFF_VERSION=0.16.5
      pip:
        - ruff==${PIP_RUFF_VERSION}
  - linter_name: ruff-format
    name: PYTHON_RUFF_FORMAT
    cli_executable: ruff
    install:
      dockerfile:
        - |-
          ARG PIP_RUFF_VERSION=0.16.5
      pip:
        - ruff==${PIP_RUFF_VERSION}
"""


# Mirrors upstream's generated manifest: the authoritative flavor -> linters map.
# REPOSITORY_BETTERLEAKS declares `all_flavors`, so upstream puts it in every flavor.
ALL_FLAVORS = {
    "ci_light": {
        "label": "Optimized for CI items",
        "descriptors": ["JAVASCRIPT"],
        "linters": ["JAVASCRIPT_PRETTIER", "REPOSITORY_BETTERLEAKS"],
    },
    "go": {
        "label": "Optimized for GO based projects",
        "descriptors": ["GO"],
        "linters": ["GO_GOLANGCI_LINT", "GO_REVIVE", "REPOSITORY_BETTERLEAKS"],
    },
    "javascript": {
        "label": "Optimized for JAVASCRIPT based projects",
        "descriptors": ["JAVASCRIPT"],
        "linters": ["JAVASCRIPT_BIOME", "JAVASCRIPT_PRETTIER", "REPOSITORY_BETTERLEAKS"],
    },
}


@pytest.fixture(name="descriptors_dir")
def descriptors_dir_fixture(tmp_path: Path) -> Path:
    """Build a minimal descriptors tree mirroring MegaLinter v10 layout."""
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "prettier.megalinter-linter.yml").write_text(SHARED_PRETTIER)
    (shared / "eslint.megalinter-linter.yml").write_text(SHARED_ESLINT)
    (shared / "biome.megalinter-linter.yml").write_text(SHARED_BIOME)
    (tmp_path / "javascript.megalinter-descriptor.yml").write_text(JAVASCRIPT_DESCRIPTOR)
    (tmp_path / "typescript.megalinter-descriptor.yml").write_text(TYPESCRIPT_DESCRIPTOR)
    (tmp_path / "python.megalinter-descriptor.yml").write_text(PYTHON_DESCRIPTOR)
    (tmp_path / "all_flavors.json").write_text(json.dumps(ALL_FLAVORS))
    return tmp_path


@pytest.mark.parametrize("linter_key", ["JAVASCRIPT_PRETTIER", "TYPESCRIPT_PRETTIER"])
def test_prettier_resolves_via_extends(descriptors_dir: Path, linter_key: str) -> None:
    """Linters whose install block lives in a shared file still resolve."""
    linters = extract_linter_info(descriptors_dir)

    assert linter_key in linters
    assert linters[linter_key]["type"] == "npm"
    assert linters[linter_key]["package"] == "prettier"
    assert linters[linter_key]["version"] == "3.9.6"


def test_own_keys_win_over_shared(descriptors_dir: Path) -> None:
    """A linter's own install block takes precedence over the shared one."""
    linters = extract_linter_info(descriptors_dir)

    assert linters["JAVASCRIPT_ES"]["type"] == "npm"
    assert linters["JAVASCRIPT_ES"]["package"] == "eslint"
    assert linters["JAVASCRIPT_ES"]["version"] == "9.40.0"
    assert "@microsoft/eslint-formatter-sarif" in linters["JAVASCRIPT_ES"]["npm_packages"]


def test_version_command_uses_cli_executable(descriptors_dir: Path) -> None:
    """A linter whose binary differs from its name is versioned via that binary."""
    linters = extract_linter_info(descriptors_dir)

    assert linters["PYTHON_RUFF_FORMAT"]["version_command"] == "ruff --version"
    assert linters["PYTHON_RUFF"]["version_command"] == "ruff --version"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("RUN wget -q https://example.com/install.sh | sh", True),
        ("RUN curl -sfL https://example.com/install.sh | sh -s -- -b /usr/bin", True),
        # A bare `| sh` pipe has no 'install' or '.sh' marker and does not match
        ("RUN curl -sfL https://example.com/get | sh", False),
        ("RUN WGET_OPTS=x wget https://example.com/x.SH", True),
        ("RUN apk add --no-cache curl", False),
        ("RUN npm install -g markdownlint-cli", False),
        # The download must follow RUN on the same line, not precede it
        ("# curl install\nRUN echo hi", False),
        ("COPY --from=x /usr/bin/wget /usr/bin/install.sh", False),
    ],
)
def test_has_download_install_run(text: str, expected: bool) -> None:
    """Install-script detection matches a RUN that downloads then installs."""
    assert has_download_install_run(text) is expected


def test_flavor_linters_come_from_the_manifest(descriptors_dir: Path) -> None:
    """Flavor membership is read from upstream's generated all_flavors.json."""
    flavors = extract_base_flavor_linters(descriptors_dir)

    assert "JAVASCRIPT_BIOME" in flavors["javascript"]
    assert "JAVASCRIPT_BIOME" not in flavors["ci_light"]
    assert "JAVASCRIPT_PRETTIER" in flavors["ci_light"]


def test_all_flavors_linters_land_in_every_flavor(descriptors_dir: Path) -> None:
    """A linter declaring `all_flavors` is in every flavor, not one named that."""
    flavors = extract_base_flavor_linters(descriptors_dir)

    assert "REPOSITORY_BETTERLEAKS" in flavors["go"]
    assert "REPOSITORY_BETTERLEAKS" in flavors["ci_light"]


def test_unknown_flavor_is_absent(descriptors_dir: Path) -> None:
    """A flavor the manifest does not list resolves to no linters."""
    flavors = extract_base_flavor_linters(descriptors_dir)

    assert flavors.get("rust", []) == []


def test_dockerfile_stage_gives_image_version_and_binary() -> None:
    """A FROM stage named after the linter supplies the image, and COPY supplies the paths."""
    lines = [
        "ARG ACTION_ACTIONLINT_VERSION=1.7.10",
        "FROM rhysd/actionlint:${ACTION_ACTIONLINT_VERSION} AS actionlint",
        "COPY --link --from=actionlint /usr/local/bin/actionlint /usr/bin/actionlint",
    ]

    assert parse_dockerfile_instructions(lines, "ACTION_ACTIONLINT") == {
        "version": "1.7.10",
        "image": "rhysd/actionlint",
        "binary_path": "/usr/local/bin/actionlint",
        "target_path": "/usr/bin/actionlint",
        "stage_name": "actionlint",
    }


def test_dockerfile_version_keeps_the_prefix_around_the_variable() -> None:
    """A tag such as v${VAR} resolves to v<value>, not <value>."""
    lines = ["ARG X_TOOL_VERSION=2.0.1\nFROM org/tool:v${X_TOOL_VERSION} as tool-build"]

    result = parse_dockerfile_instructions(lines, "X_TOOL")

    assert result["version"] == "v2.0.1"
    assert result["stage_name"] == "tool-build"


def test_dockerfile_literal_tag_is_the_version() -> None:
    """A stage tag with no variable is used as is."""
    result = parse_dockerfile_instructions(["from org/tool:3.4 AS tool"], "X_TOOL")

    assert result["version"] == "3.4"
    assert result["image"] == "org/tool"


def test_dockerfile_unknown_variable_falls_back_to_the_linter_arg() -> None:
    """An undefined tag variable leaves the stage version unresolved, so the linter ARG is used."""
    lines = [
        "ARG X_TOOL_VERSION=9.9",
        "FROM org/tool:${UNDEFINED} AS tool",
    ]

    assert parse_dockerfile_instructions(lines, "X_TOOL")["version"] == "9.9"


def test_dockerfile_without_a_stage_takes_the_linter_version_arg() -> None:
    """With no matching stage, the version comes from an ARG named after the linter key."""
    lines = [
        "ARG OTHER_LINT_VERSION=1.0",
        "ARG BASH_SHELL-CHECK_THING=x",
        "ARG BASH_SHELL_CHECK_VERSION=0.10.0",
    ]

    result = parse_dockerfile_instructions(lines, "BASH_SHELL-CHECK")

    assert result["version"] == "0.10.0"
    assert result["image"] is None
    assert result["stage_name"] is None


def test_dockerfile_skips_comments_blanks_and_other_stages() -> None:
    """Comments, empty entries and COPYs from unrelated stages are ignored; the first match wins."""
    lines = [
        "",
        "# COPY --from=tool /commented /out",
        "COPY --from=builder /usr/bin/other /usr/bin/other",
        "COPY --link --from=tool /first /usr/bin/first\n\nCOPY --from=tool /second /usr/bin/second",
    ]

    result = parse_dockerfile_instructions(lines, "X_TOOL")

    assert result["binary_path"] == "/first"
    assert result["target_path"] == "/usr/bin/first"
    assert result["stage_name"] == "tool"
    assert result["image"] is None
    assert result["version"] is None


def test_dockerfile_copy_parse_is_linear_on_long_lines() -> None:
    """A long COPY line that never completes a --from= must not backtrack quadratically."""
    line = "COPY" + " " * 40000 + "x"

    started = time.perf_counter()
    result = parse_dockerfile_instructions([line], "X_TOOL")

    assert result["binary_path"] is None
    assert time.perf_counter() - started < 0.5


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("prettier@${NPM_PRETTIER_VERSION}", "prettier"),
        ("@scope/pkg@${NPM_PKG_VERSION}", "@scope/pkg"),
        ("@scope/pkg@1.2.3", "@scope/pkg"),
        ("@scope/pkg", "@scope/pkg"),
        ("pkg@1.2.3", "pkg"),
        ("pkg", "pkg"),
    ],
)
def test_strip_npm_version_keeps_the_scope(raw: str, expected: str) -> None:
    """The version goes, but a scoped package keeps its leading @."""
    assert strip_npm_version(raw) == expected
