"""Print the staged changes as Git Data API tree entries, keeping modes and deletions."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

GITLINK = "160000"


def git(repo: Path, *args: str) -> str:
    """Return the output of a git command run in repo, line endings untouched."""
    result = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    return result.stdout.decode("utf-8")


def tree_entries(repo: Path) -> list[dict]:
    """Return one entry per staged path: its blob content, or sha null when deleted."""
    raw = git(repo, "diff", "--cached", "--raw", "-z", "--no-renames", "--no-abbrev")
    fields = raw.split("\0")[:-1]
    entries = []
    for meta, path in zip(fields[0::2], fields[1::2], strict=True):
        old_mode, new_mode, _, new_sha, status = meta.lstrip(":").split()
        if status == "U":
            raise ValueError(f"{path}: unmerged")
        if GITLINK in (old_mode, new_mode):
            raise ValueError(f"{path}: submodules are not supported")
        if status == "D":
            entries.append({"path": path, "mode": old_mode, "type": "blob", "sha": None})
            continue
        try:
            content = git(repo, "cat-file", "blob", new_sha)
        except UnicodeDecodeError:
            raise ValueError(f"{path}: not UTF-8 text") from None
        entries.append({"path": path, "mode": new_mode, "type": "blob", "content": content})
    return entries


def main(argv: list[str] | None = None) -> int:
    """Print the entries for the repo as JSON."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path, nargs="?", default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        entries = tree_entries(args.repo)
    except ValueError as error:
        # stderr: the workflow captures stdout into a variable, hiding the annotation
        print(f"::error::{error}", file=sys.stderr)
        return 1
    print(json.dumps(entries))
    return 0


if __name__ == "__main__":
    sys.exit(main())
