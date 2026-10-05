"""Tests for generate.py helpers."""

from generate import unique_by_package


def test_unique_by_package_drops_linters_sharing_a_package() -> None:
    """Linters backed by one package, like ruff and ruff-format, install it once."""
    linters = [
        {"name": "ruff", "package": "ruff"},
        {"name": "pylint", "package": "pylint"},
        {"name": "ruff", "package": "ruff"},
    ]

    assert [l["package"] for l in unique_by_package(linters)] == ["ruff", "pylint"]
