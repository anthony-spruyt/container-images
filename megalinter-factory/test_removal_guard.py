"""Tests for the guard that keeps a linter removal from shipping as a patch."""

import io
import json
from pathlib import Path

import pytest
import yaml

from removal_guard import check, main, removed_linters, squash_is_breaking

LYCHEE = ["SPELL_LYCHEE"]
LANGUAGES = {"go": ["GO_GOLANGCI_LINT"], "python": ["PYTHON_RUFF", "PYTHON_RUFF_FORMAT"]}
NO_FORMAT = {**LANGUAGES, "python": ["PYTHON_RUFF"]}
FLAVORS = {"go": ["go"], "python": ["python"], "go-python": ["go", "python"]}
REMOVED = {
    "megalinter-go-python": ["PYTHON_RUFF_FORMAT"],
    "megalinter-python": ["PYTHON_RUFF_FORMAT"],
}
STAMPS = ["megalinter-go-python/.rebuild-stamp", "megalinter-python/.rebuild-stamp"]
PYTHON_YAML = "megalinter-factory/languages/python.yaml"
PYTHON = "megalinter-python"
BREAKING = "feat!: drop ruff format"
TWO_COMMITS = ["x", "y"]


def dump(path: Path, data: dict) -> None:
    """Write data to path as YAML."""
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


def write_repo(root: Path, base: list[str], languages: dict, flavors: dict) -> Path:
    """Lay out a repo root with a factory and megalinter-<name>/flavor.yaml per flavor."""
    factory = root / "megalinter-factory"
    (factory / "languages").mkdir(parents=True)
    dump(factory / "base.yaml", {"linters": base})
    for name, linters in languages.items():
        dump(factory / "languages" / f"{name}.yaml", {"linters": linters})
    for name, flavor_languages in flavors.items():
        flavor_dir = root / f"megalinter-{name}"
        flavor_dir.mkdir()
        dump(flavor_dir / "flavor.yaml", {"name": name, "languages": flavor_languages})
    return root


@pytest.fixture(name="base")
def fixture_base(tmp_path: Path) -> Path:
    """The repo as it is on main."""
    return write_repo(tmp_path / "base", LYCHEE, LANGUAGES, FLAVORS)


def test_unchanged_repo_removes_nothing(base: Path, tmp_path: Path) -> None:
    """Identical compositions on both sides report no removal."""
    head = write_repo(tmp_path / "head", LYCHEE, LANGUAGES, FLAVORS)

    assert not removed_linters(base, head)


def test_language_losing_a_linter_reports_its_flavors(base: Path, tmp_path: Path) -> None:
    """Dropping ruff format from python affects python and go-python, not go."""
    head = write_repo(tmp_path / "head", LYCHEE, NO_FORMAT, FLAVORS)

    assert removed_linters(base, head) == REMOVED


def test_base_losing_a_linter_reports_every_flavor(base: Path, tmp_path: Path) -> None:
    """Every flavor carries the base set."""
    head = write_repo(tmp_path / "head", [], LANGUAGES, FLAVORS)

    assert set(removed_linters(base, head)) == {f"megalinter-{name}" for name in FLAVORS}


def test_flavor_dropping_a_language_reports_it(base: Path, tmp_path: Path) -> None:
    """A flavor.yaml edit can remove linters too."""
    head = write_repo(tmp_path / "head", LYCHEE, LANGUAGES, {**FLAVORS, "go-python": ["go"]})

    assert removed_linters(base, head) == {"megalinter-go-python": LANGUAGES["python"]}


def test_additions_and_new_or_deleted_flavors_pass(base: Path, tmp_path: Path) -> None:
    """Only a flavor present on both sides can lose a linter."""
    flavors = {"go": ["go"], "python": ["python"], "base": []}
    head = write_repo(tmp_path / "head", [*LYCHEE, "ACTION_ACTIONLINT"], LANGUAGES, flavors)

    assert not removed_linters(base, head)


@pytest.mark.parametrize(
    ("title", "messages", "expected"),
    [
        ("feat(megalinter)!: drop pylint", TWO_COMMITS, True),
        ("feat!: drop pylint", TWO_COMMITS, True),
        ("feat(megalinter): drop pylint", TWO_COMMITS, False),
        ("feat: drop pylint", ["a", "b\n\nBREAKING CHANGE: enable ruff instead"], True),
        ("feat: drop pylint", ["a", "b\n\nBREAKING-CHANGE: enable ruff instead"], True),
        ("feat(megalinter)!: drop pylint", ["fix(megalinter): drop pylint"], False),
        ("feat(megalinter): drop pylint", ["fix(megalinter)!: drop pylint\n\nbody"], True),
        ("chore: refresh", ["a", "mentions BREAKING CHANGE: mid-line"], False),
    ],
)
def test_breaking_reads_the_squash_subject(title: str, messages: list[str], expected: bool) -> None:
    """One commit squashes to its own subject; more squash to the PR title."""
    assert squash_is_breaking(title, messages) is expected


def test_no_removal_passes_whatever_the_title(base: Path) -> None:
    """The guard only gates removals."""
    assert not check({}, "chore: x", ["chore: x"], ["megalinter-go/.rebuild-stamp"], base)


def test_breaking_removal_stamping_the_affected_flavors_passes(base: Path) -> None:
    """The documented way to ship a removal."""
    assert not check(REMOVED, BREAKING, TWO_COMMITS, [PYTHON_YAML, *STAMPS], base)


def test_removal_without_breaking_marker_fails(base: Path) -> None:
    """A removal must not release as a patch or minor."""
    errors = check(REMOVED, "feat(megalinter): drop ruff format", TWO_COMMITS, STAMPS, base)

    assert len(errors) == 1
    assert "PYTHON_RUFF_FORMAT" in errors[0]
    assert "!" in errors[0]


def test_removal_missing_an_affected_stamp_fails(base: Path) -> None:
    """An affected flavor left untouched would get the removal only as a later chore patch."""
    errors = check(REMOVED, BREAKING, TWO_COMMITS, STAMPS[:1], base)

    assert errors == [f"Touch every flavor that loses a linter, e.g. its .rebuild-stamp: {PYTHON}"]


def test_removal_touching_an_unaffected_flavor_fails(base: Path) -> None:
    """An unaffected flavor in a breaking PR would get a major release it doesn't need."""
    changed = [*STAMPS, "megalinter-go/.rebuild-stamp"]

    errors = check(REMOVED, BREAKING, TWO_COMMITS, changed, base)

    assert errors == ["Leave out flavors that lose no linter, or they go major too: megalinter-go"]


def test_factory_directory_is_not_a_flavor(base: Path) -> None:
    """megalinter-factory shares the prefix but has no flavor.yaml."""
    changed = [PYTHON_YAML, "megalinter-factory/compose.py", *STAMPS]

    assert not check(REMOVED, BREAKING, TWO_COMMITS, changed, base)


def run_main(base: Path, head: Path, title: str, commit: str, changed: list[str]) -> int:
    """Feed the CLI the JSON CI pipes in, raw git output included, and run it."""
    payload = {
        "title": title,
        "commits": f"{commit}\n\nbody\n\0",
        "changed": "".join(f"{path}\n" for path in changed),
    }
    stdin = io.StringIO(json.dumps(payload))
    return main(["--base", str(base), "--head", str(head)], stdin)


def test_main_fails_an_unmarked_removal(base: Path, tmp_path: Path, capsys) -> None:
    """The CLI exits non-zero and annotates the error."""
    head = write_repo(tmp_path / "head", LYCHEE, NO_FORMAT, FLAVORS)
    subject = "feat(megalinter): drop ruff format"

    assert run_main(base, head, subject, subject, [PYTHON_YAML, *STAMPS]) == 1
    assert "::error::" in capsys.readouterr().out


def test_main_passes_a_marked_removal(base: Path, tmp_path: Path) -> None:
    """A single commit carrying the ! is enough, whatever the PR title says."""
    head = write_repo(tmp_path / "head", LYCHEE, NO_FORMAT, FLAVORS)

    assert run_main(base, head, "whatever", BREAKING, STAMPS) == 0
