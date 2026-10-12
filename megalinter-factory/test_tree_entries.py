"""Tests for the tree entries the refresh commits through the Git Data API."""

import json
import subprocess
from pathlib import Path

import pytest

from tree_entries import main, tree_entries

STAMP = "megalinter-go/.rebuild-stamp"
SCRIPT = "megalinter-go/build.sh"


def git(repo: Path, *args: str, check: bool = True) -> None:
    """Run git in repo with a throwaway identity."""
    identity = ["-c", "user.name=test", "-c", "user.email=test@example.com"]
    subprocess.run(["git", *identity, *args], cwd=repo, check=check, capture_output=True)


def write(repo: Path, path: str, content: str, mode: int = 0o644) -> None:
    """Write a file under repo with the given permissions."""
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    target.chmod(mode)


@pytest.fixture(name="repo")
def fixture_repo(tmp_path: Path) -> Path:
    """A repo with one commit holding a stamp and an executable script."""
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "core.fileMode", "true")
    write(tmp_path, STAMP, "2026-01-01\n")
    write(tmp_path, SCRIPT, "#!/bin/sh\n", 0o755)
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_nothing_staged_gives_no_entries(repo: Path) -> None:
    """A clean index changes nothing."""
    assert not tree_entries(repo)


def test_modified_file_keeps_regular_mode(repo: Path) -> None:
    """A stamp carries its new content as a regular file."""
    write(repo, STAMP, "2026-10-12\n")
    git(repo, "add", "-A")

    assert tree_entries(repo) == [{"path": STAMP, "mode": "100644", "type": "blob", "content": "2026-10-12\n"}]


def test_new_file_is_included(repo: Path) -> None:
    """A flavor's first stamp is an added file."""
    write(repo, "megalinter-python/.rebuild-stamp", "2026-10-12\n")
    git(repo, "add", "-A")

    assert [entry["path"] for entry in tree_entries(repo)] == ["megalinter-python/.rebuild-stamp"]


def test_executable_keeps_its_mode(repo: Path) -> None:
    """An executable must not lose its bit in the commit."""
    write(repo, SCRIPT, "#!/bin/sh\necho hi\n", 0o755)
    write(repo, "megalinter-go/new.sh", "#!/bin/sh\n", 0o755)
    git(repo, "add", "-A")

    assert {entry["path"]: entry["mode"] for entry in tree_entries(repo)} == {
        SCRIPT: "100755",
        "megalinter-go/new.sh": "100755",
    }


def test_deleted_file_becomes_a_null_sha(repo: Path) -> None:
    """The API removes a path only when its entry has sha null."""
    (repo / SCRIPT).unlink()
    git(repo, "add", "-A")

    assert tree_entries(repo) == [{"path": SCRIPT, "mode": "100755", "type": "blob", "sha": None}]


def test_main_prints_the_entries_as_json(repo: Path, capsys) -> None:
    """The workflow reads the entries from stdout."""
    write(repo, STAMP, "2026-10-12\n")
    git(repo, "add", "-A")

    assert main([str(repo)]) == 0
    assert json.loads(capsys.readouterr().out) == tree_entries(repo)


def test_content_keeps_its_line_endings(repo: Path) -> None:
    """CRLF and a lone CR reach the commit unchanged."""
    (repo / STAMP).write_bytes(b"a\r\nb\rc\n")
    git(repo, "add", "-A")

    assert tree_entries(repo)[0]["content"] == "a\r\nb\rc\n"


def test_non_utf8_content_is_rejected(repo: Path) -> None:
    """The API's content field only carries UTF-8 text."""
    (repo / STAMP).write_bytes(b"\xff\xfe")
    git(repo, "add", "-A")

    with pytest.raises(ValueError, match=f"{STAMP}: not UTF-8 text"):
        tree_entries(repo)


def test_submodule_is_rejected(repo: Path) -> None:
    """A gitlink would need a commit entry, not a blob."""
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    git(repo, "update-index", "--add", "--cacheinfo", f"160000,{head},sub")

    with pytest.raises(ValueError, match="sub: submodules are not supported"):
        tree_entries(repo)


def test_unmerged_path_is_rejected(repo: Path) -> None:
    """A conflicted path has no single blob to commit."""
    git(repo, "checkout", "-q", "-b", "other")
    write(repo, STAMP, "other\n")
    git(repo, "commit", "-q", "-am", "other")
    git(repo, "checkout", "-q", "-")
    write(repo, STAMP, "mine\n")
    git(repo, "commit", "-q", "-am", "mine")
    git(repo, "merge", "-q", "other", check=False)

    with pytest.raises(ValueError, match=f"{STAMP}: unmerged"):
        tree_entries(repo)


def test_main_reports_a_rejected_path(repo: Path, capsys) -> None:
    """The workflow step fails with an annotation, and stdout stays empty."""
    (repo / STAMP).write_bytes(b"\xff\xfe")
    git(repo, "add", "-A")

    assert main([str(repo)]) == 1
    out, err = capsys.readouterr()
    assert not out
    assert f"::error::{STAMP}: not UTF-8 text" in err
