"""Tests for megalinter_extractor descriptor parsing."""

import json
from pathlib import Path

import pytest

from megalinter_extractor import (
    extract_base_flavor_linters,
    extract_linter_info,
    has_download_install_run,
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
