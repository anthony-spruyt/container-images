"""Print the staged changes as Git Data API tree entries, keeping modes and deletions."""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def git(repo: Path, *args: str) -> str:
    """Return the output of a git command run in repo."""
    result = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, encoding="utf-8")
    return result.stdout


def tree_entries(repo: Path) -> list[dict]:
    """Return one entry per staged path: its blob content, or sha null when deleted."""
    raw = git(repo, "diff", "--cached", "--raw", "-z", "--no-renames", "--no-abbrev")
    fields = raw.split("\0")[:-1]
    entries = []
    for meta, path in zip(fields[0::2], fields[1::2], strict=True):
        old_mode, new_mode, _, new_sha, status = meta.lstrip(":").split()
        if status == "D":
            entries.append({"path": path, "mode": old_mode, "type": "blob", "sha": None})
        else:
            content = git(repo, "cat-file", "blob", new_sha)
            entries.append({"path": path, "mode": new_mode, "type": "blob", "content": content})
    return entries


def main(argv: list[str] | None = None) -> int:
    """Print the entries for the repo as JSON."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path, nargs="?", default=Path.cwd())
    args = parser.parse_args(argv)
    print(json.dumps(tree_entries(args.repo)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
