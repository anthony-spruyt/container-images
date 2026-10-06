"""Tests for composing a flavor from language definitions."""

from pathlib import Path

import pytest
import yaml

from compose import compose_flavor, flavors_affected

FACTORY_DIR = Path(__file__).parent


def write_factory(tmp_path: Path, base: dict, languages: dict[str, dict]) -> Path:
    """Lay out a factory directory with a base definition and language files."""
    (tmp_path / "base.yaml").write_text(yaml.safe_dump(base), encoding="utf-8")
    (tmp_path / "languages").mkdir()
    for name, definition in languages.items():
        (tmp_path / "languages" / f"{name}.yaml").write_text(
            yaml.safe_dump(definition), encoding="utf-8"
        )
    return tmp_path


@pytest.fixture(name="factory")
def fixture_factory(tmp_path: Path) -> Path:
    """A factory with a base set and three languages, one including another."""
    return write_factory(
        tmp_path,
        base={"linters": ["SPELL_LYCHEE", "ACTION_ACTIONLINT"]},
        languages={
            "go": {
                "linters": ["GO_GOLANGCI_LINT"],
                "go_image": "golang:1",
                "extra_dockerfile": "COPY --from={{ language.go_image }} /go /go\n",
                "extra_test_linters": [{"name": "go", "version_command": "go version"}],
                "extra_test_env_vars": [{"name": "GOTOOLCHAIN", "contains": "local"}],
            },
            "python": {
                "linters": ["PYTHON_RUFF_FORMAT", "PYTHON_RUFF"],
                "extra_dockerfile": "ENV PYTHON_DEFAULT_STYLE=ruff\n",
                "extra_test_env_vars": [{"name": "PYTHON_DEFAULT_STYLE", "contains": "ruff"}],
            },
            "javascript": {
                "linters": ["JAVASCRIPT_ES"],
                "extra_dockerfile": "RUN npm install -g globals\n",
            },
            "typescript": {
                "languages": ["javascript"],
                "linters": ["TYPESCRIPT_ES"],
            },
        },
    )


def test_merges_base_and_language_linters_sorted(factory: Path) -> None:
    """A flavor gets the base linters plus its languages', in one sorted list."""
    flavor = compose_flavor({"name": "go", "languages": ["go"]}, factory)

    assert flavor["custom_linters"] == [
        "ACTION_ACTIONLINT",
        "GO_GOLANGCI_LINT",
        "SPELL_LYCHEE",
    ]


def test_compound_flavor_does_not_depend_on_language_order(factory: Path) -> None:
    """go-python and python-go compose the same linters."""
    go_python = compose_flavor({"name": "go-python", "languages": ["go", "python"]}, factory)
    python_go = compose_flavor({"name": "python-go", "languages": ["python", "go"]}, factory)

    assert go_python["custom_linters"] == python_go["custom_linters"]
    assert "GO_GOLANGCI_LINT" in go_python["custom_linters"]
    assert "PYTHON_RUFF" in go_python["custom_linters"]


def test_flavor_specific_linters_are_kept_and_deduplicated(factory: Path) -> None:
    """custom_linters in flavor.yaml add to the languages and never duplicate one."""
    flavor = compose_flavor(
        {"name": "x", "languages": ["go"], "custom_linters": ["TERRAFORM_TFLINT", "SPELL_LYCHEE"]},
        factory,
    )

    assert flavor["custom_linters"] == [
        "ACTION_ACTIONLINT",
        "GO_GOLANGCI_LINT",
        "SPELL_LYCHEE",
        "TERRAFORM_TFLINT",
    ]


def test_language_can_include_another_language_once(factory: Path) -> None:
    """typescript pulls in javascript; listing both still installs javascript once."""
    flavor = compose_flavor(
        {"name": "ts", "languages": ["typescript", "javascript"]}, factory
    )

    assert flavor["custom_linters"] == [
        "ACTION_ACTIONLINT",
        "JAVASCRIPT_ES",
        "SPELL_LYCHEE",
        "TYPESCRIPT_ES",
    ]
    assert flavor["extra_dockerfile"] == "RUN npm install -g globals"


def test_unknown_language_is_an_error(factory: Path) -> None:
    """A typo in languages must fail the build, not ship a flavor without the linters."""
    with pytest.raises(ValueError, match="rust"):
        compose_flavor({"name": "rust", "languages": ["rust"]}, factory)


def test_dockerfile_fragments_render_with_their_own_fields_in_order(factory: Path) -> None:
    """Language fragments see their file as `language`, the flavor's see `flavor`; flavor last."""
    flavor = compose_flavor(
        {
            "name": "go-python",
            "languages": ["go", "python"],
            "tool_version": "1.2.3",
            "extra_dockerfile": "ARG TOOL_VERSION={{ flavor.tool_version }}\n",
        },
        factory,
    )

    assert flavor["extra_dockerfile"] == (
        "COPY --from=golang:1 /go /go\n"
        "ENV PYTHON_DEFAULT_STYLE=ruff\n"
        "ARG TOOL_VERSION=1.2.3"
    )


def test_undefined_template_field_is_an_error(factory: Path) -> None:
    """A fragment referencing a missing field fails instead of rendering an empty value."""
    with pytest.raises(Exception, match="missing"):
        compose_flavor(
            {"name": "go", "languages": ["go"], "extra_dockerfile": "ARG X={{ flavor.missing }}\n"},
            factory,
        )


def test_test_checks_concatenate_languages_then_flavor(factory: Path) -> None:
    """Version and env checks from every language reach test.sh, flavor extras last."""
    flavor = compose_flavor(
        {
            "name": "go-python",
            "languages": ["go", "python"],
            "extra_test_linters": [{"name": "biome", "version_command": "biome --version"}],
        },
        factory,
    )

    assert [l["name"] for l in flavor["extra_test_linters"]] == ["go", "biome"]
    assert [e["name"] for e in flavor["extra_test_env_vars"]] == [
        "GOTOOLCHAIN",
        "PYTHON_DEFAULT_STYLE",
    ]


def test_flavor_without_languages_gets_only_base(factory: Path) -> None:
    """No languages means just the base set, and no extras."""
    flavor = compose_flavor({"name": "plain"}, factory)

    assert flavor["custom_linters"] == ["ACTION_ACTIONLINT", "SPELL_LYCHEE"]
    assert not flavor.get("extra_dockerfile")
    assert not flavor.get("extra_test_linters")
    assert not flavor.get("extra_test_env_vars")


@pytest.mark.parametrize(
    "flavor_yaml",
    sorted(FACTORY_DIR.parent.glob("megalinter-*/flavor.yaml")),
    ids=lambda p: p.parent.name,
)
def test_every_repository_flavor_composes(flavor_yaml: Path) -> None:
    """Every flavor in the repo names only languages that exist."""
    flavor = yaml.safe_load(flavor_yaml.read_text(encoding="utf-8"))

    assert compose_flavor(flavor, FACTORY_DIR)["custom_linters"]


def write_flavor(root: Path, name: str, languages: list[str]) -> None:
    """Create megalinter-<name>/flavor.yaml listing the given languages."""
    (root / f"megalinter-{name}").mkdir()
    (root / f"megalinter-{name}" / "flavor.yaml").write_text(
        yaml.safe_dump({"name": name, "languages": languages}), encoding="utf-8"
    )


@pytest.fixture(name="repo")
def fixture_repo(factory: Path) -> Path:
    """A repo root holding the factory and flavors with different language mixes."""
    root = factory / "repo"
    root.mkdir()
    (root / "megalinter-factory").mkdir()
    for part in ("base.yaml", "languages"):
        (factory / part).rename(root / "megalinter-factory" / part)
    write_flavor(root, "go", ["go"])
    write_flavor(root, "xfg", ["typescript"])
    write_flavor(root, "go-python", ["go", "python"])
    write_flavor(root, "plain", [])
    return root


def test_language_change_affects_only_flavors_using_it(repo: Path) -> None:
    """Changing go.yaml rebuilds the flavors that list go, and nothing else."""
    assert flavors_affected(["megalinter-factory/languages/go.yaml"], repo) == [
        "megalinter-go",
        "megalinter-go-python",
    ]


def test_included_language_change_reaches_including_flavors(repo: Path) -> None:
    """typescript includes javascript, so a javascript change rebuilds xfg."""
    assert flavors_affected(["megalinter-factory/languages/javascript.yaml"], repo) == [
        "megalinter-xfg"
    ]


def test_base_change_affects_every_flavor(repo: Path) -> None:
    """Every flavor carries the base linters."""
    assert flavors_affected(["megalinter-factory/base.yaml"], repo) == [
        "megalinter-go",
        "megalinter-go-python",
        "megalinter-plain",
        "megalinter-xfg",
    ]


def test_unrelated_change_affects_no_flavor(repo: Path) -> None:
    """Factory code and docs are not language definitions."""
    assert not flavors_affected(["megalinter-factory/generate.py", "README.md"], repo)
