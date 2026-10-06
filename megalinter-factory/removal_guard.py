"""Fail a PR that drops a linter from a flavor unless it releases that flavor as breaking."""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import TextIO

import yaml

from compose import compose_flavor

FACTORY = "megalinter-factory"
BREAKING_SUBJECT = re.compile(r"^[a-z]+(\([^)]*\))?!:")
BREAKING_FOOTER = re.compile(r"^BREAKING[ -]CHANGE:", re.MULTILINE)


def composed_linters(repo_root: Path) -> dict[str, set[str]]:
    """Map each flavor directory to the linters its composition installs."""
    linters = {}
    for flavor_yaml in sorted(repo_root.glob("megalinter-*/flavor.yaml")):
        flavor = yaml.safe_load(flavor_yaml.read_text(encoding="utf-8")) or {}
        composed = compose_flavor(flavor, repo_root / FACTORY)
        linters[flavor_yaml.parent.name] = set(composed["custom_linters"])
    return linters


def removed_linters(base_root: Path, head_root: Path) -> dict[str, list[str]]:
    """Return the linters each flavor present on both sides loses from base to head."""
    base = composed_linters(base_root)
    head = composed_linters(head_root)
    removed = {}
    for name in sorted(base.keys() & head.keys()):
        if lost := sorted(base[name] - head[name]):
            removed[name] = lost
    return removed


def squash_is_breaking(title: str, commit_messages: list[str]) -> bool:
    """Whether the squash subject has `!` or a commit carries a BREAKING CHANGE footer."""
    subject = commit_messages[0].splitlines()[0] if len(commit_messages) == 1 else title
    footer = any(BREAKING_FOOTER.search(message) for message in commit_messages)
    return footer or bool(BREAKING_SUBJECT.match(subject))


def touched_flavors(changed_files: list[str], head_root: Path) -> set[str]:
    """Return the flavor directories the change touches."""
    dirs = {path.split("/", 1)[0] for path in changed_files if "/" in path}
    flavors = {d for d in dirs if d.startswith("megalinter-")}
    return {d for d in flavors if (head_root / d / "flavor.yaml").is_file()}


def check(
    removed: dict[str, list[str]],
    title: str,
    commit_messages: list[str],
    changed_files: list[str],
    head_root: Path,
) -> list[str]:
    """Return what the PR must fix to release its removals as majors of exactly those flavors."""
    if not removed:
        return []
    errors = []
    if not squash_is_breaking(title, commit_messages):
        lost = "; ".join(f"{name} loses {', '.join(keys)}" for name, keys in removed.items())
        errors.append(
            f"{lost}. Removing a linter breaks repos that enable it: title the PR "
            "`<type>(<scope>)!: <what consumers must change>` (the commit subject for a "
            "one-commit PR), or add a BREAKING CHANGE: footer"
        )
    touched = touched_flavors(changed_files, head_root)
    # The refresh skips only flavors whose stamp the push changed
    stamped = {name for name in touched if f"{name}/.rebuild-stamp" in changed_files}
    if missing := ", ".join(sorted(set(removed) - stamped)):
        errors.append(f"Change the .rebuild-stamp of every flavor that loses a linter: {missing}")
    if extra := ", ".join(sorted(touched - set(removed))):
        errors.append(f"Leave out flavors that lose no linter, or they go major too: {extra}")
    return errors


def main(argv: list[str] | None = None, stdin: TextIO | None = None) -> int:
    """Compare the flavors on a base checkout with head and report unmarked removals.

    stdin carries JSON: the PR title, NUL-separated commit messages and changed files, one a line.
    """
    repo_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True, help="checkout of the target branch")
    parser.add_argument("--head", type=Path, default=repo_root, help="checkout of the PR")
    args = parser.parse_args(argv)

    pr = json.load(stdin or sys.stdin)
    messages = [message.strip() for message in pr["commits"].split("\0") if message.strip()]
    changed = [line for line in pr["changed"].splitlines() if line]
    removed = removed_linters(args.base, args.head)
    errors = check(removed, pr["title"], messages, changed, args.head)

    for error in errors:
        print(f"::error::{error}")
    if removed and not errors:
        for name, keys in removed.items():
            print(f"::notice::{name} drops {', '.join(keys)} as a breaking change")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
